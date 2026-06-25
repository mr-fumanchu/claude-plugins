#!/usr/bin/env python3
"""
Smoke Signal - always-on Claude Code status line.
Renders one compact line every turn:  PROJECT | MODEL (tier) | session tokens ~cost | project ~total

Reads the Status payload JSON on stdin. Never crashes the session: on any
error it prints a minimal safe line and exits 0.

House rules honored: no em or en dashes in any visible text; pipes and commas only.
"""

import sys
import os
import json

HOME = os.path.expanduser("~")
CLAUDE_DIR = os.path.join(HOME, ".claude")
TOTALS_FILE = os.path.join(CLAUDE_DIR, "cost-totals.json")
OVERRIDE_FILE = os.path.join(CLAUDE_DIR, "active-project")
OFF_FILE = os.path.join(CLAUDE_DIR, "smoke-signal-off")
EFFORT_FILE = os.path.join(CLAUDE_DIR, "active-effort")
DEBUG_PAYLOAD = os.path.join(CLAUDE_DIR, "smoke-signal-last-payload.json")

# Transcripts bigger than this are skipped for token counting (keeps it fast).
MAX_TRANSCRIPT_BYTES = 25 * 1024 * 1024

# ---- ANSI color (status lines render ANSI) -------------------------------
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GOLD = "\033[38;5;179m"      # warm gold, project name
GREEN = "\033[38;5;108m"     # forest-ish, model
BLUE = "\033[38;5;110m"      # soft navy/blue, cost
RED = "\033[1m\033[38;5;167m"  # bold red, context alert near the ceiling
SEP = DIM + "  |  " + RESET

# Context-window usage percent at which the ctx segment flips to the alert style.
ALERT_PCT = 75


# ---- pricing brain (per million tokens). Easy to update. -----------------
# (input $/Mtok, output $/Mtok). Used only as a fallback when the payload does
# not hand us a session cost directly.
PRICING = {
    "opus":   (15.0, 75.0),
    "sonnet": (3.0,  15.0),
    "haiku":  (0.80, 4.0),
    "fable":  (15.0, 75.0),
}

# Context window per model family (tokens).
WINDOWS = {
    "haiku": 200_000,
    "opus": 1_000_000,
    "sonnet": 1_000_000,
    "fable": 1_000_000,
}
DEFAULT_WINDOW = 1_000_000

# Friendly labels for known project folder names.
PROJECT_LABELS = {
    "pocket-shaman": "Pocket Shaman",
    "command-deck": "Command Deck",
    "command-deck-dashboard": "Command Deck",
    "grizzly-rag-llm": "Grizzly",
}


def safe_print(line):
    try:
        sys.stdout.write(line)
    except Exception:
        pass


def title_from_slug(slug):
    return " ".join(w.capitalize() for w in slug.replace("_", "-").split("-") if w)


def derive_project(cwd):
    """Figure out the active project name from the working directory."""
    # Manual override always wins.
    try:
        if os.path.isfile(OVERRIDE_FILE):
            with open(OVERRIDE_FILE, "r") as f:
                forced = f.read().strip()
            if forced:
                return forced
    except Exception:
        pass

    if not cwd:
        return "Claude Code"

    path = cwd.rstrip("/")
    low = path.lower()
    parts = [p for p in path.split("/") if p]

    # Dr. G workspace
    if "g - workspace" in low:
        return "Dr. G"

    # Grizzly RAG LLM folder
    if "grizzly" in low:
        return "Grizzly"

    # Anything under Claude-Workspace/projects/<name>
    if "claude-workspace" in low:
        if "projects" in parts:
            i = parts.index("projects")
            if i + 1 < len(parts):
                slug = parts[i + 1].lower()
                return PROJECT_LABELS.get(slug, title_from_slug(parts[i + 1]))
        # At or above the workspace root
        return "Claude Workspace"

    # Fallback: friendly map or basename
    base = parts[-1] if parts else "Claude Code"
    return PROJECT_LABELS.get(base.lower(), title_from_slug(base) or base)


def model_and_window(model):
    """Return (display_name, context_window) for the running model."""
    name = ""
    mid = ""
    if isinstance(model, dict):
        name = model.get("display_name") or model.get("id") or ""
        mid = (model.get("id") or "").lower()
    blob = (mid + " " + name).lower()
    window = DEFAULT_WINDOW
    for key, w in WINDOWS.items():
        if key in blob:
            window = w
            break
    if not name:
        name = "Claude"
    return name, window


def get_effort(payload=None):
    """Current reasoning effort. The status-line payload carries it live as
    effort.level (low/medium/high/xhigh/max), including mid-session changes.
    Fall back to $CLAUDE_EFFORT, then ~/.claude/active-effort."""
    try:
        if isinstance(payload, dict):
            eff = payload.get("effort")
            if isinstance(eff, dict):
                lvl = (eff.get("level") or "").strip()
                if lvl:
                    return lvl
            elif isinstance(eff, str) and eff.strip():
                return eff.strip()
    except Exception:
        pass
    env = (os.environ.get("CLAUDE_EFFORT") or "").strip()
    if env:
        return env
    try:
        if os.path.isfile(EFFORT_FILE):
            v = open(EFFORT_FILE, "r").read().strip()
            if v:
                return v
    except Exception:
        pass
    return ""


def fmt_window(w):
    try:
        w = int(w)
    except Exception:
        return ""
    if w >= 1_000_000:
        return "{:g}M".format(w / 1_000_000)
    return "{:.0f}k".format(w / 1_000)


def fmt_tokens(n):
    try:
        n = int(n)
    except Exception:
        return None
    if n <= 0:
        return None
    if n >= 1_000_000:
        return "{:.1f}M".format(n / 1_000_000)
    if n >= 1_000:
        return "{:.0f}k".format(n / 1_000)
    return str(n)


def fmt_cost(c):
    try:
        c = float(c)
    except Exception:
        return None
    if c <= 0:
        return "$0.00"
    if c < 0.01:
        return "<$0.01"
    return "${:.2f}".format(c)


def count_usage(transcript_path):
    """Return (session_tokens, context_used).
    session_tokens = input + output + cache creation summed across all turns
    (cache reads excluded so the number stays meaningful).
    context_used = the LAST turn's input-side total (input + cache creation +
    cache read), i.e. the size of the context window currently in play.
    Best effort, never raises."""
    try:
        if not transcript_path or not os.path.isfile(transcript_path):
            return 0, 0
        if os.path.getsize(transcript_path) > MAX_TRANSCRIPT_BYTES:
            return 0, 0
        session = 0
        context = 0
        with open(transcript_path, "r", errors="ignore") as f:
            for raw in f:
                raw = raw.strip()
                if not raw or '"usage"' not in raw:
                    continue
                try:
                    obj = json.loads(raw)
                except Exception:
                    continue
                usage = None
                if isinstance(obj, dict):
                    msg = obj.get("message")
                    if isinstance(msg, dict) and isinstance(msg.get("usage"), dict):
                        usage = msg["usage"]
                    elif isinstance(obj.get("usage"), dict):
                        usage = obj["usage"]
                if not usage:
                    continue
                inp = int(usage.get("input_tokens", 0) or 0)
                out = int(usage.get("output_tokens", 0) or 0)
                cc = int(usage.get("cache_creation_input_tokens", 0) or 0)
                cr = int(usage.get("cache_read_input_tokens", 0) or 0)
                session += inp + out + cc
                this_ctx = inp + cc + cr
                if this_ctx > 0:
                    context = this_ctx  # last turn wins = current context size
        return session, context
    except Exception:
        return 0, 0


def update_project_total(project, session_id, session_cost):
    """Persist this session's cost under the project and return the running
    project total across all sessions. Idempotent per session id."""
    try:
        data = {"projects": {}}
        if os.path.isfile(TOTALS_FILE):
            try:
                with open(TOTALS_FILE, "r") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict) and isinstance(loaded.get("projects"), dict):
                    data = loaded
            except Exception:
                data = {"projects": {}}

        projects = data.setdefault("projects", {})
        entry = projects.setdefault(project, {"sessions": {}})
        sessions = entry.setdefault("sessions", {})

        sid = session_id or "unknown"
        try:
            sc = float(session_cost or 0)
        except Exception:
            sc = 0.0
        # Session cost is cumulative, so overwrite (do not add) to avoid double counting.
        if sc > 0 or sid not in sessions:
            sessions[sid] = sc

        running = 0.0
        for v in sessions.values():
            try:
                running += float(v)
            except Exception:
                pass

        # Atomic write so a status-line run can never corrupt the file.
        tmp = TOTALS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, TOTALS_FILE)
        return running
    except Exception:
        try:
            return float(session_cost or 0)
        except Exception:
            return 0.0


def main():
    # Toggle: if the off file exists, render nothing. On by default (no file).
    # Takes effect on the next turn, no restart needed.
    if os.path.isfile(OFF_FILE):
        return

    raw = ""
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""

    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    # Stash the last payload once so we can confirm the real field shape.
    try:
        if not os.path.isfile(DEBUG_PAYLOAD) and payload:
            with open(DEBUG_PAYLOAD, "w") as f:
                json.dump(payload, f, indent=2)
    except Exception:
        pass

    # Working directory
    cwd = payload.get("cwd") or ""
    ws = payload.get("workspace")
    if isinstance(ws, dict):
        cwd = ws.get("current_dir") or cwd or ws.get("project_dir") or ""

    project = derive_project(cwd)
    model_name, window = model_and_window(payload.get("model"))
    effort = get_effort(payload)

    session_id = payload.get("session_id") or ""
    transcript = payload.get("transcript_path") or ""

    # Session cost: prefer the value Claude Code hands us directly.
    session_cost = 0.0
    cost = payload.get("cost")
    if isinstance(cost, dict):
        try:
            session_cost = float(cost.get("total_cost_usd", 0) or 0)
        except Exception:
            session_cost = 0.0

    tokens, context_used = count_usage(transcript)
    project_total = update_project_total(project, session_id, session_cost)

    # ---- assemble the line --------------------------------------------------
    proj_part = BOLD + GOLD + project + RESET

    model_label = "{} ({})".format(model_name, effort) if effort else model_name
    model_part = GREEN + model_label + RESET

    sess_bits = []
    tok = fmt_tokens(tokens)
    if tok:
        sess_bits.append(tok + " tok")
    sc = fmt_cost(session_cost)
    if sc:
        sess_bits.append("~" + sc)
    sess_part = BLUE + "session " + (" ".join(sess_bits) if sess_bits else "starting") + RESET

    parts = [proj_part, model_part, sess_part]

    # Context-window usage, with an inline alert near the ceiling (no popup).
    if context_used > 0 and window > 0:
        pct = int(round(100.0 * context_used / window))
        ctx_text = "ctx {}/{} ({}%)".format(fmt_tokens(context_used), fmt_window(window), pct)
        if pct >= ALERT_PCT:
            parts.append(RED + ctx_text + " compact or start a new session" + RESET)
        else:
            parts.append(DIM + ctx_text + RESET)

    parts.append(DIM + "project ~" + (fmt_cost(project_total) or "$0.00") + RESET)

    safe_print(SEP.join(parts))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Absolute last resort: never let the status line take down the session.
        safe_print("Claude Code")
