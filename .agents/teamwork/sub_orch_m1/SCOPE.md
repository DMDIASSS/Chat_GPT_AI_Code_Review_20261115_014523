# Scope: Milestone 1 — Correctness Audit & Environment Hardening

## Overview
Milestone 1 establishes verified baseline correctness, resolves identified launcher routing defects, validates runtime environment isolation, and proves simulator contract invariants.

## Assigned Features
- **Feature 1**: Baseline Hash & Contract Preservation — Verify invariant SHA256 hashes for Chronos (`cb4e93c281...`, `e0aac68a...`) and Galactus baselines.
- **Feature 2**: Launcher Routing & Virtualenv Invariant — Fix `gigaforge/20_WDL_BEST_VS_ORIGINAL_200x100.bat` to route via `_RUN.bat` and enforce `gigaforge/.venv_native` PyTorch 2.9.1+cu126.
- **Feature 3**: Native Simulator Self-Tests & GAE Verification — Execute and pass native C++ self-tests (`--selftest`, PBRS telescoping, GAE truncation, body checks, `run.py verify`).
- **Feature 20**: Read-Only Discord Governance & Provenance Logging — Ensure all logs and configurations are preserved.

## Acceptance Criteria
1. `gigaforge/20_WDL_BEST_VS_ORIGINAL_200x100.bat` is fixed so that it delegates to `_RUN.bat` instead of directly calling `.venv_native\Scripts`.
2. `pytest tests/` in `gigaforge/.venv_native` passes 100% of tests (including `test_all_launchers_use_the_single_runtime_router_and_no_old_wandb_pin`).
3. `gigaforge/native/GigaForge.exe --selftest` passes with `RESEARCH_FIXED_ROLLOUT_PBRS_GAE_SELFTEST_PASS` and `NATIVE_GAE_TERMINAL_TIMEOUT_ORDER_BODY_ACTION_TESTS_PASS`.
4. `run.py verify` passes with all native feature mask, network, and GAE assertions passing.
5. Baseline model hashes in `NovaForge/assets/chronos/` and `gigaforge/runs/research02/parents/chronos/` match the invariant SHA256 hashes verbatim.
6. Gate passes: Explorer -> Worker -> 2 Reviewers -> 2 Challengers -> 1 Forensic Auditor (`teamwork_auditor`).
