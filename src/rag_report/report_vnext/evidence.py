from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from bs4 import BeautifulSoup

from src.rag_report.config import settings
from src.rag_report.ingestion.store import DuckDBStore
from src.rag_report.report_vnext.formatting import fold_text, public_source_label
from src.rag_report.report_vnext.llm import call_llm_until_nonempty, get_llm_client
from src.rag_report.report_vnext.models import (
    AuditSnapshot,
    DroppedClaimRecord,
    EvidenceCitation,
    FinancialFact,
    GapAdjudicationRecord,
    IntroEvidencePack,
    RetrievedChunk,
)


PAGE_PATTERN = re.compile(r"=====\s*PAGE\s+(\d+)\s*=====")
INT_PATTERN = re.compile(r"\(?-?\d[\d\.\,\s]{2,}\)?")
FORMULA_SOURCE_PATH = "Khung tính toán nội bộ"


@dataclass(frozen=True)
class FactSpec:
    query_terms: tuple[str, ...]
    patterns: tuple[str, ...]
    statement_or_note: str
    absolute: bool = False
    extract_mode: str = "row"  # row | sum_dividends
    requires_support: bool = True


PROCESSED_SOURCE_PATTERNS = {
    "doanh_thu": [r"doanh thu thuan", r"doanh thu ban hang"],
    "lnst": [r"loi nhuan sau thue"],
    "tong_tai_san": [r"tong cong tai san"],
    "no_ngan_han": [r"no ngan han"],
    "hang_ton_kho": [r"hang ton kho"],
    "phai_thu_ngan_han": [r"phai thu ngan han", r"cac khoan phai thu ngan han", r"phai thu cua khach hang"],
    "cfo": [r"luu chuyen tien thuan tu hoat dong kinh doanh"],
    "cfi": [r"luu chuyen tien thuan tu hoat dong dau tu"],
    "cff": [r"luu chuyen tien thuan tu hoat dong tai chinh"],
}


OCR_EXTRACTION_SPECS = {
    "ending_cash": {
        "patterns": [
            r"tien va cac khoan tuong duong tien",
            r"tien va tuong duong tien cuoi ky",
            r"tien va cac khoan tuong duong tien cuoi ky",
        ],
        "statement_or_note": "balance_sheet",
        "absolute": False,
    },
    "dividends_paid": {
        "patterns": [
            r"co tuc",
            r"chia co tuc",
            r"co tuc phai tra",
            r"loi nhuan da tra cho chu so huu",
            r"co tuc loi nhuan nam 2016 da chi trong nam 2017",
            r"chia co tuc dot 1 nam 2017",
        ],
        "statement_or_note": "unavailable",
        "absolute": True,
    },
    "allowance_receivables": {
        "patterns": [r"du phong phai thu.*kho doi", r"du phong phai thu ngan han kho doi"],
        "statement_or_note": "notes_receivables",
        "absolute": True,
    },
    "trade_receivables_gross": {
        "patterns": [r"phai thu cua khach hang", r"phai thu khach hang"],
        "statement_or_note": "notes_receivables",
        "absolute": False,
    },
    "inventory_provision": {
        "patterns": [r"du phong giam gia hang ton kho"],
        "statement_or_note": "notes_inventory",
        "absolute": True,
    },
    "capex": {
        "patterns": [
            r"tien chi de mua sam, xay dung tscd",
            r"tien chi de mua sam, xay dung tscd va cac tsdh khac",
            r"tien chi .*mua sam.*tai san co dinh",
            r"tien chi .*xay dung.*tai san co dinh",
            r"tien chi .*xay dung.*tsdh",
        ],
        "statement_or_note": "cash_flow",
        "absolute": True,
    },
}


AUDIT_OPINION_PATTERNS = {
    "qualified": [
        r"y\s*kien(?:\s+kiem\s+toan)?\s+ngoai\s+tru",
        r"co\s+so.{0,260}y\s*kien(?:\s+kiem\s+toan)?\s+ngoai\s+tru",
    ],
    "unqualified": [
        r"y\s*kien(?:\s+kiem\s+toan)?\s+chap\s+nhan\s+toan\s+phan",
        r"phan\s+anh\s+trung\s+thuc\s+va\s+hop\s+ly",
    ],
}


FALSE_GAP_FIELDS = {
    ("dividends_paid", 2017),
    ("ending_cash", 2017),
    ("ending_cash", 2020),
    ("ending_cash", 2021),
}


COMMON_FACT_SPECS: dict[str, FactSpec] = {
    "doanh_thu": FactSpec(
        query_terms=("doanh thu", "doanh thu ban hang", "doanh thu thuan"),
        patterns=("doanh thu ban hang", "doanh thu thuan"),
        statement_or_note="income_statement",
    ),
    "lnst": FactSpec(
        query_terms=("loi nhuan sau thue", "loi nhuan sau thue chua phan phoi"),
        patterns=("loi nhuan sau thue",),
        statement_or_note="income_statement",
    ),
    "tong_tai_san": FactSpec(
        query_terms=("tong tai san", "tong cong tai san"),
        patterns=("tong tai san", "tong cong tai san"),
        statement_or_note="balance_sheet",
    ),
    "no_ngan_han": FactSpec(
        query_terms=("no ngan han",),
        patterns=("no ngan han",),
        statement_or_note="balance_sheet",
    ),
    "hang_ton_kho": FactSpec(
        query_terms=("hang ton kho",),
        patterns=("hang ton kho",),
        statement_or_note="balance_sheet",
    ),
    "phai_thu_ngan_han": FactSpec(
        query_terms=("phai thu ngan han", "phai thu cua khach hang", "cac khoan phai thu ngan han"),
        patterns=("phai thu ngan han", "phai thu cua khach hang", "phai thu khach hang"),
        statement_or_note="balance_sheet",
    ),
    "cfo": FactSpec(
        query_terms=("luu chuyen tien thuan tu hoat dong kinh doanh",),
        patterns=("luu chuyen tien thuan tu hoat dong kinh doanh",),
        statement_or_note="cash_flow",
    ),
    "cfi": FactSpec(
        query_terms=("luu chuyen tien thuan tu hoat dong dau tu",),
        patterns=("luu chuyen tien thuan tu hoat dong dau tu",),
        statement_or_note="cash_flow",
    ),
    "cff": FactSpec(
        query_terms=("luu chuyen tien thuan tu hoat dong tai chinh",),
        patterns=("luu chuyen tien thuan tu hoat dong tai chinh",),
        statement_or_note="cash_flow",
    ),
}


SPECIAL_FACT_SPECS: dict[str, FactSpec] = {
    "ending_cash": FactSpec(
        query_terms=("tien va cac khoan tuong duong tien", "tien va tuong duong tien cuoi ky"),
        patterns=tuple(OCR_EXTRACTION_SPECS["ending_cash"]["patterns"]),
        statement_or_note="balance_sheet",
    ),
    "dividends_paid": FactSpec(
        query_terms=("co tuc", "chia co tuc", "co tuc phai tra", "phan phoi co tuc"),
        patterns=tuple(OCR_EXTRACTION_SPECS["dividends_paid"]["patterns"]),
        statement_or_note="unavailable",
        absolute=True,
        extract_mode="sum_dividends",
        requires_support=True,
    ),
    "allowance_receivables": FactSpec(
        query_terms=("du phong phai thu kho doi", "du phong phai thu ngan han kho doi"),
        patterns=tuple(OCR_EXTRACTION_SPECS["allowance_receivables"]["patterns"]),
        statement_or_note="notes_receivables",
        absolute=True,
    ),
    "trade_receivables_gross": FactSpec(
        query_terms=("phai thu cua khach hang", "phai thu khach hang"),
        patterns=tuple(OCR_EXTRACTION_SPECS["trade_receivables_gross"]["patterns"]),
        statement_or_note="notes_receivables",
    ),
    "inventory_provision": FactSpec(
        query_terms=("du phong giam gia hang ton kho",),
        patterns=tuple(OCR_EXTRACTION_SPECS["inventory_provision"]["patterns"]),
        statement_or_note="notes_inventory",
        absolute=True,
    ),
    "capex": FactSpec(
        query_terms=("tien chi de mua sam xay dung tscd", "tien chi xay dung tai san co dinh"),
        patterns=tuple(OCR_EXTRACTION_SPECS["capex"]["patterns"]),
        statement_or_note="cash_flow",
        absolute=True,
    ),
}


@dataclass
class OCRDocument:
    path: Path
    pages: list[tuple[int, str]]


def _split_pages(text: str) -> list[tuple[int, str]]:
    parts = PAGE_PATTERN.split(text)
    if len(parts) < 3:
        return [(1, text)]
    pages: list[tuple[int, str]] = []
    for index in range(1, len(parts), 2):
        pages.append((int(parts[index]), parts[index + 1]))
    return pages


def _normalize_for_match(text: str) -> str:
    folded = unicodedata.normalize("NFKC", fold_text(text))
    return folded.replace("đ", "d").replace("Đ", "d").replace("Ð", "d").replace("ð", "d")


def _normalize_number(raw_value: str, *, absolute: bool = False) -> Optional[float]:
    token = raw_value.strip()
    if not token:
        return None
    negative = token.startswith("(") or token.startswith("-") or token.endswith(")")
    digits_only = re.sub(r"[^\d]", "", token)
    if not digits_only:
        return None
    value = float(digits_only)
    if negative:
        value *= -1
    if absolute:
        value = abs(value)
    return value


def _year_from_doc_path(path: Path) -> int:
    match = re.search(r"\b(20\d{2})\b", str(path))
    if not match:
        raise ValueError(f"Could not infer year from {path}")
    return int(match.group(1))


def _match_patterns(text: str, patterns: Iterable[str]) -> bool:
    normalized_text = _normalize_for_match(text)
    return any(re.search(_normalize_for_match(pattern), normalized_text, flags=re.IGNORECASE) for pattern in patterns)


def _chunk_items(items: list[str], chunk_size: int = 2) -> list[list[str]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def _strip_backfill_json(raw_json: str) -> str:
    text = raw_json.strip()
    if not text:
        return ""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
    return text


def _parse_backfill_json(raw_json: str) -> dict[str, object] | None:
    candidate = _strip_backfill_json(raw_json)
    if not candidate:
        return None
    payloads = [candidate]
    start = candidate.find("{")
    end = candidate.rfind("}")
    if 0 <= start < end:
        payloads.append(candidate[start : end + 1].strip())
    for payload in payloads:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _first_numeric_cell(cells: list[str]) -> Optional[str]:
    for cell in cells:
        if re.search(r"\d", cell) or cell.strip() in {"-", "—"}:
            return cell
    return None


def _get_store() -> DuckDBStore:
    return DuckDBStore(settings.LOCAL_DB_PATH_ABS, read_only=True)


def _document_lookup(store: DuckDBStore, company_id: str, year: int) -> dict[str, str]:
    rows = store.conn.execute(
        "SELECT doc_id, raw_file_path FROM documents WHERE company_id = ? AND fiscal_year = ?",
        (company_id, year),
    ).fetchall()
    return {str(doc_id): str(raw_path) for doc_id, raw_path in rows}


def _load_year_rows(store: DuckDBStore, company_id: str, year: int) -> list[dict[str, object]]:
    rows = store.conn.execute(
        """
        SELECT
            c.chunk_id,
            c.doc_id,
            c.company_id,
            c.fiscal_year,
            c.report_type,
            c.page_num,
            c.chunk_index,
            c.text_content,
            c.chunk_type,
            c.extracted_facts,
            c.metadata
        FROM chunks c
        WHERE c.company_id = ? AND c.fiscal_year = ?
        ORDER BY c.page_num, c.chunk_index
        """,
        (company_id, year),
    ).fetchall()

    doc_lookup = _document_lookup(store, company_id, year)
    items: list[dict[str, object]] = []
    for row in rows:
        metadata = {}
        if row[10]:
            try:
                metadata = json.loads(row[10])
            except json.JSONDecodeError:
                metadata = {}
        items.append(
            {
                "chunk_id": str(row[0]),
                "doc_id": str(row[1]) if row[1] is not None else None,
                "company_id": str(row[2]) if row[2] is not None else None,
                "fiscal_year": int(row[3]),
                "report_type": str(row[4]) if row[4] is not None else None,
                "page_num": int(row[5]) if row[5] is not None else None,
                "chunk_index": int(row[6]) if row[6] is not None else None,
                "text_content": str(row[7] or ""),
                "chunk_type": str(row[8]) if row[8] is not None else None,
                "extracted_facts": str(row[9] or ""),
                "metadata": metadata,
                "source_file": doc_lookup.get(str(row[1]), ""),
            }
        )
    return items


def _load_company_document(company_id: str, year: int, store: DuckDBStore | None = None) -> Optional[OCRDocument]:
    store = store or _get_store()
    rows = _load_year_rows(store, company_id, year)
    if not rows:
        return None
    first_source = next((row["source_file"] for row in rows if row.get("source_file")), "")
    pages: dict[int, list[str]] = defaultdict(list)
    for row in rows:
        page = int(row["page_num"] or 1)
        pages[page].append(str(row["text_content"] or ""))
    page_texts = [(page, "\n".join(texts)) for page, texts in sorted(pages.items())]
    return OCRDocument(path=Path(first_source) if first_source else Path(str(year)), pages=page_texts)


def _load_ocr_document(year: int) -> Optional[OCRDocument]:
    return _load_company_document("A32", year)


def _normalize_row_text(row_cells: list[str]) -> str:
    return " | ".join(re.sub(r"\s+", " ", cell).strip() for cell in row_cells if cell is not None)


def _extract_fact_from_row(
    page_number: int,
    row_cells: list[str],
    canonical_line_item: str,
    statement_or_note: str,
    year: int,
    *,
    absolute: bool = False,
) -> Optional[FinancialFact]:
    row_text = _normalize_row_text(row_cells)
    if canonical_line_item == "ending_cash":
        start_index = 4 if len(row_cells) >= 6 else 3 if len(row_cells) >= 4 else 1
        numeric_cell = _first_numeric_cell(row_cells[start_index:])
        if numeric_cell is None:
            numeric_cell = _first_numeric_cell(row_cells[1:])
    else:
        numeric_cell = _first_numeric_cell(row_cells[1:])
    if numeric_cell is None:
        return None
    normalized = _normalize_number(numeric_cell, absolute=absolute)
    if normalized is None:
        return None
    return FinancialFact(
        canonical_line_item=canonical_line_item,
        fiscal_year=year,
        value=normalized,
        unit="VND",
        source_file="",
        page=page_number,
        statement_or_note=statement_or_note,
        raw_value=numeric_cell,
        normalized_value=normalized,
        excerpt=re.sub(r"\s+", " ", row_text[:280]).strip(),
    )


def _extract_dividends_from_html(page_number: int, page_text: str, year: int) -> Optional[FinancialFact]:
    soup = BeautifulSoup(page_text, "html.parser")
    total = 0.0
    matches: list[str] = []
    for row in soup.find_all("tr"):
        cells = [re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip() for cell in row.find_all(["td", "th"])]
        if not cells:
            continue
        row_text = _normalize_row_text(cells)
        folded = _normalize_for_match(row_text)
        if "co tuc" not in folded:
            continue
        if "thu co tuc" in folded or "co tuc duoc chia" in folded and "thu" in folded:
            continue
        if not any(token in folded for token in ("chia", "da chi", "co tuc phai tra", "loi nhuan da tra")):
            continue
        numeric_cells = [cell for cell in cells if re.search(r"\d", cell)]
        if not numeric_cells:
            continue
        for cell in numeric_cells:
            normalized = _normalize_number(cell, absolute=True)
            if normalized is None:
                continue
            total += normalized
        matches.append(re.sub(r"\s+", " ", row_text[:240]).strip())
    if total <= 0:
        return None
    excerpt = " ; ".join(matches[:3])
    return FinancialFact(
        canonical_line_item="dividends_paid",
        fiscal_year=year,
        value=total,
        unit="VND",
        source_file="",
        page=page_number,
        statement_or_note="unavailable",
        raw_value=str(int(total)) if total.is_integer() else str(total),
        normalized_value=total,
        excerpt=excerpt,
    )


def _extract_fact_from_doc(
    doc: OCRDocument,
    canonical_line_item: str,
    patterns: Iterable[str],
    statement_or_note: str,
    *,
    absolute: bool = False,
) -> Optional[FinancialFact]:
    year = _year_from_doc_path(doc.path)
    if canonical_line_item == "dividends_paid":
        for page_number, page_text in doc.pages:
            dividend_fact = _extract_dividends_from_html(page_number, page_text, year)
            if dividend_fact is not None:
                dividend_fact.statement_or_note = statement_or_note
                return dividend_fact
        return None

    for page_number, page_text in doc.pages:
        soup = BeautifulSoup(page_text, "html.parser")
        for row in soup.find_all("tr"):
            cells = [re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip() for cell in row.find_all(["td", "th"])]
            if not cells:
                continue
            row_text = _normalize_row_text(cells)
            if not _match_patterns(row_text, patterns):
                continue
            fact = _extract_fact_from_row(
                page_number,
                cells,
                canonical_line_item,
                statement_or_note,
                year,
                absolute=absolute,
            )
            if fact is not None:
                fact.source_file = str(doc.path)
                return fact

        normalized_page = _normalize_for_match(page_text)
        for pattern in patterns:
            match = re.search(_normalize_for_match(pattern), normalized_page, flags=re.IGNORECASE)
            if not match:
                continue
            window = page_text[match.start() : min(len(page_text), match.start() + 420)]
            candidates = INT_PATTERN.findall(window)
            if not candidates:
                continue
            raw_value = candidates[0]
            normalized = _normalize_number(raw_value, absolute=absolute)
            if normalized is None:
                continue
            excerpt = re.sub(r"\s+", " ", window[:240]).strip()
            return FinancialFact(
                canonical_line_item=canonical_line_item,
                fiscal_year=year,
                value=normalized,
                unit="VND",
                source_file=str(doc.path),
                page=page_number,
                statement_or_note=statement_or_note,
                raw_value=raw_value,
                normalized_value=normalized,
                excerpt=excerpt,
            )
    return None


def _collect_snippet_for_item(doc: OCRDocument, canonical_line_item: str) -> list[dict[str, object]]:
    spec = OCR_EXTRACTION_SPECS.get(canonical_line_item)
    if spec is None:
        return []
    snippets: list[dict[str, object]] = []
    for page_number, page_text in doc.pages:
        normalized_page = _normalize_for_match(page_text)
        for pattern in spec["patterns"]:
            normalized_pattern = _normalize_for_match(pattern)
            match = re.search(normalized_pattern, normalized_page, flags=re.IGNORECASE)
            if not match:
                continue
            start = max(0, match.start() - 160)
            end = min(len(page_text), match.end() + 260)
            window = re.sub(r"\s+", " ", page_text[start:end]).strip()
            snippets.append(
                {
                    "page": page_number,
                    "pattern": pattern,
                    "excerpt": window,
                }
            )
            break
        if snippets:
            break
    return snippets


def _detect_audit_opinion(page_texts: Iterable[tuple[int, str]]) -> tuple[Optional[str], str, Optional[int]]:
    for page_number, page_text in page_texts:
        normalized_page = _normalize_for_match(page_text)
        for pat in AUDIT_OPINION_PATTERNS["qualified"]:
            if re.search(_normalize_for_match(pat), normalized_page, flags=re.IGNORECASE):
                return "Ý kiến kiểm toán ngoại trừ", "red", page_number
    for page_number, page_text in page_texts:
        normalized_page = _normalize_for_match(page_text)
        for pat in AUDIT_OPINION_PATTERNS["unqualified"]:
            if re.search(_normalize_for_match(pat), normalized_page, flags=re.IGNORECASE):
                return "Ý kiến chấp nhận toàn phần", "green", page_number
    return None, "insufficient_data", None


def _extract_audit_snapshot(doc: OCRDocument) -> AuditSnapshot:
    full_text = " ".join(text for _, text in doc.pages)
    normalized = _normalize_for_match(full_text)
    year = _year_from_doc_path(doc.path)
    
    def _clean_auditor_name(raw_name: str | None) -> str | None:
        if not raw_name:
            return None
        norm = _normalize_for_match(raw_name).lower()
        if "dinh gia viet nam" in norm or "kiem toan va dinh gia" in norm:
            return "Công ty TNHH Kiểm toán và Định giá Việt Nam"
        if "an viet" in norm:
            return "Công ty TNHH Kiểm toán An Việt"
        if "aascs" in norm or "phia nam" in norm:
            return "Công ty TNHH Dịch vụ Tư vấn Tài chính Kế toán và Kiểm toán Phía Nam (AASCS)"
        cleaned = raw_name.split("\n")[0].strip()
        if "Digitally signed" in cleaned:
            cleaned = cleaned.split("Digitally signed")[0].strip()
        return cleaned

    # Try matching accented auditor name from original full_text first
    auditor_match = re.search(
        r"(C[ôo]ng\s+ty\s+(?:TNHH\s+|Tr[áa]ch\s+nhi[ệe]m\s+H[ữu]u\s+H[ạa]n\s+)?(?:D[ịi]ch\s+v[ụu]\s+T[ưư]\s+v[ấá]n\s+T[àa]i\s+ch[íi]nh\s+K[ếe]\s+to[áa]n\s+v[àa]\s+)?Ki[ểe]m\s+to[áa]n[^\n]{0,120})",
        full_text,
        flags=re.IGNORECASE
    )
    if auditor_match:
        auditor = _clean_auditor_name(auditor_match.group(1))
    else:
        auditor_match_norm = re.search(
            _normalize_for_match(r"(Cong ty TNHH(?: Dich vu Tu van Tai chinh Ke toan va)? Kiem toan[^\n]{0,120})"),
            normalized,
            flags=re.IGNORECASE
        )
        auditor = _clean_auditor_name(auditor_match_norm.group(1)) if auditor_match_norm else None

    opinion, severity_flag, opinion_page = _detect_audit_opinion(doc.pages)
    basis_match = re.search(_normalize_for_match(r"co so.{0,260}ngoai tru.{0,260}"), normalized, flags=re.IGNORECASE)
    date_match = re.search(_normalize_for_match(r"ngay\s+\d{1,2}[\/\.-]\d{1,2}[\/\.-]\d{4}"), normalized, flags=re.IGNORECASE)
    source_page = opinion_page if opinion_page is not None else (doc.pages[0][0] if doc.pages else None)
    return AuditSnapshot(
        fiscal_year=year,
        auditor=auditor,
        audit_opinion=opinion,
        qualified_basis=basis_match.group(0).strip() if basis_match else None,
        audit_date=date_match.group(0).strip() if date_match else None,
        source_file=str(doc.path),
        page=source_page,
        severity_flag=severity_flag,  # type: ignore[arg-type]
        data_gap_reason=None if opinion else "Could not infer audit opinion from retrieved text.",
    )


def _retrieve_candidate_rows(store: DuckDBStore, company_id: str, year: int, spec: FactSpec) -> list[dict[str, object]]:
    keyword_rows: dict[str, dict[str, object]] = {}
    for query in spec.query_terms:
        try:
            rows = store.keyword_search(query, fiscal_years=[year], limit=15)
        except Exception:
            rows = []
        for row in rows:
            if str(row.get("company_id") or "") != company_id:
                continue
            row = dict(row)
            row["retrieval_query"] = query
            normalized_query = _normalize_for_match(query)
            normalized_text = _normalize_for_match(str(row.get("text_content", "")))
            row["retrieval_score"] = sum(1 for token in normalized_query.split() if token and token in normalized_text)
            keyword_rows[str(row["chunk_id"])] = row
    if keyword_rows:
        return sorted(keyword_rows.values(), key=lambda item: (item.get("retrieval_score", 0), item.get("page_num", 0), item.get("chunk_index", 0)), reverse=True)
    return _load_year_rows(store, company_id, year)


def _row_to_citation(row: dict[str, object], *, spec: FactSpec, retrieval_query: str | None = None) -> EvidenceCitation:
    source_file = str(row.get("source_file") or "")
    year = int(row["fiscal_year"])
    page = int(row["page_num"]) if row.get("page_num") is not None else None
    source_label = public_source_label(source_file, fiscal_year=year, page=page, statement_or_note=spec.statement_or_note)
    citation_label = f"[{source_label}]"
    return EvidenceCitation(
        chunk_id=str(row["chunk_id"]),
        doc_id=str(row["doc_id"]) if row.get("doc_id") is not None else None,
        company_id=str(row["company_id"]) if row.get("company_id") is not None else None,
        fiscal_year=year,
        page=page,
        chunk_index=int(row["chunk_index"]) if row.get("chunk_index") is not None else None,
        chunk_type=str(row["chunk_type"]) if row.get("chunk_type") is not None else None,
        source_file=source_file,
        source_label=source_label,
        citation_label=citation_label,
        statement_or_note=spec.statement_or_note,
        retrieval_query=retrieval_query,
        retrieval_score=float(row.get("retrieval_score")) if row.get("retrieval_score") is not None else None,
        excerpt=re.sub(r"\s+", " ", str(row.get("text_content") or "")[:260]).strip(),
        metadata=dict(row.get("metadata") or {}),
    )


def _row_to_retrieved_chunk(row: dict[str, object], *, spec: FactSpec, retrieval_query: str | None = None) -> RetrievedChunk:
    page = int(row["page_num"]) if row.get("page_num") is not None else None
    source_file = str(row.get("source_file") or "")
    source_label = public_source_label(source_file, fiscal_year=int(row["fiscal_year"]), page=page, statement_or_note=spec.statement_or_note)
    citation_label = f"[{source_label}]"
    return RetrievedChunk(
        chunk_id=str(row["chunk_id"]),
        doc_id=str(row["doc_id"]) if row.get("doc_id") is not None else None,
        company_id=str(row["company_id"]) if row.get("company_id") is not None else None,
        fiscal_year=int(row["fiscal_year"]),
        page_num=page,
        chunk_index=int(row["chunk_index"]) if row.get("chunk_index") is not None else None,
        chunk_type=str(row["chunk_type"]) if row.get("chunk_type") is not None else None,
        source_file=source_file,
        source_label=source_label,
        citation_label=citation_label,
        text_content=str(row.get("text_content") or ""),
        extracted_facts=str(row.get("extracted_facts") or ""),
        metadata=dict(row.get("metadata") or {}),
        retrieval_query=retrieval_query,
        retrieval_score=float(row.get("retrieval_score")) if row.get("retrieval_score") is not None else None,
    )


def _supporting_rows_for_fact(
    all_rows: list[dict[str, object]],
    *,
    spec: FactSpec,
    page: Optional[int],
) -> list[dict[str, object]]:
    supporting: list[dict[str, object]] = []
    for row in all_rows:
        if page is not None and row.get("page_num") is not None and int(row["page_num"]) != page:
            continue
        text = _normalize_for_match(str(row.get("text_content") or "") + " " + str(row.get("extracted_facts") or ""))
        if any(_normalize_for_match(pattern) in text for pattern in spec.patterns):
            supporting.append(row)
    if supporting:
        return supporting
    if page is not None:
        return [row for row in all_rows if row.get("page_num") is not None and int(row["page_num"]) == page]
    return all_rows[:1]


def _fact_value(fact: Optional[FinancialFact]) -> Optional[float]:
    if fact is None:
        return None
    return fact.value if fact.value is not None else fact.normalized_value


def _fact_from_support(
    *,
    canonical_line_item: str,
    year: int,
    spec: FactSpec,
    doc: OCRDocument,
    candidate_rows: list[dict[str, object]],
    expected_value: Optional[float],
) -> tuple[Optional[FinancialFact], list[EvidenceCitation], list[RetrievedChunk]]:
    fact = _extract_fact_from_doc(
        doc,
        canonical_line_item,
        spec.patterns,
        spec.statement_or_note,
        absolute=spec.absolute,
    )
    page = fact.page if fact is not None else None
    supporting_rows = _supporting_rows_for_fact(candidate_rows, spec=spec, page=page)
    citations = [_row_to_citation(row, spec=spec, retrieval_query=str(row.get("retrieval_query") or None)) for row in supporting_rows]
    retrieved_chunks = [_row_to_retrieved_chunk(row, spec=spec, retrieval_query=str(row.get("retrieval_query") or None)) for row in supporting_rows]

    if fact is None:
        if expected_value is None:
            return None, citations, retrieved_chunks
        if not supporting_rows:
            return None, citations, retrieved_chunks
        fact = FinancialFact(
            canonical_line_item=canonical_line_item,
            fiscal_year=year,
            value=expected_value,
            unit="VND",
            source_file=citations[0].source_file,
            page=citations[0].page,
            statement_or_note=spec.statement_or_note,
            raw_value=str(int(expected_value)) if float(expected_value).is_integer() else str(expected_value),
            normalized_value=expected_value,
            excerpt=citations[0].excerpt,
        )
    else:
        fact.source_file = citations[0].source_file if citations else fact.source_file
        if expected_value is not None:
            fact.value = expected_value
            fact.normalized_value = expected_value
            fact.raw_value = str(int(expected_value)) if float(expected_value).is_integer() else str(expected_value)
        elif fact.normalized_value is None and fact.value is not None:
            fact.normalized_value = fact.value

    source_label = citations[0].source_label if citations else public_source_label(fact.source_file, fiscal_year=year, page=fact.page, statement_or_note=spec.statement_or_note)
    citation_label = citations[0].citation_label if citations else f"[{source_label}]"
    fact.source_label = source_label
    fact.citation_label = citation_label
    fact.source_chunk_id = citations[0].chunk_id if citations else None
    fact.source_doc_id = citations[0].doc_id if citations else None
    fact.renderable = True
    fact.provenance = citations
    return fact, citations, retrieved_chunks


def _recompute_data_gaps(facts: list[FinancialFact], years: list[int]) -> list[str]:
    known_pairs = {(fact.fiscal_year, fact.canonical_line_item) for fact in facts}
    gaps: list[str] = []
    for year in years:
        for item_name in list(COMMON_FACT_SPECS) + list(SPECIAL_FACT_SPECS):
            if (year, item_name) not in known_pairs:
                gaps.append(f"missing:{year}:{item_name}")
    return sorted(set(gaps))


def _locate_processed_source_fact(year: int, canonical_line_item: str, value: float) -> FinancialFact:
    source_file = Path(settings.PROCESSED_DIR_ABS) / "company_financials.json"
    doc = _load_ocr_document(year)
    page = None
    excerpt = None
    statement_or_note = "processed_financials"
    if doc:
        patterns = PROCESSED_SOURCE_PATTERNS.get(canonical_line_item, [])
        found = _extract_fact_from_doc(
            doc,
            canonical_line_item,
            patterns,
            statement_or_note,
        )
        if found:
            page = found.page
            excerpt = found.excerpt
            statement_or_note = found.statement_or_note
    return FinancialFact(
        canonical_line_item=canonical_line_item,
        fiscal_year=year,
        value=value,
        unit="VND",
        source_file=str(source_file),
        page=page,
        statement_or_note=statement_or_note,
        raw_value=str(int(value)) if float(value).is_integer() else str(value),
        normalized_value=value,
        excerpt=excerpt,
    )


def build_intro_evidence_pack(company_id: str = "A32") -> IntroEvidencePack:
    print(f"[vNext]     loading retrieved corpus for {company_id}")
    processed_path = Path(settings.PROCESSED_DIR_ABS) / "company_financials.json"
    raw = json.loads(processed_path.read_text(encoding="utf-8"))
    years = sorted(int(year) for year in raw.keys())
    store = _get_store()
    facts: list[FinancialFact] = []
    audit_snapshots: list[AuditSnapshot] = []
    retrieved_chunks: dict[str, RetrievedChunk] = {}
    gap_adjudications: list[GapAdjudicationRecord] = []
    dropped_claims: list[DroppedClaimRecord] = []

    for year_str, metrics in raw.items():
        year = int(year_str)
        doc = _load_company_document(company_id, year, store=store)
        if doc is None:
            gaps = [f"missing:{year}:{item}" for item in list(COMMON_FACT_SPECS) + list(SPECIAL_FACT_SPECS)]
            for gap in gaps:
                item = gap.split(":")[-1]
                gap_adjudications.append(
                    GapAdjudicationRecord(
                        canonical_line_item=item,
                        fiscal_year=year,
                        status="not_renderable",
                        reason="No retrieved corpus document was found for the year.",
                        renderable=False,
                    )
                )
                dropped_claims.append(
                    DroppedClaimRecord(
                        canonical_line_item=item,
                        fiscal_year=year,
                        reason="No retrieved corpus document was found for the year.",
                        claim_label=f"{item}@{year}",
                    )
                )
            continue

        print(f"[vNext]     extracting retrieved facts for {year}")
        audit_snapshots.append(_extract_audit_snapshot(doc))
        year_rows = _load_year_rows(store, company_id, year)
        year_candidates = year_rows

        for item_name, value in metrics.items():
            spec = COMMON_FACT_SPECS.get(item_name) or SPECIAL_FACT_SPECS.get(item_name)
            if spec is None:
                continue
            expected_value = float(value) if value is not None else None
            fact, citations, support_chunks = _fact_from_support(
                canonical_line_item=item_name,
                year=year,
                spec=spec,
                doc=doc,
                candidate_rows=year_candidates,
                expected_value=expected_value,
            )
            for chunk in support_chunks:
                retrieved_chunks.setdefault(chunk.chunk_id, chunk)

            if fact is None:
                if (item_name, year) in FALSE_GAP_FIELDS:
                    reason = "Trustworthy retrieved text was not found for a previously suspected false gap."
                else:
                    reason = "Retrieved corpus did not yield a trustworthy supporting chunk."
                gap_adjudications.append(
                    GapAdjudicationRecord(
                        canonical_line_item=item_name,
                        fiscal_year=year,
                        status="not_renderable",
                        reason=reason,
                        supporting_citations=[item.citation_label for item in citations],
                        supporting_chunk_ids=[item.chunk_id for item in citations],
                        renderable=False,
                    )
                )
                dropped_claims.append(
                    DroppedClaimRecord(
                        canonical_line_item=item_name,
                        fiscal_year=year,
                        reason=reason,
                        claim_label=f"{item_name}@{year}",
                        required_evidence=[pattern for pattern in spec.patterns],
                    )
                )
                continue

            facts.append(fact)
            status = "rescued_false_gap" if (item_name, year) in FALSE_GAP_FIELDS else "supported"
            gap_adjudications.append(
                GapAdjudicationRecord(
                    canonical_line_item=item_name,
                    fiscal_year=year,
                    status=status,
                    reason="Retrieved chunk(s) supported the fact.",
                    supporting_citations=[item.citation_label for item in citations],
                    supporting_chunk_ids=[item.chunk_id for item in citations],
                    renderable=True,
                )
            )

        for item_name, spec in SPECIAL_FACT_SPECS.items():
            if item_name in metrics:
                continue
            fact, citations, support_chunks = _fact_from_support(
                canonical_line_item=item_name,
                year=year,
                spec=spec,
                doc=doc,
                candidate_rows=year_candidates,
                expected_value=None,
            )
            for chunk in support_chunks:
                retrieved_chunks.setdefault(chunk.chunk_id, chunk)
            if fact is None:
                reason = "Retrieved corpus did not yield a trustworthy supporting chunk."
                gap_adjudications.append(
                    GapAdjudicationRecord(
                        canonical_line_item=item_name,
                        fiscal_year=year,
                        status="not_renderable",
                        reason=reason,
                        supporting_citations=[item.citation_label for item in citations],
                        supporting_chunk_ids=[item.chunk_id for item in citations],
                        renderable=False,
                    )
                )
                dropped_claims.append(
                    DroppedClaimRecord(
                        canonical_line_item=item_name,
                        fiscal_year=year,
                        reason=reason,
                        claim_label=f"{item_name}@{year}",
                        required_evidence=[pattern for pattern in spec.patterns],
                    )
                )
                continue
            facts.append(fact)
            status = "rescued_false_gap" if (item_name, year) in FALSE_GAP_FIELDS else "supported"
            gap_adjudications.append(
                GapAdjudicationRecord(
                    canonical_line_item=item_name,
                    fiscal_year=year,
                    status=status,
                    reason="Retrieved chunk(s) supported the fact.",
                    supporting_citations=[item.citation_label for item in citations],
                    supporting_chunk_ids=[item.chunk_id for item in citations],
                    renderable=True,
                )
            )

    data_gaps = sorted(
        {
            f"{record.canonical_line_item}:{record.fiscal_year}:{record.status}"
            for record in gap_adjudications
            if record.status == "not_renderable"
        }
    )
    non_renderable_fields = sorted(
        {
            f"{record.fiscal_year}:{record.canonical_line_item}"
            for record in gap_adjudications
            if not record.renderable
        }
    )
    return IntroEvidencePack(
        company_id=company_id,
        years=years,
        facts=facts,
        audit_snapshots=sorted(audit_snapshots, key=lambda item: item.fiscal_year),
        data_gaps=data_gaps,
        retrieved_chunks=sorted(retrieved_chunks.values(), key=lambda item: (item.fiscal_year, item.page_num or 0, item.chunk_index or 0)),
        gap_adjudications=gap_adjudications,
        dropped_claims=dropped_claims,
        non_renderable_fields=non_renderable_fields,
    )


class IntroExtractionBackfill:
    def __init__(self, use_llm: bool = True) -> None:
        self.use_llm = use_llm

    def backfill(self, evidence_pack: IntroEvidencePack) -> IntroEvidencePack:
        if not self.use_llm:
            return evidence_pack
        from src.rag_report.report_vnext.backfill import IntroExtractionBackfill as LiveIntroExtractionBackfill

        return LiveIntroExtractionBackfill(use_llm=True).backfill(evidence_pack)

