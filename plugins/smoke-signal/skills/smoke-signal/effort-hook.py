#!/usr/bin/env python3
"""
UserPromptSubmit hook for the smoke-signal skill.

The Smoke Signal footer that Claude types in the desktop app shows the current
reasoning effort in the model parenthetical, e.g. "Opus 4.8 (high)". The harness
does NOT put that value into Claude's normal prompt context, so Claude was
guessing it and getting it wrong.

The harness DOES expose the live reasoning effort to hooks: as the $CLAUDE_EFFORT
environment variable and, on some events, as an "effort" object on the stdin
JSON (effort.level = low/medium/high/xhigh/max). This hook reads that live value,
injects it into Claude's context every turn so the footer is always correct, and
mirrors it to ~/.claude/active-effort so the status-line script has a fallback.
"""
import json
import os
import sys

EFFORT_FILE = os.path.expanduser("~/.claude/active-effort")
VALID = {"low", "medium", "high", "xhigh", "max", "fast"}


def detect_effort(data):
    # 1) stdin JSON effort.level (live, preferred when present)
    try:
        eff = data.get("effort")
        if isinstance(eff, dict):
            lvl = (eff.get("level") or "").strip().lower()
            if lvl:
                return lvl
        elif isinstance(eff, str) and eff.strip():
            return eff.strip().lower()
    except Exception:
        pass
    # 2) environment variable exported to the hook process
    env = (os.environ.get("CLAUDE_EFFORT") or "").strip().lower()
    if env:
        return env
    # 3) last-known mirror on disk
    try:
        with open(EFFORT_FILE) as f:
            v = f.read().strip().lower()
            if v:
                return v
    except Exception:
        pass
    return ""


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    effort = detect_effort(data)

    if effort:
        try:
            with open(EFFORT_FILE, "w") as f:
                f.write(effort + "\n")
        except Exception:
            pass
        msg = (
            "SMOKE SIGNAL EFFORT: the current reasoning effort is '{0}'. Use exactly "
            "this value in the footer's model parenthetical, e.g. 'Opus 4.8 ({0})'. "
            "This is the live value from the harness. Do not guess effort or infer "
            "it from anything else.".format(effort)
        )
    else:
        msg = (
            "SMOKE SIGNAL EFFORT: reasoning effort is unknown this turn. Omit the "
            "effort parenthetical from the footer entirely."
        )

    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": msg,
        }
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
