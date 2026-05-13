#!/usr/bin/env python3
"""
patch-agents.py — append Activity Monitor section to every project AGENTS.md.

Idempotent: skips files that already contain the section.
Skips: this project, AI-Agents, AI-GovernanceKit, cache dirs, node_modules.
"""
from __future__ import annotations

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
    dry_run = "--dry-run" in sys.argv

    candidates: list[Path] = []
    for root in SEARCH_ROOTS:
        if root.exists():
            candidates.extend(root.rglob("AGENTS.md"))

    targets = [p for p in candidates if not should_skip(p)]

    if not targets:
        print("No AGENTS.md files found.")
        return

    patched = skipped = 0
    for p in sorted(targets):
        result = patch(p, dry_run=dry_run)
        rel = p.relative_to(HOME)
        print(f"  [{result}] ~/{rel}")
        if result == "patched":
            patched += 1
        else:
            skipped += 1

    tag = " (dry run)" if dry_run else ""
    print(f"\n{patched} patched, {skipped} already up-to-date{tag}.")


if __name__ == "__main__":
    main()
