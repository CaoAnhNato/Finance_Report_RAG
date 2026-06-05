import json
import unittest
from pathlib import Path

from src.rag_report.coding_workflow import load_manifest


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / ".agents" / "manifests" / "coding-workflow.json"


class CodingWorkflowManifestGuardrailTests(unittest.TestCase):
    def test_manifest_json_is_parseable(self) -> None:
        raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(raw["workflow_name"], "coding-multi-agent")

    def test_review_and_analyze_remain_non_mutating(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        for role in ("analyze", "review"):
            self.assertFalse(manifest.subagents.roles[role].can_edit)
            self.assertNotIn("edit", manifest.subagents.roles[role].tool_permissions)

    def test_implement_retains_edit_capability(self) -> None:
        manifest = load_manifest(MANIFEST_PATH)
        self.assertTrue(manifest.subagents.roles["implement"].can_edit)
        self.assertIn("edit", manifest.subagents.roles["implement"].tool_permissions)


if __name__ == "__main__":
    unittest.main()
