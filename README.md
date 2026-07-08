# odin-claude — the Odin plugin for Claude Code

A Claude Code **marketplace** hosting the **Odin / Muninn** plugin: turn scattered
documents into a durable, provenance-tracked knowledge base (a "Muninn" — Markdown +
links + git). AI is the enabler at authoring time; the knowledge persists with no AI
and no vendor lock-in.

The plugin bundles two things:
- **the skill** (`odin/skills/odin/`) — the judgment + orchestration layer;
- **the Core MCP server** (`odin/tools/odin_mcp.py`) — a neutral, deterministic
  transport that owns every write and guarantees the invariants ("the Muninn lints
  clean" is the definition of done).

## Install

```
/plugin marketplace add WillCAboutThat/odin-claude
/plugin install odin@odin-claude
```

Then start (or reload) a session. The `odin-core` MCP server auto-starts; say
*"odin, set up a knowledge base here and remember this document …"* to begin.
`/plugin update` pulls new versions.

## Prerequisite: Python 3 + pyyaml

A plugin can't ship Python, so the machine needs **Python 3** on `PATH` with
**`pyyaml`**. The bundled server invokes `python3`; a SessionStart hook installs
`pyyaml` into the plugin's data dir if it's missing.

- **macOS / Linux / WSL2:** `python3` is native — nothing to do.
- **Windows:** `python3` usually doesn't exist. Install Python from python.org, then
  make `python3` resolve (one-time): `Copy-Item (Get-Command python).Source (Join-Path (Split-Path (Get-Command python).Source) 'python3.exe')`. A robust cross-platform launcher is planned.

## Provenance

This repo is a **generated distribution artifact** — do not edit `odin/` by hand.
The source of truth is [`WillCAboutThat/project-odin`](https://github.com/WillCAboutThat/project-odin)
(the neutral Core + the adapter skill + the bundle builder,
`adapters/claude-plugin/build_plugin.py`). Releases are built from a tagged
`project-odin` version; the plugin version tracks its `pyproject.toml`.
