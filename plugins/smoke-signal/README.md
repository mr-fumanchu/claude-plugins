# Smoke Signal (Claude Code plugin)

An always-on status readout for Claude Code. One compact line shows the active project, the live model and reasoning effort, this session's cost, context-window usage, and the project's running cost across sessions. At 75% context use it raises a red compaction alert with an animated fire-and-smoke widget so you see the limit coming.

## What's in the plugin
- `skills/smoke-signal/` — the skill (how-it-works and maintenance surface), the status-line engine `smoke-signal.py`, and the `widget/compaction-alert.html` flare.
- `hooks/hooks.json` — two hooks:
  - `UserPromptSubmit` → `effort-hook.py`: reads the live reasoning effort and injects it so the footer is always correct (no guessing).
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
