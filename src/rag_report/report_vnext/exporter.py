from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Iterable

from src.rag_report.config import settings
from src.rag_report.report_vnext.formatting import formula_math_block, public_source_label, sanitize_visible_source_text, translate_unaccented_text
from src.rag_report.report_vnext.models import (
    AppendixIndicator,
    ChartPlanItem,
    ExecutiveVerdict,
    IntroMetricPack,
    IntroRenderBundle,
    MetricRecord,
    SignalNumber,
)


METRIC_NAME_VI = {
    "Quality of Earnings / Cash Conversion": "Chất lượng lợi nhuận / Chuyển đổi tiền mặt",
    "Accrual Ratio": "Tỷ lệ dồn tích",
    "CFO Margin": "Biên dòng tiền HĐKD (CFO Margin)",
    "Receivables Intensity": "Mức độ thâm dụng phải thu",
    "DSRI": "Chỉ số DSRI",
    "Allowance Coverage – Receivables": "Tỷ lệ bao nợ xấu phải thu",
    "Inventory Provision Coverage": "Tỷ lệ bao nợ/dự phòng hàng tồn kho",
    "Dividend Stress Ratio": "Tỷ lệ căng thẳng cổ tức",
    "Cash Buffer Ratio": "Tỷ lệ đệm tiền mặt",
    "Free Cash Flow After Dividends": "Dòng tiền tự do sau cổ tức"
}


class VNextHTMLExporter:
    def __init__(self) -> None:
        self.output_dir = Path(settings.REPORT_OUTPUT_DIR_ABS) / "html"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._citation_to_number: dict[str, int] = {}
        self._number_to_citation: dict[int, str] = {}

    def _escape(self, value: Any) -> str:
        return html.escape(sanitize_visible_source_text(str(value)))

    def _sanitize_spec(self, value: Any, is_top_level: bool = True) -> Any:
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                if is_top_level and key == "title":
                    continue
                if key == "width" and isinstance(item, (int, float)):
                    sanitized[key] = "container"
                    continue
                if key == "autosize" and isinstance(item, dict):
                    sanitized[key] = self._sanitize_spec(item, is_top_level=False)
                    continue
                sanitized[key] = self._sanitize_spec(item, is_top_level=False)
            if sanitized.get("width") == "container" and "autosize" not in sanitized:
                sanitized["autosize"] = {"type": "fit-x", "contains": "padding", "resize": True}
            return sanitized
        if isinstance(value, list):
            return [self._sanitize_spec(item, is_top_level=False) for item in value]
        if isinstance(value, str):
            return sanitize_visible_source_text(value)
        return value

    def _register_citation(self, citation_text: str) -> int:
        cleaned = re.sub(r"\bBCTC\s*(\d{4})\b", r"BCTC \1", citation_text, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bBCTC(\d{4})\b", r"BCTC \1", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r",\s*", r", ", cleaned)
        cleaned = re.sub(r"\btrang\s*(\d+)\b", r"trang \1", cleaned, flags=re.IGNORECASE)
        normalized = re.sub(r"\s+", " ", cleaned.strip())
        if normalized not in self._citation_to_number:
            number = len(self._citation_to_number) + 1
            self._citation_to_number[normalized] = number
            self._number_to_citation[number] = normalized
        return self._citation_to_number[normalized]

    def _render_citation_tooltip(self, number: int, citation_text: str) -> str:
        public_label = self._escape(citation_text)
        return (
            "<span class='cite-tooltip' role='tooltip'>"
            f"<span class='cite-tooltip-title'>Nguồn {number}</span>"
            f"<span class='cite-tooltip-body'>{public_label}</span>"
            "</span>"
        )

    def _render_citation_reference(self, number: int, citation_text: str) -> str:
        tooltip = self._render_citation_tooltip(number, citation_text)
        return (
            f"<sup class='cite-ref' data-cite-number='{number}'>"
            f"{number}{tooltip}"
            "</sup>"
        )

    def _render_text_with_citations(self, text: str) -> str:
        pattern = re.compile(r"\[(BCTC\s*[^\]]+)\]")
        placeholders: list[tuple[str, int]] = []

        def replace(match: re.Match[str]) -> str:
            citation_text = re.sub(r"\s+", " ", match.group(1).strip())
            number = self._register_citation(citation_text)
            token = f"__CITE_{number}__"
            placeholders.append((token, number))
            return token

        substituted = pattern.sub(replace, text)
        escaped = self._escape(substituted)
        escaped = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"\*(.*?)\*", r"<em>\1</em>", escaped)
        for token, number in placeholders:
            citation_text = self._number_to_citation[number]
            escaped = escaped.replace(token, self._render_citation_reference(number, citation_text))
        return escaped

    def _markdown_to_html(self, markdown_text: str) -> str:
        blocks = [chunk.strip() for chunk in markdown_text.split("\n\n") if chunk.strip()]
        html_blocks: list[str] = []
        pending_bullets: list[str] = []

        def flush_bullets() -> None:
            if pending_bullets:
                html_blocks.append(f"<ul class='bullet-list'>{''.join(pending_bullets)}</ul>")
                pending_bullets.clear()

        for block in blocks:
            lines = [line.rstrip() for line in block.splitlines() if line.strip()]
            if not lines:
                continue
            if all(line.startswith("- ") for line in lines):
                pending_bullets.extend(f"<li>{self._render_text_with_citations(line[2:])}</li>" for line in lines)
                continue
            flush_bullets()
            first = lines[0]
            if first.startswith("# "):
                html_blocks.append(f"<h2>{self._render_text_with_citations(first[2:])}</h2>")
                if len(lines) > 1:
                    html_blocks.append(f"<p>{self._render_text_with_citations(' '.join(lines[1:]))}</p>")
                continue
            if first.startswith("## "):
                html_blocks.append(f"<h3>{self._render_text_with_citations(first[3:])}</h3>")
                if len(lines) > 1:
                    html_blocks.append(f"<p>{self._render_text_with_citations(' '.join(lines[1:]))}</p>")
                continue
            if first.startswith("### "):
                html_blocks.append(f"<h4>{self._render_text_with_citations(first[4:])}</h4>")
                if len(lines) > 1:
                    html_blocks.append(f"<p>{self._render_text_with_citations(' '.join(lines[1:]))}</p>")
                continue
            html_blocks.append(f"<p>{self._render_text_with_citations(' '.join(lines))}</p>")
        flush_bullets()
        return "\n".join(html_blocks)

    def _flag_label(self, flag: str) -> str:
        mapping = {
            "green": "Xanh",
            "yellow": "Vàng",
            "red": "Đỏ",
            "insufficient_data": "Thiếu dữ liệu",
        }
        return mapping.get(flag, flag)

    def _format_metric_value(self, record: MetricRecord) -> str:
        if record.computed_value is None:
            return "Chưa đủ dữ liệu"
        if record.unit == "VND":
            return f"{record.computed_value / 1e9:,.2f} tỷ VND"
        return f"{record.computed_value:,.2f}"

    def _metric_tooltip(self, record: MetricRecord) -> str:
        explanation = record.explanation
        for eng, vi in METRIC_NAME_VI.items():
            explanation = explanation.replace(eng, vi)

        rows = []
        for source in record.input_sources:
            source_label = public_source_label(
                source.source_file,
                fiscal_year=source.fiscal_year,
                page=source.page,
                statement_or_note=source.statement_or_note,
            )
            value_text = "n/a" if source.normalized_value is None else f"{source.normalized_value:,.0f}"
            rows.append(
                "<li>"
                f"<strong>{self._escape(translate_unaccented_text(source.variable_name))}</strong>: {self._escape(value_text)} {self._escape(source.unit)}<br>"
                f"<div class='metric-subtle'>{self._escape(translate_unaccented_text(source.canonical_line_item))} | {self._escape(source_label)}</div>"
                "</li>"
            )
        notes = "".join(f"<li>{self._escape(note)}</li>" for note in record.notes) or "<li>Không có ghi chú bổ sung.</li>"
        gap = f"<p class='metric-gap'>{self._escape(record.data_gap_reason)}</p>" if record.data_gap_reason else ""
        formula = formula_math_block(record.formula_latex, record.formula_display)
        source_summary = record.formula_source or "Nguồn công thức nội bộ"
        return (
            "<span class='metric-tooltip' role='tooltip'>"
            "<div class='metric-tooltip-section'><strong>Công thức</strong>"
            f"<div class='metric-formula'>{formula}</div> "
            f"<div class='metric-subtle'>Nguồn công thức: {self._escape(source_summary)}</div> "
            f"<div class='metric-subtle'>{self._escape(explanation)}</div> "
            "</div> "
            "<div class='metric-tooltip-section'><strong>Số liệu dùng để tính</strong>"
            f"<ul>{''.join(rows) if rows else '<li>Không có input.</li>'}</ul>"
            "</div> "
            "<div class='metric-tooltip-section'><strong>Ghi chú</strong>"
            f"<ul>{notes}</ul>"
            "</div> "
            f"{gap}"
            "</span>"
        )

    def _render_audit_summary(self, bundle: IntroRenderBundle) -> str:
        if not bundle.evidence_pack.audit_snapshots:
            return (
                "<section class='report-section'>"
                "<h2>Ý kiến kiểm toán</h2>"
                "<p class='callout'>Chưa trích xuất được snapshot kiểm toán từ OCR.</p>"
                "</section>"
            )
        rows = []
        for snapshot in bundle.evidence_pack.audit_snapshots:
            if not snapshot.audit_opinion:
                continue
            source_label = public_source_label(
                snapshot.source_file,
                fiscal_year=snapshot.fiscal_year,
                page=snapshot.page,
                statement_or_note="notes_audit",
            )
            rows.append(
                "<tr>"
                f"<td>{snapshot.fiscal_year}</td>"
                f"<td>{self._escape(snapshot.audit_opinion or 'Chưa rõ')}</td>"
                f"<td>{self._escape(snapshot.auditor or 'Chưa trích xuất')}</td>"
                f"<td>{self._escape(source_label)}</td>"
                "</tr>"
            )

        intro_html = ""
        if bundle.narrative.audit_intro:
            intro_html = f"<div class='audit-intro-guidance' style='margin-bottom: 15px; font-size: 0.95rem; line-height: 1.5; color: var(--text);'>{self._render_text_with_citations(bundle.narrative.audit_intro)}</div>"

        conclusion_html = ""
        if bundle.narrative.audit_conclusion:
            conclusion_html = f"<div class='audit-summary-conclusion' style='margin-top: 15px; font-weight: 500; font-size: 0.95rem; line-height: 1.5; color: var(--text);'>{self._render_text_with_citations(bundle.narrative.audit_conclusion)}</div>"

        return (
            "<section class='report-section'>"
            "<h2>Ý kiến kiểm toán qua các năm</h2>"
            f"{intro_html}"
            "<div class='table-wrap'>"
            "<table class='audit-table'>"
            "<thead><tr><th>Năm</th><th>Ý kiến</th><th>Đơn vị kiểm toán</th><th>Nguồn</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
            "</div>"
            f"{conclusion_html}"
            "</section>"
        )

    def _render_metric_table(self, metric_pack: IntroMetricPack) -> str:
        focus_ids = [
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
        ]
        by_metric: dict[str, list[MetricRecord]] = {}
        for record in metric_pack.records:
            by_metric.setdefault(record.metric_id, []).append(record)
        years = sorted({item.fiscal_year for item in metric_pack.records})
        visible_years = years[-2:]
        header_years = visible_years if len(visible_years) == 2 else visible_years + visible_years[:1]
        rows = []
        for metric_id in focus_ids:
            records = sorted(by_metric.get(metric_id, []), key=lambda item: item.fiscal_year)
            if not records:
                continue
            latest = records[-1]
            if latest.computed_value is None:
                continue
            previous = records[-2] if len(records) > 1 and records[-2].computed_value is not None else None
            prev_value = self._format_metric_value(previous) if previous else "—"
            latest_value = self._format_metric_value(latest)
            vi_name = METRIC_NAME_VI.get(latest.metric_name, latest.metric_name)
            raw_takeaway = latest.takeaway or latest.explanation
            for eng, vi in METRIC_NAME_VI.items():
                raw_takeaway = raw_takeaway.replace(eng, vi)

            rows.append(
                "<tr class='metric-row "
                f"flag-{latest.flag}'>"
                "<td class='metric-name-cell'>"
                f"<span class='metric-hover-anchor'>{self._escape(vi_name)} {self._metric_tooltip(latest)}</span>"
                f"<div class='metric-note'>{self._escape(latest.explanation)}</div>"
                "</td>"
                f"<td class='metric-formula-cell'>\\({self._escape(latest.formula_latex or latest.formula_display)}\\)</td>"
                f"<td class='metric-value-cell'>{self._escape(prev_value)}</td>"
                f"<td class='metric-value-cell'>{self._escape(latest_value)}</td>"
                f"<td class='metric-flag-cell'>{self._escape(self._flag_label(latest.flag))}</td>"
                f"<td class='metric-note-cell'>{self._escape(raw_takeaway)}</td>"
                "</tr>"
            )
        if not rows:
            return "<p class='callout'>Không có chỉ số đủ điều kiện hiển thị.</p>"
        prev_year = header_years[0] if header_years else ""
        latest_year = header_years[-1] if header_years else ""
        return (
            "<section class='report-section'>"
            "<h2>Bảng chỉ tiêu trọng yếu</h2>"
            "<div class='table-wrap'>"
            "<table class='indicator-table'>"
            "<thead>"
            "<tr>"
            "<th>Chỉ tiêu</th>"
            "<th>Công thức</th>"
            f"<th>{self._escape(str(prev_year))}</th>"
            f"<th>{self._escape(str(latest_year))}</th>"
            "<th>Đánh giá</th>"
            "<th>Nhận định nhanh</th>"
            "</tr>"
            "</thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
            "</div>"
            "</section>"
        )

    def _collect_chart_sources(self, spec: Any) -> list[str]:
        sources: list[str] = []

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                if isinstance(value.get("source_summary"), str):
                    label = sanitize_visible_source_text(value["source_summary"])
                    if label not in sources:
                        sources.append(label)
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(spec)
        return sources

    def _has_chart_data(self, spec: Any) -> bool:
        if not isinstance(spec, dict):
            return False

        def walk(value: Any) -> bool:
            if isinstance(value, dict):
                data = value.get("data")
                if isinstance(data, dict):
                    values = data.get("values")
                    if isinstance(values, list) and values:
                        return True
                for item in value.values():
                    if walk(item):
                        return True
            elif isinstance(value, list):
                for item in value:
                    if walk(item):
                        return True
            return False

        return walk(spec)

    def _render_chart_figure(self, index: int, item: Any, spec: Any) -> tuple[str, str] | None:
        if not self._has_chart_data(spec):
            return None
        sources = self._collect_chart_sources(spec)
        source_footer = "Nguồn: " + "; ".join(sources[:3]) if sources else "Nguồn: dữ liệu tài chính tổng hợp"
        dom_id = f"chart-{item.chart_id}"
        figure_id = f"figure-{item.chart_id}"
        figure_style = "style='min-height: 520px;'"
        spec_json = json.dumps(spec, ensure_ascii=False)
        figure_html = (
            f"<figure class='report-figure' id='{figure_id}' data-renderable='true' {figure_style}>"
            f"<div class='figure-kicker'>Hình {index}</div>"
            f"<div class='figure-title'>{self._escape(item.title)}</div>"
            f"<div class='figure-subtitle'>{self._escape(item.subtitle)}</div>"
            f"<div id='{dom_id}' class='chart-mount' aria-label='{self._escape(item.title)}'></div>"
            f"<figcaption class='figure-caption'>{self._escape(item.insight_line)}</figcaption>"
            f"<div class='figure-source'>{self._escape(source_footer)}</div>"
            "</figure>"
        )
        script = (
            f"safeEmbedChart('{figure_id}', '{dom_id}', {spec_json});"
        )
        return figure_html, script

    def _render_chart_pages(self, bundle: IntroRenderBundle) -> tuple[str, str]:
        chart_blocks = []
        embed_calls = []
        spec_by_id = {chart.chart_id: self._sanitize_spec(chart.spec) for chart in bundle.charts}
        for index, item in enumerate(sorted(bundle.chart_plan.items, key=lambda value: (-value.priority, value.chart_id)), start=1):
            if not item.enabled or item.chart_id not in spec_by_id:
                continue
            rendered = self._render_chart_figure(index, item, spec_by_id[item.chart_id])
            if rendered is None:
                continue
            chart_html, script = rendered
            chart_blocks.append(chart_html)
            embed_calls.append(script)
        return "\n".join(chart_blocks), "\n".join(embed_calls)

    def _render_notes(self, data_gaps: Iterable[str]) -> str:
        unique_gaps = []
        for gap in data_gaps:
            clean = sanitize_visible_source_text(gap)
            if clean not in unique_gaps:
                unique_gaps.append(clean)
        if not unique_gaps:
            return "<p class='callout'>Dữ liệu chính giai đoạn 2023–2025 đủ để phân tích các chỉ tiêu trọng yếu. Tuy nhiên, giai đoạn 2017–2019 thiếu thông tin xác nhận ý kiến kiểm toán, nên khi đọc chuỗi dài cần xem các năm này như dữ liệu tham khảo, không phải nền chính để kết luận.</p>"
        items = "".join(f"<li>{self._escape(item)}</li>" for item in unique_gaps[:10])
        return (
            "<section class='report-section'>"
            "<h2>Ghi chú cần kiểm chứng thêm</h2>"
            f"<ul class='bullet-list'>{items}</ul>"
            "</section>"
        )

    def _render_references(self) -> str:
        if not self._number_to_citation:
            return "<p class='callout'>Không có trích dẫn trực tiếp.</p>"
        items = []
        for number in sorted(self._number_to_citation):
            citation_text = self._number_to_citation[number]
            items.append(
                "<li>"
                f"<span class='cite-ref reference-ref' data-cite-number='{number}'>[{number}]{self._render_citation_tooltip(number, citation_text)}</span> "
                f"<span class='reference-text'>{self._escape(citation_text)}</span>"
                "</li>"
            )
        return f"<ol class='reference-list'>{''.join(items)}</ol>"

    def _signal_badge_class(self, level: str) -> str:
        return {
            "green": "badge badge-green",
            "yellow": "badge badge-yellow",
            "red": "badge badge-red",
            "gray": "badge badge-gray",
        }.get(level, "badge")

    def _render_signal_card(self, signal: Any) -> str:
        numbers = "".join(
            f"<div class='signal-number'><span class='signal-number-label'>{self._escape(number.label)}</span>"
            f"<span class='signal-number-value'>{self._escape(number.value)}</span>"
            f"<span class='signal-number-source'>{self._escape(number.source)}</span></div>"
            for number in getattr(signal, "main_numbers", [])
        )
        sources = ", ".join(getattr(signal, "source_refs", []))
        return (
            f"<article class='signal-card signal-card-{getattr(signal, 'alert_level', 'gray')}'>"
            f"<div class='signal-question'>{self._escape(getattr(signal, 'question', ''))}</div>"
            f"<div class='signal-conclusion'>{self._escape(getattr(signal, 'conclusion', ''))}</div>"
            f"<div class='signal-numbers'>{numbers or '<div class=\"signal-empty\">Không có số liệu.</div>'}</div>"
            f"<div class='signal-explain'>{self._escape(getattr(signal, 'plain_explanation', ''))}</div>"
            f"<div class='signal-footer'>"
            f"<span class='{self._signal_badge_class(getattr(signal, 'alert_level', 'gray'))}'>{self._escape(getattr(signal, 'alert_label', ''))}</span>"
            f"<span class='signal-reason'>{self._escape(getattr(signal, 'alert_reason', ''))}</span>"
            f"<span class='signal-source'>{self._escape(sources)}</span>"
            f"</div>"
            f"</article>"
        )

    def _render_verdict_panel(self, contract: Any) -> str:
        verdict = getattr(contract, "executive_verdict", None)
        if verdict is None:
            return ""
        focus_areas = "".join(f"<li>{self._escape(item)}</li>" for item in getattr(verdict, "focus_areas", []))
        return (
            "<div class='verdict-panel'>"
            "<div class='verdict-header'>Kết luận nhanh cho người không chuyên</div>"
            f"<div class='verdict-text'>{self._escape(getattr(verdict, 'main_message', ''))}</div>"
            "<div class='verdict-grid'>"
            f"<div class='verdict-item'><strong>Nguồn số liệu:</strong> {self._escape(getattr(verdict, 'source_reliability', ''))}</div>"
            f"<div class='verdict-item'><strong>Trạng thái tài chính:</strong> {self._escape(getattr(verdict, 'financial_signal', ''))}</div>"
            "</div>"
            f"<div class='verdict-focus'><div class='verdict-subhead'>Điểm cần kiểm tra tiếp theo</div><ul class='bullet-list'>{focus_areas}</ul></div>"
            "</div>"
        )

    def _render_opening_page(self, bundle: IntroRenderBundle, contract: Any) -> str:
        intro_html = self._markdown_to_html(bundle.narrative.markdown)
        return (
            "<section class='report-page'>"
            "<div class='section-kicker'>Tổng kết</div>"
            "<h2 class='section-title'>Phần mở đầu / Kết luận nhanh</h2>"
            f"{self._render_verdict_panel(contract)}"
            f"<div class='opening-copy'>{intro_html}</div>"
            "</section>"
        )

    def _render_audit_page(self, bundle: IntroRenderBundle) -> str:
        rows = []
        for snapshot in sorted(bundle.evidence_pack.audit_snapshots, key=lambda item: item.fiscal_year):
            rows.append(
                "<tr>"
                f"<td>{snapshot.fiscal_year}</td>"
                f"<td>{self._escape(snapshot.audit_opinion or 'Chưa rõ')}</td>"
                f"<td>{self._escape(snapshot.auditor or 'Chưa trích xuất')}</td>"
                f"<td>{self._escape(snapshot.data_gap_reason or self._format_audit_source(snapshot))}</td>"
                "</tr>"
            )
        intro = self._escape(bundle.narrative.audit_intro or "Trước khi phân tích sâu, cần xác nhận báo cáo có được kiểm toán hay không.")
        conclusion = self._escape(bundle.narrative.audit_conclusion or "")
        return (
            "<section class='report-page'>"
            "<div class='section-kicker'>Kiểm toán</div>"
            "<h2 class='section-title'>Bước 1 - Nguồn số liệu có đáng dùng không?</h2>"
            f"<div class='audit-intro'>{intro}</div>"
            "<div class='table-wrap'>"
            "<table class='audit-table'>"
            "<thead><tr><th>Năm</th><th>Ý kiến</th><th>Đơn vị kiểm toán</th><th>Nguồn</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
            "</div>"
            f"<div class='audit-conclusion'>{conclusion}</div>"
            "</section>"
        )

    def _format_audit_source(self, snapshot: Any) -> str:
        if snapshot.source_file:
            return f"BCTC {snapshot.fiscal_year}"
        return f"BCTC {snapshot.fiscal_year}"

    def _render_chart_page_group(self, items: list[Any], spec_by_id: dict[str, Any], title: str, kicker: str) -> list[str]:
        pages: list[str] = []
        for start in range(0, len(items), 2):
            chunk = items[start:start + 2]
            figures = []
            for index, item in enumerate(chunk, start=start + 1):
                rendered = self._render_chart_figure(index, item, spec_by_id[item.chart_id])
                if rendered is None:
                    continue
                figures.append(rendered[0])
            if not figures:
                continue
            pages.append(
                "<section class='report-page'>"
                f"<div class='section-kicker'>{self._escape(kicker)}</div>"
                f"<h2 class='section-title'>{self._escape(title)}</h2>"
                f"<div class='figure-grid'>{''.join(figures)}</div>"
                "</section>"
            )
        return pages

    def _render_signals_page(self, contract: Any) -> str:
        cards = "".join(self._render_signal_card(signal) for signal in getattr(contract, "key_signals", []))
        legend = (
            "<div class='signal-legend'>"
            "<span class='signal-legend-label'>Mức độ:</span>"
            "<span class='badge badge-green'>Bình thường</span>"
            "<span class='badge badge-yellow'>Cần theo dõi</span>"
            "<span class='badge badge-red'>Cảnh báo cao</span>"
            "<span class='badge badge-gray'>Thiếu dữ liệu</span>"
            "</div>"
        )
        return (
            "<section class='report-page'>"
            "<div class='section-kicker'>Tín hiệu</div>"
            "<h2 class='section-title'>Các tín hiệu trọng yếu từ số liệu</h2>"
            f"{legend}"
            f"<div class='signal-grid'>{cards}</div>"
            "</section>"
        )

    def _render_closing_page(self, contract: Any) -> str:
        verdict = getattr(contract, "executive_verdict", None)
        if verdict is None:
            return ""
        focus_areas = "".join(f"<li>{self._escape(item)}</li>" for item in getattr(verdict, "focus_areas", []))
        return (
            "<section class='report-page'>"
            "<div class='section-kicker'>Kết luận</div>"
            "<h2 class='section-title'>Chốt lại phần mở đầu</h2>"
            "<div class='closing-block'>"
            f"<div><strong>Kết luận chung:</strong> {self._escape(getattr(verdict, 'source_reliability', ''))}</div>"
            f"<div><strong>Tuy nhiên:</strong> {self._escape(getattr(verdict, 'main_message', ''))}</div>"
            f"<div><strong>Do đó:</strong><ul class='bullet-list'>{focus_areas}</ul></div>"
            "</div>"
            "</section>"
        )

    def _render_appendix_metric_page(self, metric_pack: IntroMetricPack, contract: Any, data_gaps: list[str]) -> str:
        table_html = self._render_metric_table(metric_pack)
        indicator_cards = []
        for indicator in getattr(contract, "appendix_indicators", []):
            inputs = "".join(
                f"<li><span>{self._escape(item.label)}</span><span>{self._escape(item.value)}</span><span>{self._escape(item.source)}</span></li>"
                for item in getattr(indicator, "input_values", [])
            )
            sources = ", ".join(getattr(indicator, "source_refs", []))
            notes = "".join(f"<li>{self._escape(note)}</li>" for note in getattr(indicator, "notes", []))
            indicator_cards.append(
                "<article class='appendix-indicator'>"
                f"<div class='appendix-indicator-name'>{self._escape(getattr(indicator, 'name', ''))}</div>"
                f"<div class='appendix-indicator-formula'>{self._escape(getattr(indicator, 'formula', ''))}</div>"
                f"<div class='appendix-indicator-result'><strong>Kết quả:</strong> {self._escape(getattr(indicator, 'result', ''))}</div>"
                f"<div class='appendix-indicator-inputs'><ul>{inputs}</ul></div>"
                f"<div class='appendix-indicator-sources'><strong>Nguồn:</strong> {self._escape(sources)}</div>"
                f"<div class='appendix-indicator-notes'><ul>{notes}</ul></div>"
                "</article>"
            )
        gap_html = ""
        if data_gaps:
            gap_items = "".join(f"<li>{self._escape(item)}</li>" for item in data_gaps)
            gap_html = (
                "<div class='appendix-gap-note'>"
                "<div class='appendix-gap-title'>Ghi chú thiếu dữ liệu</div>"
                f"<ul class='bullet-list'>{gap_items}</ul>"
                "</div>"
            )
        return (
            "<section class='report-page'>"
            "<div class='section-kicker'>Phụ lục kỹ thuật</div>"
            "<h2 class='section-title'>Phụ lục kỹ thuật - Công thức, số liệu đầu vào và nguồn kiểm chứng</h2>"
            f"{table_html}"
            f"{gap_html}"
            f"<div class='appendix-indicator-grid'>{''.join(indicator_cards)}</div>"
            "</section>"
        )

    def _build_css(self) -> str:
        return """
    :root {
      --paper: #f7f3ec;
      --surface: #fffdf9;
      --ink: #162033;
      --muted: #55606f;
      --line: #d8d0c6;
      --accent: #153e75;
      --accent-soft: rgba(21, 62, 117, 0.08);
      --shadow: 0 10px 24px rgba(21, 32, 51, 0.06);
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; }
    body {
      background: linear-gradient(180deg, #fcfbf8 0%, var(--paper) 100%);
      color: var(--ink);
      font-family: "Noto Serif", "Georgia", "Times New Roman", serif;
    }
    @page { size: A4 landscape; margin: 12mm; }
    .report-shell { width: min(297mm, calc(100vw - 24px)); margin: 0 auto; padding: 12px 0 28px; }
    .report-page {
      min-height: calc(210mm - 24mm);
      break-after: page;
      page-break-after: always;
      background: var(--surface);
      border: 1px solid var(--line);
      padding: 16mm 14mm;
      margin: 0 0 12mm;
    }
    .report-page:last-child { break-after: auto; page-break-after: auto; margin-bottom: 0; }
    .cover-title { font-size: clamp(2rem, 4vw, 3.2rem); line-height: 1.08; margin: 0 0 10px; font-weight: 700; }
    .cover-subtitle { font-size: 1.02rem; line-height: 1.7; color: var(--muted); max-width: 80ch; }
    .section-title { margin: 0 0 14px; font-size: 1.45rem; font-weight: 700; }
    .section-kicker { color: var(--accent); text-transform: uppercase; letter-spacing: .08em; font-size: .76rem; font-weight: 700; margin-bottom: 10px; }
    .report-section, .opening-copy, .audit-intro, .audit-conclusion, .closing-block, .signal-grid, .appendix-indicator-grid { color: var(--ink); }
    .bullet-list { padding-left: 20px; margin: 0; }
    .callout, .audit-intro, .audit-conclusion { color: var(--muted); line-height: 1.7; }
    .verdict-panel {
      background: #f8fbff; border: 1px solid #c7d8eb; border-left: 4px solid var(--accent);
      border-radius: 8px; padding: 18px 20px; margin-bottom: 24px;
    }
    .verdict-header { font-size: 1.1rem; font-weight: 700; color: var(--accent); margin-bottom: 10px; text-transform: uppercase; letter-spacing: .04em; }
    .verdict-text { color: var(--ink); font-size: .98rem; line-height: 1.65; margin-bottom: 14px; }
    .verdict-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; border-top: 1px dashed #c7d8eb; padding-top: 12px; }
    .verdict-item { font-size: .92rem; color: var(--muted); }
    .verdict-subhead { margin-top: 12px; font-size: .86rem; text-transform: uppercase; letter-spacing: .04em; color: var(--accent); font-weight: 700; }
    .signal-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
    .signal-legend { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 0 0 14px; font-size: .86rem; color: var(--muted); }
    .signal-legend-label { text-transform: uppercase; letter-spacing: .04em; color: var(--accent); font-weight: 700; }
    .signal-card {
      border: 1px solid var(--line); border-radius: 14px; background: #fff; padding: 16px;
      box-shadow: var(--shadow); display: flex; flex-direction: column; gap: 10px;
    }
    .signal-card-green { border-left: 4px solid #166534; }
    .signal-card-yellow { border-left: 4px solid #b45309; }
    .signal-card-red { border-left: 4px solid #b91c1c; }
    .signal-card-gray { border-left: 4px solid #475569; }
    .signal-question { font-weight: 700; font-size: 1rem; color: var(--accent); }
    .signal-conclusion { font-size: 1.02rem; line-height: 1.6; }
    .signal-numbers { display: grid; gap: 8px; }
    .signal-number { display: grid; grid-template-columns: 1fr auto; gap: 4px 10px; align-items: baseline; border-top: 1px dashed var(--line); padding-top: 8px; }
    .signal-number-label { color: var(--muted); font-size: .82rem; text-transform: uppercase; letter-spacing: .04em; }
    .signal-number-value { font-weight: 700; }
    .signal-number-source { grid-column: 1 / -1; color: var(--muted); font-size: .8rem; }
    .signal-explain { color: var(--muted); line-height: 1.65; }
    .signal-footer { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; border-top: 1px solid var(--line); padding-top: 8px; font-size: .86rem; color: var(--muted); }
    .badge { display: inline-block; padding: 3px 8px; border-radius: 999px; font-weight: 700; font-size: .78rem; }
    .badge-green { background: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }
    .badge-yellow { background: #fffbeb; color: #b45309; border: 1px solid #fde68a; }
    .badge-red { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }
    .badge-gray { background: #f8fafc; color: #475569; border: 1px solid #e2e8f0; }
    .figure-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
    .report-figure {
      margin: 0;
      padding: 16px;
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 8px;
      min-height: 520px;
      break-inside: avoid;
      page-break-inside: avoid;
      display: flex;
      flex-direction: column;
      word-wrap: break-word;
      overflow-wrap: break-word;
    }
    .figure-kicker { color: var(--accent); text-transform: uppercase; letter-spacing: .08em; font-weight: 700; font-size: .74rem; margin-bottom: 8px; }
    .figure-title { font-size: 1.2rem; font-weight: 700; margin-bottom: 6px; word-wrap: break-word; overflow-wrap: break-word; }
    .figure-subtitle { color: var(--muted); margin-bottom: 12px; font-size: .95rem; word-wrap: break-word; overflow-wrap: break-word; }
    .chart-mount {
      width: 100%;
      height: 300px;
      min-height: 300px;
      flex: 0 0 300px;
      margin-bottom: 8px;
    }
    .figure-caption { margin-top: 10px; color: var(--ink); font-size: .96rem; word-wrap: break-word; overflow-wrap: break-word; }
    .figure-source { margin-top: 6px; color: var(--muted); font-size: .85rem; word-wrap: break-word; overflow-wrap: break-word; }
    .table-wrap { overflow-x: auto; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
    .audit-table, .indicator-table { width: 100%; border-collapse: collapse; font-size: .94rem; background: #fff; }
    .audit-table th, .audit-table td, .indicator-table th, .indicator-table td { border-bottom: 1px solid var(--line); padding: 12px 10px; text-align: left; vertical-align: top; }
    .audit-table th, .indicator-table th { background: #f7f3ec; font-size: .8rem; letter-spacing: .04em; text-transform: uppercase; }
    .appendix-indicator-grid { display: grid; gap: 14px; margin-top: 18px; }
    .appendix-indicator { border: 1px solid var(--line); border-radius: 12px; background: #fff; padding: 14px 16px; }
    .appendix-indicator-name { font-size: 1.02rem; font-weight: 700; color: var(--accent); margin-bottom: 6px; }
    .appendix-indicator-formula { font-family: "Times New Roman", serif; font-size: .95rem; margin-bottom: 8px; }
    .appendix-indicator-inputs ul, .appendix-indicator-notes ul { margin: 6px 0 0; padding-left: 18px; }
    .appendix-indicator-inputs li, .appendix-indicator-notes li { margin-bottom: 4px; }
    .appendix-indicator-sources { color: var(--muted); margin-top: 8px; font-size: .86rem; }
    .appendix-gap-note { margin-top: 14px; border: 1px dashed var(--line); border-radius: 10px; padding: 12px 14px; background: #fbfaf7; }
    .appendix-gap-title { color: var(--accent); font-weight: 700; margin-bottom: 6px; text-transform: uppercase; letter-spacing: .04em; font-size: .82rem; }
    .reference-list { margin: 0; padding-left: 0; list-style: none; }
    .reference-list li { margin-bottom: 10px; color: var(--muted); }
    .cite-ref { position: relative; display: inline-block; margin: 0 2px; color: var(--accent); font-weight: 700; cursor: help; }
    .cite-tooltip { display: none; position: absolute; left: 0; top: calc(100% + 10px); width: min(360px, 88vw); background: #142237; color: #f8fbff; border-radius: 14px; padding: 10px 12px; box-shadow: 0 18px 36px rgba(8, 15, 31, 0.24); z-index: 30; font-weight: 400; }
    .cite-ref:hover .cite-tooltip { display: block; }
    .cite-tooltip-title { display: block; font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; color: #c7d4e6; margin-bottom: 6px; }
    .cite-tooltip-body { display: block; font-size: .88rem; line-height: 1.45; }
    .metric-hover-anchor { position: relative; display: inline-block; color: var(--accent); font-weight: 600; cursor: help; border-bottom: 1px dotted var(--accent); }
    .metric-tooltip { display: none; position: absolute; left: 0; top: calc(100% + 10px); width: 340px; background: #142237; color: #f8fbff; border-radius: 12px; padding: 12px 14px; box-shadow: 0 18px 36px rgba(8, 15, 31, 0.24); z-index: 30; font-weight: 400; text-align: left; }
    .metric-hover-anchor:hover .metric-tooltip { display: block; }
    .metric-tooltip-section { display: block; margin-bottom: 8px; }
    .metric-tooltip-section:last-child { margin-bottom: 0; }
    .metric-tooltip-section > strong { display: block; font-size: 0.8rem; text-transform: uppercase; color: #c7d4e6; margin-bottom: 4px; }
    .metric-formula { display: block; font-family: "Times New Roman", serif; font-size: 0.95rem; margin-bottom: 4px; }
    .metric-subtle { display: block; font-size: 0.8rem; color: #a3b8cc; margin-top: 2px; }
    .metric-gap { margin: 6px 0 0; color: #fecaca; font-size: 0.8rem; }
    .metric-tooltip ul { margin: 4px 0 0; padding-left: 16px; font-size: 0.8rem; color: #f8fbff; list-style-type: disc; }
    .metric-tooltip li { margin-bottom: 4px; }
    @media print {
      body { background: #fff; }
      .report-shell { width: 100%; padding: 0; }
      .report-page { box-shadow: none; border: 0; margin: 0; }
    }
        """

    def compile_report(self, bundle: IntroRenderBundle, output_filename: str | None = None) -> str:
        from src.rag_report.report_vnext.writer import build_fallback_intro_narrative

        self._citation_to_number = {}
        self._number_to_citation = {}

        contract = bundle.narrative.report_contract
        if contract is None:
            fallback_narrative = build_fallback_intro_narrative(bundle.evidence_pack, bundle.metric_pack, bundle.chart_plan)
            contract = fallback_narrative.report_contract
        if contract is None:
            contract = build_fallback_intro_narrative(bundle.evidence_pack, bundle.metric_pack, bundle.chart_plan).report_contract

        filename = output_filename or settings.VNEXT_REPORT_FILENAME
        output_path = self.output_dir / filename

        spec_by_id = {chart.chart_id: self._sanitize_spec(chart.spec) for chart in bundle.charts}
        main_items = [item for item in bundle.chart_plan.items if item.enabled and item.is_main_chart and item.chart_id in spec_by_id]
        appendix_items = [item for item in bundle.chart_plan.items if item.enabled and not item.is_main_chart and item.chart_id in spec_by_id]
        if not main_items:
            main_items = [item for item in bundle.chart_plan.items if item.enabled and item.chart_id in spec_by_id][:4]

        source_refs: list[str] = []
        for signal in getattr(contract, "key_signals", []):
            source_refs.extend(getattr(signal, "source_refs", []))
        for indicator in getattr(contract, "appendix_indicators", []):
            source_refs.extend(getattr(indicator, "source_refs", []))
        for item in bundle.chart_plan.items:
            spec = spec_by_id.get(item.chart_id)
            if spec is None:
                continue
            source_refs.extend(self._collect_chart_sources(spec))
        for ref in dict.fromkeys(ref for ref in source_refs if ref):
            self._register_citation(ref)

        pages: list[str] = []
        cover_title = bundle.narrative.title or f"{bundle.evidence_pack.company_id}: Báo cáo tài chính có đáng tin không?"
        pages.append(
            "<section class='report-page'>"
            f"<div class='section-kicker'>{self._escape(bundle.evidence_pack.company_id)}</div>"
            f"<h1 class='cover-title'>{self._escape(cover_title)}</h1>"
            f"<p class='cover-subtitle'>Báo cáo này được lập cho doanh nghiệp {self._escape(bundle.evidence_pack.company_id)} và được cấu trúc theo các phần: mở đầu, ý kiến kiểm toán, tín hiệu trọng yếu, biểu đồ chính, kết luận nhanh và phụ lục kỹ thuật.</p>"
            "<div class='page-footer'>Bản xuất HTML vNext</div>"
            "</section>"
        )
        pages.append(self._render_opening_page(bundle, contract))
        pages.append(self._render_audit_page(bundle))
        pages.append(self._render_signals_page(contract))
        pages.extend(self._render_chart_page_group(main_items, spec_by_id, "Biểu đồ chính", "Biểu đồ"))
        pages.append(self._render_closing_page(contract))
        pages.append(self._render_appendix_metric_page(bundle.metric_pack, contract, bundle.narrative.data_gaps))
        pages.extend(self._render_chart_page_group(appendix_items, spec_by_id, "Phụ lục biểu đồ", "Phụ lục"))

        references_html = self._render_references()
        css = self._build_css()
        html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{self._escape(cover_title)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Serif:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script>
    window.MathJax = {{
      tex: {{
        inlineMath: [['\\\\(', '\\\\)']],
        displayMath: [['$$', '$$']]
      }},
      svg: {{ fontCache: 'global' }}
    }};
  </script>
  <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
  <script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
  <script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
  <style>{css}</style>
</head>
<body>
  <main class="report-shell">
    {''.join(pages)}
    <section class="report-page">
      <div class="section-kicker">Tài liệu tham chiếu</div>
      <h2 class="section-title">Danh mục trích dẫn</h2>
      {references_html}
    </section>
  </main>
  <script>
    const embedOpts = {{ actions: false, renderer: 'svg' }};
    function safeEmbedChart(figureId, mountId, spec) {{
      const figure = document.getElementById(figureId);
      const mount = document.getElementById(mountId);
      if (!figure || !mount || !spec || !Object.keys(spec).length) {{
        if (figure) figure.remove();
        return;
      }}
      vegaEmbed(mount, spec, embedOpts).catch(() => {{
        if (figure) figure.remove();
      }});
    }}
    {"".join(f"safeEmbedChart('figure-{item.chart_id}', 'chart-{item.chart_id}', {json.dumps(spec_by_id[item.chart_id], ensure_ascii=False)});" for item in bundle.chart_plan.items if item.chart_id in spec_by_id)}
  </script>
</body>
</html>"""
        output_path.write_text(html_content, encoding="utf-8")
        return str(output_path)
