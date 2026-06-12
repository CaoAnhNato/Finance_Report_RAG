from __future__ import annotations

from src.rag_report.report_vnext.backfill import IntroExtractionBackfill
from src.rag_report.report_vnext.charts import IntroChartPlanner, render_intro_charts
from src.rag_report.report_vnext.feedback_log import FeedbackRule, rules_to_style_notes
from src.rag_report.report_vnext.evidence import build_intro_evidence_pack
from src.rag_report.report_vnext.llm import get_llm_call_log, reset_llm_call_log
from src.rag_report.report_vnext.exporter import VNextHTMLExporter
from src.rag_report.report_vnext.metrics import calculate_intro_metrics
from src.rag_report.report_vnext.models import IntroRenderBundle
from src.rag_report.report_vnext.writer import IntroNarrativeWriter
from src.rag_report.report_vnext.editor import IntroNarrativeEditor


class IntroReportVNextPipeline:
    def __init__(
        self,
        *,
        use_llm_extraction: bool = True,
        use_llm_chart_planning: bool = True,
        use_llm_writer: bool = True,
        use_llm_editor: bool = True,
    ) -> None:
        self.use_llm_extraction = use_llm_extraction
        self.use_llm_chart_planning = use_llm_chart_planning
        self.use_llm_writer = use_llm_writer
        self.use_llm_editor = use_llm_editor

    def build_bundle(
        self,
        company_id: str = "A32",
        *,
        style_notes: list[str] | None = None,
        feedback_rules: list[FeedbackRule] | None = None,
    ) -> IntroRenderBundle:
        reset_llm_call_log()
        print("[vNext]   extracting evidence")
        evidence_pack = build_intro_evidence_pack(company_id=company_id)
        evidence_pack = IntroExtractionBackfill(use_llm=self.use_llm_extraction).backfill(evidence_pack)
        feedback_notes: list[str] = []
        for note in list(style_notes or []) + rules_to_style_notes(feedback_rules or []):
            if note not in feedback_notes:
                feedback_notes.append(note)
        print("[vNext]   calculating metrics")
        metric_pack = calculate_intro_metrics(evidence_pack)
        print("[vNext]   planning charts")
        chart_plan = IntroChartPlanner(use_llm=self.use_llm_chart_planning).plan(
            evidence_pack,
            metric_pack,
            style_notes=feedback_notes,
        )
        print("[vNext]   rendering charts")
        charts = render_intro_charts(evidence_pack, metric_pack, chart_plan)
        print("[vNext]   writing narrative")
        narrative = IntroNarrativeWriter(use_llm=self.use_llm_writer).write(
            evidence_pack,
            metric_pack,
            chart_plan,
            style_notes=feedback_notes,
        )
        print("[vNext]   editing narrative")
        narrative = IntroNarrativeEditor(use_llm=self.use_llm_editor).edit(
            narrative,
            evidence_pack,
            metric_pack,
            chart_plan,
            style_notes=feedback_notes,
        )
        print("[vNext]   assembling bundle")
        return IntroRenderBundle(
            evidence_pack=evidence_pack,
            metric_pack=metric_pack,
            chart_plan=chart_plan,
            charts=charts,
            narrative=narrative,
            llm_calls=get_llm_call_log(),
        )

    def generate_html(self, company_id: str = "A32") -> str:
        bundle = self.build_bundle(company_id=company_id)
        return VNextHTMLExporter().compile_report(bundle)
