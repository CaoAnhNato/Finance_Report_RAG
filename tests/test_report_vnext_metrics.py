from __future__ import annotations

import unittest

from src.rag_report.report_vnext.evidence import FORMULA_SOURCE_PATH
from src.rag_report.report_vnext.metrics import calculate_intro_metrics
from src.rag_report.report_vnext.models import FinancialFact, IntroEvidencePack


def _fact(year: int, item: str, value: float, source_file: str = "source.txt") -> FinancialFact:
    return FinancialFact(
        canonical_line_item=item,
        fiscal_year=year,
        value=value,
        unit="VND",
        source_file=source_file,
        page=5,
        statement_or_note="test",
        raw_value=str(int(value)),
        normalized_value=value,
    )


class TestReportVNextMetrics(unittest.TestCase):
    def test_metrics_include_provenance_and_red_flags(self) -> None:
        evidence_pack = IntroEvidencePack(
            company_id="A32",
            years=[2024, 2025],
            facts=[
                _fact(2024, "lnst", 39269119523.0),
                _fact(2024, "cfo", 63635197220.0),
                _fact(2024, "doanh_thu", 727056756533.0),
                _fact(2024, "tong_tai_san", 495920079070.0),
                _fact(2024, "phai_thu_ngan_han", 115182153535.0),
                _fact(2024, "no_ngan_han", 269971184316.0),
                _fact(2024, "ending_cash", 101880000000.0),
                _fact(2025, "lnst", 50872308164.0),
                _fact(2025, "cfo", -55721888430.0),
                _fact(2025, "doanh_thu", 777808047055.0),
                _fact(2025, "tong_tai_san", 491118229908.0),
                _fact(2025, "phai_thu_ngan_han", 185187887273.0),
                _fact(2025, "no_ngan_han", 255076704419.0),
                _fact(2025, "ending_cash", 29210000000.0),
                _fact(2025, "trade_receivables_gross", 185187887273.0),
                _fact(2025, "allowance_receivables", 1500000000.0),
                _fact(2025, "hang_ton_kho", 141255200129.0),
                _fact(2025, "inventory_provision", 2500000000.0),
                _fact(2025, "dividends_paid", 14170000000.0),
                _fact(2025, "capex", 2780587647.0),
            ],
        )

        metric_pack = calculate_intro_metrics(evidence_pack)
        records = {(record.metric_id, record.fiscal_year): record for record in metric_pack.records}

        qoe_2025 = records[("quality_of_earnings", 2025)]
        self.assertEqual(qoe_2025.flag, "red")
        self.assertEqual(qoe_2025.formula_source, FORMULA_SOURCE_PATH)
        self.assertIsNotNone(qoe_2025.formula_latex)
        self.assertGreaterEqual(len(qoe_2025.input_sources), 2)
        self.assertTrue(qoe_2025.takeaway)
        self.assertNotEqual(qoe_2025.takeaway, qoe_2025.explanation)

        cash_buffer_2025 = records[("cash_buffer_ratio", 2025)]
        self.assertAlmostEqual(cash_buffer_2025.computed_value or 0, 29210000000.0 / 255076704419.0, places=6)
        self.assertTrue(cash_buffer_2025.takeaway.endswith("cần thận trọng."))

        fcf_2025 = records[("fcf_after_dividends", 2025)]
        self.assertEqual(fcf_2025.flag, "red")
        self.assertEqual(fcf_2025.unit, "VND")
        self.assertIn("tỷ VND", fcf_2025.takeaway)


if __name__ == "__main__":
    unittest.main()
