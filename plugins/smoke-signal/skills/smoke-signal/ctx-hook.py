#!/usr/bin/env python3
"""
UserPromptSubmit hook for the smoke-signal skill: LIVE CONTEXT USAGE.

The Smoke Signal footer that Claude types in the desktop app shows context-window
usage, e.g. "ctx ~865k/1M (86%)". The harness does NOT hand Claude the live token
count inside the chat, so Claude was ESTIMATING it and drifting badly (reported
62% when the true usage was 82% - a 20-point miss). The 75% fire-and-smoke
compaction flare could then fire late or with wrong numbers.

This hook fixes that. It reads the SAME source the Terminal status line uses (the
session transcript's last-turn usage) with the SAME math as smoke-signal.py's
count_usage(), then injects the REAL ctx number into Claude's context every turn,
exactly the way effort-hook.py injects the live reasoning effort. It also mirrors
the values to ~/.claude/active-ctx as a fallback.

context_used = the LAST turn's input-side total (input + cache_creation +
cache_read), i.e. the size of the context window currently in play. This is a
measured number, never a guess.
"""
import json
import os
import sys

CTX_FILE = os.path.expanduser("~/.claude/active-ctx")
MAX_TRANSCRIPT_BYTES = 25 * 1024 * 1024
DEFAULT_WINDOW = 200_000
ONE_M_WINDOW = 1_000_000
ALERT_PCT = 75


def count_context(transcript_path):
    """Return (context_used, model_id, projected).
    context_used = input + cache_creation + cache_read of the most recent turn
    (the exact context as of when the user hit enter).
    projected = context_used plus the typical recent per-turn growth, so a footer
    printed with it lands where the live meter sits AFTER this reply. The growth
    is measured from the transcript, not guessed; on a turn with unusually large
    tool output it can under/over shoot, which cannot be known in advance.
    Best effort, never raises."""
    context = 0
    model_id = ""
    series = []  # successive whole-context sizes, in file order
    try:
        if not transcript_path or not os.path.isfile(transcript_path):
            return 0, "", 0
        if os.path.getsize(transcript_path) > MAX_TRANSCRIPT_BYTES:
            return 0, "", 0
        with open(transcript_path, "r", errors="ignore") as f:
            for raw in f:
                if '"usage"' not in raw:
                    continue
                try:
                    obj = json.loads(raw)
                except Exception:
                    continue
                usage = None
                mid = ""
                if isinstance(obj, dict):
                    msg = obj.get("message")
                    if isinstance(msg, dict) and isinstance(msg.get("usage"), dict):
                        usage = msg["usage"]
                        mid = msg.get("model") or ""
                    elif isinstance(obj.get("usage"), dict):
                        usage = obj["usage"]
                if not usage:
                    continue
                inp = int(usage.get("input_tokens", 0) or 0)
                cc = int(usage.get("cache_creation_input_tokens", 0) or 0)
                cr = int(usage.get("cache_read_input_tokens", 0) or 0)
                this_ctx = inp + cc + cr
                if this_ctx > 0:
                    context = this_ctx  # last value wins = current context size
                    series.append(this_ctx)
                    if mid:
                        model_id = mid
    except Exception:
        return 0, "", 0

    # Measure typical recent per-turn growth from the series of context sizes.
    # Keep only sane positive jumps (ignore compaction drops and zero-deltas).
    deltas = []
    for a, b in zip(series, series[1:]):
        d = b - a
        if 50 <= d <= 25000:
            deltas.append(d)
    growth = 0
    if deltas:
        recent = deltas[-5:]
        growth = int(round(sum(recent) / len(recent)))
    projected = context + growth if context > 0 else 0
    return context, model_id, projected


def resolve_window(model_id, payload):
    """Context window in tokens for the active model. Same rules as
    smoke-signal.py: explicit number wins; a [1m] marker => 1M; Opus and Fable
    default to 1M; everything else defaults to 200k. Never inferred from a
    model's theoretical max."""
    # explicit number from the payload model object, if the harness ever sends one
    model_obj = payload.get("model") if isinstance(payload, dict) else None
    if isinstance(model_obj, dict):
        for key in ("context_window", "contextWindow", "max_input_tokens",
                    "maxInputTokens", "context_limit", "window"):
            try:
                v = int(model_obj.get(key))
                if v > 0:
                    return v
            except Exception:
                pass
        model_id = ((model_obj.get("id") or "") + " " + (model_obj.get("display_name") or "")) or model_id
    mid = (model_id or "").lower()
    if "[1m]" in mid or "1000000" in mid:
        return ONE_M_WINDOW
    if "opus" in mid or "fable" in mid:
        return ONE_M_WINDOW
    if "sonnet" in mid or "haiku" in mid:
        return DEFAULT_WINDOW
    return DEFAULT_WINDOW


def fmt_window(w):
    if w >= 1_000_000:
        return "{:g}M".format(w / 1_000_000)
    return "{:.0f}k".format(w / 1_000)


def fmt_tokens(n):
    if n >= 1_000_000:
        return "{:.2f}M".format(n / 1_000_000)
    if n >= 100_000:
        return "{:.0f}k".format(n / 1_000)
    if n >= 1_000:
        # below 100k the decimal matters: 99844 reads as 99.8k, not 100k
        return "{:.1f}k".format(n / 1_000)
    return str(n)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    transcript = ""
    if isinstance(data, dict):
        transcript = data.get("transcript_path") or ""

    context_used, model_id, projected = count_context(transcript)
    window = resolve_window(model_id, data)

    if context_used > 0 and window > 0:
        # Print the MEASURED context as of the user's send. This is the only number
        # that is provably exact at a known instant; it equals the live meter at
        # send time and whenever the reply is short. Forward projection was dropped
        # because it cannot anticipate a tool-heavy turn's own growth (the reply's
        # work does not exist yet when the footer is written).
        show = context_used
        pct = int(round(100.0 * show / window))
        ctx_str = "ctx ~{}/{} ({}%)".format(fmt_tokens(show), fmt_window(window), pct)
        try:
            with open(CTX_FILE, "w") as f:
                f.write("{}|{}|{}|{}\n".format(show, window, pct, projected))
        except Exception:
            pass
        base = (
            "SMOKE SIGNAL CTX: print this EXACT ctx segment in the footer: {0}. This is "
            "the MEASURED context (input + cache_creation + cache_read) as of the moment "
            "the user hit enter - the only provably-exact value. It equals the user's "
            "live meter at send time and whenever your reply is short; on a tool-heavy "
            "turn the meter will climb above it as that work lands, which no pre-written "
            "number can predict. Use these EXACT values - do NOT re-estimate or round "
            "them differently. measured={2} tokens, window={1}, usage={3}%."
        ).format(ctx_str, fmt_window(window), show, pct)
        if pct >= ALERT_PCT:
            alert = (
                " ALERT STATE: usage is at or past 75%. Render the footer as a one-line "
                "fenced ```diff block with a leading '-' so it shows RED, AND render the "
                "compaction-alert fire-and-smoke widget via show_widget using "
                "~/.claude/skills/smoke-signal/widget/compaction-alert.html with these "
                "live values substituted into {{PRE}} / {{PCT}} / {{POST}}."
            )
            msg = base + alert
        else:
            msg = base + (
                " Usage is below 75%: render the footer as a normal plain-text line, no "
                "red diff block and no fire widget."
            )
    else:
        msg = (
            "SMOKE SIGNAL CTX: live context usage could not be measured this turn "
            "(no transcript usage yet). Estimate conservatively and mark it with ~, or "
            "omit the ctx segment if genuinely unknown."
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
