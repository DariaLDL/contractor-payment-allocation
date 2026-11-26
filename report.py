"""Отчёт по оплате работ подрядчиков на заданную дату.

Все суммы считаются в целых копейках (int); float нигде не используется.
"""
import argparse
import csv
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

AMOUNT_RE = re.compile(r'\d+(\.\d{1,2})?')


def cents(value, where=''):
    """Строка вида '1234.50' -> 123450 копеек. Строго: без float, экспонент, минусов, >2 знаков."""
    text = (value or '').strip()
    if not AMOUNT_RE.fullmatch(text):
        raise ValueError(f'Некорректная сумма{where}: {value!r}')
    whole, _, frac = text.partition('.')
    return int(whole) * 100 + int(frac.ljust(2, '0') or 0)


def money(n):
    return f'{Decimal(n) / 100:.2f}'


def load(folder, name):
    with (folder / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def parse_date(value, where=''):
    """Пустая строка -> None; иначе ISO-дата или ValueError с указанием места."""
    text = (value or '').strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(f'Некорректная дата{where}: {value!r}') from None


def occurred(day, cutoff):
    return day is not None and day <= cutoff


def natural_key(text):
    """'W-9' < 'W-10': числа в идентификаторах сравниваются как числа."""
    return [int(p) if p.isdigit() else p for p in re.split(r'(\d+)', text)]


def validate_work(w):
    wid = w['work_id']
    status = w['status']
    completed = parse_date(w['completed_at'], f' (работа {wid}, completed_at)')
    cancelled = parse_date(w['cancelled_at'], f' (работа {wid}, cancelled_at)')
    if status not in ('planned', 'done', 'cancelled'):
        raise ValueError(f'Неизвестный статус работы {wid}: {status!r}')
    if (status == 'done') != (completed is not None) or (status == 'cancelled') != (cancelled is not None):
        raise ValueError(f'Статус работы {wid} не согласован с датами completed_at/cancelled_at')
    if completed and cancelled:
        raise ValueError(f'У работы {wid} одновременно заданы completed_at и cancelled_at')
    return completed, cancelled


def validate_payment(p):
    pid = p['payment_id']
    status = p['status']
    paid = parse_date(p['paid_at'], f' (платёж {pid}, paid_at)')
    refunded = parse_date(p['refunded_at'], f' (платёж {pid}, refunded_at)')
    if status not in ('paid', 'queued', 'refunded'):
        raise ValueError(f'Неизвестный статус платежа {pid}: {status!r}')
    if (status == 'queued') != (paid is None):
        raise ValueError(f'Статус платежа {pid} не согласован с paid_at')
    if (status == 'refunded') != (refunded is not None):
        raise ValueError(f'Статус платежа {pid} не согласован с refunded_at')
    if refunded and paid and refunded < paid:
        raise ValueError(f'Платёж {pid}: возврат раньше оплаты')
    return paid, refunded


def calculate(folder, cutoff):
    contracts, works, payments = [load(folder, n + '.csv') for n in ('contracts', 'works', 'payments')]
    for rows, key in [(contracts, 'contract_id'), (works, 'work_id'), (payments, 'payment_id')]:
        if len({r[key] for r in rows}) != len(rows):
            raise ValueError(f'Повтор идентификатора {key}')
    ids = {c['contract_id'] for c in contracts}
    work_ids = {w['work_id']: w['contract_id'] for w in works}
    for r in works + payments:
        if r['contract_id'] not in ids:
            raise ValueError(f'Неизвестный договор {r["contract_id"]!r} в записи {r.get("work_id") or r.get("payment_id")}')
    for p in payments:
        if p['work_id'] and work_ids.get(p['work_id']) != p['contract_id']:
            raise ValueError(f'Платёж {p["payment_id"]}: работа {p["work_id"]!r} не относится к договору {p["contract_id"]}')

    work_dates = {w['work_id']: validate_work(w) for w in works}
    pay_dates = {p['payment_id']: validate_payment(p) for p in payments}

    result = []
    for c in contracts:
        cid = c['contract_id']
        signed = parse_date(c['signed_at'], f' (договор {cid}, signed_at)')
        if signed is None:
            raise ValueError(f'У договора {cid} не указана дата подписания')
        contract_amount = cents(c['amount'], f' (договор {cid})')
        if not occurred(signed, cutoff):
            continue
        rows = []
        for w in works:
            if w['contract_id'] != cid:
                continue
            completed, cancelled = work_dates[w['work_id']]
            status = 'cancelled' if occurred(cancelled, cutoff) else 'done' if occurred(completed, cutoff) else 'planned'
            price = cents(w['price'], f' (работа {w["work_id"]})')
            rows.append(dict(id=w['work_id'], title=w['title'], status=status, price=price,
                             due=0 if status == 'cancelled' else price, paid=0,
                             completed=completed if status == 'done' else None))
        by_id = {r['id']: r for r in rows}
        pool = total = 0
        for p in payments:
            if p['contract_id'] != cid:
                continue
            paid_at, refunded_at = pay_dates[p['payment_id']]
            if not occurred(paid_at, cutoff) or occurred(refunded_at, cutoff):
                continue
            amount = cents(p['amount'], f' (платёж {p["payment_id"]})')
            total += amount
            if p['work_id']:
                by_id[p['work_id']]['paid'] += amount
            else:
                pool += amount
        # Общие платежи: сначала принятые работы по дате приёмки, затем остальные; ничья - по номеру.
        for r in sorted(rows, key=lambda r: (r['status'] != 'done', r['completed'] or date.min, natural_key(r['id']))):
            allocation = min(pool, max(0, r['due'] - r['paid']))
            r['paid'] += allocation
            pool -= allocation
            r['remaining'] = max(0, r['due'] - r['paid'])
            r['overpaid'] = max(0, r['paid'] - r['due'])
        if total != sum(r['paid'] for r in rows) + pool:
            raise RuntimeError(f'Договор {cid}: распределение не сходится с суммой платежей')
        result.append(dict(id=cid, contractor=c['contractor'], amount=contract_amount, rows=rows,
                           total=total, unallocated=pool))
    return result


def main():
    parser = argparse.ArgumentParser(description='Отчёт по оплате работ на дату')
    parser.add_argument('--date', required=True, type=date.fromisoformat)
    parser.add_argument('--data', type=Path, default=Path(__file__).parent / 'data')
    parser.add_argument('--output', type=Path, default=Path('output'))
    args = parser.parse_args()
    try:
        result = calculate(args.data, args.date)
    except (ValueError, KeyError, FileNotFoundError) as e:
        sys.exit(f'Ошибка данных: {e}')
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / 'works.csv').open('w', encoding='utf-8-sig', newline='') as wf, \
            (args.output / 'contracts.csv').open('w', encoding='utf-8-sig', newline='') as cf:
        w, c = csv.writer(wf, delimiter=';'), csv.writer(cf, delimiter=';')
        w.writerow(['Дата', 'Договор', 'Работа', 'Название', 'Статус', 'Цена', 'К оплате с учетом отмен', 'Выплачено', 'Осталось', 'Переплата'])
        c.writerow(['Дата', 'Договор', 'Подрядчик', 'Сумма договора', 'Цена всех работ', 'К оплате с учетом отмен', 'Фактически выплачено', 'Распределено', 'Осталось по работам', 'Переплата по работам', 'Нераспределено', 'Разница договора и действующих работ'])
        for d in result:
            rows = d['rows']
            s = lambda k: sum(r[k] for r in rows)
            for r in rows:
                w.writerow([args.date, d['id'], r['id'], r['title'], r['status'], *[money(r[k]) for k in ('price', 'due', 'paid', 'remaining', 'overpaid')]])
            c.writerow([args.date, d['id'], d['contractor'], *[money(n) for n in (d['amount'], s('price'), s('due'), d['total'], s('paid'), s('remaining'), s('overpaid'), d['unallocated'], d['amount'] - s('due'))]])
    print(f'Отчёт на {args.date}: {args.output.resolve()}')


if __name__ == '__main__':
    main()
