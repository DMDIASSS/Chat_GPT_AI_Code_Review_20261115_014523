#!/usr/bin/env python3
"""Document staged Git changes for cross-AI continuity; no external dependencies.

Usage:
  python tools/ai_handoff.py sync --staged
  python tools/ai_handoff.py check --base <SHA> --head <SHA>

'sync' never touches source, weights, datasets or Git remotes. It modifies/stages
AI_CHANGELOG.md and AI_SESSION_STATE.md only, with a *mechanical* inventory.
A coding AI must supply a meaningful separate changelog narrative.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "AI_CHANGELOG.md"
STATE = ROOT / "AI_SESSION_STATE.md"
DOCS = {"AI_CHANGELOG.md", "AI_SESSION_STATE.md"}
START = "<!-- AUTO-STAGED-STATE-START -->"
END = "<!-- AUTO-STAGED-STATE-END -->"


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def changed_names(*args: str) -> list[str]:
    # git's -z eliminates ambiguity for odd filenames (including spaces).
    raw = subprocess.run(["git", "diff", "--name-only", "-z", *args],
                         cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if raw.returncode:
        raise RuntimeError(raw.stderr.decode(errors="replace"))
    return sorted(set(x.decode("utf-8", errors="replace")
                      for x in raw.stdout.split(b"\0") if x))


def real_changes(names: list[str]) -> list[str]:
    return [name for name in names if name not in DOCS]


def sync_staged() -> int:
    names = real_changes(changed_names("--cached", "--diff-filter=ACMRTD"))
    if not names:
        print("No staged project changes; skipping handoff auto-log.")
        return 0
    if not LOG.is_file() or not STATE.is_file():
        print("Missing AI_CHANGELOG.md or AI_SESSION_STATE.md. Install kit first.", file=sys.stderr)
        return 2

    # Hash only staged change *metadata* to avoid leaking diffs or private data.
    statuses = git("diff", "--cached", "--name-status", "--", *names).strip()
    digest = hashlib.sha256(statuses.encode()).hexdigest()[:16]
    log_text = LOG.read_text(encoding="utf-8")
    marker = f"<!-- AUTO-BATCH:{digest} -->"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    branch = git("branch", "--show-current").strip() or "detached HEAD"
    inventory = "\n".join(f"- `{name}`" for name in names)
    if marker not in log_text:
        block = (
            f"\n### Staged inventory — {now} — `{branch}`\n"
            f"{marker}\n"
            "Automated only: these paths were staged when the hook ran; this is NOT "
            "a code explanation, test result or confirmed commit.\n\n"
            f"{inventory}\n"
        )
        LOG.write_text(log_text.rstrip() + "\n" + block, encoding="utf-8")

    state_text = STATE.read_text(encoding="utf-8")
    if START not in state_text or END not in state_text:
        print("AI_SESSION_STATE.md has no recognized automation block; refusing to overwrite.", file=sys.stderr)
        return 2
    i = state_text.index(START) + len(START)
    j = state_text.index(END, i)
    note = (
        f"\n- Recorded: {now}\n- Branch: `{branch}`\n"
        f"- Inventory ID: `{digest}`\n"
        "- Status: staged-only; verify a commit/push separately.\n"
        "- Files:\n" + inventory + "\n"
        "- Tests: **not verified by this automation**; AI must update human section.\n"
    )
    STATE.write_text(state_text[:i] + note + state_text[j:], encoding="utf-8")
    git("add", "--", "AI_CHANGELOG.md", "AI_SESSION_STATE.md")
    print(f"Documented {len(names)} staged project file(s); staged two handoff docs. Inventory {digest}.")
    return 0


def check_range(base: str, head: str) -> int:
    # On first-ever push the before SHA consists of 0s. A zero base cannot be
    # diffed, so fall back to the direct parent if one exists.
    if not base or set(base) == {"0"}:
        parent = subprocess.run(["git", "rev-parse", f"{head}^"],
                                cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if parent.returncode:
            print("Initial root commit: cannot compare a previous revision; skipping range check.")
            return 0
        base = parent.stdout.strip()
    names = changed_names(base, head)
    changes = real_changes(names)
    if not changes:
        print("Only the handoff docs changed, or no files changed; check passed.")
        return 0
    missing = DOCS.difference(names)
    if missing:
        print("Handoff check FAILED: project changes require updated "
              + ", ".join(sorted(missing)) + " in this push/PR range.", file=sys.stderr)
        print("Changed project paths:", *changes[:25], sep="\n  - ", file=sys.stderr)
        return 1
    print(f"Handoff check passed: {len(changes)} project path(s), both docs updated.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync", help="Auto-log staged file inventory and stage only handoff docs")
    sync.add_argument("--staged", action="store_true", required=True)
    check = sub.add_parser("check", help="Fail if changed project files lack both handoff docs")
    check.add_argument("--base", required=True)
    check.add_argument("--head", required=True)
    a = parser.parse_args()
    try:
        return sync_staged() if a.command == "sync" else check_range(a.base, a.head)
    except (OSError, RuntimeError) as exc:
        print(f"Handoff tool error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
