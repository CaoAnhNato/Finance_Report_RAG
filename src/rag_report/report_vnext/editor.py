from __future__ import annotations

import json
import re
from src.rag_report.report_vnext.llm import call_llm_until_nonempty, get_llm_client
from src.rag_report.report_vnext.models import (
    IntroNarrative,
    IntroEvidencePack,
    IntroMetricPack,
    IntroChartPlan,
    IntroReportContract,
)

BANNED_WORDS_MAP = {
    "Bước 1": "Cơ sở số liệu",
    "Câu trả lời nhanh": "Tóm tắt kết luận chính",
    "Vì sao cần thận trọng với năm gần nhất": "Tóm tắt kết luận chính",
    "Kết luận của phần này": "Kết luận chính",
    "Điểm cần kiểm tra tiếp theo": "Mạch phân tích của báo cáo",
    "Kết luận nhanh cho người không chuyên": "Kết luận chính",
    "người không chuyên": "độc giả",
    "người ngoài ngành": "độc giả",
    "doanh nghiệp khỏe": "doanh nghiệp hoạt động ổn định",
    "tiền thật": "dòng tiền thực tế",
}

def normalize_narrative_deterministic(
    narrative: IntroNarrative,
    evidence_pack: IntroEvidencePack,
) -> IntroNarrative:
    """
    Deterministic cleanup and wording replacement.
    Applies regex/string replacements to remove banned informal phrases,
    standardizes headings, and ensures audit intro/conclusion consistency.
    """
    company_id = evidence_pack.company_id
    narrative.company_id = company_id
    
    # 1. Standardize Title
    narrative.title = f"{company_id}: Số liệu báo cáo tài chính có đủ tin cậy để phân tích không?"
    
    # Helper to replace banned words case-insensitively
    def clean_text(text: str | None) -> str:
        if not text:
            return ""
        cleaned = text
        for old, new in BANNED_WORDS_MAP.items():
            # Standard string replacement
            cleaned = cleaned.replace(old, new)
            # Case-insensitive replacement using regex if not already replaced
            pattern = re.compile(re.escape(old), re.IGNORECASE)
            cleaned = pattern.sub(new, cleaned)
        return cleaned

    # 2. Clean up major text blocks
    if narrative.markdown:
        narrative.markdown = clean_text(narrative.markdown)
    if narrative.audit_intro:
        narrative.audit_intro = clean_text(narrative.audit_intro)
    if narrative.audit_conclusion:
        narrative.audit_conclusion = clean_text(narrative.audit_conclusion)

    # 3. Handle audit_intro legacy leading phrases
    if narrative.audit_intro:
        # If contains introductory filler, substitute with clean description
        fillers = [
            "Trước khi phân tích sâu",
            "Để có góc nhìn rõ hơn",
            "Trước khi đi vào phân tích chi tiết",
            "Trước khi đánh giá chi tiết",
        ]
        for filler in fillers:
            if filler in narrative.audit_intro:
                narrative.audit_intro = f"Cơ sở số liệu tài chính của doanh nghiệp {company_id} được đánh giá thông qua ý kiến kiểm toán, đơn vị kiểm toán thực hiện và mức độ đầy đủ của thông tin qua các năm tài chính."
                break

    # 4. Handle audit_conclusion consistency based on audit snapshots
    has_qualified = False
    has_insufficient = False
    for snapshot in evidence_pack.audit_snapshots:
        opinion = (snapshot.audit_opinion or "").lower()
        if "ngoại trừ" in opinion or "ngoai tru" in opinion or "trừ ngoại lệ" in opinion or snapshot.severity_flag in ("red", "yellow"):
            has_qualified = True
        if not opinion or "thiếu" in opinion or "insufficient" in opinion or snapshot.severity_flag == "insufficient_data":
            has_insufficient = True

    if has_qualified:
        narrative.audit_conclusion = (
            f"Nguồn số liệu của {company_id} có ý kiến kiểm toán ngoại trừ trong lịch sử. "
            "Độc giả cần hết sức thận trọng xem xét phạm vi ảnh hưởng của các khoản ngoại trừ trước khi thực hiện các bước phân tích tiếp theo."
        )
    elif has_insufficient:
        narrative.audit_conclusion = (
            f"Nguồn số liệu của {company_id} cơ bản đầy đủ nhưng còn một số khoảng trống dữ liệu hoặc thiếu thông tin kiểm toán rõ ràng ở một vài năm tài chính. "
            "Độ tin cậy của dữ liệu ở mức Khá."
        )
    else:
        # Completely clean
        narrative.audit_conclusion = (
            f"Nguồn số liệu của {company_id} có độ tin cậy tốt. Toàn bộ các năm trọng yếu đều nhận được ý kiến chấp nhận toàn phần "
            "từ các tổ chức kiểm toán uy tín, tạo cơ sở vững chắc cho các đánh giá tài chính chuyên sâu."
        )

    # 5. Clean report contract focus areas and key signals
    if narrative.report_contract:
        contract = narrative.report_contract
        if contract.executive_verdict:
            verdict = contract.executive_verdict
            if verdict.focus_areas:
                new_focus = []
                for area in verdict.focus_areas:
                    cleaned_area = clean_text(area)
                    # Specific mapping to highly professional phrases
                    if "CFO so với LNST" in cleaned_area or "CFO/LNST" in cleaned_area:
                        new_focus.append("Quan hệ giữa lợi nhuận sau thuế và dòng tiền kinh doanh")
                    elif "Khoản phải thu và doanh thu" in cleaned_area or "phải thu" in cleaned_area.lower():
                        new_focus.append("Khả năng chuyển hóa doanh thu thành tiền thu về")
                    elif "Thanh khoản" in cleaned_area or "Cổ tức" in cleaned_area:
                        new_focus.append("Mức đệm thanh khoản sau cổ tức và nghĩa vụ ngắn hạn")
                    elif "Độ tin cậy" in cleaned_area:
                        new_focus.append("Mức độ đầy đủ và tin cậy của dữ liệu kiểm toán")
                    else:
                        new_focus.append(cleaned_area)
                verdict.focus_areas = new_focus

        if contract.key_signals:
            for sig in contract.key_signals:
                sig.question = clean_text(sig.question)
                sig.conclusion = clean_text(sig.conclusion)
                sig.plain_explanation = clean_text(sig.plain_explanation)
                if sig.id == "source_reliability":
                    sig.question = "Số liệu báo cáo có đủ cơ sở sử dụng không?"

    return narrative


class IntroNarrativeEditor:
    def __init__(self, use_llm: bool = True) -> None:
        self.use_llm = use_llm

    def edit(
        self,
        narrative: IntroNarrative,
        evidence_pack: IntroEvidencePack,
        metric_pack: IntroMetricPack,
        chart_plan: IntroChartPlan,
        style_notes: list[str] | None = None,
    ) -> IntroNarrative:
        """
        Edits the narrative draft using an LLM layer if enabled,
        then guarantees compliance by applying a deterministic fallback.
        """
        if not self.use_llm:
            return normalize_narrative_deterministic(narrative, evidence_pack)

        try:
            client, config = get_llm_client("financial_reasoning")
            
            # Prepare context for editing
            latest_year = max(evidence_pack.years) if evidence_pack.years else 2025
            focus_years = sorted({latest_year, latest_year - 1} & set(evidence_pack.years))
            key_items = ["lnst", "cfo", "ending_cash", "phai_thu_ngan_han", "doanh_thu", "no_ngan_han", "dividends_paid", "capex"]
            
            facts_by_year = {}
            for year in focus_years:
                year_facts = []
                for item in key_items:
                    for fact in evidence_pack.facts:
                        if fact.fiscal_year == year and fact.canonical_line_item == item:
                            if fact.value is not None:
                                year_facts.append({
                                    "canonical_line_item": fact.canonical_line_item,
                                    "fiscal_year": fact.fiscal_year,
                                    "value": fact.value,
                                    "unit": fact.unit,
                                    "page": fact.page,
                                    "statement_or_note": fact.statement_or_note,
                                })
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

            compact_context = {
                "draft_narrative": narrative.model_dump(mode="json", exclude_none=False),
                "company_id": evidence_pack.company_id,
                "years": evidence_pack.years,
                "audit_snapshots": audit_snapshots,
                "data_gaps": sorted(set(evidence_pack.data_gaps)),
                "facts_by_year": facts_by_year,
                "metric_snapshot": [
                    {
                        "metric_id": record.metric_id,
                        "metric_name": record.metric_name,
                        "fiscal_year": record.fiscal_year,
                        "computed_value": record.computed_value,
                        "unit": record.unit,
                        "flag": record.flag,
                    }
                    for record in metric_pack.records if record.fiscal_year in focus_years
                ],
                "chart_plan": [
                    {
                        "chart_id": item.chart_id,
                        "title": item.title,
                        "subtitle": item.subtitle,
                        "insight_line": item.insight_line,
                    }
                    for item in chart_plan.items
                ],
                "style_notes": style_notes or [],
            }

            system_instruction = (
                "Bạn là biên tập viên báo cáo tài chính cao cấp. Nhiệm vụ của bạn là rà soát và biên tập bản nháp IntroNarrative (chứa phần mở đầu của báo cáo tài chính) "
                "để đảm bảo văn phong chuyên nghiệp, chuẩn mực, loại bỏ các từ ngữ không chuyên nghiệp hoặc các định dạng không nhất quán.\n\n"
                "QUY TẮC BIÊN TẬP:\n"
                "1. Tiêu đề chính và các heading phải chuẩn hóa, không dùng các cụm từ kiểu 'Bước 1', 'Câu trả lời nhanh', 'Vì sao cần thận trọng...', 'Điểm cần kiểm tra tiếp theo', 'Kết luận của phần này', 'Kết luận nhanh cho người không chuyên'.\n"
                "   - Hãy đổi 'Câu trả lời nhanh' hoặc 'Vì sao cần thận trọng...' thành 'Tóm tắt kết luận chính'.\n"
                "   - Hãy đổi 'Điểm cần kiểm tra tiếp theo' thành 'Mạch phân tích của báo cáo'.\n"
                "   - Hãy đổi 'Kết luận của phần này' hoặc 'Kết luận nhanh...' thành 'Kết luận chính'.\n"
                "2. Loại bỏ các từ cấm hoặc không chuyên nghiệp:\n"
                "   - Không dùng 'người không chuyên', 'người ngoài ngành', thay bằng 'độc giả' hoặc 'nhà đầu tư'.\n"
                "   - Không dùng 'doanh nghiệp khỏe', thay bằng 'doanh nghiệp có sức khỏe tài chính tốt' hoặc 'doanh nghiệp hoạt động ổn định'.\n"
                "   - Không dùng 'tiền thật', thay bằng 'dòng tiền thực tế từ hoạt động kinh doanh'.\n"
                "3. Phần audit_intro không được chứa các câu rườm rà như 'Trước khi phân tích sâu...', 'Để có góc nhìn rõ hơn...'. Hãy đi thẳng vào giới thiệu cơ sở số liệu kiểm toán.\n"
                "4. Phần audit_conclusion phải nhất quán với tình trạng kiểm toán trong audit_snapshots:\n"
                "   - Nếu có ý kiến ngoại trừ (Qualified/Qualified opinion) hoặc thiếu dữ liệu (insufficient_data), phải kết luận thận trọng, ghi rõ có điểm ngoại trừ nên cần lưu ý phạm vi ảnh hưởng.\n"
                "   - Nếu toàn bộ đều chấp nhận toàn phần (Unqualified) và ít thiếu hụt, khẳng định số liệu có độ tin cậy tốt.\n"
                "5. Đảm bảo cấu trúc JSON đầu ra giống hệt cấu trúc JSON đầu vào của IntroNarrative:\n"
                "   - 'title': Chuẩn hóa thành '{company_id}: Số liệu báo cáo tài chính có đủ tin cậy để phân tích không?'\n"
                "   - 'markdown': Đoạn văn bản markdown đã được biên tập lại ngôn từ và tiêu đề.\n"
                "   - 'audit_intro': Lời dẫn đã được biên tập.\n"
                "   - 'audit_conclusion': Kết luận đã được biên tập.\n"
                "   - 'report_contract': Đối tượng report_contract với các focus_areas được chuẩn hóa ngôn từ (ví dụ: 'Quan hệ giữa lợi nhuận sau thuế và dòng tiền kinh doanh' thay cho 'CFO so với LNST').\n\n"
                "Hãy trả về JSON thuần túy, không có code fence hay bất kỳ văn bản nào khác."
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

            # Strip code fence
            s = raw_response.strip()
            if s.startswith("```"):
                lines = s.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                s = "\n".join(lines).strip()

            parsed = json.loads(s)
            
            # Construct edited narrative from parsed JSON
            edited = IntroNarrative(
                company_id=evidence_pack.company_id,
                title=parsed.get("title") or narrative.title,
                markdown=parsed.get("markdown") or narrative.markdown,
                data_gaps=narrative.data_gaps,
                verdict=parsed.get("verdict") or narrative.verdict,
                verdict_source_reliability=parsed.get("verdict_source_reliability") or narrative.verdict_source_reliability,
                verdict_earnings_quality_2025=parsed.get("verdict_earnings_quality_2025") or narrative.verdict_earnings_quality_2025,
                verdict_liquidity_short_term=parsed.get("verdict_liquidity_short_term") or narrative.verdict_liquidity_short_term,
                verdict_needs_deep_check=parsed.get("verdict_needs_deep_check") or narrative.verdict_needs_deep_check,
                audit_intro=parsed.get("audit_intro") or narrative.audit_intro,
                audit_conclusion=parsed.get("audit_conclusion") or narrative.audit_conclusion,
            )
            
            contract_payload = parsed.get("report_contract")
            if isinstance(contract_payload, dict):
                edited.report_contract = IntroReportContract.model_validate(contract_payload)
            else:
                edited.report_contract = narrative.report_contract

            # Run deterministic normalization as a post-editing safety check
            return normalize_narrative_deterministic(edited, evidence_pack)

        except Exception as e:
            print(f"[vNext] Editor LLM failed or parsed incorrectly: {e}. Falling back to deterministic editor.")
            return normalize_narrative_deterministic(narrative, evidence_pack)
