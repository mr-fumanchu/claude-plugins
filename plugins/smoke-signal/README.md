# Smoke Signal (Claude Code plugin)

An always-on status readout for Claude Code. One compact line shows the active project, the live model and reasoning effort, this session's cost, context-window usage, and the project's running cost across sessions. At 75% context use it raises a red compaction alert with an animated fire-and-smoke widget so you see the limit coming.

## What's in the plugin
- `skills/smoke-signal/` — the skill (how-it-works and maintenance surface), the status-line engine `smoke-signal.py`, and the `widget/compaction-alert.html` flare.
- `hooks/hooks.json` — three hooks:
  - `UserPromptSubmit` → `effort-hook.py`: reads the live reasoning effort and injects it so the footer is always correct (no guessing).
  - `UserPromptSubmit` → `ctx-hook.py`: reads the real context usage from the transcript and projects it one step forward (measured context plus the user's typical recent per-turn growth), so the app footer lands on what the live meter reads after the reply instead of trailing it. Injects the exact ctx string and fires the 75% alert on the true threshold.
  - `Stop` → `cost-writer.py`: records session cost into `~/.claude/cost-totals.json` for the project total.

## Install
```
/plugin marketplace add mr-fumanchu/claude-plugins
```
```
/plugin install smoke-signal@claude-plugins
```
Restart Claude Code so the hooks load.

## The Terminal status bar is optional and manual
A plugin cannot set the Terminal `statusLine` (only your own settings.json can). The plugin already delivers the app footer, the effort hook, the cost tracker, and the 75% widget. If you also want the native bar at the bottom of a terminal, add this to `~/.claude/settings.json` and restart, pointing at the installed engine:
```json
"statusLine": {
  "type": "command",
  "command": "python3 /absolute/path/to/smoke-signal.py"
}
```

## Turn it off / on
- Off: `touch ~/.claude/smoke-signal-off`
- On: `rm ~/.claude/smoke-signal-off`

## Notes
- Hooks and settings load at session start; restart after install or any edit.
- Requires `python3` on PATH.
