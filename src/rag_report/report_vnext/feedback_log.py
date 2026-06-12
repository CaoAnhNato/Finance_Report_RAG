from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal

from pydantic import BaseModel, Field

from src.rag_report.config import settings


FeedbackSource = Literal["session", "audit", "manual"]


class FeedbackRule(BaseModel):
    rule_id: str
    message: str
    check: str | None = None
    html_contains: str | None = None
    audit_contains: str | None = None
    manual_gap: bool = False
    active: bool = True
    source: FeedbackSource = "session"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


def feedback_log_path() -> Path:
    return Path(settings.REPORT_OUTPUT_DIR_ABS) / "vnext_feedback_log.jsonl"


def _default_rules() -> list[FeedbackRule]:
    return [
        FeedbackRule(
            rule_id="seed::paged_layout",
            check="paged_layout",
            message="Keep the report in an A4 paged layout with explicit page sections.",
            source="manual",
        ),
        FeedbackRule(
            rule_id="seed::citation_numbering",
            check="citation_numbering",
            message="Keep citations numbered consecutively and hoverable.",
            source="manual",
        ),
        FeedbackRule(
            rule_id="seed::hover_source",
            check="hover_source",
            message="Keep inline citations with hover source popovers.",
            source="manual",
        ),
        FeedbackRule(
            rule_id="seed::path_hygiene",
            check="path_hygiene",
            message="Do not expose local file system paths or internal field names.",
            source="manual",
        ),
        FeedbackRule(
            rule_id="seed::chart_readability",
            check="chart_readability",
            message="Keep charts renderable or omit them entirely.",
            source="manual",
        ),
        FeedbackRule(
            rule_id="seed::signal_glossary_present",
            check="signal_glossary_present",
            message="Keep signal-specific glossary term definitions box present and complete.",
            source="manual",
        ),
        FeedbackRule(
            rule_id="seed::appendix_glossary_present",
            check="appendix_glossary_present",
            message="Keep appendix glossary section with full definitions present and complete.",
            source="manual",
        ),
        FeedbackRule(
            rule_id="seed::screenshot_compare_manual",
            message="Screenshot comparison is not automated in code; record the gap and require manual review.",
            manual_gap=True,
            source="manual",
        ),
    ]


def _stable_rule_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}::{digest}"


def load_feedback_rules(path: str | Path | None = None) -> list[FeedbackRule]:
    target = Path(path) if path is not None else feedback_log_path()
    if not target.exists():
        return []
    rules: list[FeedbackRule] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rules.append(FeedbackRule.model_validate_json(line))
    return rules


def save_feedback_rules(rules: Iterable[FeedbackRule], path: str | Path | None = None) -> Path:
    target = Path(path) if path is not None else feedback_log_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = list(rules)
    payload = "\n".join(rule.model_dump_json(exclude_none=False) for rule in normalized)
    if payload:
        payload += "\n"
    target.write_text(payload, encoding="utf-8")
    return target


def seed_feedback_log(path: str | Path | None = None) -> list[FeedbackRule]:
    target = Path(path) if path is not None else feedback_log_path()
    existing = load_feedback_rules(target)
    if existing:
        return existing
    rules = _default_rules()
    save_feedback_rules(rules, target)
    return rules


def upsert_feedback_rule(rule: FeedbackRule, path: str | Path | None = None) -> list[FeedbackRule]:
    target = Path(path) if path is not None else feedback_log_path()
    rules_by_id = {existing.rule_id: existing for existing in load_feedback_rules(target)}
    rules_by_id[rule.rule_id] = rule
    ordered = list(rules_by_id.values())
    save_feedback_rules(ordered, target)
    return ordered


def append_feedback_rules(rules: Iterable[FeedbackRule], path: str | Path | None = None) -> list[FeedbackRule]:
    target = Path(path) if path is not None else feedback_log_path()
    merged = {existing.rule_id: existing for existing in load_feedback_rules(target)}
    for rule in rules:
        merged[rule.rule_id] = rule
    ordered = list(merged.values())
    save_feedback_rules(ordered, target)
    return ordered


def rules_to_style_notes(rules: Iterable[FeedbackRule]) -> list[str]:
    notes: list[str] = []
    for rule in rules:
        if not rule.active or rule.manual_gap:
            continue
        if rule.check:
            notes.append(f"{rule.check}: {rule.message}")
        elif rule.html_contains:
            notes.append(rule.message)
        elif rule.audit_contains:
            notes.append(rule.message)
    return notes


def feedback_rule_from_issue(
    *,
    check: str | None = None,
    message: str,
    html_contains: str | None = None,
    audit_contains: str | None = None,
    manual_gap: bool = False,
    source: FeedbackSource = "audit",
) -> FeedbackRule:
    seed = "|".join(
        [
            check or "",
            html_contains or "",
            audit_contains or "",
            message,
            "manual" if manual_gap else "auto",
            source,
        ]
    )
    return FeedbackRule(
        rule_id=_stable_rule_id("issue", seed),
        check=check,
        html_contains=html_contains,
        audit_contains=audit_contains,
        manual_gap=manual_gap,
        message=message,
        source=source,
    )


def feedback_rules_from_findings(findings: Iterable[object]) -> list[FeedbackRule]:
    rules: list[FeedbackRule] = []
    for finding in findings:
        check = getattr(finding, "check", None)
        passed = bool(getattr(finding, "passed", True))
        message = str(getattr(finding, "message", ""))
        if check and not passed:
            rules.append(
                feedback_rule_from_issue(
                    check=check,
                    message=message,
                )
            )
    return rules


def feedback_rules_from_gap_notes(notes: Iterable[str]) -> list[FeedbackRule]:
    return [
        feedback_rule_from_issue(
            message=note,
            manual_gap=True,
        )
        for note in notes
    ]
