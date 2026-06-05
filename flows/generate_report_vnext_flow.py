import logging
import os
import sys
from datetime import datetime
from pathlib import Path

venv_root = Path(os.environ.get("VIRTUAL_ENV", "")) if os.environ.get("VIRTUAL_ENV") else Path(sys.executable).resolve().parent.parent
desktop_ini = venv_root / "Lib" / "site-packages" / "jsonschema_specifications" / "schemas" / "desktop.ini"
if desktop_ini.exists() and desktop_ini.is_file():
    desktop_ini.unlink()
broken_jsonschema_layout = (
    venv_root
    / "Lib"
    / "site-packages"
    / "jsonschema_specifications"
    / "schemas"
    / "draft201909"
    / "vocabularies"
).is_dir()

try:
    if broken_jsonschema_layout:
        raise RuntimeError("Local jsonschema_specifications layout is incompatible with Prefect/jsonschema auto-loading.")
    from prefect import flow, task
except Exception:
    def flow(*_args, **_kwargs):
        def decorator(fn):
            return fn

        return decorator

    def task(*_args, **_kwargs):
        def decorator(fn):
            return fn

        return decorator

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
if sys.stderr.encoding != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.rag_report.config import settings
from src.rag_report.report_vnext.audit import audit_report_html, write_audit_artifact
from src.rag_report.report_vnext.feedback_log import (
    append_feedback_rules,
    feedback_rules_from_findings,
    feedback_rules_from_gap_notes,
    rules_to_style_notes,
    seed_feedback_log,
)
from src.rag_report.report_vnext.pipeline import IntroReportVNextPipeline
from src.rag_report.report_vnext.exporter import VNextHTMLExporter


logger = logging.getLogger(__name__)


@task(name="Generate vNext Intro HTML")
def generate_vnext_intro_html(
    use_llm_extraction: bool = True,
    use_llm_chart_planning: bool = True,
    use_llm_writer: bool = True,
    style_notes: list[str] | None = None,
    feedback_rules: list | None = None,
) -> str:
    pipeline = IntroReportVNextPipeline(
        use_llm_extraction=use_llm_extraction,
        use_llm_chart_planning=use_llm_chart_planning,
        use_llm_writer=use_llm_writer,
    )
    bundle = pipeline.build_bundle(
        company_id="A32",
        style_notes=style_notes,
        feedback_rules=feedback_rules,
    )
    return VNextHTMLExporter().compile_report(bundle)


@flow(name="Prefect Report Generation Flow vNext")
def run_report_vnext_flow(
    use_llm_extraction: bool = True,
    use_llm_chart_planning: bool = True,
    use_llm_writer: bool = True,
) -> str:
    logger.info("Starting vNext intro report generation flow.")
    reference_path = settings.REPORT_BENCHMARK_REFERENCE_HTML
    feedback_rules = seed_feedback_log()
    style_notes = rules_to_style_notes(feedback_rules)
    last_html_path = ""
    last_audit = None
    max_attempts = max(1, settings.VNEXT_MAX_ATTEMPTS)
    for attempt in range(1, max_attempts + 1):
        print(f"[vNext] attempt {attempt}/{settings.VNEXT_MAX_ATTEMPTS}: building bundle")
        html_path = generate_vnext_intro_html(
            use_llm_extraction=use_llm_extraction,
            use_llm_chart_planning=use_llm_chart_planning,
            use_llm_writer=use_llm_writer,
            style_notes=style_notes or None,
            feedback_rules=feedback_rules,
        )
        audit = audit_report_html(
            Path(html_path).read_text(encoding="utf-8"),
            report_path=html_path,
            reference_path=reference_path,
            feedback_rules=feedback_rules,
        )
        audit.attempt_index = attempt
        attempt_dir = Path(settings.REPORT_OUTPUT_DIR_ABS) / "eval_runs" / f"vnext_intro_{datetime.now().strftime('%Y%m%d_%H%M%S')}_attempt_{attempt}"
        audit_path = write_audit_artifact(attempt_dir, audit)
        logger.info("Attempt %s score=%.3f pass=%s audit=%s", attempt, audit.score, audit.overall_pass, audit_path)
        print(f"[vNext] attempt {attempt}: score={audit.score:.3f} pass={audit.overall_pass}")
        last_html_path = html_path
        last_audit = audit
        if audit.overall_pass:
            return html_path
        new_feedback_rules = feedback_rules_from_findings(finding for finding in audit.findings if not finding.passed)
        known_messages = {rule.message for rule in feedback_rules}
        new_feedback_rules.extend(
            feedback_rules_from_gap_notes(note for note in audit.benchmark_gap_notes if note not in known_messages)
        )
        if new_feedback_rules:
            feedback_rules = append_feedback_rules(new_feedback_rules)
        style_notes = rules_to_style_notes(feedback_rules)

    raise RuntimeError(
        "vNext intro report did not pass audit after "
        f"{settings.VNEXT_MAX_ATTEMPTS} attempts. "
        f"Last score={last_audit.score if last_audit else 'n/a'}, output={last_html_path}, "
        f"notes={last_audit.benchmark_gap_notes if last_audit else []}"
    )


if __name__ == "__main__":
    print(run_report_vnext_flow())
