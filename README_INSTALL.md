# Install the handoff/context kit

This ZIP is **documentation and optional Git automation only**, not a bot update. It contains no trained model, private replays, API keys or user-specific diagnostic JSONs. Nothing has been committed or pushed to GitHub by this package's creation.

1. Keep a backup of any existing similarly named files. Check your local repo status **before** extracting. Open `E:\Downloads\Chat_GPT_AI`, ensure you are working on the intended `codex/native-quality-campaign` branch, and extract the contents of this ZIP **into that repository root**. On file conflicts, compare/merge rather than replacing newer work. If a project `AGENTS.md` exists, merge the agent instructions rather than blindly overwriting it.
2. Read `AI_START_HERE.md`, `CURRENT_ISSUE.md` and `AI_SESSION_STATE.md`. The previous 548-line `AI_CONTINUATION_PROMPT.md` remains the detailed source-of-truth handoff and is **not overwritten** by this kit.
3. To use the **automatic staged-change recording** hook, from Windows **CMD**:

   ```bat
   cd /d "E:\Downloads\Chat_GPT_AI"
   git status --short
   git config --get core.hooksPath
   ```

   If that last command returns an existing hook directory, **review/merge** that configuration first. Otherwise enable this project's opt-in hook:

   ```bat
   git config core.hooksPath .githooks
   ```

   The hook runs `tools/ai_handoff.py sync --staged` before each commit, automatically records the staged file inventory in `AI_CHANGELOG.md`, updates the machine snapshot in `AI_SESSION_STATE.md`, and stages those two docs. It changes **documentation only**. The coding AI must still write meaningful summaries, evidence and tests itself. The included GitHub Actions workflow checks that both docs accompany source changes on future pushes/PRs once the package is committed to GitHub.
4. Stage a **reviewed whitelist** of the new docs/tooling and commit to the correct branch. Example for installing this kit (if you have no existing conflicting edits):

   ```bat
   git add AGENTS.md AI_START_HERE.md PROJECT_CONTEXT.md CURRENT_ISSUE.md AI_SESSION_STATE.md AI_CHANGELOG.md RESOURCE_LINKS.md GITHUB_ACCESS.md README_INSTALL.md
   git add tools/ai_handoff.py .githooks/pre-commit .github/workflows/ai-handoff-check.yml
   git diff --cached --stat
   git diff --cached --check
   git commit -m "Add reusable AI handoff and changelog automation"
   git push origin codex/native-quality-campaign
   ```

   Check `git diff --cached --name-only` before commit: no `data/`, weight files, private chat exports or unrelated modifications. Do not force push.
5. For the next AI, paste/upload `AI_START_HERE.md` and give the **branch link**. The AI should read repo handoff files, edit/commit docs whenever it changes code, and hand back updated Markdown. If it cannot read GitHub, attach these files directly.

## Checks and limitations

You can manually update machine inventory from **staged changes** with:

```bat
python tools\ai_handoff.py sync --staged
```

This is not automatic unless the Git hook is enabled, or the agent explicitly runs it. GitHub Actions **enforces** accompanying docs; it does not write the meaningful explanations for an AI. When making source updates outside Git (e.g., distributing a standalone ZIP without committing), the AI must include an updated Markdown changelog itself.

The local/deeplink Codex chat pointer does not grant access to another AI; the original chat's exported text must be attached separately if necessary. Do not publish a raw transcript containing private information into a public GitHub repository.

## GitHub read/edit access

See [GITHUB_ACCESS.md](GITHUB_ACCESS.md). Connecting GitHub in ChatGPT usually provides **read/search** access; **Codex** or an authorized coding workspace is needed to edit/push. Do not share GitHub passwords or personal access tokens.
