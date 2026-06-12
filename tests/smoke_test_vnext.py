from __future__ import annotations

import unittest
from pathlib import Path
from src.rag_report.report_vnext.pipeline import IntroReportVNextPipeline
from src.rag_report.report_vnext.exporter import VNextHTMLExporter

class SmokeTestVNext(unittest.TestCase):
    def test_vnext_pipeline_and_rendering(self) -> None:
        # Initialize pipeline without LLM dependencies
        pipeline = IntroReportVNextPipeline(
            use_llm_extraction=False,
            use_llm_chart_planning=False,
            use_llm_writer=False
        )
        
        # Build bundle
        bundle = pipeline.build_bundle(company_id="A32")
        
        # Verify bundle components
        self.assertIsNotNone(bundle.evidence_pack)
        self.assertIsNotNone(bundle.metric_pack)
        self.assertIsNotNone(bundle.chart_plan)
        self.assertIsNotNone(bundle.charts)
        self.assertIsNotNone(bundle.narrative)
        
        # Verify charts spec details (legend additions & no axis collision)
        earnings_cash_chart = next((c for c in bundle.charts if c.chart_id == "earnings_cash"), None)
        if earnings_cash_chart:
            spec = earnings_cash_chart.spec
            # Check for legend definition in earnings_cash
            self.assertIn("legend", str(spec))
            self.assertIn("Lợi nhuận sau thuế (LNST)", str(spec))

        receivables_revenue_chart = next((c for c in bundle.charts if c.chart_id == "receivables_revenue"), None)
        if receivables_revenue_chart:
            spec = receivables_revenue_chart.spec
            # Check for legend and independent scale
            self.assertIn("legend", str(spec))
            self.assertIn("independent", str(spec))

        # Generate HTML report
        exporter = VNextHTMLExporter()
        html_content = exporter.compile_report(bundle, output_filename="smoke_test_vnext_output.html")
        
        # Read content
        html_path = Path(html_content)
        self.assertTrue(html_path.exists())
        html_text = html_path.read_text(encoding="utf-8")
        
        # Check cover page title CSS max-width constraint removed or adjusted
        self.assertNotIn("max-width: 13ch", html_text)
        
        # Check that unaccented keys (like cfo, lnst, ending_cash) are replaced in table and source descriptions
        # Note: We escaped and lowercased them, but the display labels should show accented Vietnamese.
        self.assertIn("Dòng tiền từ HĐKD (CFO)", html_text)
        self.assertIn("Lợi nhuận sau thuế (LNST)", html_text)
        self.assertIn("Tiền cuối kỳ", html_text)
        self.assertIn("Doanh thu thuần", html_text)
        
        print("Smoke test passed successfully!")

if __name__ == "__main__":
    unittest.main()
