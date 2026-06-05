from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from src.rag_report.report_vnext.formatting import public_source_label, sanitize_visible_source_text, translate_unaccented_text
from src.rag_report.report_vnext.llm import call_llm_until_nonempty, get_llm_client
from src.rag_report.report_vnext.models import ChartPlanItem, IntroChartPlan, IntroEvidencePack, IntroMetricPack, RenderedChart


COLOR_SCALE = {
    "green": "#0f766e",
    "yellow": "#d97706",
    "red": "#dc2626",
    "insufficient_data": "#94a3b8",
}


def _fact_source_summary(fact: Any) -> str:
    canonical = translate_unaccented_text(fact.canonical_line_item)
    return (
        f"{canonical} | "
        f"{public_source_label(fact.source_file, fiscal_year=fact.fiscal_year, page=fact.page, statement_or_note=fact.statement_or_note)}"
    )


def _metric_source_summary(record: Any) -> str:
    if not record.input_sources:
        return "Không có input sources."
    parts = []
    for source in record.input_sources:
        var_name = translate_unaccented_text(source.variable_name)
        canonical = translate_unaccented_text(source.canonical_line_item)
        parts.append(
            f"{var_name}: {canonical} | "
            f"{public_source_label(source.source_file, fiscal_year=source.fiscal_year, page=source.page, statement_or_note=source.statement_or_note)}"
        )
    return " ; ".join(parts)


def _fact_table(evidence_pack: IntroEvidencePack, canonical_line_item: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for fact in evidence_pack.facts:
        if fact.canonical_line_item != canonical_line_item or fact.value is None:
            continue
        rows.append(
            {
                "year": fact.fiscal_year,
                "value": round(fact.value / 1e9, 4),
                "source_summary": _fact_source_summary(fact),
            }
        )
    return sorted(rows, key=lambda item: item["year"])


def _metric_table(metric_pack: IntroMetricPack, metric_id: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in metric_pack.records:
        if record.metric_id != metric_id or record.computed_value is None:
            continue
        rows.append(
            {
                "year": record.fiscal_year,
                "value": round(record.computed_value, 6),
                "source_summary": _metric_source_summary(record),
            }
        )
    return sorted(rows, key=lambda item: item["year"])


def _vega_base(title: str, subtitle: str) -> dict:
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "width": 520,
        "height": 280,
        "title": {"text": title, "subtitle": subtitle, "anchor": "start", "fontSize": 16, "color": "#10213d"},
        "config": {
            "view": {"stroke": None},
            "axis": {
                "labelColor": "#425066",
                "titleColor": "#425066",
                "domainColor": "#cbd5e1",
                "gridColor": "#e2e8f0",
            },
            "legend": {"labelColor": "#425066", "titleColor": "#425066"},
            "background": "transparent",
        },
    }


def _merge_year_series(series: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    by_year: dict[int, dict[str, object]] = defaultdict(dict)
    provenance: dict[int, list[str]] = defaultdict(list)
    for name, rows in series.items():
        for row in rows:
            year = int(row["year"])
            by_year[year]["year"] = year
            by_year[year][name] = row["value"]
            source_summary = row.get("source_summary")
            if isinstance(source_summary, str) and source_summary:
                provenance[year].append(f"{name}: {source_summary}")
    merged: list[dict[str, object]] = []
    for year in sorted(by_year):
        row = dict(by_year[year])
        if provenance.get(year):
            row["source_summary"] = " ; ".join(provenance[year])
        merged.append(row)
    return merged


def _compact_metric_snapshot(metric_pack: IntroMetricPack) -> list[dict[str, object]]:
    focus_ids = {
        "quality_of_earnings",
        "accrual_ratio",
        "cfo_margin",
        "receivables_intensity",
        "dsri",
        "allowance_coverage_receivables",
        "inventory_provision_coverage",
        "dividend_stress_ratio",
        "cash_buffer_ratio",
        "fcf_after_dividends",
    }
    return [
        {
            "metric_id": record.metric_id,
            "metric_name": record.metric_name,
            "fiscal_year": record.fiscal_year,
            "computed_value": record.computed_value,
            "flag": record.flag,
            "unit": record.unit,
        }
        for record in metric_pack.records
        if record.metric_id in focus_ids and record.computed_value is not None
    ]


def _years_from_evidence(evidence_pack: IntroEvidencePack, metric_pack: IntroMetricPack) -> list[int]:
    years = set(evidence_pack.years)
    years.update(fact.fiscal_year for fact in evidence_pack.facts)
    years.update(snapshot.fiscal_year for snapshot in evidence_pack.audit_snapshots)
    years.update(record.fiscal_year for record in metric_pack.records if record.computed_value is not None)
    return sorted(years)


def _group_facts_by_item(evidence_pack: IntroEvidencePack) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for fact in evidence_pack.facts:
        if fact.value is not None:
            grouped[fact.canonical_line_item].append(fact)
    for facts in grouped.values():
        facts.sort(key=lambda fact: fact.fiscal_year)
    return grouped


def _group_metrics_by_id(metric_pack: IntroMetricPack) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for record in metric_pack.records:
        if record.computed_value is not None:
            grouped[record.metric_id].append(record)
    for records in grouped.values():
        records.sort(key=lambda record: record.fiscal_year)
    return grouped


def _latest_item(items: list[Any]) -> Any | None:
    return items[-1] if items else None


def _previous_item(items: list[Any]) -> Any | None:
    return items[-2] if len(items) > 1 else None


def _fmt_vnd_billion(value: float | None) -> str:
    if value is None:
        return "chưa có số liệu"
    return f"{value / 1e9:,.2f} tỷ đồng"


def _fmt_ratio(value: float | None) -> str:
    if value is None:
        return "chưa có số liệu"
    return f"{value:,.2f}"


def _trend_word(current: float | None, previous: float | None) -> str:
    if current is None or previous is None:
        return "chưa đủ chuỗi để so sánh"
    if current > previous:
        return "tăng"
    if current < previous:
        return "giảm"
    return "đi ngang"


def _chart_year_span(years: list[int]) -> str:
    if not years:
        return ""
    if len(years) == 1:
        return str(years[0])
    return f"{years[0]}–{years[-1]}"


def _build_audit_chart(evidence_pack: IntroEvidencePack) -> ChartPlanItem | None:
    if not evidence_pack.audit_snapshots:
        return None
    snapshots = sorted(evidence_pack.audit_snapshots, key=lambda item: item.fiscal_year)
    years = [snapshot.fiscal_year for snapshot in snapshots]
    latest = snapshots[-1]
    previous = snapshots[-2] if len(snapshots) > 1 else None
    title = f"Diễn biến ý kiến kiểm toán {_chart_year_span(years)}"
    subtitle_parts = [f"Dãy kiểm toán theo năm từ {_chart_year_span(years)}."]
    if previous and previous.audit_opinion and latest.audit_opinion:
        subtitle_parts.append(
            f"Chuyển từ {previous.audit_opinion.lower()} năm {previous.fiscal_year} sang {latest.audit_opinion.lower()} năm {latest.fiscal_year}."
        )
    elif latest.audit_opinion:
        subtitle_parts.append(f"Năm {latest.fiscal_year} ghi nhận {latest.audit_opinion.lower()}.")
    if previous and previous.audit_opinion and latest.audit_opinion:
        insight = f"Năm {latest.fiscal_year} ghi nhận {latest.audit_opinion.lower()} sau năm {previous.fiscal_year} {previous.audit_opinion.lower()}."
    elif latest.audit_opinion:
        insight = f"Năm {latest.fiscal_year} ghi nhận {latest.audit_opinion.lower()}."
    else:
        insight = f"Năm {latest.fiscal_year} có snapshot kiểm toán nhưng chưa trích xuất được ý kiến rõ ràng."
    if latest.severity_flag != "green":
        insight += f" Mức cảnh báo hiện ở trạng thái {latest.severity_flag}."
    return ChartPlanItem(
        chart_id="audit_timeline",
        title=title,
        subtitle=" ".join(subtitle_parts),
        insight_line=insight,
        enabled=True,
        priority=100,
    )


def _build_earnings_cash_chart(evidence_pack: IntroEvidencePack) -> ChartPlanItem | None:
    grouped = _group_facts_by_item(evidence_pack)
    lnst_rows = grouped.get("lnst", [])
    cfo_rows = grouped.get("cfo", [])
    cash_rows = grouped.get("ending_cash", [])
    if not (lnst_rows and cfo_rows and cash_rows):
        return None
    years = sorted({row.fiscal_year for row in lnst_rows + cfo_rows + cash_rows})
    latest_year = years[-1]
    latest_lnst = _latest_item([row for row in lnst_rows if row.fiscal_year == latest_year])
    latest_cfo = _latest_item([row for row in cfo_rows if row.fiscal_year == latest_year])
    latest_cash = _latest_item([row for row in cash_rows if row.fiscal_year == latest_year])
    previous_lnst = _previous_item(lnst_rows)
    previous_cfo = _previous_item(cfo_rows)
    title = f"LNST, CFO và tiền cuối kỳ {_chart_year_span(years)}"
    subtitle = f"So sánh lợi nhuận kế toán với dòng tiền thực nhận trong giai đoạn {_chart_year_span(years)}."
    if latest_lnst and latest_cfo and latest_cash:
        gap_text = _fmt_vnd_billion(latest_lnst.value - latest_cfo.value)
        insight = (
            f"Năm {latest_year}, LNST đạt {_fmt_vnd_billion(latest_lnst.value)} trong khi CFO là {_fmt_vnd_billion(latest_cfo.value)}; "
            f"khoảng chênh giữa hai dòng là {gap_text} và tiền cuối kỳ ở mức {_fmt_vnd_billion(latest_cash.value)}."
        )
    else:
        insight = f"Dữ liệu năm {latest_year} đủ để so LNST, CFO và tiền cuối kỳ trên cùng trục năm."
    if previous_lnst and previous_cfo:
        insight += (
            f" So với năm {previous_lnst.fiscal_year}, LNST {_trend_word(latest_lnst.value if latest_lnst else None, previous_lnst.value)}"
            f" và CFO {_trend_word(latest_cfo.value if latest_cfo else None, previous_cfo.value)}."
        )
    return ChartPlanItem(
        chart_id="earnings_cash",
        title=title,
        subtitle=subtitle,
        insight_line=insight,
        enabled=True,
        priority=90,
    )


def _build_accrual_dashboard_chart(metric_pack: IntroMetricPack) -> ChartPlanItem | None:
    grouped = _group_metrics_by_id(metric_pack)
    qoe_rows = grouped.get("quality_of_earnings", [])
    accrual_rows = grouped.get("accrual_ratio", [])
    if not (qoe_rows or accrual_rows):
        return None
    years = sorted({row.fiscal_year for row in qoe_rows + accrual_rows})
    latest_year = years[-1]
    latest_qoe = _latest_item(qoe_rows)
    previous_qoe = _previous_item(qoe_rows)
    latest_accrual = _latest_item(accrual_rows)
    previous_accrual = _previous_item(accrual_rows)
    title = f"Chất lượng lợi nhuận và accrual ratio {_chart_year_span(years)}"
    subtitle = f"Đọc đồng thời quality of earnings và accrual ratio để thấy mức độ chuyển hóa lợi nhuận qua {_chart_year_span(years)}."
    parts = [f"Năm {latest_year}"]
    if latest_qoe:
        parts.append(f"quality of earnings đạt {_fmt_ratio(latest_qoe.computed_value)}")
    if latest_accrual:
        parts.append(f"accrual ratio ở mức {_fmt_ratio(latest_accrual.computed_value)}")
    insight = "; ".join(parts) + "."
    if previous_qoe and previous_accrual:
        insight += (
            f" So với {previous_qoe.fiscal_year}, quality of earnings {_trend_word(latest_qoe.computed_value if latest_qoe else None, previous_qoe.computed_value)}"
            f" và accrual ratio {_trend_word(latest_accrual.computed_value if latest_accrual else None, previous_accrual.computed_value)}."
        )
    return ChartPlanItem(
        chart_id="accrual_dashboard",
        title=title,
        subtitle=subtitle,
        insight_line=insight,
        enabled=True,
        priority=85,
    )


def _build_receivables_chart(evidence_pack: IntroEvidencePack, metric_pack: IntroMetricPack) -> ChartPlanItem | None:
    facts = _group_facts_by_item(evidence_pack)
    metrics = _group_metrics_by_id(metric_pack)
    revenue_rows = facts.get("doanh_thu", [])
    receivables_rows = facts.get("phai_thu_ngan_han", [])
    dsri_rows = metrics.get("dsri", [])
    if not (revenue_rows and receivables_rows and dsri_rows):
        return None
    years = sorted({row.fiscal_year for row in revenue_rows + receivables_rows + dsri_rows})
    latest_year = years[-1]
    latest_revenue = _latest_item([row for row in revenue_rows if row.fiscal_year == latest_year])
    latest_receivables = _latest_item([row for row in receivables_rows if row.fiscal_year == latest_year])
    latest_dsri = _latest_item([row for row in dsri_rows if row.fiscal_year == latest_year])
    previous_dsri = _previous_item(dsri_rows)
    title = f"Phải thu và doanh thu {_chart_year_span(years)}"
    subtitle = f"Đối chiếu tăng trưởng doanh thu với nhịp tăng của phải thu và DSRI trong giai đoạn {_chart_year_span(years)}."
    insight = (
        f"Năm {latest_year}, phải thu ngắn hạn ở mức {_fmt_vnd_billion(latest_receivables.value if latest_receivables else None)} "
        f"trên doanh thu {_fmt_vnd_billion(latest_revenue.value if latest_revenue else None)}; DSRI đạt {_fmt_ratio(latest_dsri.computed_value if latest_dsri else None)}."
    )
    if previous_dsri:
        insight += f" So với {previous_dsri.fiscal_year}, DSRI {_trend_word(latest_dsri.computed_value if latest_dsri else None, previous_dsri.computed_value)}."
    return ChartPlanItem(
        chart_id="receivables_revenue",
        title=title,
        subtitle=subtitle,
        insight_line=insight,
        enabled=True,
        priority=80,
    )


def _build_provision_chart(metric_pack: IntroMetricPack) -> ChartPlanItem | None:
    grouped = _group_metrics_by_id(metric_pack)
    allowance_rows = grouped.get("allowance_coverage_receivables", [])
    inventory_rows = grouped.get("inventory_provision_coverage", [])
    if not (allowance_rows or inventory_rows):
        return None
    years = sorted({row.fiscal_year for row in allowance_rows + inventory_rows})
    latest_year = years[-1]
    latest_allowance = _latest_item(allowance_rows)
    latest_inventory = _latest_item(inventory_rows)
    title = f"Bao phủ dự phòng cho phải thu và tồn kho {_chart_year_span(years)}"
    subtitle = f"So sánh coverage của phải thu với tồn kho để thấy lớp đệm dự phòng nào mỏng hơn trong giai đoạn {_chart_year_span(years)}."
    insight = (
        f"Năm {latest_year}, allowance coverage đạt {_fmt_ratio(latest_allowance.computed_value if latest_allowance else None)} "
        f"và inventory coverage đạt {_fmt_ratio(latest_inventory.computed_value if latest_inventory else None)}."
    )
    return ChartPlanItem(
        chart_id="provision_risk",
        title=title,
        subtitle=subtitle,
        insight_line=insight,
        enabled=True,
        priority=75,
    )


def _build_dividend_chart(evidence_pack: IntroEvidencePack, metric_pack: IntroMetricPack) -> ChartPlanItem | None:
    facts = _group_facts_by_item(evidence_pack)
    metrics = _group_metrics_by_id(metric_pack)
    dividends_rows = facts.get("dividends_paid", [])
    cfo_rows = facts.get("cfo", [])
    cash_rows = metrics.get("cash_buffer_ratio", [])
    if not (dividends_rows and cfo_rows and cash_rows):
        return None
    years = sorted({row.fiscal_year for row in dividends_rows + cfo_rows + cash_rows})
    latest_year = years[-1]
    latest_dividends = _latest_item([row for row in dividends_rows if row.fiscal_year == latest_year])
    latest_cfo = _latest_item([row for row in cfo_rows if row.fiscal_year == latest_year])
    latest_cash = _latest_item([row for row in cash_rows if row.fiscal_year == latest_year])
    title = f"Cổ tức, CFO và đệm tiền {_chart_year_span(years)}"
    subtitle = f"Đặt dòng tiền hoạt động cạnh cổ tức đã trả và cash buffer để đo áp lực thanh khoản trong giai đoạn {_chart_year_span(years)}."
    insight = (
        f"Năm {latest_year}, cổ tức đã trả {_fmt_vnd_billion(latest_dividends.value if latest_dividends else None)} "
        f"so với CFO {_fmt_vnd_billion(latest_cfo.value if latest_cfo else None)}; cash buffer ở mức {_fmt_ratio(latest_cash.computed_value if latest_cash else None)}."
    )
    return ChartPlanItem(
        chart_id="dividend_liquidity",
        title=title,
        subtitle=subtitle,
        insight_line=insight,
        enabled=True,
        priority=70,
    )


def _build_heatmap_chart(metric_pack: IntroMetricPack) -> ChartPlanItem | None:
    grouped = _group_metrics_by_id(metric_pack)
    focus_ids = [
        "quality_of_earnings",
        "accrual_ratio",
        "dsri",
        "allowance_coverage_receivables",
        "inventory_provision_coverage",
        "dividend_stress_ratio",
        "cash_buffer_ratio",
    ]
    available_rows = [row for metric_id in focus_ids for row in grouped.get(metric_id, [])]
    if not available_rows:
        return None
    years = sorted({row.fiscal_year for row in available_rows})
    latest_year = years[-1]
    red_count = sum(1 for row in available_rows if row.flag == "red")
    yellow_count = sum(1 for row in available_rows if row.flag == "yellow")
    title = f"Bản đồ cảnh báo theo năm {_chart_year_span(years)}"
    subtitle = f"Giữ toàn bộ trục năm {years[0]}–{years[-1]} nếu dữ liệu có mặt, để đọc được nền 2020 và các năm kế tiếp khi chúng xuất hiện."
    insight = (
        f"Trong chuỗi đến năm {latest_year}, có {red_count} chỉ số đỏ và {yellow_count} chỉ số vàng; "
        f"trục năm vẫn giữ nguyên tất cả mốc dữ liệu, bao gồm 2020 nếu bộ số liệu có sẵn."
    )
    return ChartPlanItem(
        chart_id="red_flag_heatmap",
        title=title,
        subtitle=subtitle,
        insight_line=insight,
        enabled=True,
        priority=60,
    )


def build_default_intro_chart_plan(evidence_pack: IntroEvidencePack, metric_pack: IntroMetricPack) -> IntroChartPlan:
    items = [
        item
        for item in [
            _build_audit_chart(evidence_pack),
            _build_earnings_cash_chart(evidence_pack),
            _build_accrual_dashboard_chart(metric_pack),
            _build_receivables_chart(evidence_pack, metric_pack),
            _build_provision_chart(metric_pack),
            _build_dividend_chart(evidence_pack, metric_pack),
            _build_heatmap_chart(metric_pack),
        ]
        if item is not None
    ]
    items.sort(key=lambda item: (-item.priority, item.chart_id))
    return IntroChartPlan(company_id=evidence_pack.company_id, items=items)


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    lines = cleaned.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    cleaned = "\n".join(lines).strip()
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].lstrip()
    return cleaned


class IntroChartPlanner:
    def __init__(self, use_llm: bool = True) -> None:
        self.use_llm = use_llm

    def plan(
        self,
        evidence_pack: IntroEvidencePack,
        metric_pack: IntroMetricPack,
        *,
        style_notes: list[str] | None = None,
    ) -> IntroChartPlan:
        default_plan = build_default_intro_chart_plan(evidence_pack, metric_pack)
        if not self.use_llm or not default_plan.items:
            return default_plan

        client, config = get_llm_client("chart_planning")
        messages = [
            {
                "role": "system",
                "content": (
                    "Bạn là chart planning specialist cho báo cáo tài chính theo phong cách research note. "
                    "Trả về JSON array gồm chart_id, title, subtitle, insight_line, enabled, priority, skip_reason. "
                    "Chỉ dùng các chart_id đã có trong input, không tạo chart mới. "
                    "Mọi title/subtitle/insight_line phải bám vào dữ liệu thực tế trong context, có năm, giá trị hoặc xu hướng cụ thể; "
                    "tránh câu chữ chung chung. "
                    "Nếu biểu đồ có trục năm, giữ nguyên mốc 2020 khi dữ liệu gốc có năm này."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Company: {evidence_pack.company_id}\n"
                    f"Years: {json.dumps(_years_from_evidence(evidence_pack, metric_pack), ensure_ascii=False)}\n"
                    f"Default plan:\n{default_plan.model_dump_json(indent=2, exclude_none=False)}\n\n"
                    f"Metric snapshot:\n{json.dumps(_compact_metric_snapshot(metric_pack), ensure_ascii=False, indent=2)}\n\n"
                    f"Audit snapshots:\n{json.dumps([item.model_dump(mode='json') for item in evidence_pack.audit_snapshots], ensure_ascii=False, indent=2)}\n\n"
                    f"Style notes:\n{json.dumps(style_notes or [], ensure_ascii=False, indent=2)}"
                ),
            },
        ]
        raw_json = call_llm_until_nonempty(
            client,
            config.model,
            messages,
            temperature=0.1,
            max_tokens=1200,
            stream=True,
            first_token_deadline_seconds=45.0,
        )
        try:
            parsed = json.loads(_strip_code_fence(raw_json))
        except json.JSONDecodeError:
            return default_plan
        if not isinstance(parsed, list):
            return default_plan

        items_by_id = {item.chart_id: item for item in default_plan.items}
        changed = False
        for payload in parsed:
            if not isinstance(payload, dict):
                continue
            chart_id = payload.get("chart_id")
            if chart_id not in items_by_id:
                continue
            try:
                candidate = ChartPlanItem.model_validate(payload)
            except Exception:
                continue
            items_by_id[chart_id] = candidate
            changed = True
        if not changed:
            return default_plan
        items = sorted(items_by_id.values(), key=lambda item: (-item.priority, item.chart_id))
        return IntroChartPlan(company_id=evidence_pack.company_id, items=items)


def render_intro_charts(
    evidence_pack: IntroEvidencePack,
    metric_pack: IntroMetricPack,
    chart_plan: IntroChartPlan,
) -> list[RenderedChart]:
    rendered: list[RenderedChart] = []
    for item in chart_plan.items:
        if not item.enabled:
            continue
        spec = None
        if item.chart_id == "audit_timeline" and evidence_pack.audit_snapshots:
            values = sorted(
                [
                    {
                        "year": snapshot.fiscal_year,
                        "opinion": snapshot.audit_opinion or "Chưa rõ",
                        "severity": {"green": 0, "yellow": 1, "red": 2, "insufficient_data": 3}[snapshot.severity_flag],
                        "Trạng thái": {"green": "An toàn", "yellow": "Chú ý", "red": "Cảnh báo", "insufficient_data": "Thiếu dữ liệu"}[snapshot.severity_flag],
                        "source_summary": public_source_label(
                            snapshot.source_file,
                            fiscal_year=snapshot.fiscal_year,
                            page=snapshot.page,
                            statement_or_note="notes_audit",
                        ),
                    }
                    for snapshot in evidence_pack.audit_snapshots
                ],
                key=lambda row: row["year"],
            )
            spec = _vega_base(item.title, item.subtitle) | {
                "data": {"values": values},
                "mark": {"type": "line", "point": True, "strokeWidth": 3},
                "encoding": {
                    "x": {"field": "year", "type": "ordinal", "sort": "ascending", "title": "Năm"},
                    "y": {"field": "severity", "type": "quantitative", "title": "Mức cảnh báo"},
                    "color": {
                        "field": "Trạng thái",
                        "type": "nominal",
                        "scale": {
                            "domain": ["An toàn", "Chú ý", "Cảnh báo", "Thiếu dữ liệu"],
                            "range": ["#0f766e", "#d97706", "#dc2626", "#94a3b8"]
                        },
                        "legend": {"title": "Mức cảnh báo"}
                    },
                    "tooltip": [{"field": "year"}, {"field": "opinion"}, {"field": "source_summary", "title": "Nguồn"}],
                },
            }
        elif item.chart_id == "earnings_cash":
            values = []
            for row in _fact_table(evidence_pack, "lnst"):
                values.append({"year": row["year"], "metric": "Lợi nhuận sau thuế (LNST)", "value": row["value"], "source_summary": row.get("source_summary")})
            for row in _fact_table(evidence_pack, "cfo"):
                values.append({"year": row["year"], "metric": "Dòng tiền từ HĐKD (CFO)", "value": row["value"], "source_summary": row.get("source_summary")})
            for row in _fact_table(evidence_pack, "ending_cash"):
                values.append({"year": row["year"], "metric": "Tiền cuối kỳ", "value": row["value"], "source_summary": row.get("source_summary")})
            if values:
                spec = _vega_base(item.title, item.subtitle) | {
                    "data": {"values": values},
                    "encoding": {
                        "color": {
                            "field": "metric",
                            "type": "nominal",
                            "scale": {
                                "domain": ["Lợi nhuận sau thuế (LNST)", "Dòng tiền từ HĐKD (CFO)", "Tiền cuối kỳ"],
                                "range": ["#2f6fed", "#f59e0b", "#0f766e"]
                            },
                            "legend": {"title": "Chỉ tiêu"}
                        }
                    },
                    "layer": [
                        {
                            "transform": [{"filter": "datum.metric === 'Lợi nhuận sau thuế (LNST)' || datum.metric === 'Dòng tiền từ HĐKD (CFO)'"}],
                            "mark": {"type": "bar"},
                            "encoding": {
                                "x": {"field": "year", "type": "ordinal", "sort": "ascending", "title": "Năm"},
                                "y": {"field": "value", "type": "quantitative", "axis": {"title": "Tỷ VND"}},
                                "xOffset": {"field": "metric", "type": "nominal"},
                                "tooltip": [{"field": "year"}, {"field": "metric"}, {"field": "value", "title": "Giá trị"}, {"field": "source_summary", "title": "Nguồn"}],
                            },
                        },
                        {
                            "transform": [{"filter": "datum.metric === 'Tiền cuối kỳ'"}],
                            "mark": {"type": "line", "point": True, "strokeWidth": 3},
                            "encoding": {
                                "x": {"field": "year", "type": "ordinal", "sort": "ascending"},
                                "y": {"field": "value", "type": "quantitative", "axis": {"title": None}},
                                "tooltip": [{"field": "year"}, {"field": "metric"}, {"field": "value", "title": "Giá trị"}, {"field": "source_summary", "title": "Nguồn"}],
                            },
                        },
                    ],
                }
        elif item.chart_id == "accrual_dashboard":
            values = []
            for row in _metric_table(metric_pack, "quality_of_earnings"):
                values.append({"year": row["year"], "metric": "Chất lượng lợi nhuận", "value": row["value"], "source_summary": row.get("source_summary")})
            for row in _metric_table(metric_pack, "accrual_ratio"):
                values.append({"year": row["year"], "metric": "Tỷ lệ dồn tích", "value": row["value"], "source_summary": row.get("source_summary")})
            if values:
                spec = _vega_base(item.title, item.subtitle) | {
                    "data": {"values": values},
                    "mark": {"type": "line", "point": True, "strokeWidth": 3},
                    "encoding": {
                        "x": {"field": "year", "type": "ordinal", "sort": "ascending", "title": "Năm"},
                        "y": {"field": "value", "type": "quantitative", "title": "Tỷ lệ"},
                        "color": {
                            "field": "metric",
                            "type": "nominal",
                            "scale": {
                                "domain": ["Chất lượng lợi nhuận", "Tỷ lệ dồn tích"],
                                "range": ["#2f6fed", "#dc2626"]
                            },
                            "legend": {"title": "Chỉ tiêu"}
                        },
                        "tooltip": [{"field": "year"}, {"field": "metric"}, {"field": "value"}, {"field": "source_summary", "title": "Nguồn"}],
                    },
                }
        elif item.chart_id == "receivables_revenue":
            values = []
            for row in _fact_table(evidence_pack, "doanh_thu"):
                values.append({"year": row["year"], "metric": "Doanh thu", "value": row["value"], "source_summary": row.get("source_summary")})
            for row in _fact_table(evidence_pack, "phai_thu_ngan_han"):
                values.append({"year": row["year"], "metric": "Phải thu ngắn hạn", "value": row["value"], "source_summary": row.get("source_summary")})
            for row in _metric_table(metric_pack, "dsri"):
                values.append({"year": row["year"], "metric": "Chỉ số DSRI", "value": row["value"], "source_summary": row.get("source_summary")})
            if values:
                spec = _vega_base(item.title, item.subtitle) | {
                    "data": {"values": values},
                    "encoding": {
                        "color": {
                            "field": "metric",
                            "type": "nominal",
                            "scale": {
                                "domain": ["Doanh thu", "Phải thu ngắn hạn", "Chỉ số DSRI"],
                                "range": ["#cbd5e1", "#2f6fed", "#dc2626"]
                            },
                            "legend": {"title": "Chỉ tiêu"}
                        }
                    },
                    "resolve": {"scale": {"y": "independent"}},
                    "layer": [
                        {
                            "transform": [{"filter": "datum.metric === 'Doanh thu' || datum.metric === 'Phải thu ngắn hạn'"}],
                            "mark": {"type": "bar"},
                            "encoding": {
                                "x": {"field": "year", "type": "ordinal", "sort": "ascending", "title": "Năm"},
                                "y": {"field": "value", "type": "quantitative", "axis": {"title": "Tỷ VND", "orient": "left"}},
                                "xOffset": {"field": "metric", "type": "nominal"},
                                "tooltip": [{"field": "year"}, {"field": "metric"}, {"field": "value", "title": "Giá trị"}, {"field": "source_summary", "title": "Nguồn"}],
                            },
                        },
                        {
                            "transform": [{"filter": "datum.metric === 'Chỉ số DSRI'"}],
                            "mark": {"type": "line", "point": True, "strokeWidth": 3},
                            "encoding": {
                                "x": {"field": "year", "type": "ordinal", "sort": "ascending"},
                                "y": {"field": "value", "type": "quantitative", "axis": {"title": "Chỉ số DSRI", "orient": "right"}},
                                "tooltip": [{"field": "year"}, {"field": "metric"}, {"field": "value", "title": "Giá trị"}, {"field": "source_summary", "title": "Nguồn"}],
                            },
                        },
                    ],
                }
        elif item.chart_id == "provision_risk":
            values = []
            for row in _metric_table(metric_pack, "allowance_coverage_receivables"):
                values.append({"year": row["year"], "metric": "Bao phủ phải thu", "value": row["value"], "source_summary": row.get("source_summary")})
            for row in _metric_table(metric_pack, "inventory_provision_coverage"):
                values.append({"year": row["year"], "metric": "Bao phủ hàng tồn kho", "value": row["value"], "source_summary": row.get("source_summary")})
            if values:
                spec = _vega_base(item.title, item.subtitle) | {
                    "data": {"values": values},
                    "mark": {"type": "bar"},
                    "encoding": {
                        "x": {"field": "year", "type": "ordinal", "sort": "ascending", "title": "Năm"},
                        "y": {"field": "value", "type": "quantitative", "title": "Coverage"},
                        "color": {
                            "field": "metric",
                            "type": "nominal",
                            "scale": {
                                "domain": ["Bao phủ phải thu", "Bao phủ hàng tồn kho"],
                                "range": ["#dc2626", "#0f766e"]
                            },
                            "legend": {"title": "Chỉ tiêu"}
                        },
                        "xOffset": {"field": "metric"},
                        "tooltip": [{"field": "year"}, {"field": "metric"}, {"field": "value"}, {"field": "source_summary", "title": "Nguồn"}],
                    },
                }
        elif item.chart_id == "dividend_liquidity":
            values = []
            for row in _fact_table(evidence_pack, "dividends_paid"):
                values.append({"year": row["year"], "metric": "Cổ tức đã trả", "value": row["value"], "source_summary": row.get("source_summary")})
            for row in _fact_table(evidence_pack, "cfo"):
                values.append({"year": row["year"], "metric": "Dòng tiền từ HĐKD (CFO)", "value": row["value"], "source_summary": row.get("source_summary")})
            for row in _metric_table(metric_pack, "cash_buffer_ratio"):
                values.append({"year": row["year"], "metric": "Hệ số đệm tiền mặt", "value": row["value"], "source_summary": row.get("source_summary")})
            if values:
                spec = _vega_base(item.title, item.subtitle) | {
                    "data": {"values": values},
                    "encoding": {
                        "color": {
                            "field": "metric",
                            "type": "nominal",
                            "scale": {
                                "domain": ["Cổ tức đã trả", "Dòng tiền từ HĐKD (CFO)", "Hệ số đệm tiền mặt"],
                                "range": ["#0f766e", "#dc2626", "#2f6fed"]
                            },
                            "legend": {"title": "Chỉ tiêu"}
                        }
                    },
                    "resolve": {"scale": {"y": "independent"}},
                    "layer": [
                        {
                            "transform": [{"filter": "datum.metric === 'Cổ tức đã trả' || datum.metric === 'Dòng tiền từ HĐKD (CFO)'"}],
                            "mark": {"type": "bar"},
                            "encoding": {
                                "x": {"field": "year", "type": "ordinal", "sort": "ascending", "title": "Năm"},
                                "y": {"field": "value", "type": "quantitative", "axis": {"title": "Tỷ VND", "orient": "left"}},
                                "xOffset": {"field": "metric", "type": "nominal"},
                                "tooltip": [{"field": "year"}, {"field": "metric"}, {"field": "value", "title": "Giá trị"}, {"field": "source_summary", "title": "Nguồn"}],
                            },
                        },
                        {
                            "transform": [{"filter": "datum.metric === 'Hệ số đệm tiền mặt'"}],
                            "mark": {"type": "line", "point": True, "strokeWidth": 3},
                            "encoding": {
                                "x": {"field": "year", "type": "ordinal", "sort": "ascending"},
                                "y": {"field": "value", "type": "quantitative", "axis": {"title": "Hệ số đệm tiền mặt", "orient": "right"}},
                                "tooltip": [{"field": "year"}, {"field": "metric"}, {"field": "value", "title": "Giá trị"}, {"field": "source_summary", "title": "Nguồn"}],
                            },
                        },
                    ],
                }
        elif item.chart_id == "red_flag_heatmap":
            values = sorted(
                [
                    {
                        "year": record.fiscal_year,
                        "metric": record.metric_name,
                        "flag": record.flag,
                        "source_summary": _metric_source_summary(record),
                    }
                    for record in metric_pack.records
                    if record.metric_id
                    in {
                        "quality_of_earnings",
                        "accrual_ratio",
                        "dsri",
                        "allowance_coverage_receivables",
                        "inventory_provision_coverage",
                        "dividend_stress_ratio",
                        "cash_buffer_ratio",
                    }
                ],
                key=lambda row: (row["year"], row["metric"]),
            )
            if values:
                spec = _vega_base(item.title, item.subtitle) | {
                    "data": {"values": values},
                    "mark": {"type": "rect", "cornerRadius": 4},
                    "encoding": {
                        "x": {"field": "year", "type": "ordinal", "sort": "ascending", "title": "Năm"},
                        "y": {"field": "metric", "type": "nominal", "title": "Chỉ số"},
                        "color": {
                            "field": "flag",
                            "type": "nominal",
                            "scale": {"domain": list(COLOR_SCALE), "range": ["#bbf7d0", "#fde68a", "#fecaca", "#e2e8f0"]},
                        },
                        "tooltip": [{"field": "year"}, {"field": "metric"}, {"field": "flag"}, {"field": "source_summary", "title": "Nguồn"}],
                    },
                }
        if spec is not None:
            rendered.append(RenderedChart(chart_id=item.chart_id, spec=spec))
    return rendered

