from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


MetricFlag = Literal["green", "yellow", "red", "insufficient_data"]
TaskType = Literal["planner", "extraction", "financial_reasoning", "chart_planning"]


class FinancialFact(BaseModel):
    canonical_line_item: str
    fiscal_year: int
    value: Optional[float] = None
    unit: str = "VND"
    source_file: str
    page: Optional[int] = None
    statement_or_note: str
    raw_value: Optional[str] = None
    normalized_value: Optional[float] = None
    excerpt: Optional[str] = None
    data_gap_reason: Optional[str] = None
    source_label: Optional[str] = None
    citation_label: Optional[str] = None
    source_chunk_id: Optional[str] = None
    source_doc_id: Optional[str] = None
    renderable: bool = True
    provenance: List["EvidenceCitation"] = Field(default_factory=list)


class EvidenceCitation(BaseModel):
    chunk_id: str
    doc_id: Optional[str] = None
    company_id: Optional[str] = None
    fiscal_year: int
    page: Optional[int] = None
    chunk_index: Optional[int] = None
    chunk_type: Optional[str] = None
    source_file: str
    source_label: str
    citation_label: str
    statement_or_note: str = "unavailable"
    retrieval_query: Optional[str] = None
    retrieval_score: Optional[float] = None
    rerank_score: Optional[float] = None
    excerpt: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    chunk_id: str
    doc_id: Optional[str] = None
    company_id: Optional[str] = None
    fiscal_year: int
    page_num: Optional[int] = None
    chunk_index: Optional[int] = None
    chunk_type: Optional[str] = None
    source_file: str
    source_label: str
    citation_label: str
    text_content: str
    extracted_facts: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    retrieval_query: Optional[str] = None
    retrieval_score: Optional[float] = None
    rerank_score: Optional[float] = None


class GapAdjudicationRecord(BaseModel):
    canonical_line_item: str
    fiscal_year: int
    status: Literal["supported", "rescued_false_gap", "missing", "not_renderable"]
    reason: str
    supporting_citations: List[str] = Field(default_factory=list)
    supporting_chunk_ids: List[str] = Field(default_factory=list)
    renderable: bool = True


class DroppedClaimRecord(BaseModel):
    canonical_line_item: str
    fiscal_year: int
    reason: str
    claim_label: str
    required_evidence: List[str] = Field(default_factory=list)


class AuditSnapshot(BaseModel):
    fiscal_year: int
    auditor: Optional[str] = None
    audit_opinion: Optional[str] = None
    qualified_basis: Optional[str] = None
    emphasis_of_matter: Optional[str] = None
    audit_date: Optional[str] = None
    source_file: Optional[str] = None
    page: Optional[int] = None
    severity_flag: MetricFlag = "insufficient_data"
    data_gap_reason: Optional[str] = None


class IntroEvidencePack(BaseModel):
    company_id: str
    years: List[int]
    facts: List[FinancialFact] = Field(default_factory=list)
    audit_snapshots: List[AuditSnapshot] = Field(default_factory=list)
    data_gaps: List[str] = Field(default_factory=list)
    retrieved_chunks: List[RetrievedChunk] = Field(default_factory=list)
    gap_adjudications: List[GapAdjudicationRecord] = Field(default_factory=list)
    dropped_claims: List[DroppedClaimRecord] = Field(default_factory=list)
    non_renderable_fields: List[str] = Field(default_factory=list)


class MetricInputSource(BaseModel):
    variable_name: str
    fiscal_year: Optional[int] = None
    canonical_line_item: str
    source_file: str
    page: Optional[int] = None
    statement_or_note: str
    raw_value: Optional[str] = None
    normalized_value: Optional[float] = None
    unit: str = "VND"
    excerpt: Optional[str] = None
    data_gap_reason: Optional[str] = None


class MetricRecord(BaseModel):
    metric_id: str
    metric_name: str
    fiscal_year: int
    formula_display: str
    formula_latex: Optional[str] = None
    formula_source: str
    formula_code_version: str
    explanation: str
    takeaway: str = ""
    input_values: Dict[str, Optional[float]] = Field(default_factory=dict)
    input_sources: List[MetricInputSource] = Field(default_factory=list)
    computed_value: Optional[float] = None
    unit: str
    flag: MetricFlag
    notes: List[str] = Field(default_factory=list)
    data_gap_reason: Optional[str] = None


class IntroMetricPack(BaseModel):
    company_id: str
    records: List[MetricRecord] = Field(default_factory=list)


class ChartPlanItem(BaseModel):
    chart_id: str
    title: str
    subtitle: str
    insight_line: str
    enabled: bool
    priority: int = 0
    skip_reason: Optional[str] = None


class IntroChartPlan(BaseModel):
    company_id: str
    items: List[ChartPlanItem] = Field(default_factory=list)


class IntroNarrative(BaseModel):
    company_id: str
    title: str
    markdown: str
    data_gaps: List[str] = Field(default_factory=list)
    verdict: Optional[str] = None
    verdict_source_reliability: Optional[str] = None
    verdict_earnings_quality_2025: Optional[str] = None
    verdict_liquidity_short_term: Optional[str] = None
    verdict_needs_deep_check: Optional[str] = None
    audit_intro: Optional[str] = None
    audit_conclusion: Optional[str] = None


class RenderedChart(BaseModel):
    chart_id: str
    spec: Dict[str, Any]


class IntroRenderBundle(BaseModel):
    evidence_pack: IntroEvidencePack
    metric_pack: IntroMetricPack
    chart_plan: IntroChartPlan
    charts: List[RenderedChart]
    narrative: IntroNarrative
    llm_calls: List[Dict[str, Any]] = Field(default_factory=list)
