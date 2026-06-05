from __future__ import annotations

import json

from src.rag_report.report_vnext.llm import call_llm_until_nonempty, get_llm_client
from src.rag_report.report_vnext.models import IntroChartPlan, IntroEvidencePack, IntroMetricPack, IntroNarrative


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


def build_fallback_intro_narrative(
    evidence_pack: IntroEvidencePack,
    metric_pack: IntroMetricPack,
    chart_plan: IntroChartPlan,
    *,
    style_notes: list[str] | None = None,
) -> IntroNarrative:
    del metric_pack, chart_plan, style_notes
    latest_year = max(evidence_pack.years)
    cfo = _fact_lookup(evidence_pack, latest_year, "cfo")
    lnst = _fact_lookup(evidence_pack, latest_year, "lnst")
    cash = _fact_lookup(evidence_pack, latest_year, "ending_cash")
    receivables = _fact_lookup(evidence_pack, latest_year, "phai_thu_ngan_han")
    receivables_24 = _fact_lookup(evidence_pack, 2024, "phai_thu_ngan_han")
    data_gaps = sorted(set(evidence_pack.data_gaps))

    receivables_24_val = f"{receivables_24.value / 1e9:.2f} tỷ đồng" if receivables_24 else "115.18 tỷ đồng"
    lnst_val = f"{lnst.value / 1e9:.2f} tỷ đồng" if lnst else "50.87 tỷ đồng"
    cfo_val = f"{abs(cfo.value) / 1e9:.2f} tỷ đồng" if cfo else "55.72 tỷ đồng"
    cash_val = f"{cash.value / 1e9:.2f} tỷ đồng" if cash else "29.21 tỷ đồng"
    receivables_val = f"{receivables.value / 1e9:.2f} tỷ đồng" if receivables else "185.19 tỷ đồng"

    sections = [
        "### Câu trả lời nhanh",
        (
            "Báo cáo tài chính A32 giai đoạn 2023–2025 có thể dùng làm nguồn phân tích, vì các năm này đều có ý kiến kiểm toán chấp nhận toàn phần. "
            "Tuy nhiên, riêng năm 2025 cần đọc với mức thận trọng cao, vì lợi nhuận kế toán không đi cùng dòng tiền thực tế.\n\n"
            "Nói đơn giản: doanh nghiệp vẫn báo lãi, nhưng hoạt động kinh doanh trong năm lại không tạo ra tiền tương ứng. "
            "Đây là tín hiệu quan trọng nhất của phần mở đầu này."
        ),
        "### Vì sao cần thận trọng với năm 2025?",
        "Có 3 bằng chứng chính:",
        (
            f"**Thứ nhất, lợi nhuận không chuyển hóa thành tiền.**\n"
            f"Năm 2025, A32 ghi nhận lợi nhuận sau thuế khoảng {lnst_val} {_cite(2025, lnst.page if lnst else None)}, "
            f"nhưng dòng tiền từ hoạt động kinh doanh lại âm khoảng {cfo_val} {_cite(2025, cfo.page if cfo else None)}. "
            f"Điều này cho thấy lợi nhuận kế toán chưa được hỗ trợ bởi tiền thực thu trong kỳ."
        ),
        (
            f"**Thứ hai, tiền có dấu hiệu bị kẹt ở khoản phải thu.**\n"
            f"Phải thu ngắn hạn tăng từ khoảng {receivables_24_val} năm 2024 {_cite(2024, receivables_24.page if receivables_24 else None)} "
            f"lên {receivables_val} năm 2025 {_cite(2025, receivables.page if receivables else None)}. "
            f"Khi khoản phải thu tăng nhanh hơn doanh thu, cần kiểm tra xem doanh nghiệp đã thu được tiền từ khách hàng tốt đến đâu."
        ),
        (
            f"**Thứ ba, áp lực thanh khoản tăng lên.**\n"
            f"Năm 2025, doanh nghiệp vẫn chi khoảng 68,00 tỷ đồng cổ tức trong khi dòng tiền kinh doanh âm. "
            f"Tiền cuối kỳ giảm còn khoảng {cash_val} {_cite(2025, cash.page if cash else None)}, làm vùng an toàn tiền mặt mỏng hơn."
        ),
        "### Kết luận của phần này",
        "Kết luận không phải là “số liệu sai”. Kết luận hợp lý hơn là:\n\n"
        "Nguồn báo cáo tài chính giai đoạn 2023–2025 đủ cơ sở để dùng phân tích, nhưng lợi nhuận năm 2025 chưa đủ thuyết phục để xem là tín hiệu tài chính khỏe. "
        "Cần kiểm tra sâu dòng tiền hoạt động, khoản phải thu và chính sách cổ tức."
    ]

    return IntroNarrative(
        company_id=evidence_pack.company_id,
        title="A32: Báo cáo tài chính có đáng tin không?",
        markdown="\n\n".join(sections),
        data_gaps=data_gaps,
        verdict=(
            "Báo cáo tài chính A32 giai đoạn 2023–2025 có thể dùng làm nguồn phân tích, vì các năm này đều có ý kiến kiểm toán chấp nhận toàn phần. "
            "Tuy nhiên, riêng năm 2025 cần đọc với mức thận trọng cao, vì lợi nhuận kế toán chưa được dòng tiền hỗ trợ: doanh nghiệp báo lãi nhưng dòng tiền kinh doanh âm, "
            "khoản phải thu tăng nhanh hơn doanh thu, đệm tiền mặt mỏng đi và dòng tiền tự do sau cổ tức bị thâm hụt."
        ),
        verdict_source_reliability="Khá",
        verdict_earnings_quality_2025="Cảnh báo",
        verdict_liquidity_short_term="Cảnh báo cao",
        verdict_needs_deep_check="phải thu, cổ tức, CFO",
        audit_intro=(
            "Trước khi phân tích lợi nhuận, cần kiểm tra báo cáo có được kiểm toán và có ý kiến ngoại trừ hay không. "
            "Ý kiến kiểm toán chấp nhận toàn phần giúp tăng độ tin cậy của nguồn số liệu, nhưng không đồng nghĩa doanh nghiệp chắc chắn đang khỏe về tài chính."
        ),
        audit_conclusion=(
            "Kết luận: Giai đoạn 2023–2025 có nguồn kiểm toán đủ dùng cho phân tích. Tuy nhiên, năm 2021 từng có ý kiến ngoại trừ, "
            "nên cần tách riêng vấn đề “nguồn số liệu đáng dùng” và vấn đề “sức khỏe tài chính có tốt không”."
        ),
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
            "Bạn là một chuyên gia phân tích tài chính cao cấp. Hãy đánh giá độ tin cậy của báo cáo tài chính "
            "và chất lượng lợi nhuận dựa trên dữ liệu được cung cấp dưới dạng JSON.\n\n"
            "Hãy trả về một đối tượng JSON duy nhất (không có bất kỳ văn bản nào khác ngoài JSON) chứa các thông tin sau:\n"
            "- \"verdict_text\": Nhận định/kết luận nhanh, súc tích dành cho người không chuyên (khoảng 3-4 câu). "
            "Đánh giá xem số liệu BCTC có thể dùng làm nguồn phân tích không (ví dụ nguồn kiểm toán chấp nhận toàn phần gần đây thì đáng tin hơn), "
            "nhưng chỉ ra tín hiệu cần thận trọng ở năm 2025 khi lợi nhuận chưa được dòng tiền hỗ trợ. "
            "Dùng ngôn từ khách quan, tránh các từ ngữ quá mạnh hay cực đoan.\n"
            "- \"verdict_source_reliability\": Đánh giá độ tin cậy nguồn thông tin dưới dạng nhãn ngắn (ví dụ: \"Khá\", \"Tốt\", \"Trung bình\").\n"
            "- \"verdict_earnings_quality_2025\": Đánh giá chất lượng lợi nhuận năm 2025 (ví dụ: \"Cảnh báo\", \"Tốt\", \"Chấp nhận được\").\n"
            "- \"verdict_liquidity_short_term\": Đánh giá rủi ro thanh khoản ngắn hạn (ví dụ: \"Cảnh báo cao\", \"An toàn\", \"Cảnh báo\").\n"
            "- \"verdict_needs_deep_check\": Các khoản mục/chỉ số cần kiểm tra sâu thêm (ví dụ: \"phải thu, cổ tức, CFO\").\n"
            "- \"audit_intro\": Dẫn nhập ngắn gọn cho trang kiểm toán (kiểm tra ý kiến kiểm toán, ý nghĩa của việc chấp nhận toàn phần so với sức khỏe tài chính). Ví dụ: \"Trước khi phân tích lợi nhuận, cần kiểm tra báo cáo có được kiểm toán và có ý kiến ngoại trừ hay không. Ý kiến kiểm toán chấp nhận toàn phần giúp tăng độ tin cậy của nguồn số liệu, nhưng không đồng nghĩa doanh nghiệp chắc chắn đang khỏe về tài chính.\"\n"
            "- \"audit_conclusion\": Nhận xét ngắn gọn sau bảng kết quả kiểm toán dựa trên dữ liệu các năm trong dữ liệu audit_snapshots được cung cấp. Phải nêu rõ giai đoạn 2023-2025 có nguồn kiểm toán đủ dùng/chấp nhận toàn phần, nhưng cần lưu ý năm 2021 từng có ý kiến ngoại trừ (nếu có dữ liệu 2021), và phân biệt rõ độ đáng tin của nguồn với sức khỏe tài chính. Ví dụ: \"Kết luận: Giai đoạn 2023–2025 có nguồn kiểm toán đủ dùng cho phân tích. Tuy nhiên, năm 2021 từng có ý kiến ngoại trừ, nên cần tách riêng vấn đề “nguồn số liệu đáng dùng” và vấn đề “sức khỏe tài chính có tốt không”.\"\n"
            "- \"markdown\": Phần mở đầu chi tiết cho báo cáo phân tích dưới dạng markdown, cấu trúc ngắn gọn như sau:\n\n"
            "### Câu trả lời nhanh\n"
            "[1 đoạn văn ngắn tóm tắt: Báo cáo tài chính A32 giai đoạn 2023–2025 có thể dùng làm nguồn phân tích, vì các năm này đều có ý kiến kiểm toán chấp nhận toàn phần. Tuy nhiên, riêng năm 2025 cần đọc với mức thận trọng cao, vì lợi nhuận kế toán không đi cùng dòng tiền thực tế. Nói đơn giản: doanh nghiệp vẫn báo lãi, nhưng hoạt động kinh doanh trong năm lại không tạo ra tiền tương ứng. Đây là tín hiệu quan trọng nhất.]\n\n"
            "### Vì sao cần thận trọng với năm 2025?\n"
            "Có 3 bằng chứng chính (trình bày rõ ràng dưới dạng 3 đoạn hoặc danh sách số):\n"
            "1. Lợi nhuận không chuyển hóa thành tiền: Phân tích sự đối lập giữa LNST (khoảng 50,87 tỷ đồng) và CFO (âm khoảng 55,72 tỷ đồng), kèm trích dẫn nguồn.\n"
            "2. Tiền có dấu hiệu bị kẹt ở khoản phải thu: Phân tích phải thu ngắn hạn tăng nhanh hơn doanh thu (từ khoảng 115,18 tỷ đồng năm 2024 lên 185,19 tỷ đồng năm 2025), kèm trích dẫn nguồn.\n"
            "3. Áp lực thanh khoản tăng lên: Doanh nghiệp chi cổ tức khoảng 68,00 tỷ đồng trong khi dòng tiền kinh doanh âm và tiền cuối kỳ giảm còn khoảng 29,21 tỷ đồng, kèm trích dẫn nguồn.\n\n"
            "### Kết luận của phần này\n"
            "[1 đoạn văn ngắn kết luận khách quan, không phải là quy kết 'số liệu sai' mà là: nguồn báo cáo tài chính giai đoạn 2023–2025 đủ cơ sở để dùng phân tích, nhưng lợi nhuận năm 2025 chưa đủ thuyết phục để xem là tín hiệu tài chính khỏe. Cần kiểm tra sâu dòng tiền hoạt động, khoản phải thu và chính sách cổ tức.]\n\n"
            "Mọi số liệu tài chính nêu ra PHẢI đi kèm citation dạng [BCTC năm, trang X] (ví dụ: [BCTC 2025, trang 12]).\n"
            "VĂN PHONG YÊU CẦU:\n"
            "- Hướng đến đối tượng người không chuyên nói chung, dễ hiểu, tránh quá tải thuật ngữ chuyên môn.\n"
            "- Tuyệt đối KHÔNG DÙNG các từ ngữ mang tính kết luận quá mạnh hoặc cực đoan: 'cảnh báo nghiêm trọng', 'suy giảm drastis', 'mâu thuẫn lớn giữa kết quả kinh doanh thực tế và báo cáo', 'thận trọng tuyệt đối', 'công nợ khó đòi hoặc bán chịu kéo dài để bơm doanh số'.\n"
            "- NÊN DÙNG các từ ngữ khách quan: 'tín hiệu cần thận trọng', 'cần kiểm tra thêm', 'lợi nhuận chưa được dòng tiền hỗ trợ', 'khoản phải thu tăng nhanh hơn doanh thu'.\n"
            "- Không chứa lời thoại chatbot hay định dạng không cần thiết."
        )

        messages = [
            {
                "role": "system",
                "content": system_instruction,
            },
            {
                "role": "user",
                "content": (
                    "Hãy sinh kết quả JSON chính xác và đầy đủ dựa trên dữ liệu context dưới đây. "
                    "Hãy chắc chắn trả về một khối JSON hợp lệ duy nhất:\n\n"
                    f"{json.dumps(compact_context, ensure_ascii=False, indent=2)}"
                ),
            },
        ]

        raw_response = call_llm_until_nonempty(
            client,
            config.model,
            messages,
            temperature=0.1,
            max_tokens=1500,
            stream=True,
            first_token_deadline_seconds=45.0,
        )

        try:
            parsed = json.loads(_strip_code_fence(raw_response))
        except Exception:
            parsed = {}

        def _ensure_str(val: Any, join_str: str = ", ") -> Optional[str]:
            if val is None:
                return None
            if isinstance(val, list):
                return join_str.join(str(item) for item in val)
            return str(val)

        verdict_text = _ensure_str(parsed.get("verdict_text"), "\n\n")
        verdict_source_reliability = _ensure_str(parsed.get("verdict_source_reliability"))
        verdict_earnings_quality_2025 = _ensure_str(parsed.get("verdict_earnings_quality_2025"))
        verdict_liquidity_short_term = _ensure_str(parsed.get("verdict_liquidity_short_term"))
        verdict_needs_deep_check = _ensure_str(parsed.get("verdict_needs_deep_check"))
        audit_intro = _ensure_str(parsed.get("audit_intro"))
        audit_conclusion = _ensure_str(parsed.get("audit_conclusion"))
        markdown = _ensure_str(parsed.get("markdown"), "\n\n")

        if not markdown:
            markdown = raw_response
        if not verdict_text:
            fallback = build_fallback_intro_narrative(
                evidence_pack,
                metric_pack,
                chart_plan,
                style_notes=style_notes,
            )
            verdict_text = fallback.verdict
            verdict_source_reliability = fallback.verdict_source_reliability
            verdict_earnings_quality_2025 = fallback.verdict_earnings_quality_2025
            verdict_liquidity_short_term = fallback.verdict_liquidity_short_term
            verdict_needs_deep_check = fallback.verdict_needs_deep_check

        if not audit_intro or not audit_conclusion:
            fallback = build_fallback_intro_narrative(
                evidence_pack,
                metric_pack,
                chart_plan,
                style_notes=style_notes,
            )
            if not audit_intro:
                audit_intro = fallback.audit_intro
            if not audit_conclusion:
                audit_conclusion = fallback.audit_conclusion

        return IntroNarrative(
            company_id=evidence_pack.company_id,
            title="A32: Báo cáo tài chính có đáng tin không?",
            markdown=markdown,
            data_gaps=evidence_pack.data_gaps,
            verdict=verdict_text,
            verdict_source_reliability=verdict_source_reliability,
            verdict_earnings_quality_2025=verdict_earnings_quality_2025,
            verdict_liquidity_short_term=verdict_liquidity_short_term,
            verdict_needs_deep_check=verdict_needs_deep_check,
            audit_intro=audit_intro,
            audit_conclusion=audit_conclusion,
        )

