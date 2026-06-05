from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from src.rag_report.coding_workflow.models import (
    AnalysisBrief,
    CodingWorkflowManifest,
    CoordinatorInitState,
    ImplementationResult,
    ReviewResult,
    TodoItem,
)


EXPECTED_SUBAGENT_MODEL = "gpt-5.4-mini"
EXPECTED_SUBAGENT_REASONING = "high"


def load_manifest(path: str | Path) -> CodingWorkflowManifest:
    return CodingWorkflowManifest.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_template_state(path: str | Path) -> CoordinatorInitState:
    return CoordinatorInitState.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_init_state(path: str | Path) -> CoordinatorInitState:
    return CoordinatorInitState.model_validate_json(Path(path).read_text(encoding="utf-8"))


def save_init_state(path: str | Path, state: CoordinatorInitState) -> None:
    Path(path).write_text(
        state.model_dump_json(indent=2, exclude_none=False),
        encoding="utf-8",
    )


def build_init_state(task_id: str, objective: str, todo_titles: Iterable[str]) -> CoordinatorInitState:
    todos = [
        TodoItem(id=f"todo-{idx}", title=title, status="pending")
        for idx, title in enumerate(todo_titles, start=1)
    ]
    return CoordinatorInitState(
        task_id=task_id,
        objective=objective,
        status="pending",
        active_phase="bootstrap",
        todo_items=todos,
        decisions_locked=[],
        files_in_scope=[],
        files_touched=[],
        analysis_brief_ref=None,
        implementation_brief_ref=None,
        review_brief_ref=None,
        test_commands=[],
        test_status="not_run",
        open_questions=[],
        next_action="run_analyze",
        compact_brief="Bootstrap complete. Analyze phase is next.",
    )


def build_compact_brief(state: CoordinatorInitState) -> str:
    scope = ", ".join(state.files_in_scope) if state.files_in_scope else "none"
    touched = ", ".join(state.files_touched) if state.files_touched else "none"
    return (
        f"Task {state.task_id}: {state.objective}. "
        f"Status={state.status}, phase={state.active_phase}, "
        f"scope={scope}, touched={touched}, next_action={state.next_action}."
    )


def _assert_actor_identity(role: str, actor_model: str, actor_reasoning: str) -> None:
    if actor_model != EXPECTED_SUBAGENT_MODEL or actor_reasoning != EXPECTED_SUBAGENT_REASONING:
        raise ValueError(
            f"{role} actor mismatch: expected {EXPECTED_SUBAGENT_MODEL}/{EXPECTED_SUBAGENT_REASONING}, "
            f"got {actor_model}/{actor_reasoning}."
        )


def route_after_analysis(
    state: CoordinatorInitState,
    analysis: AnalysisBrief,
    analysis_ref: str | None = None,
) -> CoordinatorInitState:
    _assert_actor_identity("analyze", analysis.actor_model, analysis.actor_reasoning)
    updated = state.model_copy(deep=True)
    updated.status = "analysis_done"
    updated.active_phase = "implement"
    updated.files_in_scope = sorted(set(updated.files_in_scope + analysis.files_to_touch))
    if analysis_ref is not None:
        updated.analysis_brief_ref = analysis_ref
    updated.next_action = "prepare_implementation_packet"
    updated.compact_brief = build_compact_brief(updated)
    return updated


def route_after_implementation(state: CoordinatorInitState, result: ImplementationResult) -> CoordinatorInitState:
    _assert_actor_identity("implement", result.actor_model, result.actor_reasoning)
    updated = state.model_copy(deep=True)
    updated.files_touched = sorted(set(updated.files_touched + result.changed_files))
    updated.test_commands = result.commands_run
    if result.status == "blocked_missing_input":
        updated.status = "blocked"
        updated.active_phase = "blocked"
        updated.test_status = "blocked"
        updated.open_questions = list(dict.fromkeys(updated.open_questions + result.blockers))
        updated.next_action = "ask_user_for_missing_input"
    elif result.status == "blocked_other":
        updated.status = "blocked"
        updated.active_phase = "blocked"
        updated.test_status = "blocked"
        updated.next_action = "investigate_blocker"
    else:
        updated.status = "implementation_batch_done"
        updated.active_phase = "review"
        if any(test.outcome == "failed" for test in result.test_outcomes):
            updated.test_status = "fail"
        elif any(test.outcome == "blocked" for test in result.test_outcomes):
            updated.test_status = "blocked"
        elif any(test.outcome == "passed" for test in result.test_outcomes):
            updated.test_status = "partial_pass"
        else:
            updated.test_status = "not_run"
        updated.next_action = "run_review"
    updated.compact_brief = build_compact_brief(updated)
    return updated


def route_after_review(state: CoordinatorInitState, result: ReviewResult) -> CoordinatorInitState:
    _assert_actor_identity("review", result.actor_model, result.actor_reasoning)
    updated = state.model_copy(deep=True)
    updated.status = "review_done"
    if result.approve_or_rework == "rework":
        updated.active_phase = "implement"
        updated.next_action = "prepare_rework_packet"
    elif updated.test_status == "partial_pass":
        updated.active_phase = "complete"
        updated.status = "awaiting_user_validation"
        updated.next_action = "await_user_validation"
    else:
        updated.active_phase = "complete"
        updated.status = "completed"
        updated.next_action = "archive_or_start_next_task"
    updated.compact_brief = build_compact_brief(updated)
    return updated


def validate_result_size(result, max_output_chars: int) -> bool:
    payload = result.model_dump_json(exclude_none=False)
    return len(payload) <= max_output_chars


def artifact_run_dir(state_root: str | Path, task_id: str) -> Path:
    return Path(state_root) / "runs" / task_id
