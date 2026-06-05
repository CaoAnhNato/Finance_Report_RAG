from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


AgentRole = Literal["coordinator", "analyze", "implement", "review"]
TodoStatus = Literal["pending", "in_progress", "done", "blocked"]
WorkflowStatus = Literal[
    "pending",
    "analysis_done",
    "implementation_batch_done",
    "review_done",
    "blocked",
    "completed",
    "awaiting_user_validation",
]
WorkflowPhase = Literal["bootstrap", "analyze", "implement", "review", "blocked", "complete"]
ReasoningLevel = Literal["high"]
TestStatus = Literal["not_run", "partial_pass", "pass", "fail", "blocked"]
ImplementationStatus = Literal["implemented", "blocked_missing_input", "blocked_other"]
ReviewDecision = Literal["approve", "rework"]
ReviewStatus = Literal["approved", "rework"]
TestOutcome = Literal["passed", "failed", "skipped", "blocked"]
FindingSeverity = Literal["low", "medium", "high", "critical"]


class TodoItem(BaseModel):
    id: str = Field(description="Stable TODO item identifier.")
    title: str = Field(description="Short task title.")
    status: TodoStatus = Field(default="pending", description="Current completion state.")


class TaskEnvelope(BaseModel):
    task_id: str
    role: AgentRole
    actor_model: str
    actor_reasoning: ReasoningLevel
    objective: str
    constraints: List[str] = Field(default_factory=list)
    files: List[str] = Field(default_factory=list)
    artifact_refs: List[str] = Field(default_factory=list)
    acceptance_checks: List[str] = Field(default_factory=list)
    budget_hint: Optional[str] = None


class AnalysisBrief(BaseModel):
    actor_model: str
    actor_reasoning: ReasoningLevel
    problem_frame: str
    files_to_touch: List[str] = Field(default_factory=list)
    proposed_steps: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    needed_checks: List[str] = Field(default_factory=list)
    required_docs: List[str] = Field(default_factory=list)
    recommended_tests: List[str] = Field(default_factory=list)


class ImplementationPacket(BaseModel):
    actor_model: str
    actor_reasoning: ReasoningLevel
    locked_scope: str
    edit_goals: List[str] = Field(default_factory=list)
    files_allowed: List[str] = Field(default_factory=list)
    tests_to_run: List[str] = Field(default_factory=list)
    must_not_change: List[str] = Field(default_factory=list)
    requires_official_docs: bool = False
    external_dependencies: List[str] = Field(default_factory=list)


class TestResult(BaseModel):
    command: str
    outcome: TestOutcome
    summary: str


class ImplementationResult(BaseModel):
    actor_model: str
    actor_reasoning: ReasoningLevel
    status: ImplementationStatus
    changed_files: List[str] = Field(default_factory=list)
    edit_summary: List[str] = Field(default_factory=list)
    commands_run: List[str] = Field(default_factory=list)
    test_outcomes: List[TestResult] = Field(default_factory=list)
    open_issues: List[str] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)


class ReviewFinding(BaseModel):
    severity: FindingSeverity
    message: str
    file_path: Optional[str] = None


class ReviewResult(BaseModel):
    actor_model: str
    actor_reasoning: ReasoningLevel
    status: ReviewStatus
    findings: List[ReviewFinding] = Field(default_factory=list)
    missing_tests: List[str] = Field(default_factory=list)
    regression_risks: List[str] = Field(default_factory=list)
    required_rework: List[str] = Field(default_factory=list)
    approve_or_rework: ReviewDecision


class AgentPolicy(BaseModel):
    model: str
    reasoning: ReasoningLevel
    tool_permissions: List[str] = Field(default_factory=list)
    max_output_chars: int = Field(ge=500)
    can_edit: bool = False


class SubagentPolicySet(BaseModel):
    default_model: str
    default_reasoning: Literal["high"]
    roles: dict[Literal["analyze", "implement", "review"], AgentPolicy]


class CodingWorkflowManifest(BaseModel):
    schema_version: str
    workflow_name: Literal["coding-multi-agent"]
    override_allowed: Literal[False]
    result_schema_version: str
    coordinator: AgentPolicy
    subagents: SubagentPolicySet

    @model_validator(mode="after")
    def validate_locked_models(self) -> "CodingWorkflowManifest":
        if self.coordinator.model != "gpt-5.4":
            raise ValueError("Coordinator model must stay locked to gpt-5.4.")
        if self.coordinator.reasoning != "high":
            raise ValueError("Coordinator reasoning must stay locked to high.")
        if self.subagents.default_model != "gpt-5.4-mini":
            raise ValueError("Sub-agent default model must stay locked to gpt-5.4-mini.")
        if self.subagents.default_reasoning != "high":
            raise ValueError("Sub-agent default reasoning must stay locked to high.")
        for role_name, policy in self.subagents.roles.items():
            if policy.model != "gpt-5.4-mini":
                raise ValueError(f"{role_name} must use gpt-5.4-mini.")
            if policy.reasoning != "high":
                raise ValueError(f"{role_name} reasoning must stay at high.")
        analyze = self.subagents.roles["analyze"]
        review = self.subagents.roles["review"]
        implement = self.subagents.roles["implement"]
        if analyze.can_edit:
            raise ValueError("Analyze role must not edit files.")
        if review.can_edit:
            raise ValueError("Review role must not edit files.")
        if not implement.can_edit:
            raise ValueError("Implement role must retain edit capability.")
        return self


class CoordinatorInitState(BaseModel):
    task_id: str
    objective: str
    status: WorkflowStatus
    active_phase: WorkflowPhase
    todo_items: List[TodoItem] = Field(default_factory=list)
    decisions_locked: List[str] = Field(default_factory=list)
    files_in_scope: List[str] = Field(default_factory=list)
    files_touched: List[str] = Field(default_factory=list)
    analysis_brief_ref: Optional[str] = None
    implementation_brief_ref: Optional[str] = None
    review_brief_ref: Optional[str] = None
    test_commands: List[str] = Field(default_factory=list)
    test_status: TestStatus = "not_run"
    open_questions: List[str] = Field(default_factory=list)
    next_action: str
    compact_brief: str


class StyleAuditFinding(BaseModel):
    check: str
    passed: bool
    severity: FindingSeverity = "low"
    message: str


class StyleAuditResult(BaseModel):
    report_path: str
    reference_path: Optional[str] = None
    overall_pass: bool
    score: float
    findings: List[StyleAuditFinding] = Field(default_factory=list)
    benchmark_gap_notes: List[str] = Field(default_factory=list)
    browser_ready: bool = False
    browser_notes: List[str] = Field(default_factory=list)
    attempt_index: int = 0
