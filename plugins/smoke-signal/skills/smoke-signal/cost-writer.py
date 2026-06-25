#!/usr/bin/env python3
"""
Smoke Signal cost writer - Stop hook.

WHY THIS EXISTS: smoke-signal.py writes ~/.claude/cost-totals.json, but only as a
Terminal statusLine command. Tony works in the desktop app, where the statusLine
never runs, so cost-totals.json stayed empty. Stop/SessionEnd hooks do NOT receive
a cost field (confirmed against the Claude Code hooks docs), so a hook cannot read
the live cost from its own payload.

THE SOURCE WE USE: Claude Code persists authoritative cost to disk in
~/.claude.json under projects[<cwd>]: `lastCost` (USD for that project's most
recent COMPLETED session), `lastSessionId`, and a `lastModelUsage` breakdown.
These are real, Claude-Code-computed numbers (not token-math estimates), written
at session end. This hook syncs them into cost-totals.json keyed by the real
session id, so the per-project running total is accurate and never double counts.

Limitation, stated honestly: the IN-PROGRESS session's cost is not on disk until
it ends, so the live session is captured on the next session's syncs, not during
itself. The project TOTAL (what the footer's "project ~$Y" needs) is accurate.

Runs on every Stop. No stdout, exit 0 always, so it can never disturb the Anna
TTS Stop hook that shares this event.
"""

import sys
import os
import json

HOME = os.path.expanduser("~")
CLAUDE_DIR = os.path.join(HOME, ".claude")
TOTALS_FILE = os.path.join(CLAUDE_DIR, "cost-totals.json")
CLAUDE_JSON = os.path.join(HOME, ".claude.json")
OVERRIDE_FILE = os.path.join(CLAUDE_DIR, "active-project")
DEBUG_PAYLOAD = os.path.join(CLAUDE_DIR, "smoke-signal-stop-payload.json")

PROJECT_LABELS = {
    "pocket-shaman": "Pocket Shaman",
    "command-deck": "Command Deck",
    "command-deck-dashboard": "Command Deck",
    "grizzly-rag-llm": "Grizzly",
}


def title_from_slug(slug):
    return " ".join(w.capitalize() for w in slug.replace("_", "-").split("-") if w)


def derive_project(cwd):
    """Friendly project name from a working directory. Mirrors
    smoke-signal.derive_project so both writers agree on keys. The manual
    override is deliberately NOT applied here (we key by each project's own path,
    not the single active project)."""
    if not cwd:
        return "Claude Code"
    path = cwd.rstrip("/")
    low = path.lower()
    parts = [p for p in path.split("/") if p]
    if "g - workspace" in low:
        return "Dr. G"
    if "grizzly" in low:
        return "Grizzly"
    if "claude-workspace" in low:
        if "projects" in parts:
            i = parts.index("projects")
            if i + 1 < len(parts):
                slug = parts[i + 1].lower()
                return PROJECT_LABELS.get(slug, title_from_slug(parts[i + 1]))
        return "Claude Workspace"
    base = parts[-1] if parts else "Claude Code"
    return PROJECT_LABELS.get(base.lower(), title_from_slug(base) or base)


def load_totals():
    data = {"projects": {}}
    if os.path.isfile(TOTALS_FILE):
        try:
            loaded = json.load(open(TOTALS_FILE, "r"))
            if isinstance(loaded, dict) and isinstance(loaded.get("projects"), dict):
                data = loaded
        except Exception:
            pass
    return data


def save_totals(data):
    try:
        tmp = TOTALS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, TOTALS_FILE)
    except Exception:
        pass


def upsert(data, project, session_id, cost):
    """Record one session's cost under a project. Idempotent per session id;
    cost is the session total, so overwrite (never add)."""
    try:
        sc = float(cost or 0)
    except Exception:
        return False
    sid = session_id or "unknown"
    projects = data.setdefault("projects", {})
    entry = projects.setdefault(project, {"sessions": {}})
    sessions = entry.setdefault("sessions", {})
    if sessions.get(sid) == sc:
        return False  # already recorded with this value, nothing to do
    if sc > 0 or sid not in sessions:
        sessions[sid] = sc
        return True
    return False


def sync_from_claude_json(data):
    """Pull every project's last completed-session cost from ~/.claude.json into
    cost-totals.json. Returns True if anything changed."""
    changed = False
    try:
        cj = json.load(open(CLAUDE_JSON, "r"))
    except Exception:
        return False
    projects = cj.get("projects")
    if not isinstance(projects, dict):
        return False
    for path, e in projects.items():
        if not isinstance(e, dict):
            continue
        if "lastCost" not in e:
            continue
        sid = e.get("lastSessionId")
        if not sid:
            continue
        name = derive_project(path)
        if upsert(data, name, sid, e.get("lastCost")):
            changed = True
    return changed


def main():
    # Stash the raw Stop payload once per run for diagnostics (confirms the hook
    # is firing and what fields Claude Code actually sends).
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    try:
        with open(DEBUG_PAYLOAD, "w") as f:
            json.dump(payload if isinstance(payload, dict) else {}, f, indent=2)
    except Exception:
        pass

    data = load_totals()
    changed = sync_from_claude_json(data)

    # Future-proof: if a Stop payload ever DOES carry cost, record the current
    # session live too (keyed by its real id).
    if isinstance(payload, dict):
        cost = payload.get("cost")
        if isinstance(cost, dict) and cost.get("total_cost_usd") is not None:
            sid = payload.get("session_id") or ""
            cwd = payload.get("cwd") or ""
            ws = payload.get("workspace")
            if not cwd and isinstance(ws, dict):
                cwd = ws.get("current_dir") or ws.get("project_dir") or ""
            if sid:
                if upsert(data, derive_project(cwd), sid, cost.get("total_cost_usd")):
                    changed = True

    if changed:
        save_totals(data)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
