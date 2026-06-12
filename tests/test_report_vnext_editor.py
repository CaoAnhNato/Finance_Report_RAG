from __future__ import annotations

import unittest
from src.rag_report.report_vnext.editor import IntroNarrativeEditor
from src.rag_report.report_vnext.audit import narrative_wording_hygiene
from src.rag_report.report_vnext.models import (
    IntroNarrative,
    IntroEvidencePack,
    IntroMetricPack,
    IntroChartPlan,
)


class TestReportVNextEditor(unittest.TestCase):
    def test_deterministic_normalization(self) -> None:
        editor = IntroNarrativeEditor(use_llm=False)
        narrative = IntroNarrative(
            company_id="A32",
            title="Đánh giá năng lực tài chính",
            markdown="""
## Bước 1: Nguồn số liệu
Kết luận nhanh cho người không chuyên: Số liệu này tốt.
Câu trả lời nhanh là không có vấn đề.
Điểm cần kiểm tra tiếp theo là tiền thật.
            """,
        )
        evidence = IntroEvidencePack(company_id="A32", years=[2025])
        metrics = IntroMetricPack(company_id="A32", records=[])
        chart_plan = IntroChartPlan(company_id="A32", items=[])

        edited = editor.edit(
            narrative,
            evidence_pack=evidence,
            metric_pack=metrics,
            chart_plan=chart_plan,
            style_notes=[],
        )

        # Confirm replacements
        self.assertNotIn("Bước 1", edited.markdown)
        self.assertNotIn("Kết luận nhanh cho người không chuyên", edited.markdown)
        self.assertNotIn("Câu trả lời nhanh", edited.markdown)
        self.assertNotIn("Điểm cần kiểm tra tiếp theo", edited.markdown)
        self.assertNotIn("tiền thật", edited.markdown)

        self.assertIn("Cơ sở số liệu", edited.markdown)
        self.assertIn("Kết luận chính", edited.markdown)
        self.assertIn("Tóm tắt kết luận chính", edited.markdown)
        self.assertIn("Mạch phân tích của báo cáo", edited.markdown)
        self.assertIn("dòng tiền thực tế", edited.markdown)

    def test_narrative_wording_hygiene_audit(self) -> None:
        # Violating narrative
        bad_narrative = IntroNarrative(
            company_id="A32",
            title="Bước 2: Phân tích chỉ tiêu",
            markdown="Đây là câu trả lời nhanh về tiền thật.",
        )
        violations = narrative_wording_hygiene(bad_narrative)
        self.assertGreater(len(violations), 0)

        # Non-violating narrative
        good_narrative = IntroNarrative(
            company_id="A32",
            title="Cơ sở số liệu và kiểm toán",
            markdown="Đây là đánh giá cốt lõi về tiền mặt và tương đương tiền.",
        )
        violations = narrative_wording_hygiene(good_narrative)
        self.assertEqual(len(violations), 0)


if __name__ == "__main__":
    unittest.main()
