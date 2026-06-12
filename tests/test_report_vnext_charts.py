from __future__ import annotations

import unittest

from src.rag_report.report_vnext.charts import build_default_intro_chart_plan, render_intro_charts
from src.rag_report.report_vnext.models import (
    AuditSnapshot,
    FinancialFact,
    IntroEvidencePack,
    IntroMetricPack,
    MetricInputSource,
    MetricRecord,
)


def _fact(canonical_line_item: str, fiscal_year: int, value: float, page: int) -> FinancialFact:
    return FinancialFact(
        canonical_line_item=canonical_line_item,
        fiscal_year=fiscal_year,
        value=value,
        source_file=rf"C:\data\{fiscal_year}\report.txt",
        page=page,
        statement_or_note="statement",
    )


def _metric(metric_id: str, metric_name: str, fiscal_year: int, value: float, flag: str) -> MetricRecord:
    return MetricRecord(
        metric_id=metric_id,
        metric_name=metric_name,
        fiscal_year=fiscal_year,
        formula_display=f"{metric_id} formula",
        formula_source="internal",
        formula_code_version="v1",
        explanation=f"{metric_name} for {fiscal_year}",
        input_values={"value": value},
        input_sources=[
            MetricInputSource(
                variable_name="value",
                fiscal_year=fiscal_year,
                canonical_line_item=metric_id,
                source_file=rf"C:\data\{fiscal_year}\metric.txt",
                page=7,
                statement_or_note="metric",
                normalized_value=value,
            )
        ],
        computed_value=value,
        unit="ratio",
        flag=flag,  # type: ignore[arg-type]
    )


def _sample_pack() -> tuple[IntroEvidencePack, IntroMetricPack]:
    evidence_pack = IntroEvidencePack(
        company_id="A32",
        years=[2020, 2021, 2024, 2025],
        facts=[
            _fact("lnst", 2024, 1_000_000_000, 9),
            _fact("lnst", 2025, 1_800_000_000, 9),
            _fact("cfo", 2024, 400_000_000, 10),
            _fact("cfo", 2025, -500_000_000, 10),
            _fact("ending_cash", 2024, 2_500_000_000, 11),
            _fact("ending_cash", 2025, 1_200_000_000, 11),
            _fact("doanh_thu", 2024, 10_000_000_000, 12),
            _fact("doanh_thu", 2025, 12_000_000_000, 12),
            _fact("phai_thu_ngan_han", 2024, 3_000_000_000, 13),
            _fact("phai_thu_ngan_han", 2025, 4_500_000_000, 13),
            _fact("dividends_paid", 2024, 200_000_000, 14),
            _fact("dividends_paid", 2025, 300_000_000, 14),
        ],
        audit_snapshots=[
            AuditSnapshot(
                fiscal_year=2020,
                audit_opinion="Chấp nhận toàn phần",
                severity_flag="green",
                source_file=r"C:\data\2020\audit.txt",
                page=2,
            ),
            AuditSnapshot(
                fiscal_year=2021,
                audit_opinion="Ngoại trừ",
                severity_flag="yellow",
                source_file=r"C:\data\2021\audit.txt",
                page=2,
            ),
            AuditSnapshot(
                fiscal_year=2025,
                audit_opinion="Chấp nhận toàn phần",
                severity_flag="green",
                source_file=r"C:\data\2025\audit.txt",
                page=2,
            ),
        ],
    )

    metric_pack = IntroMetricPack(
        company_id="A32",
        records=[
            _metric("quality_of_earnings", "Quality of Earnings / Cash Conversion", 2020, 0.95, "green"),
            _metric("accrual_ratio", "Accrual Ratio", 2020, 0.08, "green"),
            _metric("quality_of_earnings", "Quality of Earnings / Cash Conversion", 2024, 0.85, "green"),
            _metric("quality_of_earnings", "Quality of Earnings / Cash Conversion", 2025, 0.40, "red"),
            _metric("accrual_ratio", "Accrual Ratio", 2024, 0.10, "green"),
            _metric("accrual_ratio", "Accrual Ratio", 2025, 0.30, "red"),
            _metric("dsri", "DSRI", 2024, 1.05, "green"),
            _metric("dsri", "DSRI", 2025, 1.25, "yellow"),
            _metric("allowance_coverage_receivables", "Allowance Coverage Receivables", 2024, 0.55, "yellow"),
            _metric("allowance_coverage_receivables", "Allowance Coverage Receivables", 2025, 0.45, "red"),
            _metric("inventory_provision_coverage", "Inventory Provision Coverage", 2024, 0.70, "green"),
            _metric("inventory_provision_coverage", "Inventory Provision Coverage", 2025, 0.65, "yellow"),
            _metric("cash_buffer_ratio", "Cash Buffer Ratio", 2024, 1.20, "green"),
            _metric("cash_buffer_ratio", "Cash Buffer Ratio", 2025, 0.90, "red"),
            _metric("dividend_stress_ratio", "Dividend Stress Ratio", 2024, 0.80, "green"),
            _metric("dividend_stress_ratio", "Dividend Stress Ratio", 2025, 1.10, "red"),
        ],
    )
    return evidence_pack, metric_pack


class TestReportVNextCharts(unittest.TestCase):
    def test_default_intro_chart_plan_is_data_driven(self) -> None:
        evidence_pack, metric_pack = _sample_pack()
        plan = build_default_intro_chart_plan(evidence_pack, metric_pack)

        self.assertEqual(
            [item.chart_id for item in plan.items],
            [
                "audit_timeline",
                "profit_vs_cfo_cash",
                "receivables_vs_revenue",
                "dividend_cfo_cash",
                "inventory_working_capital",
                "red_flag_heatmap",
            ],
        )
        self.assertIn("2025", plan.items[0].insight_line)
        self.assertIn("LNST", plan.items[1].insight_line)
        self.assertIn("phải thu", plan.items[2].insight_line.lower())
        self.assertIn("2020", plan.items[-1].title)
        self.assertNotIn("Dùng để", plan.items[0].insight_line)
        self.assertNotIn("Ý kiến kiểm toán là tín hiệu đầu tiên", plan.items[0].insight_line)

    def test_render_intro_charts_uses_line_audit_spec_and_keeps_2020(self) -> None:
        evidence_pack, metric_pack = _sample_pack()
        plan = build_default_intro_chart_plan(evidence_pack, metric_pack)
        charts = render_intro_charts(evidence_pack, metric_pack, plan)
        spec_by_id = {chart.chart_id: chart.spec for chart in charts}

        audit_spec = spec_by_id["audit_timeline"]
        self.assertIn("layer", audit_spec)
        self.assertEqual(audit_spec["layer"][0]["mark"]["type"], "line")
        self.assertEqual(audit_spec["layer"][1]["mark"]["type"], "point")

        heatmap_values = spec_by_id["red_flag_heatmap"]["data"]["values"]
        years = [row["year"] for row in heatmap_values]
        self.assertIn(2020, years)
        self.assertEqual(years[0], 2020)
        self.assertTrue(all(years[index] <= years[index + 1] for index in range(len(years) - 1)))

        self.assertEqual([chart.chart_id for chart in charts], [item.chart_id for item in plan.items])


if __name__ == "__main__":
    unittest.main()
