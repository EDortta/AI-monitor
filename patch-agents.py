#!/usr/bin/env python3
"""
patch-agents.py — append Activity Monitor section to every project AGENTS.md.

Idempotent: skips files that already contain the section.
Skips: this project, AI-Agents, AI-GovernanceKit, cache dirs, node_modules,
and any repo whose git remote doesn't belong to an owner in OWN_REMOTE_OWNERS.

Safe by default: prints what it would do (dry run) unless --apply is
passed, and --apply still asks for confirmation unless --yes is given.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HOME = Path.home()

# Directories to search (relative to HOME)
SEARCH_ROOTS = [
    HOME / "Sync" / "Projects",
    HOME / "Sync" / "Y2",
]

SKIP_DIRS = {
    "AI-monitor",
    "AI-Agents",
    "AI-GovernanceKit",
    "node_modules",
    ".git",
    ".venv",
    "__pycache__",
    ".cache",
    ".tmp",
    ".codex",
}

# Explicit allowlist: only repos whose git remote references one of these
# owners get patched. Repos with no remote (local-only scratch work) are
# still patched. Everything else — vendored libraries, forks of third-party
# projects, client checkouts not in this list — is skipped even if found
# under SEARCH_ROOTS. Extend this set deliberately, don't widen SKIP_DIRS
# instead (that's a denylist and misses checkouts nobody thought to add).
OWN_REMOTE_OWNERS = {"EDortta", "Zeecred"}


def repo_remote_url(agents_md: Path) -> str | None:
    for parent in agents_md.parents:
        if (parent / ".git").exists():
            try:
                out = subprocess.run(
                    ["git", "-C", str(parent), "remote", "get-url", "origin"],
                    capture_output=True, text=True, timeout=5,
                )
            except (OSError, subprocess.TimeoutExpired):
                return None
            return out.stdout.strip() if out.returncode == 0 else None
    return None


def is_third_party(agents_md: Path) -> bool:
    url = repo_remote_url(agents_md)
    if url is None:
        return False
    return not any(owner.lower() in url.lower() for owner in OWN_REMOTE_OWNERS)


SECTION_MARKER = "## Activity Monitor"

SECTION = """
## Activity Monitor

> Only applies when `~/Sync/agent-status.json` exists (agent-monitor is installed).
> If the file does not exist, skip this section entirely.

**On session start** — read the file, merge your entry, write back:

```json
{"agent": "<claude-code|codex|cursor>", "project": "<short-path-from-Sync/Projects/>",
 "task": "<one sentence>", "started": "<ISO-UTC>", "heartbeat": "<ISO-UTC>"}
```

- `agent` must be exactly `claude-code`, `codex`, or `cursor`.
- Never overwrite other agents' entries — read first, merge, then write.
- Update `task` and `heartbeat` when your focus changes significantly.

**On session end** — remove your entry from `agent-status.json`, then append to
`~/Sync/agent-log.md`:

```
## YYYY-MM-DD HH:MM · <agent> · <project>
<What was done — 1–3 lines>

**Next:** <one concrete next step, or —>

---
```

Append only. Never edit existing entries. `**Next:**` line is required.
"""


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def patch(agents_md: Path, dry_run: bool = False) -> str:
    text = agents_md.read_text(encoding="utf-8")
    if SECTION_MARKER in text:
        return "already patched"
    new_text = text.rstrip("\n") + "\n" + SECTION
    if not dry_run:
        agents_md.write_text(new_text, encoding="utf-8")
    return "patched"


def main() -> None:
    apply = "--apply" in sys.argv
    skip_confirm = "--yes" in sys.argv
    dry_run = not apply

    candidates: list[Path] = []
    for root in SEARCH_ROOTS:
        if root.exists():
            candidates.extend(root.rglob("AGENTS.md"))

    own = [p for p in candidates if not should_skip(p)]
    targets = [p for p in own if not is_third_party(p)]
    third_party = [p for p in own if is_third_party(p)]

    if not targets:
        print("No AGENTS.md files to patch.")
        return

    to_write = [p for p in sorted(targets) if SECTION_MARKER not in p.read_text(encoding="utf-8")]

    print(f"Found {len(targets)} AGENTS.md file(s); {len(to_write)} would be modified:")
    for p in to_write:
        print(f"  ~/{p.relative_to(HOME)}")
    if third_party:
        print(f"Skipped {len(third_party)} file(s) in repos not in {sorted(OWN_REMOTE_OWNERS)}:")
        for p in sorted(third_party):
            print(f"  ~/{p.relative_to(HOME)}")

    if dry_run:
        print("\nDry run — no files written. Re-run with --apply to write.")
        return

    if to_write and not skip_confirm:
        answer = input(f"\nWrite the section above to {len(to_write)} file(s)? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Aborted, nothing written.")
            return

    patched = skipped = 0
    for p in sorted(targets):
        result = patch(p, dry_run=False)
        rel = p.relative_to(HOME)
        print(f"  [{result}] ~/{rel}")
        if result == "patched":
            patched += 1
        else:
            skipped += 1

    print(f"\n{patched} patched, {skipped} already up-to-date.")


if __name__ == "__main__":
    main()
