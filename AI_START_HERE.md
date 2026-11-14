# START HERE — Continue the Rocket League Replay-Imitation Bot

**Prepared:** 2026-10-17. **Target:** improve real in-game behavior of the existing bot, with an eventual aspiration of SSL/Zen-level play. That aspiration is **not** an achieved or measured rank.

## Prompt for the next coding AI

You are taking over an active engineering project. **Do the work**, not merely draft a speculative roadmap. First inspect the current Git branch and documentation; then identify, test and implement the smallest evidence-backed fix for the existing replay-imitation RLBot. Leave the repo, tests and handoff documentation in a state another AI can immediately continue.

### Source of truth and conversation

- Repository: https://github.com/DMDIASSS/Chat_GPT_AI
- Active branch: https://github.com/DMDIASSS/Chat_GPT_AI/tree/codex/native-quality-campaign
- **Detailed original handoff (read in full):** https://github.com/DMDIASSS/Chat_GPT_AI/blob/codex/native-quality-campaign/AI_CONTINUATION_PROMPT.md
- Known diagnostic baseline (historical; inspect the current HEAD): https://github.com/DMDIASSS/Chat_GPT_AI/tree/4c45deadc39508459a1b69a4b6018f878453c89f
- Previous private conversation (Codex local URL): https://chatgpt.com/local/01a12e3a-b5f7-7473-a0b8-783603c0906a
- Same conversation (Codex desktop deep link): codex://threads/01a12e3a-b5f7-7473-a0b8-783603c0906a
- **Important:** those local/deep links are pointers for the user, **not publicly readable chat exports**. Do not claim to have read them without actual access. The user has a ~3.1 MB text export named `Вставленный текст.txt`, which they can attach in the AI conversation if full chat context is needed. Do **not** commit an unreviewed raw chat export to this public repo. This Markdown and the existing detailed handoff supply the main context without it.
- Supplementary reference links (including historical project and research material): [RESOURCE_LINKS.md](RESOURCE_LINKS.md).

### Non-negotiable current goal

**Training is offline supervised imitation of high-quality *human replay* data**, covering supported 1v1, 2v2 and 3v3 formats. Do not switch to PPO, self-play, teacher-generated games, Nexto/271 pretrained weights, or RL reward-shaping unless the user expressly changes scope. RocketSim physics/reconstruction checks and inference-time forecasts are allowed; they are **not training matches**. Work toward stronger *observed* gameplay, not paper metrics alone.

The actual existing exported bot has been reported to **idle/AFK, circle, rarely boost beyond kickoff, and not visibly jump**. It sometimes makes defensive touches. Earlier logs (76 sampled outputs) showed 0 observed jump presses and 1 boost press, while token 14 often issued near-full steer and zero throttle. Those were sparse samples, not proof that jump is impossible. The *vocabulary* contains jump/boost, and synthetic wrapper tests pass; the critical **actual-model diagnostic reports are still unknown**. Diagnose learned policy vs reconstruction vs tokenization vs exported weights vs packet/feature parity vs inference latency/closed-loop shift **before** proposing more epochs, bigger models or controller heuristics.

### Priorities (act in this order)

1. Check `git status`, `git log`, branch, `AGENTS.md`, current scripts and any new reports. Never assume the 2026-10-17 handoff is newer than live repo files.
2. If locally available, read these **private files without publishing them**:
   - `data\isolated\replay_imitation\runs\replay_scratch01\validation_diagnostics.json`
   - `data\rlbot_exports\ReplayDuelsDoubles\CONTROL_DIAGNOSTICS.json`
   - New all-format run progress/protocol and existing checkpoint metadata as needed.
3. If unavailable, work on independently testable source inspection and give the user **only these minimal Windows CMD checks**:

   ```bat
   cd /d "E:\Downloads\Chat_GPT_AI"
   CHECK_REPLAY_DUELS_DOUBLES.bat
   REPLAY_IL_FINAL.bat status
   ```

   After running the first check, the user can upload the two JSON reports. Do not assume a cloud checkout can access `E:` or ignored weights/datasets.
4. Compare raw reconstructed labels, chosen action tokens, first-8-tick jump/boost rates, exported/model parity, packet-to-feature parity, callback command counts, inference p95 / 66.67 ms decision budget and resets. Keep hypotheses separate from verified conclusions; see [CURRENT_ISSUE.md](CURRENT_ISSUE.md).
5. Make **one small, measured, compatible fix** with tests and a before/after result. If changing the training protocol, create a versioned new experiment while preserving existing runs. Source updates can be distributed as an explicit-whitelist small ZIP; private data should never go into an update.
6. **After every meaningful change, update** `AI_CHANGELOG.md` (why, files, test evidence and limitations), `AI_SESSION_STATE.md` (current state, next actions, missing reports) and, when facts change, `CURRENT_ISSUE.md`/`PROJECT_CONTEXT.md`. Do this in the same commit. Follow `AGENTS.md`. Optional hook/CI enforce or augment this; automated file lists are **not** a substitute for explanation.
7. In your final reply, always give a short copyable **handoff summary** or link to the updated `.md` and list commit SHA/branch, changed files, tests executed, confirmed results, unknowns and next action. If no GitHub write access, return updated Markdown files/ZIP for the user to commit. Never claim an upload/push happened if it did not.

### Data protection and reproducibility

Never delete/overwrite raw `.replay`, cached `.npz` shards, tokens, selected `best.pt`, resumable `latest.pt`, optimizer/RNG state, private logs or existing RLBot exports. No `git add .` or force push by default; stage an explicit whitelist and inspect staged paths and size. No API keys, Epic launch details, W&B auth, HAR captures, private logs or full chat exports in GitHub. Do not silently change files under `replay_il/` or the earlier frozen observation fingerprint source files and then bypass protocol identity safeguards. Preserve unrelated user edits. Do not claim a test with a synthetic/random model demonstrates competitive ability.

### Verified historical context, not today's run results

- Original replay imitation run: `replay_scratch01`, 279 replay inputs, four rejects, 196,062 accepted samples, 10 epochs, 24,450 updates; 3,271,683-parameter model initialized from scratch. Offline test top-1 action token ~23.70%, top-5 ~55.21%. These are **prediction metrics, not playing rank**.
- Separate current all-format dataset/run: `dataset_mixed3v3_02` / `replay_mixed3v3_02`. Newer actual status must be checked. A previous preparation log had 287 inputs, 196,132 accepted samples and 12 rejects. Some BoxCars parse failures remained.
- Latest known diagnostic update: https://github.com/DMDIASSS/Chat_GPT_AI/raw/4c45deadc39508459a1b69a4b6018f878453c89f/downloads/Replay_Control_Check_Update.zip. An earlier test report said 27 relevant tests passed; it did **not** test live user gameplay.
- User's reported Windows machine: i5-10300H, GTX 1650 Mobile 4 GB, 16 GB RAM. Cloud resources and RLBot's Python/CUDA installation may differ.

### Useful commands, only when appropriate

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
REPLAY_IL_FINAL.bat cache
REPLAY_IL_FINAL.bat status
REPLAY_IL_FINAL.bat results --run replay_scratch01
REPLAY_IL_FINAL.bat start --device cuda
```

The final command **resumes** the current all-format run if compatible; it is not a recommended diagnosis of idling without evidence. `--epochs 20` means a **total** target of 20, and early stopping may still prevent more updates. Do not restart a completed or currently running training job just for a demonstration.

### End-of-task handoff contract

At the end of each coding task, include in the reply: **(a)** what changed/why, **(b)** exact files and commit, **(c)** commands and results for tests actually run, **(d)** next test/report needed, **(e)** link to updated `AI_SESSION_STATE.md`, `AI_CHANGELOG.md` or attach their new contents, and **(f)** any local-only actions. Update these files **during** the task, not only as a future promise.

**Start now:** inspect the branch and actual reports, apply the narrowest defensible solution, keep changelog/context live, and finish with an exportable handoff.
