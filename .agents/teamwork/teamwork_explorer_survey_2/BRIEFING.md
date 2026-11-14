# BRIEFING — 2026-11-07T21:27:00Z

## Mission
Perform a read-only investigation of native simulator contracts, physics, observation/action definitions, rewards, and evaluation frameworks in E:\Downloads\Chat_GPT_AI.

## 🔒 My Identity
- Archetype: teamwork_explorer
- Roles: Simulator Contracts & Evaluation Protocol Explorer
- Working directory: E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_survey_2\
- Original parent: cee93413-6e94-42af-a811-08721badd7f7
- Milestone: Milestone 1 - Audit & Baseline Verification

## 🔒 Key Constraints
- Read-only investigation — do NOT implement or modify source code/weights
- Do NOT launch heavy evaluation runs
- Adhere strictly to the 5-component handoff protocol
- Only write metadata inside own directory

## Current Parent
- Conversation ID: cee93413-6e94-42af-a811-08721badd7f7
- Updated: 2026-11-07T21:27:00Z

## Investigation State
- **Explored paths**:
  - `gigaforge/` (native C++ source `main.cpp`, `evaluate.h`, `native_features.h`, `checks.h`, `CMakeLists.txt`, `tools/patch_upstream.py`, `head_to_head.py`, `research.py`, `research_eval.py`, tests, evaluation outputs, parent baselines)
  - `NovaForge/` (`nova/environment.py`, `nova/chronos.py`, `nova/giga_teachers.py`, `nova/teachers.py`, `nova/forge_env.py`, `assets/chronos`, `assets/galactus`)
  - `forgeleague/` (`README.md`, `run.py`, `runs/duel01/`)
- **Key findings**:
  - Pinned simulator engine: RocketSim 2.2.1, RLGym 2.0.1, RLGym-tools 2.6.5, RLGym-compat 2.3.6; GigaLearnCPP commit `86e11c3881a21225a43c36b14af40f0b3c87e7dd` patched with stable car order, thread pool controls, and GAE bootstrap fix, compiled into `GigaForge.exe`.
  - Contracts: Chronos (225 obs, 90 actions, horizontal mirroring, Breakout hitbox); Galactus V2 (258 obs with boost vector + 30-dim 5-step ball forecast, no mirroring, Octane hitbox).
  - Both bots use tick skip = 8 (15 Hz) and action delay = 7 ticks held + 1 tick newly applied command.
  - Rewards: Potential-Based Reward Shaping (`GoalPotential`) with 5 basis functions and $\pm 10$ goal terminal.
  - Evaluation harnesses: `direct-h2h-v1` (200/2,000 game paired direct H2H, paired-seed Student-t 95% CI) and `arena-rng-v4` (panel evaluation with sequential $\alpha$-spending).
  - Historical result: Chronos trial 38 completed a 2,000-game `direct-h2h-v1` evaluation against `original_chronos` at 135s/game, scoring 49.05% [0.4706, 0.5104] (failed promotion threshold). Neither baseline has been promoted.
- **Unexplored areas**: None within the declared investigation scope.

## Key Decisions Made
- All evidence extracted directly with exact file paths, line numbers, hashes, and code snippets.
- Document both Python and C++ implementations and contrast any historical divergences (e.g. ForgeLeague Octane vs GigaForge Breakout for Chronos).

## Artifact Index
- DISPATCH.md — Task dispatch and instructions
- BRIEFING.md — Persistent situational awareness
- progress.md — Liveness heartbeat and milestone tracking
- handoff.md — Final 5-component handoff report
