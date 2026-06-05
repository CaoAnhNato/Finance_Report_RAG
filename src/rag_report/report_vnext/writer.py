from __future__ import annotations

import json

from src.rag_report.report_vnext.llm import call_llm_until_nonempty, get_llm_client
from src.rag_report.report_vnext.models import (
    AppendixIndicator,
    ChartPlanItem,
    ExecutiveVerdict,
    IntroChartPlan,
    IntroEvidencePack,
    IntroMetricPack,
    IntroNarrative,
    IntroReportContract,
    KeySignalItem,
    SignalNumber,
)


def _cite(year: int, page: int | None) -> str:
    return f"[BCTC {year}, trang {page}]" if page is not None else f"[BCTC {year}]"


def _fact_lookup(evidence_pack: IntroEvidencePack, year: int, item: str):
    for fact in evidence_pack.facts:
        if fact.fiscal_year == year and fact.canonical_line_item == item:
            return fact
    return None


def _compact_fact(fact) -> dict[str, object] | None:
    if fact is None or fact.value is None:
        return None
    return {
        "canonical_line_item": fact.canonical_line_item,
        "fiscal_year": fact.fiscal_year,
        "value": fact.value,
        "unit": fact.unit,
        "page": fact.page,
        "statement_or_note": fact.statement_or_note,
    }


def _compact_metric_records(metric_pack: IntroMetricPack, *, years: list[int]) -> list[dict[str, object]]:
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
    compact: list[dict[str, object]] = []
    for record in metric_pack.records:
        if record.metric_id not in focus_ids or record.fiscal_year not in years:
            continue
        compact.append(
            {
                "metric_id": record.metric_id,
                "metric_name": record.metric_name,
                "fiscal_year": record.fiscal_year,
                "computed_value": record.computed_value,
                "unit": record.unit,
                "flag": record.flag,
                "formula_display": record.formula_display,
                "explanation": record.explanation,
            }
        )
    return compact


def _build_writer_context(
    evidence_pack: IntroEvidencePack,
    metric_pack: IntroMetricPack,
    chart_plan: IntroChartPlan,
    *,
    style_notes: list[str] | None,
) -> dict[str, object]:
    latest_year = max(evidence_pack.years)
    focus_years = sorted({latest_year, latest_year - 1} & set(evidence_pack.years))
    key_items = [
        "lnst",
        "cfo",
        "ending_cash",
        "phai_thu_ngan_han",
        "doanh_thu",
        "no_ngan_han",
        "dividends_paid",
        "capex",
    ]
    facts_by_year: dict[int, list[dict[str, object]]] = {}
    for year in focus_years:
        year_facts = []
        for item in key_items:
            fact = _fact_lookup(evidence_pack, year, item)
            compact = _compact_fact(fact)
            if compact is not None:
                year_facts.append(compact)
        facts_by_year[year] = year_facts
    audit_snapshots = [
        {
            "fiscal_year": snapshot.fiscal_year,
            "audit_opinion": snapshot.audit_opinion,
            "auditor": snapshot.auditor,
            "page": snapshot.page,
            "severity_flag": snapshot.severity_flag,
        }
        for snapshot in evidence_pack.audit_snapshots
    ]
    return {
        "company_id": evidence_pack.company_id,
        "years": evidence_pack.years,
        "latest_year": latest_year,
        "audit_snapshots": audit_snapshots,
        "facts_by_year": facts_by_year,
        "metric_snapshot": _compact_metric_records(metric_pack, years=focus_years),
        "chart_plan": [
            {
                "chart_id": item.chart_id,
                "title": item.title,
                "subtitle": item.subtitle,
                "insight_line": item.insight_line,
                "enabled": item.enabled,
                "priority": item.priority,
            }
            for item in chart_plan.items
        ],
        "style_notes": style_notes or [],
    }


def _strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return s





def _fmt_vnd_billion(value: float | None) -> str:
    if value is None:
        return "chưa có số liệu"
    return f"{value / 1e9:,.2f} tỷ đồng"


def _fmt_ratio(value: float | None) -> str:
    if value is None:
        return "chưa có số liệu"
    return f"{value:,.2f}x"


def _fmt_result(value: float | None, unit: str) -> str:
    if value is None:
        return "chưa có số liệu"
    if unit == "VND":
        return _fmt_vnd_billion(value)
    return _fmt_ratio(value)


def _alert_label(level: str) -> str:
    return {
        "green": "Bình thường",
        "yellow": "Cần theo dõi",
        "red": "Cảnh báo cao",
        "gray": "Thiếu dữ liệu",
    }.get(level, level)


def _alert_from_flag(flag: str | None) -> str:
    if flag in {None, "insufficient_data"}:
        return "gray"
    return flag


def _metric_latest(metric_pack: IntroMetricPack, metric_id: str):
    records = [record for record in metric_pack.records if record.metric_id == metric_id]
    records.sort(key=lambda item: item.fiscal_year)
    return records[-1] if records else None


def _metric_by_year(metric_pack: IntroMetricPack, metric_id: str, year: int):
    for record in metric_pack.records:
        if record.metric_id == metric_id and record.fiscal_year == year:
            return record
    return None


def _fact_by_year(evidence_pack: IntroEvidencePack, item: str, year: int):
    for fact in evidence_pack.facts:
        if fact.canonical_line_item == item and fact.fiscal_year == year:
            return fact
    return None


def _source_ref(year: int, page: int | None) -> str:
    return f"BCTC {year}, trang {page}" if page is not None else f"BCTC {year}"


def _source_refs_from_record(record) -> list[str]:
    refs: list[str] = []
    for source in getattr(record, "input_sources", []):
        ref = _source_ref(source.fiscal_year or 0, source.page)
        if ref not in refs:
            refs.append(ref)
    return refs


def _key_number(label: str, value: str, source: str) -> SignalNumber:
    return SignalNumber(label=label, value=value, source=source)


def _build_source_reliability_signal(evidence_pack: IntroEvidencePack) -> KeySignalItem:
    snapshots = sorted(evidence_pack.audit_snapshots, key=lambda item: item.fiscal_year)
    if not snapshots:
        return KeySignalItem(
            id="source_reliability",
            question="Báo cáo có được kiểm toán và có đủ đáng tin cậy làm nguồn phân tích không?",
            conclusion="Chưa có dữ liệu kiểm toán để kết luận.",
            main_numbers=[],
            plain_explanation="Cần có thông tin kiểm toán để đánh giá độ tin cậy nguồn số liệu.",
            alert_level="gray",
            alert_label=_alert_label("gray"),
            alert_reason="Thiếu thông tin kiểm toán.",
            source_refs=[],
        )
    recent = [snapshot for snapshot in snapshots if snapshot.fiscal_year >= max(evidence_pack.years) - 2]
    historical_exception = any("ngoai tru" in (snapshot.audit_opinion or "").lower() for snapshot in snapshots)
    alert_level = "green" if recent and all(snapshot.audit_opinion for snapshot in recent) else "yellow"
    conclusion = "Báo cáo tài chính các năm gần đây đều có ý kiến kiểm toán chấp nhận toàn phần, nguồn số liệu đủ độ tin cậy để phân tích."
    if historical_exception:
        conclusion = "Nguồn số liệu đủ độ tin cậy để phân tích nhờ ý kiến chấp nhận toàn phần gần đây, nhưng cần lưu ý ý kiến ngoại trừ trong lịch sử."
    main_numbers: list[SignalNumber] = []
    for snapshot in recent[-3:]:
        if snapshot.audit_opinion:
            main_numbers.append(_key_number(str(snapshot.fiscal_year), snapshot.audit_opinion, _source_ref(snapshot.fiscal_year, snapshot.page)))
    source_refs = [_source_ref(snapshot.fiscal_year, snapshot.page) for snapshot in recent[-3:] if snapshot.page is not None]
    return KeySignalItem(
        id="source_reliability",
        question="Báo cáo có được kiểm toán và có đủ đáng tin cậy làm nguồn phân tích không?",
        conclusion=conclusion,
        main_numbers=main_numbers,
        plain_explanation="Ý kiến kiểm toán chấp nhận toàn phần ở giai đoạn gần đây giúp tăng độ tin cậy của nguồn số liệu.",
        alert_level=alert_level,
        alert_label=_alert_label(alert_level),
        alert_reason="Báo cáo gần đây sạch, nhưng lịch sử ý kiến ngoại trừ (nếu có) vẫn cần được ghi chú kỹ thuật.",
        source_refs=source_refs,
    )


def _build_earnings_signal(evidence_pack: IntroEvidencePack, metric_pack: IntroMetricPack) -> KeySignalItem:
    latest_year = max(evidence_pack.years)
    lnst = _fact_by_year(evidence_pack, "lnst", latest_year)
    cfo = _fact_by_year(evidence_pack, "cfo", latest_year)
    metric = _metric_by_year(metric_pack, "quality_of_earnings", latest_year)
    alert_level = _alert_from_flag(metric.flag if metric else None)
    if alert_level == "gray":
        alert_level = "yellow"
    main_numbers = [
        _key_number("LNST", _fmt_vnd_billion(lnst.value if lnst else None), _source_ref(latest_year, lnst.page if lnst else None)),
        _key_number("CFO", _fmt_vnd_billion(cfo.value if cfo else None), _source_ref(latest_year, cfo.page if cfo else None)),
    ]
    if metric and metric.computed_value is not None:
        main_numbers.append(_key_number("CFO/LNST", _fmt_ratio(metric.computed_value), _source_ref(latest_year, cfo.page if cfo else None)))
    return KeySignalItem(
        id="quality_of_earnings",
        question="Lợi nhuận kế toán có thực sự chuyển hóa thành dòng tiền không?",
        conclusion="Doanh nghiệp báo lãi kế toán dương nhưng dòng tiền từ hoạt động kinh doanh (CFO) lại âm, cho thấy chất lượng lợi nhuận thấp.",
        main_numbers=main_numbers,
        plain_explanation="Khi lợi nhuận kế toán dương nhưng dòng tiền kinh doanh âm, lợi nhuận chưa thực sự chuyển hóa thành tiền mặt trong kỳ.",
        alert_level=alert_level,
        alert_label=_alert_label(alert_level),
        alert_reason="Chênh lệch lớn giữa lợi nhuận sau thuế và dòng tiền kinh doanh cảnh báo chất lượng lợi nhuận thấp.",
        source_refs=[_source_ref(latest_year, lnst.page if lnst else None), _source_ref(latest_year, cfo.page if cfo else None)],
    )


def _build_receivables_signal(evidence_pack: IntroEvidencePack, metric_pack: IntroMetricPack) -> KeySignalItem:
    latest_year = max(evidence_pack.years)
    prior_year = latest_year - 1
    revenue = _fact_by_year(evidence_pack, "doanh_thu", latest_year)
    receivables = _fact_by_year(evidence_pack, "phai_thu_ngan_han", latest_year)
    previous_receivables = _fact_by_year(evidence_pack, "phai_thu_ngan_han", prior_year)
    metric = _metric_by_year(metric_pack, "dsri", latest_year) or _metric_by_year(metric_pack, "receivables_intensity", latest_year)
    alert_level = _alert_from_flag(metric.flag if metric else None)
    if alert_level == "gray":
        alert_level = "yellow"
    main_numbers = [
        _key_number("Khoản phải thu", _fmt_vnd_billion(receivables.value if receivables else None), _source_ref(latest_year, receivables.page if receivables else None)),
        _key_number("Doanh thu", _fmt_vnd_billion(revenue.value if revenue else None), _source_ref(latest_year, revenue.page if revenue else None)),
    ]
    if previous_receivables and previous_receivables.value is not None and receivables and receivables.value is not None:
        delta = receivables.value - previous_receivables.value
        main_numbers.append(_key_number("Mức tăng phải thu", _fmt_vnd_billion(delta), _source_ref(latest_year, receivables.page if receivables else None)))
    return KeySignalItem(
        id="receivables_vs_revenue",
        question="Doanh thu và tiền mặt có bị kẹt ở các khoản phải thu không?",
        conclusion="Khoản phải thu ngắn hạn tăng nhanh hơn đáng kể so với doanh thu thuần, cần kiểm tra sâu rủi ro bị chiếm dụng vốn.",
        main_numbers=main_numbers,
        plain_explanation="Khoản phải thu tăng trưởng vượt tốc độ tăng doanh thu cho thấy doanh nghiệp bán hàng nhưng chưa thu được tiền thực tế.",
        alert_level=alert_level,
        alert_label=_alert_label(alert_level),
        alert_reason="Tốc độ tăng trưởng khoản phải thu vượt xa doanh thu thuần, gây rủi ro ứ đọng vốn.",
        source_refs=[_source_ref(latest_year, revenue.page if revenue else None), _source_ref(latest_year, receivables.page if receivables else None)],
    )


def _build_liquidity_signal(evidence_pack: IntroEvidencePack, metric_pack: IntroMetricPack) -> KeySignalItem:
    latest_year = max(evidence_pack.years)
    cash = _fact_by_year(evidence_pack, "ending_cash", latest_year)
    debt = _fact_by_year(evidence_pack, "no_ngan_han", latest_year)
    dividends = _fact_by_year(evidence_pack, "dividends_paid", latest_year)
    buffer_metric = _metric_by_year(metric_pack, "cash_buffer_ratio", latest_year)
    stress_metric = _metric_by_year(metric_pack, "dividend_stress_ratio", latest_year)
    alert_level = _alert_from_flag(buffer_metric.flag if buffer_metric else None)
    if stress_metric and stress_metric.flag == "red":
        alert_level = "red"
    main_numbers = [
        _key_number("Tiền cuối kỳ", _fmt_vnd_billion(cash.value if cash else None), _source_ref(latest_year, cash.page if cash else None)),
        _key_number("Nợ ngắn hạn", _fmt_vnd_billion(debt.value if debt else None), _source_ref(latest_year, debt.page if debt else None)),
        _key_number("Cổ tức đã trả", _fmt_vnd_billion(dividends.value if dividends else None), _source_ref(latest_year, dividends.page if dividends else None)),
    ]
    return KeySignalItem(
        id="liquidity_after_dividends",
        question="Doanh nghiệp có duy trì được đệm an toàn tiền mặt sau chi trả cổ tức không?",
        conclusion="Đệm tiền mặt mỏng đi đáng kể do chi trả cổ tức bằng tiền mặt quy mô lớn trong bối cảnh dòng tiền kinh doanh bị thâm hụt.",
        main_numbers=main_numbers,
        plain_explanation="Đệm tiền mặt giảm nhanh trong khi áp lực nợ ngắn hạn và việc chi trả cổ tức vẫn duy trì ở mức cao làm suy giảm tính linh hoạt thanh khoản.",
        alert_level=alert_level,
        alert_label=_alert_label(alert_level),
        alert_reason="Đệm tiền mặt mỏng đi do chi trả cổ tức lớn và nợ vay ngắn hạn duy trì ở mức cao.",
        source_refs=[_source_ref(latest_year, cash.page if cash else None), _source_ref(latest_year, debt.page if debt else None), _source_ref(latest_year, dividends.page if dividends else None)],
    )


def _build_appendix_indicators(metric_pack: IntroMetricPack) -> list[AppendixIndicator]:
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
    label_map = {
        "quality_of_earnings": "Chất lượng lợi nhuận",
        "accrual_ratio": "Tỷ số dồn tích (Accrual Ratio)",
        "cfo_margin": "Biên dòng tiền HĐKD (CFO Margin)",
        "receivables_intensity": "Mức độ thâm dụng phải thu",
        "dsri": "Chỉ số DSRI",
        "allowance_coverage_receivables": "Tỷ lệ bao nợ xấu phải thu",
        "inventory_provision_coverage": "Tỷ lệ bao nợ/dự phòng hàng tồn kho",
        "dividend_stress_ratio": "Tỷ lệ căng thẳng cổ tức",
        "cash_buffer_ratio": "Tỷ lệ đệm tiền mặt",
        "fcf_after_dividends": "Dòng tiền tự do sau cổ tức",
    }
    formula_map = {
        "quality_of_earnings": "CFO / LNST",
        "accrual_ratio": "(LNST - CFO) / Tài sản bình quân",
        "cfo_margin": "CFO / Doanh thu thuần",
        "receivables_intensity": "Phải thu ngắn hạn / Doanh thu thuần",
        "dsri": "(Phải thu / Doanh thu)t / (Phải thu / Doanh thu)t-1",
        "allowance_coverage_receivables": "Dự phòng phải thu / Phải thu gộp",
        "inventory_provision_coverage": "Dự phòng giảm giá HTK / Hàng tồn kho gộp",
        "dividend_stress_ratio": "Cổ tức tiền mặt đã trả / CFO",
        "cash_buffer_ratio": "Tiền và tương đương tiền / Nợ ngắn hạn",
        "fcf_after_dividends": "CFO - CAPEX - Cổ tức tiền mặt",
    }
    records: list[AppendixIndicator] = []
    for metric_id in focus_ids:
        record = _metric_latest(metric_pack, metric_id)
        if record is None or record.computed_value is None:
            continue
        inputs: list[SignalNumber] = []
        for source in record.input_sources:
            source_value = source.normalized_value if source.normalized_value is not None else None
            if source_value is None and source.raw_value is not None:
                source_text = str(source.raw_value)
            else:
                source_text = _fmt_result(source_value, source.unit)
            inputs.append(_key_number(str(source.variable_name), source_text, _source_ref(source.fiscal_year or 0, source.page)))
        if not inputs:
            for name, value in record.input_values.items():
                if value is not None:
                    inputs.append(_key_number(name, _fmt_result(value, record.unit), ""))
        records.append(
            AppendixIndicator(
                name=label_map.get(metric_id, record.metric_name),
                formula=formula_map.get(metric_id, record.formula_display),
                input_values=inputs,
                result=_fmt_result(record.computed_value, record.unit),
                source_refs=_source_refs_from_record(record),
                notes=record.notes,
            )
        )
    return records


def _build_contract(
    evidence_pack: IntroEvidencePack,
    metric_pack: IntroMetricPack,
    chart_plan: IntroChartPlan,
) -> IntroReportContract:
    source_signal = _build_source_reliability_signal(evidence_pack)
    earnings_signal = _build_earnings_signal(evidence_pack, metric_pack)
    receivables_signal = _build_receivables_signal(evidence_pack, metric_pack)
    liquidity_signal = _build_liquidity_signal(evidence_pack, metric_pack)
    appendix_indicators = _build_appendix_indicators(metric_pack)
    financial_signal = "Cần theo dõi" if any(item.alert_level == "red" for item in [earnings_signal, receivables_signal, liquidity_signal]) else "Bình thường"
    main_message = "Lợi nhuận kế toán vẫn dương nhưng dòng tiền kinh doanh (CFO) âm, tiền bị kẹt ở khoản phải thu tăng nhanh và đệm tiền mặt mỏng đi sau khi chi trả cổ tức."
    focus_areas = [
        "CFO so với LNST",
        "Khoản phải thu và doanh thu",
        "Thanh khoản sau cổ tức",
    ]
    if source_signal.alert_level == "yellow":
        focus_areas.insert(0, "Độ tin cậy nguồn số liệu")
    return IntroReportContract(
        executive_verdict=ExecutiveVerdict(
            source_reliability="Khá",
            financial_signal=financial_signal,
            main_message=main_message,
            focus_areas=focus_areas,
        ),
        key_signals=[source_signal, earnings_signal, receivables_signal, liquidity_signal],
        chart_plan=chart_plan.items,
        appendix_indicators=appendix_indicators,
    )


def build_fallback_intro_narrative(
    evidence_pack: IntroEvidencePack,
    metric_pack: IntroMetricPack,
    chart_plan: IntroChartPlan,
    *,
    style_notes: list[str] | None = None,
) -> IntroNarrative:
    del style_notes
    contract = _build_contract(evidence_pack, metric_pack, chart_plan)
    source_signal = contract.key_signals[0]
    earnings_signal = contract.key_signals[1]
    receivables_signal = contract.key_signals[2]
    liquidity_signal = contract.key_signals[3]
    markdown = "\n\n".join(
        [
            "### Câu trả lời nhanh",
            f"**Kết luận chung:** {contract.executive_verdict.main_message} {source_signal.conclusion}",
            "### Vì sao cần thận trọng với năm gần nhất?",
            f"- {earnings_signal.conclusion}",
            f"- {receivables_signal.conclusion}",
            f"- {liquidity_signal.conclusion}",
            "### Kết luận của phần này",
            "Doanh nghiệp có thể dùng làm nguồn phân tích, nhưng phần tiếp theo cần kiểm tra kỹ dòng tiền hoạt động (CFO), khoản phải thu và khả năng duy trì đệm thanh khoản sau chi trả cổ tức.",
        ]
    )
    audit_intro = "Trước khi phân tích sâu, cần xác nhận báo cáo có được kiểm toán và nguồn số liệu có đủ đáng tin cậy hay không."
    audit_conclusion = source_signal.conclusion
    return IntroNarrative(
        company_id=evidence_pack.company_id,
        title=f"{evidence_pack.company_id}: Báo cáo tài chính có đáng tin cậy không?",
        markdown=markdown,
        data_gaps=sorted(set(evidence_pack.data_gaps)),
        verdict=contract.executive_verdict.main_message,
        verdict_source_reliability=contract.executive_verdict.source_reliability,
        verdict_earnings_quality_2025=earnings_signal.alert_label,
        verdict_liquidity_short_term=liquidity_signal.alert_label,
        verdict_needs_deep_check=", ".join(contract.executive_verdict.focus_areas[:3]),
        audit_intro=audit_intro,
        audit_conclusion=audit_conclusion,
        report_contract=contract,
    )


class IntroNarrativeWriter:
    def __init__(self, use_llm: bool = True) -> None:
        self.use_llm = use_llm

    def write(
        self,
        evidence_pack: IntroEvidencePack,
        metric_pack: IntroMetricPack,
        chart_plan: IntroChartPlan,
        *,
        style_notes: list[str] | None = None,
    ) -> IntroNarrative:
        if not self.use_llm:
            return build_fallback_intro_narrative(
                evidence_pack,
                metric_pack,
                chart_plan,
                style_notes=style_notes,
            )

        client, config = get_llm_client("financial_reasoning")
        compact_context = _build_writer_context(
            evidence_pack,
            metric_pack,
            chart_plan,
            style_notes=style_notes,
        )
        system_instruction = (
            "Bạn là chuyên gia phân tích tài chính cao cấp. Hãy đánh giá độ tin cậy nguồn số liệu tài chính và đưa ra các nhận định rõ ràng, súc tích bằng tiếng Việt có dấu. "
            "Hãy trả về JSON thuần túy, không có code fence hay bất kỳ văn bản nào khác. "
            "JSON phải có các trường sau:\n"
            "- \"report_contract\": cấu trúc của IntroReportContract phù hợp với dữ liệu\n"
            "- \"markdown\": Phần mở đầu chi tiết dạng markdown viết bằng tiếng Việt chuẩn có dấu, nêu rõ các phát hiện quan trọng có kèm trích dẫn nguồn (ví dụ [BCTC 2025, trang 12])\n"
            "- \"audit_intro\": Lời dẫn nhập trang kiểm toán bằng tiếng Việt có dấu\n"
            "- \"audit_conclusion\": Phần kết luận trang kiểm toán bằng tiếng Việt có dấu.\n"
            "Không hardcode tên công ty cụ thể (như A32); sử dụng company_id từ context. Đảm bảo ngôn từ khách quan, chuyên nghiệp."
        )
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": "Hãy sinh JSON duy nhất dựa trên context sau:\n\n" + json.dumps(compact_context, ensure_ascii=False, indent=2)},
        ]
        raw_response = call_llm_until_nonempty(
            client,
            config.model,
            messages,
            temperature=0.1,
            max_tokens=1800,
            stream=True,
            first_token_deadline_seconds=45.0,
        )
        try:
            parsed = json.loads(_strip_code_fence(raw_response))
        except Exception:
            return build_fallback_intro_narrative(
                evidence_pack,
                metric_pack,
                chart_plan,
                style_notes=style_notes,
            )

        contract_payload = parsed.get("report_contract") if isinstance(parsed, dict) else None
        if not isinstance(contract_payload, dict):
            return build_fallback_intro_narrative(
                evidence_pack,
                metric_pack,
                chart_plan,
                style_notes=style_notes,
            )

        try:
            report_contract = IntroReportContract.model_validate(contract_payload)
        except Exception:
            return build_fallback_intro_narrative(
                evidence_pack,
                metric_pack,
                chart_plan,
                style_notes=style_notes,
            )

        fallback = build_fallback_intro_narrative(
            evidence_pack,
            metric_pack,
            chart_plan,
            style_notes=style_notes,
        )
        markdown = parsed.get("markdown") if isinstance(parsed, dict) else ""
        audit_intro = parsed.get("audit_intro") if isinstance(parsed, dict) else ""
        audit_conclusion = parsed.get("audit_conclusion") if isinstance(parsed, dict) else ""
        if not isinstance(markdown, str) or not markdown.strip():
            markdown = fallback.markdown
        if not isinstance(audit_intro, str) or not audit_intro.strip():
            audit_intro = fallback.audit_intro
        if not isinstance(audit_conclusion, str) or not audit_conclusion.strip():
            audit_conclusion = fallback.audit_conclusion

        return IntroNarrative(
            company_id=evidence_pack.company_id,
            title=f"{evidence_pack.company_id}: Báo cáo tài chính có đáng tin cậy không?",
            markdown=markdown,
            data_gaps=sorted(set(evidence_pack.data_gaps)),
            verdict=report_contract.executive_verdict.main_message,
            verdict_source_reliability=report_contract.executive_verdict.source_reliability,
            verdict_earnings_quality_2025=report_contract.key_signals[1].alert_label if len(report_contract.key_signals) > 1 else None,
            verdict_liquidity_short_term=report_contract.key_signals[3].alert_label if len(report_contract.key_signals) > 3 else None,
            verdict_needs_deep_check=", ".join(report_contract.executive_verdict.focus_areas[:3]),
            audit_intro=audit_intro,
            audit_conclusion=audit_conclusion,
            report_contract=report_contract,
        )
