# DISPATCH — teamwork_worker_m1_1

## Identity
- Role: Milestone 1 Environment & Correctness Worker
- Type: teamwork_worker
- Working directory: E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_worker_m1_1\
- Exclusive Write Ownership: `gigaforge/20_WDL_BEST_VS_ORIGINAL_200x100.bat` (NO other implementation files may be modified)

## Mandate & Inputs
- Authoritative User Request: E:\Downloads\Chat_GPT_AI\.agents\teamwork\ORIGINAL_REQUEST.md (MUST read first)
- Project Scope Document: E:\Downloads\Chat_GPT_AI\.agents\teamwork\PROJECT.md
- Milestone Scope Document: E:\Downloads\Chat_GPT_AI\.agents\teamwork\sub_orch_m1\SCOPE.md
- Explorer Findings:
  - `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_m1_1\handoff.md`
  - `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_m1_3\handoff.md`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Objective & Tasks
1. Fix `gigaforge/20_WDL_BEST_VS_ORIGINAL_200x100.bat`:
   Replace lines 7–12:
   ```bat
   if not exist ".venv_native\Scripts\python.exe" goto fallback
   ".venv_native\Scripts\python.exe" -u runtime_bootstrap.py run h2h --run research02 --rounds 200 --seconds 100
   goto finished
   :fallback
   py -3.11 -u runtime_bootstrap.py run h2h --run research02 --rounds 200 --seconds 100
   :finished
   ```
   with:
   ```bat
   call "%~dp0_RUN.bat" run h2h --run research02 --rounds 200 --seconds 100
   ```
2. Execute the full 8-step verification sequence using `gigaforge/.venv_native\Scripts\python.exe`:
   - Step 1: Run launcher routing test:
     `E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe -m pytest gigaforge/tests/test_runtime_finder.py -k test_all_launchers_use_the_single_runtime_router_and_no_old_wandb_pin -v`
   - Step 2: Run direct native C++ self-tests:
     `E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe -c "import subprocess, sys; from pathlib import Path; sys.path.insert(0, 'E:/Downloads/Chat_GPT_AI/gigaforge'); import run; sys.exit(subprocess.run([str(run.binary()), '--selftest'], env=run.environment()).returncode)"`
   - Step 3: Run feature mask, network, and GAE verification:
     `E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe E:\Downloads\Chat_GPT_AI\gigaforge\run.py verify`
   - Step 4: Run identical-actor full match RNG reproducibility check:
     `E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe E:\Downloads\Chat_GPT_AI\gigaforge\tests\check_eval_rng.py`
   - Step 5: Run head-to-head protocol, selection, and export parity check:
     `E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe E:\Downloads\Chat_GPT_AI\gigaforge\tests\check_head_to_head.py`
   - Step 6: Run native warmup integration check:
     `E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe E:\Downloads\Chat_GPT_AI\gigaforge\tests\check_native.py`
   - Step 7: Verify baseline model invariant SHA256 hashes across `NovaForge/assets/` and `gigaforge/runs/research02/parents/`.
   - Step 8: Run the full unit test suite:
     `E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe -m pytest gigaforge/tests/ -v`

## Output Requirements
- Record all verbatim command outputs and test passes in `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_worker_m1_1\handoff.md`.
- Call `send_message` to orchestrator (conversation ID: cee93413-6e94-42af-a811-08721badd7f7).

## 2026-11-07T21:46:28Z
You are teamwork_worker_m1_1.
Your working directory is: E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_worker_m1_1\
Your task dispatch file is: E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_worker_m1_1\DISPATCH.md
MANDATORY: Read ORIGINAL_REQUEST.md first before starting work: E:\Downloads\Chat_GPT_AI\.agents\teamwork\ORIGINAL_REQUEST.md
Also read PROJECT.md: E:\Downloads\Chat_GPT_AI\.agents\teamwork\PROJECT.md
And M1 SCOPE.md: E:\Downloads\Chat_GPT_AI\.agents\teamwork\sub_orch_m1\SCOPE.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Exclusive Write Ownership: gigaforge/20_WDL_BEST_VS_ORIGINAL_200x100.bat
(You own ONLY this file for edits. Do NOT edit any other implementation files.)

Task:
1. Fix gigaforge/20_WDL_BEST_VS_ORIGINAL_200x100.bat per Explorer handoffs:
   Replace lines 7-12 with:
   call "%~dp0_RUN.bat" run h2h --run research02 --rounds 200 --seconds 100
2. Execute the full 8-step verification sequence using gigaforge/.venv_native\Scripts\python.exe:
   - Step 1: pytest gigaforge/tests/test_runtime_finder.py -k test_all_launchers_use_the_single_runtime_router_and_no_old_wandb_pin -v
   - Step 2: Native self-test: python.exe -c "import subprocess, sys; from pathlib import Path; sys.path.insert(0, 'E:/Downloads/Chat_GPT_AI/gigaforge'); import run; sys.exit(subprocess.run([str(run.binary()), '--selftest'], env=run.environment()).returncode)"
   - Step 3: Feature mask, network, and GAE verification: python.exe gigaforge/run.py verify
   - Step 4: Identical-actor RNG check: python.exe gigaforge/tests/check_eval_rng.py
   - Step 5: Head-to-head protocol check: python.exe gigaforge/tests/check_head_to_head.py
   - Step 6: Native warmup integration check: python.exe gigaforge/tests/check_native.py
   - Step 7: Baseline model invariant SHA256 hashes verification
   - Step 8: Full unit test suite: pytest gigaforge/tests/ -v (must pass 100%!)
3. Write your complete handoff report with verbatim command outputs to E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_worker_m1_1\handoff.md.
4. Call send_message to orchestrator (conversation ID: cee93413-6e94-42af-a811-08721badd7f7).
