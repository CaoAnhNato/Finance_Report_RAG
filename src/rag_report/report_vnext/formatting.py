from __future__ import annotations

import re
import unicodedata
from pathlib import Path

STATEMENT_LABELS = {
    "processed_financials": "Dữ liệu tài chính tổng hợp",
    "cash_flow": "Lưu chuyển tiền tệ",
    "notes_receivables": "Thuyết minh phải thu",
    "notes_inventory": "Thuyết minh hàng tồn kho",
    "notes_audit": "Báo cáo kiểm toán",
    "balance_sheet": "Bảng cân đối kế toán",
    "income_statement": "Báo cáo kết quả kinh doanh",
    "unavailable": "Nguồn không xác định",
}


def year_from_path(source_file: str | None) -> int | None:
    if not source_file:
        return None
    match = re.search(r"\b(20\d{2})\b", source_file)
    return int(match.group(1)) if match else None


def normalize_statement_label(statement_or_note: str | None) -> str | None:
    if not statement_or_note:
        return None
    val = statement_or_note.strip()
    norm_key = val.lower().replace("_", " ").replace("-", " ").strip()
    mapping = {
        "processed_financials": "Dữ liệu tài chính tổng hợp",
        "processed financials": "Dữ liệu tài chính tổng hợp",
        "du lieu tong hop a32": "Dữ liệu tài chính tổng hợp",
        
        "cash_flow": "Lưu chuyển tiền tệ",
        "cash flow": "Lưu chuyển tiền tệ",
        "luu chuyen tien te": "Lưu chuyển tiền tệ",
        
        "notes_receivables": "Thuyết minh phải thu",
        "notes receivables": "Thuyết minh phải thu",
        "thuyet minh phai thu": "Thuyết minh phải thu",
        
        "notes_inventory": "Thuyết minh hàng tồn kho",
        "notes inventory": "Thuyết minh hàng tồn kho",
        "thuyet minh hang ton kho": "Thuyết minh hàng tồn kho",
        
        "notes_audit": "Báo cáo kiểm toán",
        "notes audit": "Báo cáo kiểm toán",
        "bao cao kiem toan": "Báo cáo kiểm toán",
        
        "balance_sheet": "Bảng cân đối kế toán",
        "balance sheet": "Bảng cân đối kế toán",
        "bang can doi ke toan": "Bảng cân đối kế toán",
        
        "income_statement": "Báo cáo kết quả kinh doanh",
        "income statement": "Báo cáo kết quả kinh doanh",
        "bao cao ket qua kinh doanh": "Báo cáo kết quả kinh doanh",
        
        "unavailable": "Nguồn không xác định",
    }
    return mapping.get(norm_key, val)


def public_source_label(
    source_file: str | None,
    *,
    fiscal_year: int | None = None,
    page: int | None = None,
    statement_or_note: str | None = None,
) -> str:
    parts: list[str] = []
    year = fiscal_year if fiscal_year is not None else year_from_path(source_file)
    if year is not None:
        parts.append(f"BCTC {year}")
    statement_label = normalize_statement_label(statement_or_note)
    if page is not None:
        parts.append(f"trang {page}")
    if statement_label and statement_label not in {"Dữ liệu tài chính tổng hợp", "Nguồn không xác định"}:
        parts.append(statement_label)
    if not parts:
        return "Nguồn nội bộ"
    return ", ".join(parts)


def sanitize_visible_source_text(text: str) -> str:
    text = re.sub(r"[A-Za-z]:(?:\\{1,2})(?!\\)[^<>\n\r]+", "Nguồn nội bộ", text)
    text = re.sub(r"[A-Za-z]:/(?!/)[^<>\n\r]+", "Nguồn nội bộ", text)
    text = re.sub(r"/Users/[^<>\n\r]+", "Nguồn nội bộ", text)
    text = text.replace("source_file", "nguồn nội bộ")
    return text


def formula_math_block(formula_latex: str | None, fallback: str) -> str:
    formula = formula_latex or fallback
    return f"\\({formula}\\)"


def fold_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    stripped = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", stripped).lower().strip()


LINE_ITEM_NAME_VI = {
    "cfo": "Dòng tiền từ HĐKD (CFO)",
    "lnst": "Lợi nhuận sau thuế (LNST)",
    "tong_tai_san": "Tổng tài sản",
    "doanh_thu": "Doanh thu",
    "no_ngan_han": "Nợ ngắn hạn",
    "allowance_receivables": "Dự phòng phải thu ngắn hạn",
    "trade_receivables_gross": "Phải thu ngắn hạn gộp",
    "inventory_provision": "Dự phòng giảm giá hàng tồn kho",
    "hang_ton_kho": "Hàng tồn kho",
    "dividends_paid": "Cổ tức đã trả",
    "ending_cash": "Tiền cuối kỳ",
    "capex": "CAPEX",
    "receivables": "Phải thu ngắn hạn",
    "revenue": "Doanh thu thuần",
    "total_assets_t": "Tổng tài sản kỳ này",
    "total_assets_t_minus_1": "Tổng tài sản kỳ trước",
    "receivables_t": "Phải thu kỳ này",
    "revenue_t": "Doanh thu kỳ này",
    "receivables_t_minus_1": "Phải thu kỳ trước",
    "revenue_t_minus_1": "Doanh thu kỳ trước",
    "current_liabilities": "Nợ ngắn hạn",
    "inventory_net": "Hàng tồn kho thuần",
    "net_receivables": "Phải thu ngắn hạn thuần",
    "gross_receivables": "Phải thu ngắn hạn gộp",
    "phai_thu_ngan_han": "Phải thu ngắn hạn",
    "phai_thu_gop": "Phải thu ngắn hạn gộp",
    "du_phong_phai_thu": "Dự phòng phải thu ngắn hạn",
    "inventory": "Hàng tồn kho",
    "allowance": "Dự phòng phải thu ngắn hạn",
    "cash_conversion": "Chuyển đổi tiền mặt",
    "accrual_ratio": "Tỷ lệ dồn tích",
    "quality_of_earnings": "Chất lượng lợi nhuận",
    "receivables_intensity": "Thâm dụng phải thu",
    "dsri": "Chỉ số DSRI",
    "allowance_coverage_receivables": "Tỷ lệ bao nợ xấu phải thu",
    "inventory_provision_coverage": "Tỷ lệ bao dự phòng hàng tồn kho",
    "dividend_stress_ratio": "Tỷ lệ căng thẳng cổ tức",
    "cash_buffer_ratio": "Tỷ lệ đệm tiền mặt",
    "fcf_after_dividends": "Dòng tiền tự do sau cổ tức"
}


def translate_unaccented_text(text: str | None) -> str:
    if not text:
        return ""
    sorted_items = sorted(LINE_ITEM_NAME_VI.items(), key=lambda x: len(x[0]), reverse=True)
    res = text
    for key, val in sorted_items:
        res = re.sub(rf"\b{re.escape(key)}\b", val, res, flags=re.IGNORECASE)
    return res

