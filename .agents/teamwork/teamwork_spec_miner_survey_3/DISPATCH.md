# DISPATCH — teamwork_spec_miner_survey_3

## Identity
- Role: Export, Latency & RLBot Spec Miner
- Type: teamwork_spec_miner
- Working directory: E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_spec_miner_survey_3\

## Mandate & Inputs
- Authoritative User Request: E:\Downloads\Chat_GPT_AI\.agents\teamwork\ORIGINAL_REQUEST.md (MUST read first)
- Project Root: E:\Downloads\Chat_GPT_AI

## Objective
Extract precise requirements, specifications, and current implementations for packaging, export, deployment, opponent panels, and latency constraints:
1. Examine existing bot export formats and artifacts in the repo: RLBot v5 `.toml` + `.lt` (LibTorch / TorchScript) and/or `.pt` + `.cfg` configurations. Check bot metadata, appearance configs, loadout, and car types.
2. Investigate RLBot bot launchers, entry points, agent classes, and execution flows for Windows.
3. Check model export scripts: trace/script conversion from PyTorch, logit/action parity verification routines, and device selection (CPU vs CUDA/GPU).
4. Identify action delay deadlines (e.g. 15ms / 30ms / 60Hz / 120Hz ticks) and latency measurement methods (observation creation time + forward pass time + action parsing).
5. Enumerate available baseline opponent bots in the repository (e.g., Nexto, Element, Necto, Kamael, standard baselines) forming the secondary opponent panel.
6. Check for any Discord research exports, authorized channels, or documentation in the repository (read-only governance).

## Scope Boundaries
- READ-ONLY investigation. DO NOT edit or modify any files.
- DO NOT launch games or bots.

## Output Requirements
- Write a detailed, self-contained `handoff.md` in `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_spec_miner_survey_3\handoff.md` with full evidence (file paths, line numbers, findings, recommendations).
- When done, call `send_message` to orchestrator (conversation ID: cee93413-6e94-42af-a811-08721badd7f7) with a concise summary and reference to your handoff file.

## 2026-11-07T21:19:55Z
From: cee93413-6e94-42af-a811-08721badd7f7
Task: Extract precise requirements, specifications, and current implementations for packaging, export, deployment, opponent panels, and latency constraints in E:\Downloads\Chat_GPT_AI.
1. Examine existing bot export formats and artifacts in the repo: RLBot v5 .toml + .lt (LibTorch / TorchScript) and/or .pt + .cfg configurations. Check bot metadata, appearance configs, loadout, and car types.
2. Investigate RLBot bot launchers, entry points, agent classes, and execution flows for Windows.
3. Check model export scripts: trace/script conversion from PyTorch, logit/action parity verification routines, and device selection (CPU vs CUDA/GPU).
4. Identify action delay deadlines (e.g. 15ms / 30ms / 60Hz / 120Hz ticks) and latency measurement methods (observation creation time + forward pass time + action parsing).
5. Enumerate available baseline opponent bots in the repository (e.g., Nexto, Element, Necto, Kamael, standard baselines) forming the secondary opponent panel.
6. Check for any Discord research exports, authorized channels, or documentation in the repository (read-only governance).

Scope: READ-ONLY investigation. DO NOT edit or modify any files. DO NOT launch games or bots.
Output: Write your detailed report to E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_spec_miner_survey_3\handoff.md.
When finished, send a message to the orchestrator (conversation ID: cee93413-6e94-42af-a811-08721badd7f7) summarizing your findings and pointing to handoff.md.
