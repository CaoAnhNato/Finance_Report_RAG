from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.rag_report.report_vnext.evidence import FORMULA_SOURCE_PATH
from src.rag_report.report_vnext.models import (
    FinancialFact,
    IntroEvidencePack,
    IntroMetricPack,
    MetricFlag,
    MetricInputSource,
    MetricRecord,
)


FORMULA_CODE_VERSION = "vnext-intro-metrics-1"

FORMULA_LATEX_BY_ID = {
    "quality_of_earnings": r"\frac{\mathrm{CFO}}{\mathrm{LNST}}",
    "accrual_ratio": r"\frac{\mathrm{LNST} - \mathrm{CFO}}{\mathrm{Tài\ sản\ bình\ quân}}",
    "cfo_margin": r"\frac{\mathrm{CFO}}{\mathrm{Doanh\ thu\ thuần}}",
    "receivables_intensity": r"\frac{\mathrm{Phải\ thu\ ngắn\ hạn}}{\mathrm{Doanh\ thu\ thuần}}",
    "dsri": r"\frac{(\mathrm{Phải\ thu}/\mathrm{Doanh\ thu})_t}{(\mathrm{Phải\ thu}/\mathrm{Doanh\ thu})_{t-1}}",
    "allowance_coverage_receivables": r"\frac{\mathrm{Dự\ phòng\ phải\ thu}}{\mathrm{Phải\ thu\ gộp}}",
    "inventory_provision_coverage": r"\frac{\mathrm{Dự\ phòng\ giảm\ giá\ HTK}}{\mathrm{Hàng\ tồn\ kho\ gộp}}",
    "dividend_stress_ratio": r"\frac{\mathrm{Cổ\ tức\ tiền\ mặt\ đã\ trả}}{\mathrm{CFO}}",
    "cash_buffer_ratio": r"\frac{\mathrm{Tiền\ và\ tương\ đương\ tiền}}{\mathrm{Nợ\ ngắn\ hạn}}",
    "fcf_after_dividends": r"\mathrm{CFO} - \mathrm{CAPEX} - \mathrm{Cổ\ tức\ tiền\ mặt}",
    "beneish_m_score": r"\mathrm{DSRI,\ GMI,\ AQI,\ SGI,\ DEPI,\ SGAI,\ LVGI,\ TATA}",
}


@dataclass
class MetricContext:
    evidence_pack: IntroEvidencePack
    facts_by_key: dict[tuple[int, str], FinancialFact]

    def fact(self, year: int, item: str) -> Optional[FinancialFact]:
        return self.facts_by_key.get((year, item))


def _context_from_evidence(evidence_pack: IntroEvidencePack) -> MetricContext:
    keyed: dict[tuple[int, str], FinancialFact] = {}
    for fact in evidence_pack.facts:
        keyed[(fact.fiscal_year, fact.canonical_line_item)] = fact
    return MetricContext(evidence_pack=evidence_pack, facts_by_key=keyed)


def _input_source(variable_name: str, fact: Optional[FinancialFact]) -> MetricInputSource:
    if fact is None:
        return MetricInputSource(
            variable_name=variable_name,
            canonical_line_item="missing",
            source_file="unavailable",
            statement_or_note="unavailable",
            data_gap_reason=f"Thiếu dữ liệu cho biến '{variable_name}'.",
        )
    return MetricInputSource(
        variable_name=variable_name,
        fiscal_year=fact.fiscal_year,
        canonical_line_item=fact.canonical_line_item,
        source_file=fact.source_file,
        page=fact.page,
        statement_or_note=fact.statement_or_note,
        raw_value=fact.raw_value,
        normalized_value=fact.normalized_value if fact.normalized_value is not None else fact.value,
        unit=fact.unit,
        excerpt=fact.excerpt,
        data_gap_reason=fact.data_gap_reason,
    )


def _format_metric_value(value: Optional[float], unit: str) -> str:
    if value is None:
        return "chưa xác định"
    if unit == "VND":
        return f"{value / 1e9:,.2f} tỷ VND"
    if unit == "ratio":
        return f"{value:,.2f}x"
    return f"{value:,.2f}"


def _takeaway_phrase(flag: MetricFlag) -> str:
    return {
        "green": "mức theo dõi ổn định",
        "yellow": "cần theo dõi thêm",
        "red": "cần thận trọng",
        "insufficient_data": "chưa đủ dữ liệu",
    }[flag]


def _default_takeaway(metric_name: str, computed_value: Optional[float], unit: str, flag: MetricFlag) -> str:
    if computed_value is None:
        return f"{metric_name}: {_takeaway_phrase(flag)}."
    return f"{_format_metric_value(computed_value, unit)}; {_takeaway_phrase(flag)}."


def _build_record(
    *,
    metric_id: str,
    metric_name: str,
    year: int,
    formula_display: str,
    explanation: str,
    formula_latex: Optional[str] = None,
    input_values: dict[str, Optional[float]],
    input_facts: list[tuple[str, Optional[FinancialFact]]],
    computed_value: Optional[float],
    unit: str,
    flag: MetricFlag,
    notes: list[str],
    takeaway: Optional[str] = None,
    data_gap_reason: Optional[str] = None,
) -> MetricRecord:
    return MetricRecord(
        metric_id=metric_id,
        metric_name=metric_name,
        fiscal_year=year,
        formula_display=formula_display,
        formula_latex=formula_latex or FORMULA_LATEX_BY_ID.get(metric_id),
        formula_source=FORMULA_SOURCE_PATH,
        formula_code_version=FORMULA_CODE_VERSION,
        explanation=explanation,
        takeaway=takeaway or _default_takeaway(metric_name, computed_value, unit, flag),
        input_values=input_values,
        input_sources=[_input_source(name, fact) for name, fact in input_facts],
        computed_value=computed_value,
        unit=unit,
        flag=flag,
        notes=notes,
        data_gap_reason=data_gap_reason,
    )


def _metric_insufficient(
    year: int,
    metric_id: str,
    metric_name: str,
    formula_display: str,
    explanation: str,
    input_facts: list[tuple[str, Optional[FinancialFact]]],
    reason: str,
    unit: str = "ratio",
) -> MetricRecord:
    return _build_record(
        metric_id=metric_id,
        metric_name=metric_name,
        year=year,
        formula_display=formula_display,
        formula_latex=FORMULA_LATEX_BY_ID.get(metric_id),
        explanation=explanation,
        input_values={name: fact.value if fact else None for name, fact in input_facts},
        input_facts=input_facts,
        computed_value=None,
        unit=unit,
        flag="insufficient_data",
        notes=[],
        takeaway=f"{metric_name}: chưa đủ dữ liệu.",
        data_gap_reason=reason,
    )


def _consecutive_previous_year(year: int, context: MetricContext) -> Optional[int]:
    prev = year - 1
    if prev not in context.evidence_pack.years:
        return None
    return prev


def _flag_cash_conversion(value: float, lnst: float, cfo: float) -> MetricFlag:
    if cfo < 0 < lnst:
        return "red"
    if value < 0.5:
        return "yellow"
    if value > 1:
        return "green"
    return "yellow"


def _flag_accrual_ratio(value: float) -> MetricFlag:
    if value >= 0.10:
        return "red"
    if value >= 0.05:
        return "yellow"
    return "green"


def _flag_cfo_margin(value: float) -> MetricFlag:
    if value < 0:
        return "red"
    if value < 0.05:
        return "yellow"
    return "green"


def _flag_receivables_intensity(value: float) -> MetricFlag:
    if value >= 0.22:
        return "red"
    if value >= 0.15:
        return "yellow"
    return "green"


def _flag_dsri(value: float) -> MetricFlag:
    if value > 1.3:
        return "red"
    if value > 1.2:
        return "yellow"
    return "green"


def _flag_coverage(value: float) -> MetricFlag:
    if value < 0.02:
        return "red"
    if value < 0.05:
        return "yellow"
    return "green"


def _flag_dividend_stress(value: float, cfo: float, dividends: float) -> MetricFlag:
    if cfo <= 0 < dividends:
        return "red"
    if value > 1:
        return "red"
    if value > 0.7:
        return "yellow"
    return "green"


def _flag_cash_buffer(value: float) -> MetricFlag:
    if value < 0.15:
        return "red"
    if value < 0.30:
        return "yellow"
    return "green"


def _flag_fcf_after_dividends(value: float) -> MetricFlag:
    return "red" if value < 0 else "green"


def _fact_value(fact: Optional[FinancialFact]) -> Optional[float]:
    if fact is None:
        return None
    return fact.value if fact.value is not None else fact.normalized_value


def _compute_single_year_metrics(year: int, context: MetricContext) -> list[MetricRecord]:
    records: list[MetricRecord] = []

    lnst = context.fact(year, "lnst")
    cfo = context.fact(year, "cfo")
    revenue = context.fact(year, "doanh_thu")
    total_assets = context.fact(year, "tong_tai_san")
    receivables = context.fact(year, "phai_thu_ngan_han")
    receivables_gross = context.fact(year, "trade_receivables_gross") or receivables
    allowance = context.fact(year, "allowance_receivables")
    inventory_net = context.fact(year, "hang_ton_kho")
    inventory_provision = context.fact(year, "inventory_provision")
    dividends = context.fact(year, "dividends_paid")
    ending_cash = context.fact(year, "ending_cash")
    current_liabilities = context.fact(year, "no_ngan_han")
    capex = context.fact(year, "capex")

    lnst_value = _fact_value(lnst)
    cfo_value = _fact_value(cfo)
    revenue_value = _fact_value(revenue)

    if lnst_value is None or cfo_value is None or lnst_value == 0:
        records.append(
            _metric_insufficient(
                year,
                "quality_of_earnings",
                "Quality of Earnings / Cash Conversion",
                "CFO / LNST",
                "Đo mức độ lợi nhuận kế toán chuyển hóa thành tiền từ hoạt động kinh doanh.",
                [("cfo", cfo), ("lnst", lnst)],
                "Thiếu CFO hoặc LNST, hoặc LNST bằng 0.",
            )
        )
    else:
        qoe = cfo_value / lnst_value
        records.append(
            _build_record(
                metric_id="quality_of_earnings",
                metric_name="Quality of Earnings / Cash Conversion",
                year=year,
                formula_display="CFO / LNST",
                explanation="Đo mức độ lợi nhuận kế toán chuyển hóa thành tiền từ hoạt động kinh doanh.",
                input_values={"cfo": cfo_value, "lnst": lnst_value},
                input_facts=[("cfo", cfo), ("lnst", lnst)],
                computed_value=qoe,
                unit="ratio",
                flag=_flag_cash_conversion(qoe, lnst_value, cfo_value),
                notes=[],
            )
        )

    prev_year = _consecutive_previous_year(year, context)
    if prev_year is None:
        records.append(
            _metric_insufficient(
                year,
                "accrual_ratio",
                "Accrual Ratio",
                "(LNST - CFO) / Tài sản bình quân",
                "Tỷ lệ cao cho thấy lợi nhuận phụ thuộc nhiều hơn vào dồn tích thay vì tiền thực thu.",
                [("lnst", lnst), ("cfo", cfo), ("total_assets", total_assets)],
                "Thiếu năm liền trước để tính tài sản bình quân; không nội suy qua năm 2022.",
            )
        )
    else:
        prev_assets = context.fact(prev_year, "tong_tai_san")
        prev_assets_value = _fact_value(prev_assets)
        total_assets_value = _fact_value(total_assets)
        if None in (lnst_value, cfo_value, total_assets_value, prev_assets_value):
            records.append(
                _metric_insufficient(
                    year,
                    "accrual_ratio",
                    "Accrual Ratio",
                    "(LNST - CFO) / Tài sản bình quân",
                    "Tỷ lệ cao cho thấy lợi nhuận phụ thuộc nhiều hơn vào dồn tích thay vì tiền thực thu.",
                    [("lnst", lnst), ("cfo", cfo), ("total_assets_t", total_assets), ("total_assets_t_minus_1", prev_assets)],
                    "Thiếu dữ liệu tài sản để tính bình quân hoặc thiếu LNST/CFO.",
                )
            )
        else:
            average_assets = (total_assets_value + prev_assets_value) / 2
            accrual_ratio = (lnst_value - cfo_value) / average_assets if average_assets else None
            if accrual_ratio is None:
                records.append(
                    _metric_insufficient(
                        year,
                        "accrual_ratio",
                        "Accrual Ratio",
                        "(LNST - CFO) / Tài sản bình quân",
                        "Tỷ lệ cao cho thấy lợi nhuận phụ thuộc nhiều hơn vào dồn tích thay vì tiền thực thu.",
                        [("lnst", lnst), ("cfo", cfo), ("total_assets_t", total_assets), ("total_assets_t_minus_1", prev_assets)],
                        "Tài sản bình quân bằng 0.",
                    )
                )
            else:
                records.append(
                    _build_record(
                        metric_id="accrual_ratio",
                        metric_name="Accrual Ratio",
                        year=year,
                        formula_display="(LNST - CFO) / Tài sản bình quân",
                        explanation="Tỷ lệ cao cho thấy lợi nhuận phụ thuộc nhiều hơn vào dồn tích thay vì tiền thực thu.",
                        input_values={
                            "lnst": lnst_value,
                            "cfo": cfo_value,
                            "total_assets_t": total_assets_value,
                            "total_assets_t_minus_1": prev_assets_value,
                        },
                        input_facts=[
                            ("lnst", lnst),
                            ("cfo", cfo),
                            ("total_assets_t", total_assets),
                            ("total_assets_t_minus_1", prev_assets),
                        ],
                        computed_value=accrual_ratio,
                        unit="ratio",
                        flag=_flag_accrual_ratio(accrual_ratio),
                        notes=[],
                    )
                )

    if cfo_value is None or revenue_value in (None, 0):
        records.append(
            _metric_insufficient(
                year,
                "cfo_margin",
                "CFO Margin",
                "CFO / Doanh thu thuần",
                "Đo năng lực biến doanh thu thành tiền từ hoạt động kinh doanh.",
                [("cfo", cfo), ("revenue", revenue)],
                "Thiếu CFO hoặc doanh thu thuần.",
            )
        )
    else:
        cfo_margin = cfo_value / revenue_value
        records.append(
            _build_record(
                metric_id="cfo_margin",
                metric_name="CFO Margin",
                year=year,
                formula_display="CFO / Doanh thu thuần",
                explanation="Đo năng lực biến doanh thu thành tiền từ hoạt động kinh doanh.",
                input_values={"cfo": cfo_value, "revenue": revenue_value},
                input_facts=[("cfo", cfo), ("revenue", revenue)],
                computed_value=cfo_margin,
                unit="ratio",
                flag=_flag_cfo_margin(cfo_margin),
                notes=[],
            )
        )

    receivables_value = _fact_value(receivables)
    if receivables_value is None or revenue_value in (None, 0):
        records.append(
            _metric_insufficient(
                year,
                "receivables_intensity",
                "Receivables Intensity",
                "Phải thu ngắn hạn / Doanh thu thuần",
                "Đo mức độ doanh thu đang nằm trong công nợ phải thu.",
                [("receivables", receivables), ("revenue", revenue)],
                "Thiếu phải thu ngắn hạn hoặc doanh thu thuần.",
            )
        )
    else:
        intensity = receivables_value / revenue_value
        records.append(
            _build_record(
                metric_id="receivables_intensity",
                metric_name="Receivables Intensity",
                year=year,
                formula_display="Phải thu ngắn hạn / Doanh thu thuần",
                explanation="Đo mức độ doanh thu đang nằm trong công nợ phải thu.",
                input_values={"receivables": receivables_value, "revenue": revenue_value},
                input_facts=[("receivables", receivables), ("revenue", revenue)],
                computed_value=intensity,
                unit="ratio",
                flag=_flag_receivables_intensity(intensity),
                notes=[],
            )
        )

    if prev_year is None:
        records.append(
            _metric_insufficient(
                year,
                "dsri",
                "DSRI",
                "(Phải thu/Doanh thu)t / (Phải thu/Doanh thu)t-1",
                "DSRI > 1 cho thấy phải thu tăng nhanh hơn doanh thu.",
                [("receivables_t", receivables), ("revenue_t", revenue)],
                "Thiếu năm liền trước; không nội suy qua năm 2022.",
            )
        )
    else:
        prev_receivables = context.fact(prev_year, "phai_thu_ngan_han")
        prev_revenue = context.fact(prev_year, "doanh_thu")
        prev_receivables_value = _fact_value(prev_receivables)
        prev_revenue_value = _fact_value(prev_revenue)
        current = None if None in (receivables_value, revenue_value) or not revenue_value else receivables_value / revenue_value
        base = None if None in (prev_receivables_value, prev_revenue_value) or not prev_revenue_value else prev_receivables_value / prev_revenue_value
        if current is None or base in (None, 0):
            records.append(
                _metric_insufficient(
                    year,
                    "dsri",
                    "DSRI",
                    "(Phải thu/Doanh thu)t / (Phải thu/Doanh thu)t-1",
                    "DSRI > 1 cho thấy phải thu tăng nhanh hơn doanh thu.",
                    [
                        ("receivables_t", receivables),
                        ("revenue_t", revenue),
                        ("receivables_t_minus_1", prev_receivables),
                        ("revenue_t_minus_1", prev_revenue),
                    ],
                    "Thiếu doanh thu hoặc phải thu cho một trong hai năm.",
                )
            )
        else:
            dsri = current / base
            records.append(
                _build_record(
                    metric_id="dsri",
                    metric_name="DSRI",
                    year=year,
                    formula_display="(Phải thu/Doanh thu)t / (Phải thu/Doanh thu)t-1",
                    explanation="DSRI > 1 cho thấy phải thu tăng nhanh hơn doanh thu.",
                    input_values={
                        "receivables_t": receivables_value,
                        "revenue_t": revenue_value,
                        "receivables_t_minus_1": prev_receivables_value,
                        "revenue_t_minus_1": prev_revenue_value,
                    },
                    input_facts=[
                        ("receivables_t", receivables),
                        ("revenue_t", revenue),
                        ("receivables_t_minus_1", prev_receivables),
                        ("revenue_t_minus_1", prev_revenue),
                    ],
                    computed_value=dsri,
                    unit="ratio",
                    flag=_flag_dsri(dsri),
                    notes=[],
                )
            )

    gross_receivables_value = _fact_value(receivables_gross)
    allowance_value = _fact_value(allowance)
    if allowance_value is None or gross_receivables_value in (None, 0):
        records.append(
            _metric_insufficient(
                year,
                "allowance_coverage_receivables",
                "Allowance Coverage – Receivables",
                "Dự phòng phải thu / Phải thu gộp",
                "Ước lượng mức độ bao phủ rủi ro công nợ phải thu.",
                [("allowance_receivables", allowance), ("trade_receivables_gross", receivables_gross)],
                "Thiếu dự phòng phải thu hoặc phải thu gộp.",
            )
        )
    else:
        coverage = allowance_value / gross_receivables_value
        notes = []
        if receivables_gross is receivables:
            notes.append("Dùng phải thu ngắn hạn làm proxy cho phải thu gộp do thiếu chi tiết OCR.")
        records.append(
            _build_record(
                metric_id="allowance_coverage_receivables",
                metric_name="Allowance Coverage – Receivables",
                year=year,
                formula_display="Dự phòng phải thu / Phải thu gộp",
                explanation="Ước lượng mức độ bao phủ rủi ro công nợ phải thu.",
                input_values={
                    "allowance_receivables": allowance_value,
                    "trade_receivables_gross": gross_receivables_value,
                },
                input_facts=[("allowance_receivables", allowance), ("trade_receivables_gross", receivables_gross)],
                computed_value=coverage,
                unit="ratio",
                flag=_flag_coverage(coverage),
                notes=notes,
            )
        )

    inventory_net_value = _fact_value(inventory_net)
    inventory_provision_value = _fact_value(inventory_provision)
    if inventory_provision_value is None or inventory_net_value is None:
        records.append(
            _metric_insufficient(
                year,
                "inventory_provision_coverage",
                "Inventory Provision Coverage",
                "Dự phòng giảm giá HTK / Hàng tồn kho gộp",
                "Phản ánh mức độ suy giảm giá trị tồn kho đã được phản ánh qua dự phòng.",
                [("inventory_provision", inventory_provision), ("inventory_gross_proxy", inventory_net)],
                "Thiếu dự phòng hàng tồn kho hoặc hàng tồn kho.",
            )
        )
    else:
        inventory_gross_proxy = inventory_net_value + inventory_provision_value
        coverage = inventory_provision_value / inventory_gross_proxy if inventory_gross_proxy else None
        if coverage is None:
            records.append(
                _metric_insufficient(
                    year,
                    "inventory_provision_coverage",
                    "Inventory Provision Coverage",
                    "Dự phòng giảm giá HTK / Hàng tồn kho gộp",
                    "Phản ánh mức độ suy giảm giá trị tồn kho đã được phản ánh qua dự phòng.",
                    [("inventory_provision", inventory_provision), ("inventory_net", inventory_net)],
                    "Hàng tồn kho gộp bằng 0.",
                )
            )
        else:
            records.append(
                _build_record(
                    metric_id="inventory_provision_coverage",
                    metric_name="Inventory Provision Coverage",
                    year=year,
                    formula_display="Dự phòng giảm giá HTK / Hàng tồn kho gộp",
                    explanation="Phản ánh mức độ suy giảm giá trị tồn kho đã được phản ánh qua dự phòng.",
                    input_values={
                        "inventory_provision": inventory_provision_value,
                        "inventory_net": inventory_net_value,
                        "inventory_gross_proxy": inventory_gross_proxy,
                    },
                    input_facts=[("inventory_provision", inventory_provision), ("inventory_net", inventory_net)],
                    computed_value=coverage,
                    unit="ratio",
                    flag=_flag_coverage(coverage),
                    notes=["Hàng tồn kho gộp được ước bằng hàng tồn kho thuần + dự phòng."],
                )
            )

    dividends_value = _fact_value(dividends)
    if dividends_value is None or cfo_value in (None, 0):
        records.append(
            _metric_insufficient(
                year,
                "dividend_stress_ratio",
                "Dividend Stress Ratio",
                "Cổ tức tiền mặt đã trả / CFO",
                "Đo mức độ cổ tức gây áp lực lên dòng tiền hoạt động.",
                [("dividends_paid", dividends), ("cfo", cfo)],
                "Thiếu cổ tức đã trả hoặc CFO bằng 0.",
            )
        )
    else:
        ratio = dividends_value / cfo_value
        records.append(
            _build_record(
                metric_id="dividend_stress_ratio",
                metric_name="Dividend Stress Ratio",
                year=year,
                formula_display="Cổ tức tiền mặt đã trả / CFO",
                explanation="Đo mức độ cổ tức gây áp lực lên dòng tiền hoạt động.",
                input_values={"dividends_paid": dividends_value, "cfo": cfo_value},
                input_facts=[("dividends_paid", dividends), ("cfo", cfo)],
                computed_value=ratio,
                unit="ratio",
                flag=_flag_dividend_stress(ratio, cfo_value, dividends_value),
                notes=[],
            )
        )

    ending_cash_value = _fact_value(ending_cash)
    current_liabilities_value = _fact_value(current_liabilities)
    if ending_cash_value is None or current_liabilities_value in (None, 0):
        records.append(
            _metric_insufficient(
                year,
                "cash_buffer_ratio",
                "Cash Buffer Ratio",
                "Tiền và tương đương tiền / Nợ ngắn hạn",
                "Đánh giá bộ đệm thanh khoản sau khi xét công nợ ngắn hạn.",
                [("ending_cash", ending_cash), ("current_liabilities", current_liabilities)],
                "Thiếu tiền cuối kỳ hoặc nợ ngắn hạn.",
            )
        )
    else:
        ratio = ending_cash_value / current_liabilities_value
        records.append(
            _build_record(
                metric_id="cash_buffer_ratio",
                metric_name="Cash Buffer Ratio",
                year=year,
                formula_display="Tiền và tương đương tiền / Nợ ngắn hạn",
                explanation="Đánh giá bộ đệm thanh khoản sau khi xét công nợ ngắn hạn.",
                input_values={"ending_cash": ending_cash_value, "current_liabilities": current_liabilities_value},
                input_facts=[("ending_cash", ending_cash), ("current_liabilities", current_liabilities)],
                computed_value=ratio,
                unit="ratio",
                flag=_flag_cash_buffer(ratio),
                notes=[],
            )
        )

    capex_value = _fact_value(capex)
    if cfo_value is None or dividends_value is None or capex_value is None:
        records.append(
            _metric_insufficient(
                year,
                "fcf_after_dividends",
                "Free Cash Flow After Dividends",
                "CFO - CAPEX - Cổ tức tiền mặt",
                "Đo lượng tiền còn lại sau đầu tư duy trì và chi trả cổ tức.",
                [("cfo", cfo), ("capex", capex), ("dividends_paid", dividends)],
                "Thiếu CFO, CAPEX hoặc cổ tức đã trả.",
                unit="VND",
            )
        )
    else:
        value = cfo_value - capex_value - dividends_value
        records.append(
            _build_record(
                metric_id="fcf_after_dividends",
                metric_name="Free Cash Flow After Dividends",
                year=year,
                formula_display="CFO - CAPEX - Cổ tức tiền mặt",
                explanation="Đo lượng tiền còn lại sau đầu tư duy trì và chi trả cổ tức.",
                input_values={"cfo": cfo_value, "capex": capex_value, "dividends_paid": dividends_value},
                input_facts=[("cfo", cfo), ("capex", capex), ("dividends_paid", dividends)],
                computed_value=value,
                unit="VND",
                flag=_flag_fcf_after_dividends(value),
                notes=[],
            )
        )

    records.append(
        _metric_insufficient(
            year,
            "beneish_m_score",
            "Beneish M-score",
            "DSRI, GMI, AQI, SGI, DEPI, SGAI, LVGI, TATA",
            "Bộ lọc cảnh báo xác suất thao túng lợi nhuận, không dùng như kết luận gian lận.",
            [("dsri", None)],
            "Chưa đủ chuỗi dữ liệu chi tiết để tính Beneish M-score một cách đáng tin cậy.",
        )
    )
    return records


def calculate_intro_metrics(evidence_pack: IntroEvidencePack) -> IntroMetricPack:
    context = _context_from_evidence(evidence_pack)
    records: list[MetricRecord] = []
    for year in evidence_pack.years:
        records.extend(_compute_single_year_metrics(year, context))
    return IntroMetricPack(company_id=evidence_pack.company_id, records=records)
