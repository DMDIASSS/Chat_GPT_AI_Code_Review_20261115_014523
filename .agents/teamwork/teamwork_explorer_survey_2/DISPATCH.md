# DISPATCH — teamwork_explorer_survey_2

## Identity
- Role: Simulator Contracts & Evaluation Protocol Explorer
- Type: teamwork_explorer
- Working directory: E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_survey_2\

## Mandate & Inputs
- Authoritative User Request: E:\Downloads\Chat_GPT_AI\.agents\teamwork\ORIGINAL_REQUEST.md (MUST read first)
- Project Root: E:\Downloads\Chat_GPT_AI

## Objective
Perform a read-only investigation of native simulator contracts, physics, observation/action definitions, rewards, and evaluation frameworks:
1. Identify the underlying simulator engine (RocketSim, rlgym, rlgym-sim, rlgym-compat, etc.) and versions used.
2. Audit native simulator contracts: observation builders, feature extraction, normalization, action spaces (discrete vs continuous, bins), action delays/tick skips, and hitbox implementations (specifically Chronos Breakout vs Galactus V2 Octane).
3. Analyze reward functions, shaping terms, terminal conditions, and state resets used in Chronos and Galactus.
4. Survey existing evaluation harnesses: inspect `direct-h2h-v1`, `arena-rng-v4`, match runners, color rotation (blue/orange), game tick rules, overtime handling, seed generation, and confidence interval calculation scripts.
5. Check how baseline models are loaded and run in evaluation matches, verifying deterministic reproducibility and fairness.

## Scope Boundaries
- READ-ONLY exploration. DO NOT edit or modify any source code or model weights.
- DO NOT launch heavy evaluation runs.

## Output Requirements
- Write a detailed, self-contained `handoff.md` in `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_survey_2\handoff.md` with full evidence (file paths, line numbers, findings, recommendations).
- When done, call `send_message` to orchestrator (conversation ID: cee93413-6e94-42af-a811-08721badd7f7) with a concise summary and reference to your handoff file.
