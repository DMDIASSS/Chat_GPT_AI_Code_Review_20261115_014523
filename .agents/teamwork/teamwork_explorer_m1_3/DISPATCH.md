# DISPATCH — teamwork_explorer_m1_3

## Identity
- Role: Native C++ Self-Test & Hash Verification Explorer
- Type: teamwork_explorer
- Working directory: E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_m1_3\

## Mandate & Inputs
- Authoritative User Request: E:\Downloads\Chat_GPT_AI\.agents\teamwork\ORIGINAL_REQUEST.md (MUST read first)
- Project Scope Document: E:\Downloads\Chat_GPT_AI\.agents\teamwork\PROJECT.md
- Milestone Scope Document: E:\Downloads\Chat_GPT_AI\.agents\teamwork\sub_orch_m1\SCOPE.md

## Objective
Investigate native self-test suites and model hash verification routines:
1. Identify all self-test flags and verification routines: `gigaforge/native/GigaForge.exe --selftest`, `run.py verify`, `tests/check_eval_rng.py`, `tests/check_head_to_head.py`.
2. Inspect what each check verifies (PBRS GAE self-test, stable car ordering, terminal timeouts, identical-actor RNG bitwise reproduction).
3. Document baseline model files and expected SHA256 hashes (`POLICY.lt`, `SHARED_HEAD.lt`) across `NovaForge/assets/` and `gigaforge/runs/research02/parents/`.
4. Outline exact sequential test commands the Worker must execute to prove Milestone 1 completion.

## Scope Boundaries
- READ-ONLY exploration. DO NOT edit or modify files.

## Output Requirements
- Write your detailed report to `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_m1_3\handoff.md`.
- Call `send_message` to orchestrator (conversation ID: cee93413-6e94-42af-a811-08721badd7f7).


## 2026-11-07T21:35:13Z
[Message] timestamp=2026-11-07T21:35:13Z sender=cee93413-6e94-42af-a811-08721badd7f7 priority=MESSAGE_PRIORITY_HIGH
Task: Investigate native self-test suites and model hash verification routines:
1. Identify all self-test flags and verification routines: gigaforge/native/GigaForge.exe --selftest, run.py verify, tests/check_eval_rng.py, tests/check_head_to_head.py.
2. Inspect what each check verifies (PBRS GAE self-test, stable car ordering, terminal timeouts, identical-actor RNG bitwise reproduction).
3. Document baseline model files and expected SHA256 hashes (POLICY.lt, SHARED_HEAD.lt) across NovaForge/assets/ and gigaforge/runs/research02/parents/.
4. Outline exact sequential test commands the Worker must execute to prove Milestone 1 completion.

Scope: READ-ONLY exploration. DO NOT edit or modify files.
Output: Write handoff.md in your working directory and call send_message to orchestrator (cee93413-6e94-42af-a811-08721badd7f7).
