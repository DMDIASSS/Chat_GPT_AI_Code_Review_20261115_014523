# Challenger 1 Dispatch: Retention Adversarial Verification

**Agent**: `challenger_m2_1` (`teamwork_challenger`)  
**Working Directory**: `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_challenger_m2_1\`  
**Assigned Scope**: Adversarial Verification of Candidate Checkpoint Retention (Feature 5)

## Mandatory Documents to Read First
1. `E:\Downloads\Chat_GPT_AI\.agents\teamwork\ORIGINAL_REQUEST.md` (authoritative request)
2. `E:\Downloads\Chat_GPT_AI\.agents\teamwork\PROJECT.md` (project specifications & hardware limits)
3. `E:\Downloads\Chat_GPT_AI\.agents\teamwork\sub_orch_m2\SCOPE.md` (Milestone 2 scope)
4. `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_worker_m2_1\handoff.md` (Worker implementation report)
5. `E:\Downloads\Chat_GPT_AI\gigaforge\research.py`
6. `E:\Downloads\Chat_GPT_AI\gigaforge\tests\test_trial_watch.py`

## Adversarial Focus
- Stress-test candidate retention: verify that when a candidate is pinned to `watch_pins/`, subsequent deletion of the branch directory does NOT cause `head_to_head.py` or `trial_watch.find_exact` to report `lookup: "missing"`.
- Verify behavior across multiple candidates and families.
- Confirm zero tampering with user processes (`RocketLeague.exe`, `EpicGamesLauncher.exe`).
- Run empirical tests and deliver `handoff.md` with explicit verdict: `APPROVE` or `REQUEST_CHANGES`.

## 2026-11-07T22:56:54Z
You are challenger_m2_1, a teamwork_challenger assigned to Adversarial Verification of Candidate Checkpoint Retention (Feature 5) in Milestone 2.

Working directory:
E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_challenger_m2_1\

Mandatory first step: Read these files:
1. E:\Downloads\Chat_GPT_AI\.agents\teamwork\ORIGINAL_REQUEST.md
2. E:\Downloads\Chat_GPT_AI\.agents\teamwork\PROJECT.md
3. E:\Downloads\Chat_GPT_AI\.agents\teamwork\sub_orch_m2\SCOPE.md
4. E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_worker_m2_1\handoff.md
5. E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_challenger_m2_1\DISPATCH.md
6. E:\Downloads\Chat_GPT_AI\gigaforge\research.py
7. E:\Downloads\Chat_GPT_AI\gigaforge\tests\test_trial_watch.py

Task:
- Adversarially stress-test candidate retention: verify that when a candidate is pinned to `watch_pins/`, subsequent deletion of the branch directory does NOT cause `head_to_head.py` or `trial_watch.find_exact` to report `lookup: "missing"`.
- Verify behavior across multiple candidates and families.
- Confirm zero tampering with user processes (RocketLeague.exe, EpicGamesLauncher.exe).
- Run tests and deliver handoff.md with an explicit verdict: APPROVE or REQUEST_CHANGES.
- Send completion message when done.
