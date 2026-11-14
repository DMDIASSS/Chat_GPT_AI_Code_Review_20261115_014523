# Connecting an AI to this GitHub repository

## For reading code in ChatGPT

Where supported by the account, open **Settings → Plugins → GitHub** (or the plugin containing GitHub), connect your GitHub account and authorize access to `DMDIASSS/Chat_GPT_AI`. ChatGPT's GitHub connection is for **reading/searching code**, not pushing modifications. Official instructions: https://help.openai.com/en/articles/11145903-connecting-github-to-chatgpt

The public repository can also be read by an AI with internet access even without authorization. Give the AI the **specific branch** `codex/native-quality-campaign` and `AI_START_HERE.md` / `AI_CONTINUATION_PROMPT.md` links so it does not fall back to stale `main`.

## For editing and pushing code

Use **Codex** in a workspace that has the repository attached and authorized to write/push, or another coding agent with explicitly approved git access. GitHub read-only plugins do not imply write permissions. Review proposed changes and commits before enabling broad access. Grant access to this repository, not all your repositories, when the provider offers that choice. Do not paste a GitHub personal access token or password into a chat.

A coding AI must check repository status and preserve dirty/user files. It should work on the requested branch or a reviewable feature branch/PR. Every useful commit should include a human-quality `AI_CHANGELOG.md` entry and `AI_SESSION_STATE.md` update, enforced/assisted by the provided hook and workflow.

## For private local model data

Access to GitHub does **not** give the agent access to `E:\Downloads\Chat_GPT_AI\data` (ignored checkpoints and replays) or the user's private Codex chat thread. If an agent must diagnose the actual saved model, upload the two small JSON reports first; only provide model/export weights separately when necessary through a private transfer method.

## Handing over to a new AI

Give the new AI:

1. `AI_START_HERE.md` in this repo, or attach it.
2. The branch link: https://github.com/DMDIASSS/Chat_GPT_AI/tree/codex/native-quality-campaign
3. `AI_SESSION_STATE.md` and `AI_CHANGELOG.md` (or repo links once committed).
4. The two locally generated diagnostic JSON reports if available.
5. The old chat export **only if required**, attached inside the chat, not committed publicly. The local chat pointer `https://chatgpt.com/local/01a12e3a-b5f7-7473-a0b8-783603c0906a` and `codex://threads/01a12e3a-b5f7-7473-a0b8-783603c0906a` will not provide another AI automatic access to its contents.
