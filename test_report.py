import unittest
from pathlib import Path
from datetime import date
from report import calculate, cents

class ReportTests(unittest.TestCase):
    def report(self, day):
        return calculate(Path(__file__).parent/'data', date.fromisoformat(day))
    def test_target(self):
        a,b=self.report('2026-11-10')
        self.assertEqual(a['total'],31500000)
        self.assertEqual(b['total'],7500000)
        self.assertEqual(sum(r['remaining'] for r in a['rows']),18500000)
        self.assertEqual(sum(r['remaining'] for r in b['rows']),1500000)
        self.assertEqual(a['rows'][2]['due'],0)
        self.assertEqual(b['rows'][2]['status'],'planned')
    def test_before_refund(self):
        self.assertEqual(self.report('2026-09-05')[0]['total'],35000000)
    def test_later_payment(self):
        b=self.report('2026-11-12')[1]
        self.assertEqual(b['unallocated'],500000)
        self.assertEqual(b['rows'][2]['status'],'done')
    def test_exact(self):
        self.assertEqual(cents('0.29'),29)
        with self.assertRaises(ValueError): cents('0.001')

if __name__=='__main__': unittest.main()
