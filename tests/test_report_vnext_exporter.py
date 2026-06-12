from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.rag_report.report_vnext.exporter import VNextHTMLExporter
from src.rag_report.report_vnext.models import (
    ChartPlanItem,
    IntroChartPlan,
    IntroEvidencePack,
    IntroMetricPack,
    IntroNarrative,
    IntroRenderBundle,
    MetricInputSource,
    MetricRecord,
    RenderedChart,
)


class TestReportVNextExporter(unittest.TestCase):
    def test_exporter_renders_a4_pages_and_numbered_citations(self) -> None:
        bundle = IntroRenderBundle(
            evidence_pack=IntroEvidencePack(company_id="A32", years=[2025]),
            metric_pack=IntroMetricPack(
                company_id="A32",
                records=[
                    MetricRecord(
                        metric_id="quality_of_earnings",
                        metric_name="Quality of Earnings / Cash Conversion",
                        fiscal_year=2025,
                        formula_display="CFO / LNST",
                        formula_source="Khung tinh toan noi bo A32",
                        formula_code_version="v1",
                        explanation="Do muc do loi nhuan chuyen hoa thanh tien.",
                        takeaway="CFO am nhung LNST duong.",
                        input_values={"cfo": -1.0, "lnst": 2.0},
                        input_sources=[
                            MetricInputSource(
                                variable_name="cfo",
                                fiscal_year=2025,
                                canonical_line_item="cfo",
                                source_file=r"C:\Users\Admin\HUIT - Hoc Tap\Nam 3\Semester_2\Class\RAG_Report\data\A32\2025\A32_Baocaotaichinh_2025_Kiemtoan\A32_Baocaotaichinh_2025_Kiemtoan_extracted.txt",
                                page=9,
                                statement_or_note="cash_flow",
                                normalized_value=-1.0,
                            )
                        ],
                        computed_value=-0.5,
                        unit="ratio",
                        flag="red",
                        notes=["Ghi chu kiem thu"],
                    )
                ],
            ),
            chart_plan=IntroChartPlan(
                company_id="A32",
                items=[
                    ChartPlanItem(
                        chart_id="red_flag_heatmap",
                        title="Heatmap",
                        subtitle="Sub",
                        insight_line="Insight",
                        enabled=True,
                        priority=10,
                    )
                ],
            ),
            charts=[RenderedChart(chart_id="red_flag_heatmap", spec={"mark": "rect", "data": {"values": [{"year": 2025, "flag": "red", "source_summary": "BCTC 2025, trang 9"}]}})],
            narrative=IntroNarrative(
                company_id="A32",
                title="Danh gia do tin cay so lieu va chat luong loi nhuan",
                markdown="## Tom tat\n\nDoan van [BCTC 2025, trang 9].",
            ),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("src.rag_report.report_vnext.exporter.settings.REPORT_OUTPUT_DIR_ABS", tmp_dir):
                output_path = VNextHTMLExporter().compile_report(bundle, output_filename="demo.html")
                html_text = Path(output_path).read_text(encoding="utf-8")

        self.assertIn("@page", html_text)
        self.assertIn("size: A4", html_text)
        self.assertIn("report-page", html_text)
        self.assertIn("report-figure", html_text)
        self.assertIn("Noto Serif", html_text)
        self.assertIn("cite-ref", html_text)
        self.assertIn("data-cite-number='1'", html_text)
        self.assertIn("Nguồn công thức", html_text)
        self.assertIn("BCTC 2025, trang 9", html_text)
        self.assertIn("CFO / LNST", html_text)
        self.assertIn("Bảng chỉ tiêu trọng yếu", html_text)
        self.assertIn("Nhận định nhanh", html_text)
        self.assertIn("CFO am nhung LNST duong.", html_text)
        self.assertIn("Danh gia do tin cay so lieu va chat luong loi nhuan", html_text)
        self.assertEqual(html_text.count("chỉ tiêu trọng yếu"), 1)
        self.assertNotIn("C:\\Users\\Admin", html_text)
        self.assertNotIn("source_file", html_text)
        self.assertNotIn("Company:", html_text)
        self.assertNotIn("Scope:", html_text)
        self.assertNotIn("View:", html_text)
        self.assertNotIn("figure-panel", html_text)
        
        # Glossary rendering checks
        self.assertIn("Thuật ngữ sử dụng trong phần tín hiệu", html_text)
        self.assertIn("Bảng thuật ngữ tài chính sử dụng trong báo cáo", html_text)
        self.assertIn("CFO", html_text)
        self.assertIn("LNST", html_text)
        self.assertIn("Chất lượng lợi nhuận", html_text)


if __name__ == "__main__":
    unittest.main()
