from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.rag_report.report_vnext.audit import audit_report_html
from src.rag_report.report_vnext.feedback_log import (
    FeedbackRule,
    load_feedback_rules,
    rules_to_style_notes,
    save_feedback_rules,
)


def _valid_report_html(body_text: str) -> str:
    return f"""
    <html>
      <head>
        <style>@page {{ size: A4; margin: 12mm; }}</style>
      </head>
      <body>
        <section class="report-page">
          <p>{body_text} <sup class="cite-ref" data-cite-number="1">1<span class="cite-tooltip"><span class="cite-tooltip-title">Source 1</span><span class="cite-tooltip-body">BCTC 2025, page 9</span></span></sup></p>
          <figure class="report-figure" data-renderable="true">
            <div class="chart-mount"></div>
            <figcaption class="figure-caption">Insight</figcaption>
            <div class="figure-source">Source: BCTC 2025, page 9</div>
          </figure>
        </section>
      </body>
    </html>
    """


class TestReportVNextFeedbackLog(unittest.TestCase):
    def test_feedback_log_round_trip_filters_manual_gap_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "vnext_feedback_log.jsonl"
            rules = [
                FeedbackRule(
                    rule_id="custom::phrase",
                    check="custom_check",
                    message="Keep the custom check note.",
                ),
                FeedbackRule(
                    rule_id="custom::screenshot",
                    message="Screenshot compare remains manual.",
                    manual_gap=True,
                    source="manual",
                ),
            ]
            save_feedback_rules(rules, path)

            loaded = load_feedback_rules(path)
            self.assertEqual([rule.rule_id for rule in loaded], ["custom::phrase", "custom::screenshot"])
            self.assertEqual(rules_to_style_notes(loaded), ["custom_check: Keep the custom check note."])

    def test_audit_enforces_persisted_html_rule_and_records_manual_gap(self) -> None:
        html_text = _valid_report_html("Revenue remains steady")
        rules = [
            FeedbackRule(
                rule_id="custom::phrase",
                html_contains="Keep this exact phrase",
                message="Keep this exact phrase in the report body.",
            ),
            FeedbackRule(
                rule_id="custom::screenshot",
                message="Screenshot compare is manual only.",
                manual_gap=True,
                source="manual",
            ),
        ]

        result = audit_report_html(html_text, report_path="demo.html", feedback_rules=rules)
        checks = {finding.check: finding for finding in result.findings}

        self.assertFalse(result.overall_pass)
        self.assertIn("feedback::custom::phrase", checks)
        self.assertFalse(checks["feedback::custom::phrase"].passed)
        self.assertTrue(any("Screenshot compare is manual only." in note for note in result.benchmark_gap_notes))


if __name__ == "__main__":
    unittest.main()
