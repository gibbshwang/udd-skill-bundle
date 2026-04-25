# AX Universal Data Downloader — Skill Bundle

Skill for Claude Code, Gemini CLI, and Codex CLI that generates
self-healing, scheduled Python projects for corporate data downloads.

## Install

```bash
cp -r skills/udd ~/.claude/skills/udd
# Or symlink:
ln -s $(pwd)/skills/udd ~/.claude/skills/udd
```

## Usage

In any of the three CLIs, with autonomous mode enabled:
- Claude Code: `/udd`
- Gemini CLI: `activate_skill udd`
- Codex CLI: `skill udd`

See `SKILL.md` for the full pipeline.

## Development

```bash
cd skills/udd
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```
