import tempfile
import unittest
from pathlib import Path

from src.rag_report.coding_workflow import (
    AnalysisBrief,
    CoordinatorInitState,
    ImplementationResult,
    ReviewResult,
    build_init_state,
    load_init_state,
    load_manifest,
    load_template_state,
    route_after_analysis,
    route_after_implementation,
    route_after_review,
    save_init_state,
    validate_result_size,
)
from src.rag_report.coding_workflow.models import ReviewFinding, TestResult


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / ".agents" / "manifests" / "coding-workflow.json"
TEMPLATE_PATH = ROOT / ".agents" / "state" / "coding_workflow_init.template.json"


class CodingWorkflowContractTests(unittest.TestCase):
    def test_manifest_is_locked_to_required_models(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        self.assertFalse(manifest.override_allowed)
        self.assertEqual(manifest.coordinator.model, "gpt-5.4")
        self.assertEqual(manifest.coordinator.reasoning, "high")
        self.assertEqual(manifest.subagents.default_model, "gpt-5.4-mini")
        self.assertEqual(manifest.subagents.default_reasoning, "high")

    def test_tool_scopes_match_role_safety(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        analyze = manifest.subagents.roles["analyze"]
        implement = manifest.subagents.roles["implement"]
        review = manifest.subagents.roles["review"]
        self.assertFalse(analyze.can_edit)
        self.assertFalse(review.can_edit)
        self.assertTrue(implement.can_edit)
        self.assertNotIn("edit", analyze.tool_permissions)
        self.assertNotIn("edit", review.tool_permissions)
        self.assertIn("edit", implement.tool_permissions)

    def test_template_state_matches_schema(self) -> None:
        template = load_template_state(TEMPLATE_PATH)
        self.assertEqual(template.status, "pending")
        self.assertEqual(template.active_phase, "bootstrap")
        self.assertEqual(template.test_status, "not_run")

    def test_resume_round_trip_uses_state_file_only(self) -> None:
        state = build_init_state(
            task_id="task-123",
            objective="Refactor coordinator state handling.",
            todo_titles=["Analyze scope", "Implement helper", "Review diff"],
        )
        state.analysis_brief_ref = ".agents/state/runs/task-123/analysis.json"
        state.files_in_scope = ["src/rag_report/coding_workflow/manager.py"]
        state.compact_brief = "Analyze complete. Prepare implementation packet."
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "coding_workflow_init.json"
            save_init_state(state_path, state)
            loaded = load_init_state(state_path)
        self.assertIsInstance(loaded, CoordinatorInitState)
        self.assertEqual(loaded.task_id, state.task_id)
        self.assertEqual(loaded.analysis_brief_ref, state.analysis_brief_ref)
        self.assertEqual(loaded.compact_brief, state.compact_brief)

    def test_cost_shape_output_stays_within_manifest_cap(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        analysis = AnalysisBrief(
            actor_model="gpt-5.4-mini",
            actor_reasoning="high",
            problem_frame="Need a bounded workflow contract.",
            files_to_touch=["a.py", "b.py"],
            proposed_steps=["Define schema", "Add tests"],
            risks=["Over-broad routing"],
            needed_checks=["unit tests"],
            required_docs=[],
            recommended_tests=["python -m unittest tests.test_coding_workflow_contracts"],
        )
        self.assertTrue(validate_result_size(analysis, manifest.subagents.roles["analyze"].max_output_chars))

    def test_blocked_input_routing_stops_work(self) -> None:
        state = build_init_state("task-456", "Add cloud integration helper.", ["Analyze", "Implement", "Review"])
        result = ImplementationResult(
            actor_model="gpt-5.4-mini",
            actor_reasoning="high",
            status="blocked_missing_input",
            changed_files=[],
            edit_summary=[],
            commands_run=[],
            test_outcomes=[],
            open_issues=[],
            blockers=["Missing API key and endpoint URL."],
        )
        next_state = route_after_implementation(state, result)
        self.assertEqual(next_state.status, "blocked")
        self.assertEqual(next_state.active_phase, "blocked")
        self.assertEqual(next_state.next_action, "ask_user_for_missing_input")

    def test_analysis_routing_locks_scope_before_implementation(self) -> None:
        state = build_init_state("task-321", "Add coding workflow manifest loader.", ["Analyze", "Implement", "Review"])
        analysis = AnalysisBrief(
            actor_model="gpt-5.4-mini",
            actor_reasoning="high",
            problem_frame="Need manifest loader and validation helper.",
            files_to_touch=[
                "src/rag_report/coding_workflow/manager.py",
                "src/rag_report/coding_workflow/models.py",
            ],
            proposed_steps=["Add helper", "Add tests"],
            risks=["Manifest drift"],
            needed_checks=["unit tests"],
            required_docs=[],
            recommended_tests=[".venv\\Scripts\\python -m unittest tests.test_coding_workflow_contracts"],
        )
        next_state = route_after_analysis(
            state,
            analysis,
            analysis_ref=".agents/state/runs/task-321/analysis.json",
        )
        self.assertEqual(next_state.status, "analysis_done")
        self.assertEqual(next_state.active_phase, "implement")
        self.assertEqual(next_state.next_action, "prepare_implementation_packet")
        self.assertEqual(next_state.analysis_brief_ref, ".agents/state/runs/task-321/analysis.json")
        self.assertIn("src/rag_report/coding_workflow/manager.py", next_state.files_in_scope)

    def test_routing_supports_rework_then_completion(self) -> None:
        state = build_init_state("task-789", "Implement a helper module.", ["Analyze", "Implement", "Review"])
        impl_result = ImplementationResult(
            actor_model="gpt-5.4-mini",
            actor_reasoning="high",
            status="implemented",
            changed_files=["src/rag_report/coding_workflow/manager.py"],
            edit_summary=["Added helper functions."],
            commands_run=[".venv\\Scripts\\python -m unittest tests.test_coding_workflow_contracts"],
            test_outcomes=[TestResult(command="unit", outcome="passed", summary="Focused tests passed.")],
            open_issues=[],
            blockers=[],
        )
        after_impl = route_after_implementation(state, impl_result)
        self.assertEqual(after_impl.status, "implementation_batch_done")
        self.assertEqual(after_impl.active_phase, "review")

        review_rework = ReviewResult(
            actor_model="gpt-5.4-mini",
            actor_reasoning="high",
            status="rework",
            findings=[ReviewFinding(severity="medium", message="Missing edge-case test.")],
            missing_tests=["edge case for blocked state"],
            regression_risks=["state transition may miss one branch"],
            required_rework=["Add blocked state regression test."],
            approve_or_rework="rework",
        )
        after_rework = route_after_review(after_impl, review_rework)
        self.assertEqual(after_rework.active_phase, "implement")
        self.assertEqual(after_rework.next_action, "prepare_rework_packet")

        review_approve = ReviewResult(
            actor_model="gpt-5.4-mini",
            actor_reasoning="high",
            status="approved",
            findings=[],
            missing_tests=[],
            regression_risks=[],
            required_rework=[],
            approve_or_rework="approve",
        )
        after_approve = route_after_review(after_impl, review_approve)
        self.assertIn(after_approve.status, {"awaiting_user_validation", "completed"})
        self.assertEqual(after_approve.active_phase, "complete")


if __name__ == "__main__":
    unittest.main()
