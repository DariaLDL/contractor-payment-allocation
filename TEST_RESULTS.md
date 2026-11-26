# Результаты проверки

## Проверка после исправления структуры репозитория — 26.11.2026

Среда: Linux, Python 3.12.14. Проверено относительно исходного коммита `8ea00c0`.

До исправления `python -m unittest -v` обнаружил все 31 тест, но завершился
с `FAILED (failures=1, errors=6)`: вместо входных CSV в `data/contracts.csv`
и `data/works.csv` лежали выходные отчёты, что приводило к `KeyError: 'contract_id'`.

Исправлена только раскладка файлов:

- Существующие отчёты перенесены из `data/` в `examples/2026-11-10/`.
- Оригинальные `contracts.csv` и `works.csv` из корня перенесены в `data/`.
- Удалены побайтовые дубликаты `payments.csv` и `FORMAT.md` из корня;
  сохранены их экземпляры в `data/`.
- Удалены ненужный `data/.gitkeep` и `candidate_b_clean.zip`.
- Из архива сохранён `.gitignore`, исключающий результаты запуска и служебные файлы Python.

Побайтовое сравнение с файлами исходного коммита подтвердило сохранность
всех входных CSV, `FORMAT.md` и обоих эталонных отчётов. Данные не создавались
и не редактировались; `report.py` и `test_report.py` не изменены.

После исправления:

```text
$ python -m unittest -v
Ran 31 tests in 0.196s

OK
```

Дополнительно CLI запущен на дату `2026-11-10` с выводом во временную папку:
оба полученных CSV побайтово совпали с `examples/2026-11-10/`.

---

Ниже сохранён отчёт о предыдущей проверке из исходного репозитория
(Linux, Python 3.12.3). Упоминания исходной загрузки и `contracts_1.csv`/`works_1.csv`
относятся к той проверке, а не к текущей структуре репозитория.

## 1. Исходное состояние (до изменений)

Исходная раскладка из загрузки (файлы в корне, папки `data/` нет): `python -m unittest -v` -> `Ran 4 tests ... FAILED (errors=3)`,
причина - `FileNotFoundError: .../data/contracts.csv`. `python report.py --date 2026-11-10` падает с той же ошибкой.

Находка по данным: в загрузке `contracts.csv` и `works.csv` - **не входные данные, а выходные отчёты** `report.py`
(заголовки `Дата;Договор;Подрядчик;...`, разделитель `;`). Настоящие входы - `contracts_1.csv` и `works_1.csv`.
Проверено: вывод исходного `report.py` на 2026-11-10 байт в байт совпал с загруженными `contracts.csv` и `works.csv`.

Если положить загруженные `contracts.csv`/`works.csv` в `data/` буквально, расчёт был бы невозможен. Поэтому:

| Было | Стало |
|---|---|
| `contracts_1.csv` | `data/contracts.csv` |
| `works_1.csv` | `data/works.csv` |
| `payments.csv`, `FORMAT.md` | `data/payments.csv`, `data/FORMAT.md` |
| `contracts.csv`, `works.csv` (отчёты) | `examples/2026-11-10/contracts.csv`, `works.csv` |
| исходный `README.md` (текст задания) | `TASK.md`; новый `README.md` написан заново |

Со входными данными в `data/` исходный (немодифицированный) код проходил 4/4 теста.

## 2. Что изменено в коде

Расчётная логика и формат вывода сохранены; на данных из `data/` вывод побайтово идентичен прежнему.

- `cents`: вместо `Decimal(value) * 100` - строгий разбор строкой `\d+(\.\d{1,2})?`. Проверено на старом коде: `cents('abc')` бросал `InvalidOperation` (не `ValueError`); сумма `99999999999999999999999999999.99` молча превращалась в `10000000000000000000000000000000` копеек (ограничение точности контекста Decimal в 28 знаков). На реальных суммах это не проявлялось.
- Даты разбираются в объекты `date` один раз (раньше сортировка приёмок шла по строкам `completed_at`; на ISO-датах результат тот же).
- Сортировка при равных датах - «натуральная» (`W-9` < `W-10`), раньше строковая (`W-10` < `W-9`).
- Проверено на старом коде: договор D-2 с пустым `signed_at` молча пропадал из отчёта (остался только D-1); платёж P-2 со статусом `refunded` без `refunded_at` считался выплаченным (выплачено по D-1 = 365 000 вместо 315 000). Теперь в обоих случаях ошибка с понятным текстом; проверяется согласованность статусов и дат работ и платежей.
- `assert` (отключается при `python -O`) заменён на явную проверку с `RuntimeError`.
- `main()` печатает «Ошибка данных: …» и выходит с кодом 1 вместо трассировки.
- Сообщения об ошибках теперь содержат идентификатор записи.

## 3. Итоговый прогон автотестов

Команда: `python -m unittest -v`

```
test_cancellation_and_completion_date_boundaries (test_report.Allocation.test_cancellation_and_completion_date_boundaries) ... ok
test_cancelled_work (test_report.Allocation.test_cancelled_work) ... ok
test_contract_amount_kept_as_is (test_report.Allocation.test_contract_amount_kept_as_is) ... ok
test_contract_without_works (test_report.Allocation.test_contract_without_works) ... ok
test_direct_overpay_stays_on_work (test_report.Allocation.test_direct_overpay_stays_on_work) ... ok
test_direct_payment_first_then_pool (test_report.Allocation.test_direct_payment_first_then_pool) ... ok
test_direct_payment_to_cancelled_is_overpay (test_report.Allocation.test_direct_payment_to_cancelled_is_overpay) ... ok
test_done_before_planned_then_by_completion_date (test_report.Allocation.test_done_before_planned_then_by_completion_date) ... ok
test_kopeks_no_float_drift (test_report.Allocation.test_kopeks_no_float_drift) ... ok
test_payment_date_boundaries (test_report.Allocation.test_payment_date_boundaries) ... ok
test_pool_excess_is_unallocated (test_report.Allocation.test_pool_excess_is_unallocated) ... ok
test_refunded_in_future_still_counts (test_report.Allocation.test_refunded_in_future_still_counts) ... ok
test_tie_by_natural_id (test_report.Allocation.test_tie_by_natural_id) ... ok
test_exact (test_report.Cents.test_exact) ... ok
test_money (test_report.Cents.test_money) ... ok
test_natural_key (test_report.Cents.test_natural_key) ... ok
test_rejects_bad (test_report.Cents.test_rejects_bad) ... ok
test_bad_data_gives_message_not_traceback (test_report.Cli.test_bad_data_gives_message_not_traceback) ... ok
test_bad_date_argument (test_report.Cli.test_bad_date_argument) ... ok
test_end_to_end_matches_reference (test_report.Cli.test_end_to_end_matches_reference) ... ok
test_before_refund (test_report.RealData.test_before_refund) ... ok
test_contract_not_yet_signed (test_report.RealData.test_contract_not_yet_signed) ... ok
test_invariant_all_dates (test_report.RealData.test_invariant_all_dates) ... ok
test_later_payment (test_report.RealData.test_later_payment) ... ok
test_refund_day_inclusive (test_report.RealData.test_refund_day_inclusive) ... ok
test_target_date_per_work (test_report.RealData.test_target_date_per_work) ... ok
test_bad_amounts_and_dates (test_report.Validation.test_bad_amounts_and_dates) ... ok
test_duplicate_ids (test_report.Validation.test_duplicate_ids) ... ok
test_status_date_mismatch (test_report.Validation.test_status_date_mismatch) ... ok
test_unknown_contract_or_foreign_work (test_report.Validation.test_unknown_contract_or_foreign_work) ... ok
test_work_bound_to_other_contract (test_report.Validation.test_work_bound_to_other_contract) ... ok

----------------------------------------------------------------------
Ran 31 tests in 0.145s

OK
```

Тесты: 4 исходных (адаптированы, добавлены проверки по каждой работе) + 27 новых = 31. Покрыто: цифры на 10.11.2026 по каждой работе, возврат (до/в день/после), договор до подписания, инвариант `выплачено = распределено + нераспределено` для каждой даты 20.08-31.12.2026, порядок распределения пула, прямой платёж + пул, переплаты, отменённые работы, границы дат, копейки без дрейфа `float`, невалидные данные, CLI.

**В процессе один тест упал** - из-за неверного ожидания в самом тесте (пул 100 ₽ целиком уходит на W-1 с более ранней приёмкой, а не делится). Код соответствовал `DECISIONS.md`; исправлен тест, а не код.

## 4. Регрессия вывода

```
python report.py --date 2026-11-10 --output /tmp/chk
cmp /tmp/chk/works.csv examples/2026-11-10/works.csv        # без различий
cmp /tmp/chk/contracts.csv examples/2026-11-10/contracts.csv # без различий
```

## 5. Итоги на 10.11.2026 (из `output/contracts.csv`)

| Договор | Выплачено | Осталось по работам | Переплата | Нераспределено |
|---|---:|---:|---:|---:|
| D-1 | 315 000,00 | 185 000,00 | 0,00 | 0,00 |
| D-2 | 75 000,00 | 15 000,00 | 0,00 | 0,00 |

Ручная проверка: D-1 = P-1 300 000 + P-3 15 000 (P-2 возвращён 10.09, P-4 в очереди); D-2 = 45 000 + 25 000 + 5 000 (P-8 от 12.11 ещё не было).

## 6. Чего не проверено

- Python 3.10 и 3.11 (только 3.12.3).
- Данные реального бухгалтера: допущения из `DECISIONS.md` (п. 4, 5, 6, 9) подтверждены не были.
- Транскрипт Claude Code (`/export`) не создан.
