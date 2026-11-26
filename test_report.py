import csv
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from report import calculate, cents, money, natural_key

ROOT = Path(__file__).parent
CONTRACT_H = ['contract_id', 'contractor', 'amount', 'signed_at']
WORK_H = ['work_id', 'contract_id', 'title', 'price', 'status', 'completed_at', 'cancelled_at']
PAY_H = ['payment_id', 'contract_id', 'work_id', 'purpose', 'amount', 'status', 'created_at', 'paid_at', 'refunded_at']


def synth(contracts, works, payments):
    """Временная папка data с заданными строками; возвращает Path."""
    tmp = tempfile.TemporaryDirectory()
    folder = Path(tmp.name)
    for name, header, rows in (('contracts', CONTRACT_H, contracts), ('works', WORK_H, works), ('payments', PAY_H, payments)):
        with (folder / f'{name}.csv').open('w', encoding='utf-8', newline='') as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
    synth.keep.append(tmp)
    return folder


synth.keep = []


def C(cid='D', amount='1000.00', signed='2026-01-01'):
    return [cid, 'X', amount, signed]


def W(wid, price='100.00', status='planned', done='', canc='', cid='D'):
    return [wid, cid, 't', price, status, done, canc]


def P(pid, amount, work='', status='paid', paid='2026-02-01', refunded='', cid='D'):
    return [pid, cid, work, '', amount, status, '2026-01-31', paid, refunded]


def by(rows):
    return {r['id']: r for r in rows}


class RealData(unittest.TestCase):
    def report(self, day):
        return calculate(ROOT / 'data', date.fromisoformat(day))

    def test_target_date_per_work(self):
        a, b = self.report('2026-11-10')
        wa, wb = by(a['rows']), by(b['rows'])
        # D-1: P-1 300000 без привязки, P-3 15000 к W-14; P-2 возвращён, P-4 в очереди
        self.assertEqual(a['total'], 31500000)
        self.assertEqual({k: (v['status'], v['paid'], v['remaining']) for k, v in wa.items()}, {
            'W-11': ('done', 10000000, 0), 'W-12': ('done', 10000000, 0),
            'W-13': ('cancelled', 0, 0), 'W-14': ('done', 10000000, 0),
            'W-15': ('planned', 1500000, 8500000), 'W-16': ('planned', 0, 10000000)})
        self.assertEqual(a['unallocated'], 0)
        self.assertEqual(sum(r['remaining'] for r in a['rows']), 18500000)
        # D-2: P-8 (12.11) ещё не случился, W-23 принята 11.11 -> на 10.11 плановая
        self.assertEqual(b['total'], 7500000)
        self.assertEqual({k: (v['status'], v['paid'], v['remaining']) for k, v in wb.items()}, {
            'W-21': ('done', 2000000, 0), 'W-22': ('done', 3000000, 0), 'W-23': ('planned', 2500000, 1500000)})

    def test_before_refund(self):
        self.assertEqual(self.report('2026-09-05')[0]['total'], 35000000)

    def test_refund_day_inclusive(self):
        self.assertEqual(self.report('2026-09-09')[0]['total'], 35000000)
        self.assertEqual(self.report('2026-09-10')[0]['total'], 30000000)

    def test_later_payment(self):
        b = self.report('2026-11-12')[1]
        self.assertEqual(b['unallocated'], 500000)
        self.assertEqual(b['rows'][2]['status'], 'done')

    def test_contract_not_yet_signed(self):
        self.assertEqual(self.report('2026-08-24'), [])
        self.assertEqual([c['id'] for c in self.report('2026-08-25')], ['D-1'])
        self.assertEqual([c['id'] for c in self.report('2026-09-20')], ['D-1', 'D-2'])

    def test_invariant_all_dates(self):
        d = date(2026, 8, 20)
        while d <= date(2026, 12, 31):
            for c in calculate(ROOT / 'data', d):
                s = lambda k: sum(r[k] for r in c['rows'])
                self.assertEqual(c['total'], s('paid') + c['unallocated'], f'{c["id"]} {d}')
                self.assertTrue(all(r['remaining'] >= 0 and r['overpaid'] >= 0 for r in c['rows']))
            d = date.fromordinal(d.toordinal() + 1)


class Cents(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(cents('0.29'), 29)
        self.assertEqual(cents('19.99'), 1999)
        self.assertEqual(cents('100'), 10000)
        self.assertEqual(cents('0.1'), 10)
        self.assertEqual(cents(' 5.50 '), 550)
        self.assertEqual(cents('99999999999999999999.99'), 9999999999999999999999)

    def test_rejects_bad(self):
        for bad in ('0.001', '', '-1.00', '1e2', 'NaN', 'Infinity', '1,5', '1_000', 'abc', '1.', '.5', None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                cents(bad)

    def test_money(self):
        self.assertEqual(money(0), '0.00')
        self.assertEqual(money(5), '0.05')
        self.assertEqual(money(123456789), '1234567.89')

    def test_natural_key(self):
        self.assertEqual(sorted(['W-10', 'W-9', 'W-2'], key=natural_key), ['W-2', 'W-9', 'W-10'])


class Allocation(unittest.TestCase):
    def run_calc(self, works, payments, day='2026-06-01', contract=None):
        return calculate(synth([contract or C()], works, payments), date.fromisoformat(day))[0]

    def test_done_before_planned_then_by_completion_date(self):
        c = self.run_calc(
            [W('W-1'), W('W-2', status='done', done='2026-03-02'), W('W-3', status='done', done='2026-03-01')],
            [P('P-1', '150.00')])
        r = by(c['rows'])
        self.assertEqual((r['W-3']['paid'], r['W-2']['paid'], r['W-1']['paid']), (10000, 5000, 0))

    def test_tie_by_natural_id(self):
        c = self.run_calc([W('W-10', status='done', done='2026-03-01'), W('W-9', status='done', done='2026-03-01')],
                          [P('P-1', '100.00')])
        r = by(c['rows'])
        self.assertEqual((r['W-9']['paid'], r['W-10']['paid']), (10000, 0))

    def test_direct_payment_first_then_pool(self):
        works = [W('W-1', status='done', done='2026-03-01'), W('W-2', status='done', done='2026-03-02')]
        # пул 100: целиком уходит на более раннюю W-1, у W-2 остаётся только прямой платёж 60
        c = self.run_calc(works, [P('P-1', '60.00', work='W-2'), P('P-2', '100.00')])
        r = by(c['rows'])
        self.assertEqual((r['W-1']['paid'], r['W-2']['paid'], r['W-2']['remaining']), (10000, 6000, 4000))
        self.assertEqual(c['unallocated'], 0)
        # пул 140: W-1 закрыта на 100, оставшиеся 40 доплачивают W-2 до 100
        c = self.run_calc(works, [P('P-1', '60.00', work='W-2'), P('P-2', '140.00')])
        r = by(c['rows'])
        self.assertEqual((r['W-1']['paid'], r['W-2']['paid'], r['W-2']['remaining']), (10000, 10000, 0))
        self.assertEqual((c['unallocated'], c['total']), (0, 20000))

    def test_direct_overpay_stays_on_work(self):
        c = self.run_calc([W('W-1'), W('W-2')], [P('P-1', '130.00', work='W-1'), P('P-2', '50.00')])
        r = by(c['rows'])
        self.assertEqual((r['W-1']['paid'], r['W-1']['overpaid'], r['W-1']['remaining']), (13000, 3000, 0))
        self.assertEqual((r['W-2']['paid'], r['W-2']['remaining']), (5000, 5000))

    def test_pool_excess_is_unallocated(self):
        c = self.run_calc([W('W-1', price='100.00')], [P('P-1', '250.50')])
        self.assertEqual((c['rows'][0]['paid'], c['unallocated'], c['total']), (10000, 15050, 25050))

    def test_cancelled_work(self):
        c = self.run_calc([W('W-1', status='cancelled', canc='2026-03-01'), W('W-2')], [P('P-1', '100.00')])
        r = by(c['rows'])
        self.assertEqual((r['W-1']['status'], r['W-1']['due'], r['W-1']['paid'], r['W-1']['remaining']), ('cancelled', 0, 0, 0))
        self.assertEqual(r['W-2']['paid'], 10000)

    def test_direct_payment_to_cancelled_is_overpay(self):
        c = self.run_calc([W('W-1', status='cancelled', canc='2026-03-01')], [P('P-1', '40.00', work='W-1')])
        self.assertEqual((c['rows'][0]['paid'], c['rows'][0]['overpaid']), (4000, 4000))

    def test_cancellation_and_completion_date_boundaries(self):
        works = [W('W-1', status='cancelled', canc='2026-03-01'), W('W-2', status='done', done='2026-03-01')]
        before = by(self.run_calc(works, [], day='2026-02-28')['rows'])
        on = by(self.run_calc(works, [], day='2026-03-01')['rows'])
        self.assertEqual((before['W-1']['status'], before['W-2']['status']), ('planned', 'planned'))
        self.assertEqual((on['W-1']['status'], on['W-2']['status']), ('cancelled', 'done'))

    def test_payment_date_boundaries(self):
        pays = [P('P-1', '10.00', paid='2026-03-01'), P('P-2', '20.00', paid='2026-03-02'),
                P('P-3', '30.00', status='queued', paid='')]
        self.assertEqual(self.run_calc([W('W-1')], pays, day='2026-02-28')['total'], 0)
        self.assertEqual(self.run_calc([W('W-1')], pays, day='2026-03-01')['total'], 1000)
        self.assertEqual(self.run_calc([W('W-1')], pays, day='2026-03-02')['total'], 3000)

    def test_refunded_in_future_still_counts(self):
        p = [P('P-1', '10.00', status='refunded', paid='2026-03-01', refunded='2026-04-01')]
        self.assertEqual(self.run_calc([W('W-1')], p, day='2026-03-31')['total'], 1000)
        self.assertEqual(self.run_calc([W('W-1')], p, day='2026-04-01')['total'], 0)

    def test_kopeks_no_float_drift(self):
        c = self.run_calc([W('W-1', price='0.30'), W('W-2', price='0.30')], [P('P-1', '0.10'), P('P-2', '0.20'), P('P-3', '0.10')])
        self.assertEqual((c['total'], sum(r['paid'] for r in c['rows'])), (40, 40))
        self.assertEqual((by(c['rows'])['W-1']['remaining'], by(c['rows'])['W-2']['remaining']), (0, 20))

    def test_contract_without_works(self):
        c = self.run_calc([], [P('P-1', '10.00')])
        self.assertEqual((c['rows'], c['unallocated'], c['total']), ([], 1000, 1000))

    def test_contract_amount_kept_as_is(self):
        c = self.run_calc([W('W-1', status='cancelled', canc='2026-03-01'), W('W-2')], [], contract=C(amount='200.00'))
        self.assertEqual(c['amount'], 20000)


class Validation(unittest.TestCase):
    def fail(self, contracts=None, works=None, payments=None, day='2026-06-01'):
        folder = synth(contracts if contracts is not None else [C()], works if works is not None else [W('W-1')],
                       payments if payments is not None else [])
        with self.assertRaises(ValueError):
            calculate(folder, date.fromisoformat(day))

    def test_duplicate_ids(self):
        self.fail(works=[W('W-1'), W('W-1')])
        self.fail(payments=[P('P-1', '1.00'), P('P-1', '2.00')])
        self.fail(contracts=[C(), C()])

    def test_unknown_contract_or_foreign_work(self):
        self.fail(works=[W('W-1', cid='Z')])
        self.fail(payments=[P('P-1', '1.00', cid='Z')])
        self.fail(works=[W('W-1')], payments=[P('P-1', '1.00', work='W-404')])

    def test_work_bound_to_other_contract(self):
        folder = synth([C('D'), C('E')], [W('W-1', cid='E')], [P('P-1', '1.00', work='W-1', cid='D')])
        with self.assertRaises(ValueError):
            calculate(folder, date(2026, 6, 1))

    def test_bad_amounts_and_dates(self):
        self.fail(works=[W('W-1', price='1.234')])
        self.fail(payments=[P('P-1', '-5.00')])
        self.fail(contracts=[C(signed='')])
        self.fail(contracts=[C(signed='01.01.2026')])
        self.fail(payments=[P('P-1', '1.00', paid='2026-13-01')])

    def test_status_date_mismatch(self):
        self.fail(works=[W('W-1', status='done')])
        self.fail(works=[W('W-1', status='cancelled')])
        self.fail(works=[W('W-1', status='planned', done='2026-03-01')])
        self.fail(works=[W('W-1', status='weird')])
        self.fail(payments=[P('P-1', '1.00', status='paid', paid='')])
        self.fail(payments=[P('P-1', '1.00', status='queued', paid='2026-03-01')])
        self.fail(payments=[P('P-1', '1.00', status='refunded')])
        self.fail(payments=[P('P-1', '1.00', status='paid', refunded='2026-03-01')])
        self.fail(payments=[P('P-1', '1.00', status='refunded', paid='2026-03-05', refunded='2026-03-01')])


class Cli(unittest.TestCase):
    def test_end_to_end_matches_reference(self):
        with tempfile.TemporaryDirectory() as out:
            r = subprocess.run([sys.executable, str(ROOT / 'report.py'), '--date', '2026-11-10', '--output', out],
                               capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(r.returncode, 0, r.stderr)
            for name in ('works.csv', 'contracts.csv'):
                self.assertEqual((Path(out) / name).read_bytes(), (ROOT / 'examples' / '2026-11-10' / name).read_bytes())

    def test_bad_data_gives_message_not_traceback(self):
        folder = synth([C()], [W('W-1', price='1.234')], [])
        with tempfile.TemporaryDirectory() as out:
            r = subprocess.run([sys.executable, str(ROOT / 'report.py'), '--date', '2026-06-01', '--data', str(folder), '--output', out],
                               capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 1)
        self.assertIn('Ошибка данных', r.stderr)
        self.assertNotIn('Traceback', r.stderr)

    def test_bad_date_argument(self):
        r = subprocess.run([sys.executable, str(ROOT / 'report.py'), '--date', '10.11.2026'], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == '__main__':
    unittest.main()
