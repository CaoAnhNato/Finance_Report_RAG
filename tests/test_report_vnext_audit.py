from __future__ import annotations

import unittest

from src.rag_report.report_vnext.audit import audit_report_html


class TestReportVNextAudit(unittest.TestCase):
    def test_audit_accepts_paged_layout_and_numbered_citations(self) -> None:
        html_text = """
        <html>
          <head>
            <style>@page { size: A4; margin: 12mm; }</style>
          </head>
          <body>
            <section class="report-page">
              <p>Doanh thu <sup class="cite-ref" data-cite-number="1">1<span class="cite-tooltip"><span class="cite-tooltip-title">Nguồn 1</span><span class="cite-tooltip-body">BCTC 2025, trang 9</span></span></sup></p>
              <figure class="report-figure" data-renderable="true">
                <div class="chart-mount"></div>
                <figcaption class="figure-caption">Insight</figcaption>
                <div class="figure-source">Nguồn: BCTC 2025, trang 9</div>
              </figure>
            </section>
          </body>
        </html>
        """

        result = audit_report_html(html_text, report_path="demo.html")
        self.assertTrue(result.overall_pass)
        checks = {finding.check: finding.passed for finding in result.findings}
        self.assertTrue(checks["paged_layout"])
        self.assertTrue(checks["citation_numbering"])
        self.assertTrue(checks["hover_source"])
        self.assertTrue(checks["chart_readability"])
        self.assertTrue(checks["path_hygiene"])

    def test_audit_rejects_path_leaks(self) -> None:
        html_text = """
        <html><body>
          <section class="report-page">
            <p>C:\\Users\\Admin\\secret.txt</p>
          </section>
        </body></html>
        """

        result = audit_report_html(html_text, report_path="demo.html")
        checks = {finding.check: finding.passed for finding in result.findings}
        self.assertFalse(checks["path_hygiene"])
        self.assertFalse(result.overall_pass)


if __name__ == "__main__":
    unittest.main()
