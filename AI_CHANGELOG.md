# AI-maintained changelog and evidence log

This is **not** a copy of Git's commit history. Each coding AI must give a plain-language explanation of *why* a change was made, exactly *what* changed, compatibility/data risks, *what was actually tested* and measured outcomes. Use past tense only for things verified. Newest **human/AI-written** entries go first. The hook appends a separate, lower-confidence staged-file inventory; do not confuse it with a completed test report.

## AI-written change summaries (newest first)

### 2026-10-17 — Prepared cross-AI context package (documentation tooling only)

- **Why:** the project passed between coding AIs and needed self-contained issue state, persistent links and auditable change summaries.
- **Changes:** prepared `AI_START_HERE.md`, `PROJECT_CONTEXT.md`, `CURRENT_ISSUE.md`, `AI_SESSION_STATE.md`, `RESOURCE_LINKS.md`, `AGENTS.md`, this changelog and optional hook/CI tooling for later installation.
- **Verification:** project facts cross-checked against the exported Codex conversation and the existing public `AI_CONTINUATION_PROMPT.md` as available on 2026-10-17. The hook check can be tested in a disposable local git repository; **no real bot model/gameplay has been tested by this task**.
- **Limitations:** the files are **not committed/pushed to GitHub by this document**. Existing private reports, weights and actual local training state have not been accessed.
- **Next:** integrate this folder safely into the intended branch and run the user-model diagnostics, then update this log with the result.

## Machine-logged staged change batches (automatic, file inventory only)

_After installation, `tools/ai_handoff.py sync --staged` or the optional pre-commit hook records staged file paths here. A batch is **not** proof of a passing test, improvement, completed commit, successful push, or AI review._

### Staged inventory — 2026-10-17 11:15 UTC — `my-custom-branch`
<!-- AUTO-BATCH:5c91409916ce5c69 -->
Automated only: these paths were staged when the hook ran; this is NOT a code explanation, test result or confirmed commit.

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
