# DISPATCH — sub_orch_m1

## Identity
- Role: Sub-orchestrator for Milestone 1 (Correctness Audit & Environment Hardening)
- Type: sub_orchestrator
- Working directory: E:\Downloads\Chat_GPT_AI\.agents\teamwork\sub_orch_m1\
- Parent conversation ID: cee93413-6e94-42af-a811-08721badd7f7

## Mandate & Inputs
- Authoritative User Request: E:\Downloads\Chat_GPT_AI\.agents\teamwork\ORIGINAL_REQUEST.md (MUST read first)
- Project Scope Document: E:\Downloads\Chat_GPT_AI\.agents\teamwork\PROJECT.md
- Milestone Scope Document: E:\Downloads\Chat_GPT_AI\.agents\teamwork\sub_orch_m1\SCOPE.md
- Survey Reports:
  - `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_survey_1\handoff.md`
  - `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_survey_2\handoff.md`
  - `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_spec_miner_survey_3\handoff.md`

## Procedure
As sub-orchestrator for M1, apply the Project Pattern iteration loop (Explorer -> Worker -> 2 Reviewers -> 2 Challengers -> 1 Forensic Auditor):
1. Spawn 3 Explorers (teamwork_explorer) to plan the exact fix for `20_WDL_BEST_VS_ORIGINAL_200x100.bat` and verification strategy.
2. Spawn a Worker (teamwork_worker) with Explorer findings and integrity warning to apply the fix and run tests in `gigaforge/.venv_native`.
3. Spawn 2 Reviewers (teamwork_reviewer) independently to review changes and run test suites.
4. Spawn 2 Challengers (teamwork_challenger) to verify determinism and protocol compliance.
5. Spawn a Forensic Auditor (teamwork_auditor) for binary integrity check.
6. Evaluate Gate and write `GATE_STATUS.md`. When passed, write `handoff.md` and report completion back to orchestrator.
