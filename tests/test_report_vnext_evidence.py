from __future__ import annotations

import unittest

from src.rag_report.report_vnext.evidence import (
    SPECIAL_FACT_SPECS,
    _extract_fact_from_doc,
    _load_company_document,
    _normalize_for_match,
    build_intro_evidence_pack,
)


class TestReportVNextEvidence(unittest.TestCase):
    def test_normalize_for_match_folds_d_bar_to_d(self) -> None:
        folded = _normalize_for_match("Tiền và các khoản tương đương tiền")
        self.assertIn("tien va cac khoan tuong duong tien", folded)

    def test_ending_cash_is_rescued_from_retrieved_rows(self) -> None:
        expected_values = {
            2017: 145658316125.0,
            2020: 44359080786.0,
            2021: 97299243376.0,
        }
        spec = SPECIAL_FACT_SPECS["ending_cash"]

        for year, expected_value in expected_values.items():
            doc = _load_company_document("A32", year)
            fact = _extract_fact_from_doc(
                doc,
                "ending_cash",
                spec.patterns,
                spec.statement_or_note,
                absolute=spec.absolute,
            )
            self.assertIsNotNone(fact, f"ending_cash fact missing for {year}")
            self.assertAlmostEqual(fact.value or 0, expected_value)

        evidence_pack = build_intro_evidence_pack("A32")
        facts = {(fact.fiscal_year, fact.canonical_line_item): fact for fact in evidence_pack.facts}
        adjudications = {
            (item.fiscal_year, item.canonical_line_item): item for item in evidence_pack.gap_adjudications
        }

        for year, expected_value in expected_values.items():
            fact = facts[(year, "ending_cash")]
            self.assertAlmostEqual(fact.value or 0, expected_value)
            self.assertNotIn(f"ending_cash:{year}:not_renderable", evidence_pack.data_gaps)
            self.assertEqual(adjudications[(year, "ending_cash")].status, "rescued_false_gap")
            self.assertTrue(adjudications[(year, "ending_cash")].renderable)


if __name__ == "__main__":
    unittest.main()
