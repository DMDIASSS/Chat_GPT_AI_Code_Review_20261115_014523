# DISPATCH — sub_orch_e2e

## Identity
- Role: E2E Testing Track Orchestrator
- Type: sub_orchestrator
- Working directory: E:\Downloads\Chat_GPT_AI\.agents\teamwork\sub_orch_e2e\
- Parent conversation ID: cee93413-6e94-42af-a811-08721badd7f7

## Mandate & Inputs
- Authoritative User Request: E:\Downloads\Chat_GPT_AI\.agents\teamwork\ORIGINAL_REQUEST.md (MUST read first)
- Project Scope Document: E:\Downloads\Chat_GPT_AI\.agents\teamwork\PROJECT.md
- E2E Scope Document: E:\Downloads\Chat_GPT_AI\.agents\teamwork\sub_orch_e2e\SCOPE.md
- Survey Reports:
  - `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_survey_1\handoff.md`
  - `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_survey_2\handoff.md`
  - `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_spec_miner_survey_3\handoff.md`

## Procedure
As E2E Testing Orchestrator, design and implement the requirement-driven, opaque-box test suite across Tiers 1-4:
1. Initialize `E:\Downloads\Chat_GPT_AI\.agents\teamwork\TEST_INFRA.md`.
2. Decompose or iterate using `teamwork_test_writer` and `teamwork_worker` subagents to build and verify test cases for Tiers 1, 2, 3, and 4.
3. Review and audit the test suite via Reviewer, Challenger, and Auditor.
4. When 100% of the test suite passes, publish `E:\Downloads\Chat_GPT_AI\.agents\teamwork\TEST_READY.md`.
5. Send completion report back to orchestrator.
