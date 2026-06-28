---
name: smoke-signal
description: Always-on Claude Code status line. Renders one compact line at the bottom of every session in every project, showing the active project name first, then the running model and tier, then this session's tokens and cost, then the project's running cost total across all sessions. A passive, no-questions companion to Token Saver, the readout is always lit, never prompts, and never interrupts. Use this skill when Tony says "smoke signal", asks how the status line works, why the project name is wrong, why the cost looks off, how to force a project name, or how to change the model pricing or tiers. The behavior is enforced by the statusLine entry in settings.json, this skill is the how-it-works and maintenance surface.
---

# Smoke Signal

Smoke Signal is Tony's always-on Claude Code status line. It is the signal rising at the edge of camp, glance down and it tells you where you are, who is steering, and what the fire is costing. It runs on every turn, in every project, with no prompts and no questions.

It is the passive twin of Token Saver. Token Saver is an interactive skill that asks questions, suggests model switches, and compresses output. Smoke Signal asks nothing. It just keeps the readout lit. Both can run at once, they do not conflict.

---

## What It Shows

One compact line, left to right:

```
Pocket Shaman | Opus 4.8 (high) | session 142k tok ~$1.20 | ctx 121k/1M (12%) | project ~$2.87
```

1. **Active project** (first and most prominent, bold gold). Where you are working right now.
2. **Model and effort** (green). The real running model plus the current reasoning effort (low / medium / high, or fast).
3. **Session readout** (blue). This session's token count and cost.
4. **Context usage** (dim). Approximate context-window use with percent. Near the ceiling it flips to an inline alert (see below).
5. **Project total** (dim). The running cost for this project across all sessions.

No em or en dashes ever appear in the line, pipes and commas only.

### Context alert (no popup)

When context usage reaches **75%** of the window, the footer flips to an alert form right in place, no popup, nothing interrupts the session.

- In the **Terminal**: the ctx segment renders in bold red ANSI text.
- In the **app footer**: the whole footer is wrapped in a fenced ```` ```diff ```` block with a leading `-`, which the app paints red. No HTML, no emoji, no dot.

Example app alert:

````
```diff
- Pocket Shaman | Opus 4.8 (high) | session ~$1.90 | ctx 850k/1M (85%) compact or start a new session | project ~$2.87
```
````

Threshold is `ALERT_PCT` in the script (default 75).

---

## Two Ways It Renders

Smoke Signal carries the same data, project, model, session cost, project total, but it delivers it two different ways depending on the surface. This matters: a Claude Code `statusLine` only paints in the Terminal, so the desktop and web apps need a different pipe.

- **Desktop and web app (primary): a footer line.** The readout is printed as PLAIN TEXT as the last line of every reply, so it renders anywhere chat renders. Standing rule in the workspace CLAUDE.md: end every response with `Project | Model (effort) | session ~$X | ctx ~NNk/WINDOW (P%) | project ~$Y`. **No HTML tags ever** (`<sub>`, `<span>`, etc. render as literal visible text in Tony's app). To make it smaller, shorten the wording, never add tags. The alert state uses a fenced ```diff``` block instead (see Context Usage).
- **Verify before writing.** Claude must NOT repeat the previous footer's values from memory. At the start of every turn, refresh each segment from the live state: model and effort from the current turn's context (fall back to `~/.claude/active-effort` for effort, drop the parenthetical if both are unknown), session/project cost from the running totals, ctx % from this turn's input-side tokens against the model window. If a value is unknown, omit that segment rather than guess. The footer can lie if not refreshed; this rule keeps it honest.
- **Terminal CLI (secondary): the native status line.** The `statusLine` key in settings.json runs the engine script every turn and paints the bar at the bottom of the Terminal. Only the Terminal honors this slot.

Both surfaces honor the same off switch (`~/.claude/smoke-signal-off`). Use whichever surface you are in, or both.

---

## Hard Truth About Models

The status line reports the **real running model**, the one Claude Code hands it on stdin every turn. That is the model actually doing the work and being billed. A skill or a status line cannot change which model runs, that is set by Tony's app model dropdown. Smoke Signal never displays a model Tony only "picked", it shows what is live.

---

## How It Works

- Config lives in `~/.claude/settings.json` under the top-level `statusLine` key:
  ```json
  "statusLine": {
    "type": "command",
    "command": "python3 /Users/spiritwalker/.claude/skills/smoke-signal/smoke-signal.py"
  }
  ```
- Claude Code runs that command every turn and pipes a JSON payload to it on stdin. Whatever the script prints to stdout becomes the status line.
- Settings and hook changes load at session start, so a new install or an edit to the script needs a Claude Code restart to take effect.

### The payload (fields the script reads)
- `workspace.current_dir` (falls back to `cwd`) drives the project name.
- `model.display_name` and `model.id` drive the model name and tier.
- `cost.total_cost_usd` is the session cost, used directly when present.
- `transcript_path` is parsed to count session tokens.
- `session_id` keys the project total so a session is never double counted.

The first payload the script ever sees is saved once to `~/.claude/smoke-signal-last-payload.json` so the real field shape can be confirmed. Delete that file to capture a fresh sample.

---

## Turning It Off and On

Smoke Signal is on by default the moment it is installed, baked in globally for every session. To switch it off and on there is a simple flag file, no restart and no settings editing needed, the change takes effect on the very next turn.

- **Off:** create `~/.claude/smoke-signal-off`. The line goes blank.
  ```
  touch ~/.claude/smoke-signal-off
  ```
- **On:** delete that file. The line returns.
  ```
  rm ~/.claude/smoke-signal-off
  ```

**Voice toggle.** When Tony says "smoke signal off", "turn off smoke signal", or "kill the status line", create the off file. When he says "smoke signal on", "turn smoke signal back on", or "bring back the status line", remove it. Confirm the new state in one short line. Default is always on.

**Anna voice never reads the footer aloud.** The anna-voice Stop hook (`~/.claude/skills/anna-voice/stop-hook.py`) calls `strip_smoke_signal()` before TTS, removing the plain footer line (the alert variant is a fenced diff block, already dropped by `strip_markdown`). The footer is visual only, the body's last sentence ends the spoken response.

---

## Active Project Detection

Resolved from the working directory in this order:

1. **Override file.** If `~/.claude/active-project` exists and is non-empty, its text is the project name, no questions asked. Use this for the rare case the working directory does not reflect the real focus.
2. Path contains `G - workspace` then it is **Dr. G**.
3. Path contains `grizzly` then it is **Grizzly**.
4. Path under `Claude-Workspace/projects/<name>` then `<name>` is mapped to a friendly label (see the map below), or title-cased.
5. Path at or above the `Claude-Workspace` root then it is **Claude Workspace**.
6. Otherwise the folder basename, friendly-mapped or title-cased.

**Friendly label map** (easy to extend in the script's `PROJECT_LABELS`):

| Folder slug | Shown as |
|---|---|
| pocket-shaman | Pocket Shaman |
| command-deck | Command Deck |
| grizzly-rag-llm | Grizzly |

To force a name for one session:
```
echo "Command Deck" > ~/.claude/active-project
```
Remove it to return to automatic detection:
```
rm ~/.claude/active-project
```

---

## Model and Effort

The parenthetical after the model is the **current reasoning effort**, low / medium / high, or fast. It is not a made-up capability word.

The harness exposes the live reasoning effort, so neither surface guesses any more. It is read in this priority:

1. The turn payload's `effort.level` (low / medium / high / xhigh / max), which the Terminal engine reads straight from stdin.
2. The `$CLAUDE_EFFORT` environment variable, exported to every hook process.
3. `~/.claude/active-effort`, a one-word fallback file the hook keeps mirrored.

`effort-hook.py` is a UserPromptSubmit hook that reads the live value every turn, injects it into Claude's context so the app footer prints the correct effort with no guessing, and rewrites the mirror file. This replaced the old behavior where the app footer effort was guessed by Claude and was often wrong (it would show medium while the session was on high). If the value is genuinely unknown the parenthetical is dropped. Hooks load at session start, so a fresh install or a hook edit needs a Claude Code restart.

---

## Context Usage and the Alert

**Context used** is read from the transcript: the last turn's input side (input + cache creation + cache read), which is the size of the window currently in play. It is shown against the live window for the active model variant (Opus and Fable 1M; Sonnet and Haiku 200K, with Sonnet reaching 1M only via the `sonnet[1m]` variant) with a percent.

In the **Terminal**, `smoke-signal.py` reads this straight from the transcript every turn, so it is always accurate. In the **app**, the footer is typed by Claude, who used to ESTIMATE the percentage and drift badly (once showing 62% at a true 82%). That is now fixed by `ctx-hook.py`, a UserPromptSubmit hook that mirrors the effort hook. It runs the same transcript math (input + cache creation + cache read) and injects the MEASURED context as of the moment the user hit enter, the exact ctx string for Claude to print. This is the only provably-exact value: it equals the user's live context meter at send time, and closely whenever the reply is short. The honest limit, stated plainly: a footer is text Claude types, so the reply's own work is not yet on the transcript when the number is written, and on a tool-heavy turn (big file reads, many edits) the meter climbs above the footer as that work lands. No pre-written number can predict that, and the true post-reply context is only re-counted on the NEXT turn. A forward-projection variant was tried and dropped because it underread badly on heavy turns. The hook writes `~/.claude/active-ctx` (`measured|window|pct|projected`) as a fallback and tells Claude when usage is past 75% so the red diff block and fire widget fire on the true threshold. Like all hooks, it loads at session start, so a fresh install or hook edit needs a Claude Code restart.

When usage reaches `ALERT_PCT` (default 75%), the ctx segment flips to the inline alert: bold red in the Terminal, and in the app footer the whole line is wrapped in a fenced ```diff``` block with a leading `-` so it paints red (no HTML, no emoji). At the same 75% mark the app also renders the compaction-alert widget (see below). No popup, nothing interrupts.

## Compaction Alert Widget (app)

At 75% the desktop and web app also shows a small animated panel: the footer line with the percentage pulsing red, a thin half-size flame 1px to the right of it, and three wavy smoke trails rising and fading off the flame. It is a visual flare that fires only in the danger zone, right before compaction.

- Template: `widget/compaction-alert.html` in this skill. It carries three tokens, `{{PRE}}`, `{{PCT}}`, `{{POST}}`, for the live footer values.
- To render: read the template, substitute the current footer text (everything up to and including `ctx ~NNNk/1M ` into `{{PRE}}`, the percentage into `{{PCT}}`, the rest into `{{POST}}`), strip the leading HTML comment, and pass it to the show_widget tool.
- It only renders when ctx is at or past 75%, never every turn, so it does not burn context while there is plenty left. The plain footer line is still printed as the canonical readout; the widget is the loud flare on top.
- App and web only. A plain Terminal cannot render the animation; there the bold red ctx segment is the alert.

---

## Cost and Tokens

**Session cost** comes straight from `cost.total_cost_usd` in the payload, the figure Claude Code itself reports. The pricing table below is a fallback for computing cost only when the payload does not provide one.

**Session tokens** are summed from the transcript: input + output + cache creation. Cache reads are excluded on purpose so the number stays meaningful instead of ballooning into the millions. Transcripts over 25 MB are skipped for speed, the line then shows cost only.

**Pricing table (per 1M tokens), matches Token Saver:**

| Model | Input | Output |
|---|---|---|
| claude-haiku-4-5 | $0.80 | $4.00 |
| claude-sonnet-4-6 | $3.00 | $15.00 |
| claude-opus-4-8 | $15.00 | $75.00 |

Cost math: `cost = (input_tokens / 1,000,000 x input_rate) + (output_tokens / 1,000,000 x output_rate)`

**Formatting:**
- Tokens: `850`, `142k`, `1.2M`.
- Cost: `$0.23`, `$1.20`, `<$0.01` when under a cent, `$0.00` only at true zero.

---

## Project Total (persists across sessions)

The running project total is stored in `~/.claude/cost-totals.json`:

```json
{
  "projects": {
    "Pocket Shaman": {
      "sessions": { "<session_id>": 1.55 }
    }
  }
}
```

- Each session's cumulative cost is written under its `session_id`, so re-running the line within a session **overwrites** rather than adds, no double counting.
- The displayed project total is the sum of every session value for that project, recomputed live every turn.
- The file is written atomically (temp then rename) so a status-line run can never corrupt it.

To reset a project's history, edit or clear that project's block in the file. To wipe everything, set the file to `{"projects": {}}`.

---

## Never Crashes the Session

Every read, parse, and write is guarded. On any error the script degrades to a minimal safe line and exits 0. Garbage input, empty input, a missing transcript, or a corrupt totals file will not take down the session. The absolute last resort prints `Claude Code`.

---

## Maintenance

| Want to | Do this |
|---|---|
| Add a friendly project name | Add a slug to `PROJECT_LABELS` in the script |
| Change a tier tag | Edit the tier in the `PRICING` map |
| Update model prices | Edit the `PRICING` map (cross-check the `claude-api` skill) |
| Force a project name | Write `~/.claude/active-project` |
| Capture a fresh payload sample | Delete `~/.claude/smoke-signal-last-payload.json`, then take one turn |
| Reset project totals | Edit `~/.claude/cost-totals.json` |
| Turn the line off | Remove the `statusLine` key from `~/.claude/settings.json`, restart |

After any edit, restart Claude Code so the change loads.

---

## Troubleshooting

- **Line is blank or shows only `Claude Code`.** The payload was empty or malformed, or the script path is wrong. Confirm the `statusLine.command` path and that the script is executable.
- **Wrong project name.** The working directory did not match a rule. Add a `PROJECT_LABELS` entry, or drop an `~/.claude/active-project` override.
- **No token count.** The transcript was missing or too large (over 25 MB), the line falls back to cost only. This is expected, not an error.
- **Cost reads $0.00.** Early in a session before any billable work, or the payload carried no `cost` block. It fills in as the session runs.
- **Edit did not take.** Status line config loads at session start, restart Claude Code.

---

## Relationship to Token Saver

- **Token Saver** is interactive: intake questions, per-turn model-switch alerts, compression, end-of-session tracker writes. Reach for it when actively trying to cut spend.
- **Smoke Signal** is passive: a constant readout, no prompts, always on. It is the glanceable ground truth that runs underneath everything.

They share the same pricing brain and the same honesty rule (show the real running model). Run both together with no conflict.
