from __future__ import annotations

import importlib
import sys
import types
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.rag_report.report_vnext.feedback_log import FeedbackRule


def _report_html(*, include_path_leak: bool) -> str:
    path_text = r"C:\Users\Admin\secret.txt" if include_path_leak else "clean report text"
    return f"""
    <html>
      <head>
        <style>@page {{ size: A4; margin: 12mm; }}</style>
      </head>
      <body>
        <section class="report-page">
          <p>{path_text} <sup class="cite-ref" data-cite-number="1">1<span class="cite-tooltip"><span class="cite-tooltip-title">Source 1</span><span class="cite-tooltip-body">BCTC 2025, page 9</span></span></sup></p>
          <figure class="report-figure" data-renderable="true">
            <div class="chart-mount"></div>
            <figcaption class="figure-caption">Insight</figcaption>
            <div class="figure-source">Source: BCTC 2025, page 9</div>
          </figure>
        </section>
      </body>
    </html>
    """


class TestReportVNextFlowValidation(unittest.TestCase):
    def test_flow_retries_with_persisted_feedback_and_appends_failed_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sys.modules.setdefault("duckdb", types.ModuleType("duckdb"))
            flow_module = importlib.import_module("flows.generate_report_vnext_flow")
            run_report_vnext_flow = flow_module.run_report_vnext_flow

            tmp_path = Path(tmp_dir)
            bad_html_path = tmp_path / "bad.html"
            good_html_path = tmp_path / "good.html"
            reference_path = tmp_path / "reference.html"
            reference_path.write_text(_report_html(include_path_leak=False), encoding="utf-8")

            generate_calls: list[dict[str, object]] = []
            appended_rules: list[FeedbackRule] = []
            persisted_rules = [
                FeedbackRule(
                    rule_id="seed::screenshot_compare_manual",
                    message="Screenshot compare is manual only.",
                    manual_gap=True,
                    source="manual",
                )
            ]

            def fake_seed_feedback_log():
                return list(persisted_rules)

            def fake_append_feedback_rules(new_rules, path=None):
                del path
                for rule in new_rules:
                    appended_rules.append(rule)
                    persisted_rules.append(rule)
                return list(persisted_rules)

            def fake_generate_vnext_intro_html(*, style_notes=None, feedback_rules=None, **_kwargs):
                generate_calls.append(
                    {
                        "style_notes": list(style_notes or []),
                        "feedback_rules": list(feedback_rules or []),
                    }
                )
                current_path = bad_html_path if len(generate_calls) == 1 else good_html_path
                current_path.write_text(
                    _report_html(include_path_leak=len(generate_calls) == 1),
                    encoding="utf-8",
                )
                return str(current_path)

            with patch("flows.generate_report_vnext_flow.settings.REPORT_OUTPUT_DIR_ABS", str(tmp_path)), patch(
                "flows.generate_report_vnext_flow.settings.REPORT_BENCHMARK_REFERENCE_HTML",
                str(reference_path),
            ), patch("flows.generate_report_vnext_flow.settings.VNEXT_MAX_ATTEMPTS", 2), patch(
                "flows.generate_report_vnext_flow.seed_feedback_log",
                side_effect=fake_seed_feedback_log,
            ), patch(
                "flows.generate_report_vnext_flow.append_feedback_rules",
                side_effect=fake_append_feedback_rules,
            ), patch(
                "flows.generate_report_vnext_flow.generate_vnext_intro_html",
                side_effect=fake_generate_vnext_intro_html,
            ):
                result = run_report_vnext_flow(
                    use_llm_extraction=False,
                    use_llm_chart_planning=False,
                    use_llm_writer=False,
                )

            self.assertEqual(result, str(good_html_path))
            self.assertEqual(len(generate_calls), 2)
            self.assertTrue(any("path_hygiene" in note for note in generate_calls[1]["style_notes"]))
            self.assertTrue(any(rule.check == "path_hygiene" for rule in appended_rules))


if __name__ == "__main__":
    unittest.main()
