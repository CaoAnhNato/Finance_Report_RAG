from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from src.rag_report.config import settings
from src.rag_report.coding_workflow.models import FindingSeverity, StyleAuditFinding, StyleAuditResult
from src.rag_report.report_vnext.feedback_log import FeedbackRule, feedback_rule_from_issue
from src.rag_report.report_vnext.formatting import fold_text
from src.rag_report.report_vnext.models import IntroNarrative


BANNED_PATTERNS = [
    (r"bước\s+\d+", "Bước + số thứ tự (ví dụ: Bước 1)"),
    (r"câu\s+trả\s+lời\s+nhanh", "Câu trả lời nhanh"),
    (r"kết\s+luận\s+nhanh\s+cho\s+người\s+không\s+chuyên", "Kết luận nhanh cho người không chuyên"),
    (r"kết\s+luận\s+nhanh", "Kết luận nhanh"),
    (r"người\s+không\s+chuyên", "người không chuyên"),
    (r"người\s+ngoài\s+ngành", "người ngoài ngành"),
    (r"tiền\s+thật", "tiền thật"),
    (r"doanh\s+nghiệp\s+khỏe", "doanh nghiệp khỏe"),
    (r"điểm\s+cần\s+kiểm\s+tra\s+tiếp\s+theo", "Điểm cần kiểm tra tiếp theo"),
    (r"chốt\s+lại\s+phần\s+mở\s+đầu", "Chốt lại phần mở đầu"),
]


def narrative_wording_hygiene(narrative: IntroNarrative) -> list[FeedbackRule]:
    """
    Scans IntroNarrative fields to detect any banned/informal terms.
    Returns a list of FeedbackRule objects if violations are found.
    """
    violations = []
    
    # Text fields to scan
    text_fields = [
        ("title", narrative.title),
        ("markdown", narrative.markdown),
        ("audit_intro", narrative.audit_intro),
        ("audit_conclusion", narrative.audit_conclusion),
        ("verdict", narrative.verdict),
        ("verdict_source_reliability", narrative.verdict_source_reliability),
        ("verdict_earnings_quality_2025", narrative.verdict_earnings_quality_2025),
        ("verdict_liquidity_short_term", narrative.verdict_liquidity_short_term),
        ("verdict_needs_deep_check", narrative.verdict_needs_deep_check),
    ]
    
    # Contract details to scan if present
    if narrative.report_contract:
        contract = narrative.report_contract
        if contract.executive_verdict:
            verdict = contract.executive_verdict
            text_fields.append(("executive_verdict.source_reliability", verdict.source_reliability))
            text_fields.append(("executive_verdict.financial_signal", verdict.financial_signal))
            text_fields.append(("executive_verdict.main_message", verdict.main_message))
            for i, area in enumerate(verdict.focus_areas):
                text_fields.append((f"executive_verdict.focus_areas[{i}]", area))
        for i, sig in enumerate(contract.key_signals):
            text_fields.append((f"key_signals[{i}].question", sig.question))
            text_fields.append((f"key_signals[{i}].conclusion", sig.conclusion))
            text_fields.append((f"key_signals[{i}].plain_explanation", sig.plain_explanation))
            
    for field_name, value in text_fields:
        if not value:
            continue
        for pattern, name in BANNED_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                msg = f"Trường '{field_name}' chứa từ ngữ không chuẩn mực: '{name}'"
                rule = feedback_rule_from_issue(
                    check="narrative_wording_hygiene",
                    message=msg,
                    source="audit",
                )
                violations.append(rule)
                
    return violations


LOCAL_PATH_PATTERNS = [
    r"[A-Za-z]:(?:\\{1,2})(?!\\)[^\s<>\"]+",
    r"[A-Za-z]:/(?!/)[^\s<>\"]+",
    r"/Users/",
    r"\\Users\\",
    r"source_file",
]


def _path_leak_detected(text: str) -> bool:
    if any(re.search(pattern, text) for pattern in LOCAL_PATH_PATTERNS):
        return True
    folded = fold_text(text)
    return "c:\\users" in folded or "/users/" in folded or "source_file" in folded


def _has_a4_layout(soup: BeautifulSoup, text: str) -> bool:
    return "@page" in text and "size: a4" in fold_text(text) and bool(soup.select_one(".report-page"))


def _citation_numbering_ok(soup: BeautifulSoup) -> bool:
    refs = soup.select(".cite-ref[data-cite-number]")
    if not refs:
        return False
    numbers = sorted({int(ref.get("data-cite-number", "0")) for ref in refs if str(ref.get("data-cite-number", "")).isdigit()})
    return numbers == list(range(1, len(numbers) + 1))


def _has_hover_source(soup: BeautifulSoup) -> bool:
    return bool(soup.select(".cite-ref")) and bool(soup.select(".cite-tooltip"))


def _chart_readability_ok(soup: BeautifulSoup) -> bool:
    if soup.select(".chart-placeholder"):
        return False
    figures = soup.select("figure.report-figure")
    if not figures:
        return True
    for figure in figures:
        if figure.get("data-renderable") != "true":
            return False
        if not figure.select_one(".chart-mount"):
            return False
        if not figure.select_one(".figure-caption"):
            return False
    return True


def _matching_finding(findings: list[StyleAuditFinding], check: str) -> StyleAuditFinding | None:
    for finding in findings:
        if finding.check == check:
            return finding
    return None


def _apply_feedback_rule(
    *,
    html_text: str,
    folded_html: str,
    findings: list[StyleAuditFinding],
    audit_text: str,
    rule: FeedbackRule,
) -> tuple[bool, str | None, float]:
    if not rule.active:
        return True, None, 0.0

    if rule.manual_gap:
        return True, rule.message, 0.0

    if rule.check:
        finding = _matching_finding(findings, rule.check)
        if finding is None:
            return False, f"Missing persisted feedback check '{rule.check}' in audit output.", 0.12
        if not finding.passed:
            return False, f"Persisted feedback check '{rule.check}' failed: {finding.message}", 0.12
        return True, None, 0.0

    if rule.html_contains:
        if rule.html_contains in html_text or fold_text(rule.html_contains) in folded_html:
            return True, None, 0.0
        return False, f"HTML is missing persisted feedback text '{rule.html_contains}'.", 0.10

    if rule.audit_contains:
        if rule.audit_contains in audit_text or fold_text(rule.audit_contains) in fold_text(audit_text):
            return True, None, 0.0
        return False, f"Audit output is missing persisted feedback text '{rule.audit_contains}'.", 0.10

    return True, None, 0.0


def audit_report_html(
    html_text: str,
    *,
    report_path: str,
    reference_path: str | None = None,
    feedback_rules: list[FeedbackRule] | None = None,
    narrative: IntroNarrative | None = None,
) -> StyleAuditResult:
    soup = BeautifulSoup(html_text, "html.parser")
    findings: list[StyleAuditFinding] = []
    score = 1.0
    benchmark_gap_notes: list[str] = []
    browser_notes: list[str] = []

    def add_find(
        check: str,
        passed: bool,
        message: str,
        severity: FindingSeverity = "low",
        penalty: float = 0.0,
    ) -> None:
        nonlocal score
        findings.append(StyleAuditFinding(check=check, passed=passed, severity=severity, message=message))
        if not passed:
            score = max(0.0, score - penalty)

    folded = fold_text(soup.get_text(" ", strip=True))
    feedback_rules = list(feedback_rules or [])

    add_find(
        "paged_layout",
        _has_a4_layout(soup, html_text) and bool(soup.select(".report-page")),
        "Report should use an A4 paged layout with explicit page sections.",
        severity="high",
        penalty=0.22,
    )
    add_find(
        "citation_numbering",
        _citation_numbering_ok(soup),
        "Citations should be numbered consecutively and rendered as hoverable refs.",
        severity="high",
        penalty=0.18,
    )
    add_find(
        "hover_source",
        _has_hover_source(soup),
        "Inline citations must expose hover source popovers.",
        severity="high",
        penalty=0.14,
    )
    add_find(
        "path_hygiene",
        not _path_leak_detected(html_text),
        "HTML must not expose local filesystem paths or internal field names.",
        severity="critical",
        penalty=0.24,
    )
    add_find(
        "chart_readability",
        _chart_readability_ok(soup),
        "Charts must either render cleanly or be omitted entirely.",
        severity="high",
        penalty=0.16,
    )

    # Check signal glossary presence and coverage
    signal_glossary_box = soup.select_one(".term-box")
    signal_glossary_ok = False
    signal_glossary_msg = "Thiếu bảng thuật ngữ tín hiệu tài chính."
    if signal_glossary_box:
        box_text = fold_text(signal_glossary_box.get_text(" ", strip=True))
        missing_terms = [t for t in ["CFO", "LNST"] if fold_text(t) not in box_text]
        if missing_terms:
            signal_glossary_msg = f"Bảng thuật ngữ tín hiệu thiếu các từ bắt buộc: {', '.join(missing_terms)}"
        else:
            signal_glossary_ok = True
            signal_glossary_msg = "Bảng thuật ngữ tín hiệu tài chính đầy đủ."

    add_find(
        "signal_glossary_present",
        signal_glossary_ok,
        signal_glossary_msg,
        severity="high",
        penalty=0.15,
    )

    # Check appendix glossary presence and coverage
    appendix_glossary_section = soup.select_one(".glossary-section")
    appendix_glossary_ok = False
    appendix_glossary_msg = "Thiếu bảng thuật ngữ phụ lục kỹ thuật."
    if appendix_glossary_section:
        sec_text = fold_text(appendix_glossary_section.get_text(" ", strip=True))
        required_appendix_terms = ["Lợi nhuận sau thuế", "Dòng tiền từ hoạt động kinh doanh"]
        missing_appendix_terms = [t for t in required_appendix_terms if fold_text(t) not in sec_text]
        if missing_appendix_terms:
            appendix_glossary_msg = f"Bảng thuật ngữ phụ lục thiếu các từ bắt buộc: {', '.join(missing_appendix_terms)}"
        else:
            appendix_glossary_ok = True
            appendix_glossary_msg = "Bảng thuật ngữ phụ lục kỹ thuật đầy đủ."

    add_find(
        "appendix_glossary_present",
        appendix_glossary_ok,
        appendix_glossary_msg,
        severity="high",
        penalty=0.15,
    )

    # Narrative hygiene check
    banned_violations = []
    if narrative:
        banned_violations = narrative_wording_hygiene(narrative)
    else:
        # Fallback to check raw HTML text for banned patterns
        for pattern, name in BANNED_PATTERNS:
            if re.search(pattern, html_text, re.IGNORECASE):
                banned_violations.append(
                    feedback_rule_from_issue(
                        check="narrative_wording_hygiene",
                        message=f"Báo cáo chứa từ ngữ không chuẩn mực: '{name}'",
                        source="audit"
                    )
                )

    add_find(
        "narrative_wording_hygiene",
        len(banned_violations) == 0,
        "Văn phong báo cáo không được chứa các từ ngữ không chuẩn mực (Bước X, câu trả lời nhanh, tiền thật, người không chuyên, etc.)." if banned_violations else "Văn phong báo cáo chuẩn mực.",
        severity="high",
        penalty=0.15,
    )

    for i, violation in enumerate(banned_violations):
        add_find(
            f"hygiene_violation_{i}",
            False,
            violation.message,
            severity="high",
            penalty=0.05,
        )

    if soup.select_one(".report-page") is None:
        benchmark_gap_notes.append("Thiếu cấu trúc A4 theo trang.")
    if "company:" in folded or "scope:" in folded or "view:" in folded:
        benchmark_gap_notes.append("Còn meta block kiểu dashboard trong HTML.")

    if reference_path:
        reference = Path(reference_path)
        if reference.exists():
            ref_text = reference.read_text(encoding="utf-8", errors="ignore")
            ref_figures = ref_text.count("figure")
            current_figures = html_text.count("report-figure")
            if current_figures < max(1, ref_figures // 3):
                benchmark_gap_notes.append("Mật độ figure thấp hơn benchmark tham chiếu.")
        else:
            benchmark_gap_notes.append(f"Reference path missing: {reference_path}")

    audit_preview_text = json.dumps(
        {
            "report_path": report_path,
            "reference_path": reference_path,
            "findings": [finding.model_dump(exclude_none=False) for finding in findings],
            "benchmark_gap_notes": benchmark_gap_notes,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    for rule in feedback_rules:
        passed, note, penalty = _apply_feedback_rule(
            html_text=html_text,
            folded_html=folded,
            findings=findings,
            audit_text=audit_preview_text,
            rule=rule,
        )
        if rule.manual_gap and note:
            benchmark_gap_notes.append(note)
            browser_notes.append(note)
            continue
        if note is not None:
            add_find(
                f"feedback::{rule.rule_id}",
                passed,
                note,
                severity="high",
                penalty=penalty,
            )

    style_pass = score >= settings.VNEXT_AUDIT_THRESHOLD and all(
        finding.passed for finding in findings if finding.severity in {"critical", "high"}
    )
    return StyleAuditResult(
        report_path=report_path,
        reference_path=reference_path,
        overall_pass=style_pass,
        score=round(score, 4),
        findings=findings,
        benchmark_gap_notes=benchmark_gap_notes,
        browser_ready=style_pass,
        browser_notes=browser_notes,
        attempt_index=0,
    )


def write_audit_artifact(output_dir: str | Path, audit: StyleAuditResult, *, filename: str = "style_audit.json") -> str:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    target = output_path / filename
    target.write_text(audit.model_dump_json(indent=2, exclude_none=False), encoding="utf-8")
    return str(target)
