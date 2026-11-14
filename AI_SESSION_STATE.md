# AI Session State — Read this first on a new handoff

_Last human-written handoff: 2026-10-17. Update with real findings after each task. Machine block at bottom is auto-maintained by the optional hook._

## Current active task

Find and fix the cause(s) of poor real-gameplay controls in the replay-only imitation bot: idling/circling, near-absent boost and unseen jumps. Do not assume training for more epochs is the fix. Detailed plan: [CURRENT_ISSUE.md](CURRENT_ISSUE.md).

## Last confirmed state

- GitHub branch: `codex/native-quality-campaign`; historical diagnostic baseline `4c45deadc39508459a1b69a4b6018f878453c89f`.
- Detailed existing continuation handoff (548 lines at handoff time): `AI_CONTINUATION_PROMPT.md` on that branch.
- Previous Codex export was provided in the chat, but not stored in this repo.
- Export diagnostics/analysis scripts reportedly committed and tested; actual laptop JSON outputs were not included in the received export.
- Last previously reported relevant tests: 27/27 for control-check code. Do **not** relabel as today's tests.
- This context kit is prepared externally and **is not yet committed to GitHub** until user or connected coding agent applies it.

## Next action, highest value

1. Check current `git status`, `git log` and any newer repo changes.
2. Obtain/read the two private JSON reports from `CHECK_REPLAY_DUELS_DOUBLES.bat` and one updated live RLBot session (or run diagnostic locally if accessible).
3. Narrow the failure to label/quantization/policy, export parity or runtime input/timing, and implement the narrowest justified fix.
4. Run targeted tests; record real before/after evidence and failures.
5. Update this document's confirmed state/next action, append a meaningful note to `AI_CHANGELOG.md`, update `CURRENT_ISSUE.md` when the bug changes, and share/push the changes on the intended branch with user authorization.

## Missing data / access boundaries

- Actual latest private weights, `tokens.npy`, saved checkpoints and caches may live **only** at `E:\Downloads\Chat_GPT_AI`, not in GitHub.
- `validation_diagnostics.json` and `CONTROL_DIAGNOSTICS.json` were requested but not present in the supplied conversation text.
- Another AI should not assume access to local Codex links or private chat history merely because their links appear in the docs.
- Do not ask for or commit secrets or entire private replay archives when diagnostics will suffice.

## Progress this session (AI must edit)

_No code/behavior fixes have been performed as part of this documentation kit. Record confirmed work here as it happens._

## Tests and evidence this session (AI must edit)

_None run against the GitHub checkout or private model by this documentation kit. Hook utility may be locally self-tested separately._

## Handoff instructions

Every task end: provide brief state summary, branch and commit SHA (if committed), exact tests/results, unresolved blockers, and link/attachment for updated `AI_CHANGELOG.md` and this file. A changed-files-only auto log is not a substitute for a meaningful explanation.

<!-- AUTO-STAGED-STATE-START -->
- Recorded: 2026-10-17 11:15 UTC
- Branch: `my-custom-branch`
- Inventory ID: `5c91409916ce5c69`
- Status: staged-only; verify a commit/push separately.
- Files:
- `.githooks/pre-commit`
- `.github/workflows/ai-handoff-check.yml`
- `AGENTS.md`
- `AI_START_HERE.md`
- `CURRENT_ISSUE.md`
- `GITHUB_ACCESS.md`
- `PROJECT_CONTEXT.md`
- `README_INSTALL.md`
- `RESOURCE_LINKS.md`
- `tools/ai_handoff.py`
- Tests: **not verified by this automation**; AI must update human section.
<!-- AUTO-STAGED-STATE-END -->
