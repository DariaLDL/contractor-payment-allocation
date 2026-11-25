import argparse
import csv
from datetime import date
from decimal import Decimal
from pathlib import Path


def cents(value):
    n = Decimal(value) * 100
    if not n.is_finite() or n != n.to_integral_value() or n < 0:
        raise ValueError(f'Некорректная сумма: {value}')
    return int(n)


def money(n):
    return f'{Decimal(n)/100:.2f}'


def load(folder, name):
    with (folder / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def occurred(value, cutoff):
    return bool(value) and date.fromisoformat(value) <= cutoff


def calculate(folder, cutoff):
    contracts, works, payments = [load(folder, n + '.csv') for n in ('contracts', 'works', 'payments')]
    for rows, key in [(contracts,'contract_id'), (works,'work_id'), (payments,'payment_id')]:
        if len({r[key] for r in rows}) != len(rows):
            raise ValueError(f'Повтор идентификатора {key}')
    ids = {c['contract_id'] for c in contracts}
    work_ids = {w['work_id']: w['contract_id'] for w in works}
    for r in works + payments:
        if r['contract_id'] not in ids:
            raise ValueError('Неизвестный договор')
    for p in payments:
        if p['work_id'] and work_ids.get(p['work_id']) != p['contract_id']:
            raise ValueError('Некорректная привязка платежа')
    result = []
    for c in contracts:
        cid = c['contract_id']
        if not occurred(c['signed_at'], cutoff):
            continue
        rows = []
        for w in works:
            if w['contract_id'] != cid:
                continue
            status = 'cancelled' if occurred(w['cancelled_at'], cutoff) else 'done' if occurred(w['completed_at'], cutoff) else 'planned'
            price = cents(w['price'])
            rows.append(dict(id=w['work_id'], title=w['title'], status=status, price=price, due=0 if status=='cancelled' else price, paid=0, completed=w['completed_at']))
        by_id = {r['id']:r for r in rows}
        pool = total = 0
        for p in payments:
            if p['contract_id'] != cid or not occurred(p['paid_at'], cutoff) or occurred(p['refunded_at'], cutoff):
                continue
            amount = cents(p['amount'])
            total += amount
            if p['work_id']:
                by_id[p['work_id']]['paid'] += amount
            else:
                pool += amount
        for r in sorted(rows, key=lambda r:(r['status']!='done', r['completed'] if r['status']=='done' else '', r['id'])):
            allocation = min(pool, max(0,r['due']-r['paid']))
            r['paid'] += allocation
            pool -= allocation
            r['remaining'] = max(0,r['due']-r['paid'])
            r['overpaid'] = max(0,r['paid']-r['due'])
        assert total == sum(r['paid'] for r in rows)+pool
        result.append(dict(id=cid, contractor=c['contractor'], amount=cents(c['amount']), rows=rows, total=total, unallocated=pool))
    return result


def main():
    parser = argparse.ArgumentParser(description='Отчёт по оплате работ на дату')
    parser.add_argument('--date', required=True, type=date.fromisoformat)
    parser.add_argument('--data', type=Path, default=Path(__file__).parent/'data')
    parser.add_argument('--output', type=Path, default=Path('output'))
    args = parser.parse_args()
    result = calculate(args.data, args.date)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output/'works.csv').open('w', encoding='utf-8-sig', newline='') as wf, (args.output/'contracts.csv').open('w', encoding='utf-8-sig', newline='') as cf:
        w,c = csv.writer(wf,delimiter=';'),csv.writer(cf,delimiter=';')
        w.writerow(['Дата','Договор','Работа','Название','Статус','Цена','К оплате с учетом отмен','Выплачено','Осталось','Переплата'])
        c.writerow(['Дата','Договор','Подрядчик','Сумма договора','Цена всех работ','К оплате с учетом отмен','Фактически выплачено','Распределено','Осталось по работам','Переплата по работам','Нераспределено','Разница договора и действующих работ'])
        for d in result:
            rows=d['rows']; s=lambda k:sum(r[k] for r in rows)
            for r in rows:
                w.writerow([args.date,d['id'],r['id'],r['title'],r['status'],*[money(r[k]) for k in ('price','due','paid','remaining','overpaid')]])
            c.writerow([args.date,d['id'],d['contractor'],*[money(n) for n in (d['amount'],s('price'),s('due'),d['total'],s('paid'),s('remaining'),s('overpaid'),d['unallocated'],d['amount']-s('due'))]])
    print(f'Отчёт на {args.date}: {args.output.resolve()}')

if __name__ == '__main__':
    main()
