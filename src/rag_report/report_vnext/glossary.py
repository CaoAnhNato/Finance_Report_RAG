from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GlossaryTerm:
    term: str
    abbreviation: str | None
    short_definition: str
    analytical_role: str
    category: str = "general"


DEFAULT_GLOSSARY_TERMS: list[GlossaryTerm] = [
    GlossaryTerm(
        term="Lợi nhuận sau thuế",
        abbreviation="LNST",
        short_definition="Phần lợi nhuận còn lại sau khi trừ chi phí và thuế.",
        analytical_role="Đánh giá kết quả lợi nhuận kế toán.",
        category="core",
    ),
    GlossaryTerm(
        term="Dòng tiền từ hoạt động kinh doanh",
        abbreviation="CFO",
        short_definition="Dòng tiền thuần tạo ra hoặc sử dụng bởi hoạt động kinh doanh chính.",
        analytical_role="Kiểm tra lợi nhuận có được hỗ trợ bởi dòng tiền hay không.",
        category="cash_flow",
    ),
    GlossaryTerm(
        term="Chất lượng lợi nhuận",
        abbreviation="CFO/LNST",
        short_definition="Mức độ lợi nhuận kế toán chuyển hóa thành dòng tiền kinh doanh.",
        analytical_role="Nếu thấp hoặc âm, cần xem xét tính bền vững của lợi nhuận.",
        category="cash_flow",
    ),
    GlossaryTerm(
        term="Tỷ lệ dồn tích",
        abbreviation="Accrual Ratio",
        short_definition="Mức chênh giữa lợi nhuận kế toán và dòng tiền, so với quy mô tài sản.",
        analytical_role="Tỷ lệ cao cho thấy lợi nhuận phụ thuộc nhiều hơn vào ghi nhận dồn tích.",
        category="technical",
    ),
    GlossaryTerm(
        term="Biên dòng tiền kinh doanh",
        abbreviation="CFO Margin",
        short_definition="CFO chia cho doanh thu thuần.",
        analytical_role="Đánh giá khả năng chuyển doanh thu thành dòng tiền kinh doanh.",
        category="cash_flow",
    ),
    GlossaryTerm(
        term="Khoản phải thu",
        abbreviation="AR",
        short_definition="Số tiền khách hàng còn phải thanh toán cho doanh nghiệp.",
        analytical_role="Đánh giá rủi ro doanh thu chưa chuyển hóa thành tiền thu về.",
        category="working_capital",
    ),
    GlossaryTerm(
        term="Doanh thu thuần",
        abbreviation="Revenue",
        short_definition="Doanh thu sau khi trừ các khoản giảm trừ.",
        analytical_role="Đối chiếu với khoản phải thu và dòng tiền.",
        category="core",
    ),
    GlossaryTerm(
        term="DSRI",
        abbreviation="DSRI",
        short_definition="Tỷ lệ phải thu/doanh thu kỳ này so với kỳ trước.",
        analytical_role="DSRI tăng cao cho thấy phải thu tăng nhanh hơn doanh thu.",
        category="working_capital",
    ),
    GlossaryTerm(
        term="Tiền và tương đương tiền",
        abbreviation="Cash",
        short_definition="Lượng tiền hoặc tài sản tương đương tiền có thể sử dụng nhanh.",
        analytical_role="Đánh giá đệm thanh khoản.",
        category="liquidity",
    ),
    GlossaryTerm(
        term="Nợ ngắn hạn",
        abbreviation="Current liabilities",
        short_definition="Nghĩa vụ phải trả trong ngắn hạn.",
        analytical_role="Đánh giá áp lực thanh toán.",
        category="liquidity",
    ),
    GlossaryTerm(
        term="Đệm thanh khoản",
        abbreviation="Cash Buffer",
        short_definition="Khả năng đáp ứng nghĩa vụ ngắn hạn bằng tiền sẵn có.",
        analytical_role="Nếu thấp, doanh nghiệp dễ chịu áp lực thanh khoản.",
        category="liquidity",
    ),
    GlossaryTerm(
        term="Cổ tức tiền mặt",
        abbreviation="Dividend paid",
        short_definition="Khoản tiền doanh nghiệp chi trả cho cổ đông.",
        analytical_role="Làm giảm lượng tiền còn lại trong doanh nghiệp.",
        category="cash_flow",
    ),
    GlossaryTerm(
        term="Dòng tiền tự do sau cổ tức",
        abbreviation="FCF after dividends",
        short_definition="CFO trừ CAPEX và cổ tức tiền mặt.",
        analytical_role="Đo lượng tiền còn lại sau đầu tư và chi trả cổ tức.",
        category="cash_flow",
    ),
    GlossaryTerm(
        term="Dự phòng phải thu",
        abbreviation="Allowance for receivables",
        short_definition="Khoản dự phòng cho rủi ro không thu hồi đủ công nợ.",
        analytical_role="Đánh giá mức độ thận trọng với công nợ phải thu.",
        category="technical",
    ),
    GlossaryTerm(
        term="Dự phòng giảm giá hàng tồn kho",
        abbreviation="Inventory provision",
        short_definition="Khoản dự phòng cho rủi ro hàng tồn kho giảm giá trị.",
        analytical_role="Đánh giá mức độ thận trọng với hàng tồn kho.",
        category="technical",
    ),
    GlossaryTerm(
        term="Ý kiến kiểm toán chấp nhận toàn phần",
        abbreviation="Unqualified opinion",
        short_definition="Kiểm toán không nêu ngoại trừ trọng yếu đối với báo cáo tài chính.",
        analytical_role="Hỗ trợ đánh giá độ tin cậy của số liệu.",
        category="audit",
    ),
    GlossaryTerm(
        term="Ý kiến kiểm toán ngoại trừ",
        abbreviation="Qualified opinion",
        short_definition="Kiểm toán nêu ngoại trừ đối với một vấn đề cụ thể.",
        analytical_role="Cần xem xét phạm vi ảnh hưởng trước khi kết luận.",
        category="audit",
    ),
]


def get_signal_glossary_terms(contract: Any | None = None) -> list[GlossaryTerm]:
    target_terms = [
        "Lợi nhuận sau thuế",
        "Dòng tiền từ hoạt động kinh doanh",
        "Khoản phải thu",
        "Cổ tức tiền mặt",
        "Đệm thanh khoản",
    ]
    if contract is not None and hasattr(contract, "key_signals") and contract.key_signals:
        has_reliability = any(getattr(sig, "id", "") == "source_reliability" for sig in contract.key_signals)
        if has_reliability:
            target_terms.append("Ý kiến kiểm toán chấp nhận toàn phần")
            target_terms.append("Ý kiến kiểm toán ngoại trừ")
    
    res = []
    for term_name in target_terms:
        for t in DEFAULT_GLOSSARY_TERMS:
            if t.term == term_name:
                res.append(t)
                break
    return res


def get_appendix_glossary_terms(metric_pack: Any | None = None, contract: Any | None = None) -> list[GlossaryTerm]:
    if metric_pack is None or not getattr(metric_pack, "records", []):
        return list(DEFAULT_GLOSSARY_TERMS)
    
    METRIC_TO_TERMS = {
        "quality_of_earnings": ["Lợi nhuận sau thuế", "Dòng tiền từ hoạt động kinh doanh", "Chất lượng lợi nhuận"],
        "accrual_ratio": ["Lợi nhuận sau thuế", "Dòng tiền từ hoạt động kinh doanh", "Tỷ lệ dồn tích"],
        "cfo_margin": ["Dòng tiền từ hoạt động kinh doanh", "Doanh thu thuần", "Biên dòng tiền kinh doanh"],
        "receivables_intensity": ["Khoản phải thu", "Doanh thu thuần"],
        "dsri": ["DSRI", "Khoản phải thu", "Doanh thu thuần"],
        "allowance_coverage_receivables": ["Dự phòng phải thu", "Khoản phải thu"],
        "inventory_provision_coverage": ["Dự phòng giảm giá hàng tồn kho"],
        "dividend_stress_ratio": ["Cổ tức tiền mặt", "Dòng tiền từ hoạt động kinh doanh"],
        "cash_buffer_ratio": ["Tiền và tương đương tiền", "Nợ ngắn hạn", "Đệm thanh khoản"],
        "fcf_after_dividends": ["Dòng tiền tự do sau cổ tức", "Dòng tiền từ hoạt động kinh doanh", "Cổ tức tiền mặt"],
    }
    
    selected_terms = set()
    for record in metric_pack.records:
        metric_id = getattr(record, "metric_id", "")
        if metric_id in METRIC_TO_TERMS:
            for term in METRIC_TO_TERMS[metric_id]:
                selected_terms.add(term)
                
    if contract is not None and hasattr(contract, "key_signals") and contract.key_signals:
        has_reliability = any(getattr(sig, "id", "") == "source_reliability" for sig in contract.key_signals)
        if has_reliability:
            selected_terms.add("Ý kiến kiểm toán chấp nhận toàn phần")
            selected_terms.add("Ý kiến kiểm toán ngoại trừ")
            
    if not selected_terms:
        return list(DEFAULT_GLOSSARY_TERMS)
        
    return [t for t in DEFAULT_GLOSSARY_TERMS if t.term in selected_terms]
