from __future__ import annotations

import unittest

from src.rag_report.report_vnext.evidence import _chunk_items, _parse_backfill_json


class TestReportVNextBackfill(unittest.TestCase):
    def test_parse_backfill_json_strips_code_fence(self) -> None:
        payload = _parse_backfill_json("```json\n{\n  \"ending_cash\": {\"normalized_value\": 1}\n}\n```")
        self.assertIsInstance(payload, dict)
        self.assertIn("ending_cash", payload)

    def test_parse_backfill_json_accepts_plain_json(self) -> None:
        payload = _parse_backfill_json("{\"dividends_paid\": {\"normalized_value\": 1}}")
        self.assertIsInstance(payload, dict)
        self.assertIn("dividends_paid", payload)

    def test_chunk_items_groups_small_batches(self) -> None:
        self.assertEqual(_chunk_items(["a", "b", "c"], 2), [["a", "b"], ["c"]])


if __name__ == "__main__":
    unittest.main()
