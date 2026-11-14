# Project Context — Replay Imitation Rocket League Bot

Updated for handoff on **2026-10-17**. This is a succinct orientation, not a replacement for the upstream [AI_CONTINUATION_PROMPT.md](https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-quality-campaign/AI_CONTINUATION_PROMPT.md). All measurements below are *historical* until confirmed in the current checkout.

## Goal and boundaries

Ultimate ambition: an exceptionally strong Rocket League bot (user's aspirational SSL+/Zen comparison), but **no current SSL/Zen gameplay benchmark has been demonstrated**. Immediate aim: make the existing replay-only imitation RLBot move and execute learned jumps/boost correctly, then progressively improve its measured closed-loop play. Training is human replay imitation only. Do not revive historical PPO, self-play, teacher weights or unrelated experiments.

## Architecture that exists

- Offline replay parsing/reconstruction; frozen/cacheable replay chunks (32 ticks by 8 controls at 120 physics Hz).
- 256 discrete medoid action chunks; controller order: throttle, steer, pitch, yaw, roll, jump, boost, handbrake.
- 8 causal observation frames at nominal 15 Hz. Transformer-style spatial/temporal neural network with 3 supervised value heads; roughly 3.27 million trainable parameters in original run.
- RLBot v4 standard Soccar export selects argmax token and executes its first 8 physics ticks; optionally basic scripted kickoff. The deployed RLBot export **does not currently use** the separately implemented 1-second RocketSim candidate-search architecture.
- Older inference-only root modules for forecasting, CPU workers and GPU performance tuning are available; their presence is not proof of parity, performance or improved match strength.

## Important existing paths

- Code branch: `codex/native-quality-campaign`
- Machine checkout: `E:\Downloads\Chat_GPT_AI`
- Entry point: `REPLAY_IL_FINAL.bat`, `replay_il_workflow.py`
- Existing selected original run: `data\isolated\replay_imitation\runs\replay_scratch01`
- Current all-format run (verify state): `data\isolated\replay_imitation\runs\replay_mixed3v3_02`
- Original RLBot export: `data\rlbot_exports\ReplayDuelsDoubles`
- Main code: `replay_il/`, `analyze_replay_policy.py`, `replay_rlbot_core.py`, `replay_rlbot_agent.py`, `export_replay_rlbot.py`, `repair_replay_rlbot.py`
- Do not break fingerprint compatibility of `replay_il/`, `afk_team_research.py`, `nexto_teacher.py` or `slater_versatile_data.py` without a new versioned protocol.

## Evidence vs unknowns

**Reported:** original imitation dataset had 196,062 accepted examples; original 10-epoch run completed. RLBot sometimes AFK/circles, very rarely boosts, no clearly observed jump. Sparse live log had 76 snapshots and token 14 dominated certain decisions; jump/boost controls exist in vocabulary. The latest export and control diagnostics were implemented and synthetic tests passed.

**Unverified / needs actual local reports:** whether real export matches the exact trained checkpoint; jump/boost rates on real validation samples; all actual RLBot callback button counts; p95 live inference latency; whether recent all-format training completed or improved play; whether current code/branch advanced after the handoff.

## Preserve

Private model weights, optimizer states, replay collections, frozen manifest/shards, matching token files, original exports, unrelated user modifications, and the exact training protocol/fingerprint checks. No private files, tokens or whole private chat transcripts on public GitHub by default.

## Handoff artifacts

Read `AI_START_HERE.md` for the current action prompt; `CURRENT_ISSUE.md` for diagnostic work, `AI_SESSION_STATE.md` for newest findings, `AI_CHANGELOG.md` for change history, `RESOURCE_LINKS.md` for URLs, and root `AGENTS.md` for agent obligations.
