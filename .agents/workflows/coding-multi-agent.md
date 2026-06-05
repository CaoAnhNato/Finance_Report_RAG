---
description: Multi-agent coding workflow for repository development tasks. Applies to code changes only, never to the runtime report pipeline unless the task explicitly targets those files.
---

# Coding Multi-Agent Workflow

Coordinator model policy:
- `GPT-5.4` only
- reasoning `High` only
- no override allowed

Sub-agent default model policy:
- `GPT-5.4-Mini` only
- reasoning `High` only
- no override allowed

Workflow contract:
1. Bootstrap by reading `AGENTS.md`, `.agents/rules/*`, `.agents/workflows/*`, `project-structure.yaml`, and `.agents/state/coding_workflow_init.json` when resuming.
2. Create a task-local TODO list before delegating work.
3. Call `Analyze` first for non-trivial tasks.
4. Lock scope into an `ImplementationPacket` before any edits.
5. Route edits only through `Implement`.
6. Route diff verification only through `Review`.
7. Persist compact state after `analysis_done`, `implementation_batch_done`, `review_done`, `blocked`, and `completed`.

Handoff rules:
- Use manager-controlled delegation only. No peer handoff between sub-agents.
- Send bounded JSON envelopes, not full transcript replays.
- Forward file paths and line refs instead of full file contents when possible.
- Resume from state file plus artifact refs, not from long chat history.

Cost and safety rules:
- Do not rerun `Analyze` after scope is locked unless `Review` identifies a direction error.
- Prefer focused tests. Run broad smoke/regression only when touching cloud/API boundaries or when explicitly requested.
- For long-running analysis/debug, provide the CLI command to the user instead of running hidden background loops.
- If a task needs missing external credentials or endpoint details, stop and return a blocked result.

Artifact layout:
- Runtime state: `.agents/state/coding_workflow_init.json`
- Long-form artifacts: `.agents/state/runs/<task_id>/`
- Committed template only: `.agents/state/coding_workflow_init.template.json`

Phase routing:
- `bootstrap` -> `analyze`
- `analyze` -> `implement`
- `implement` -> `review`
- `review` -> `implement` when rework is required
- `review` -> `completed` or `awaiting_user_validation` when approved
- any phase -> `blocked` when inputs are missing or a hard stop is reached
