"""Tests tín hiệu quality — không cần DuckDB/OCR thật."""

from __future__ import annotations

import os
import unittest

from quality_signals import _v_invoice_line_totals, aggregate_quality_signals, run_structural_validators


class TestInvoiceTotals(unittest.TestCase):
    def test_matching_invoice_scores_one(self):
        with open(os.path.join("samples", "invoice_01.txt"), encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(_v_invoice_line_totals(text, {}), 1.0)

    def test_mismatched_total_is_penalized(self):
        text = (
            "STT\tTen\tSL\tGia\tThanh tien\n"
            "1\tA\t1\t100\t100\n"
            "2\tB\t1\t100\t100\n"
            "Tong cong: 999999 VND\n"
        )
        self.assertLess(_v_invoice_line_totals(text, {}), 0.2)

    def test_non_invoice_not_penalized(self):
        self.assertEqual(_v_invoice_line_totals("bao cao khong co tong", {}), 1.0)

    def test_registered(self):
        scores = run_structural_validators(
            "1\ta\t1\t1\t10\nTong cong: 10\n", {"table_likelihood": 0.0}
        )
        self.assertIn("invoice_line_totals", scores)
        self.assertEqual(scores["invoice_line_totals"], 1.0)


class TestAggregate(unittest.TestCase):
    def test_two_candidates_produce_relative_quality(self):
        outputs = {"a": "hello world", "b": "hello#####"}
        report = aggregate_quality_signals(
            outputs,
            {"a": {}, "b": {}},
            {"a": 0.9, "b": 0.2},
        )
        self.assertAlmostEqual(sum(report.quality_estimate.values()), 1.0, places=6)
        self.assertGreater(report.quality_estimate["a"], report.quality_estimate["b"])


if __name__ == "__main__":
    unittest.main()
