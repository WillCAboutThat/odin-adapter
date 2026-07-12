<!--
  README for the WillCAboutThat/odin-adapter marketplace repo.
  SOURCE OF TRUTH: project-odin (adapters/claude-plugin/marketplace-README.md).
  The publish workflow copies it verbatim on every release — do not edit it in
  the odin-adapter repo; it will be overwritten (that repo is a build artifact).
-->
# odin-adapter — the Odin plugin, for Claude Code and Codex CLI

## The names, in thirty seconds

In Norse myth, **Odin** is the god who pays for wisdom — an eye at Mímir's
Well — and every day sends two ravens across the world: **Huginn**
(*Thought*), who flies out and observes, and **Muninn** (*Memory*), who
carries back what must not be forgotten.

That myth is this architecture:

- **Odin** is the agent you talk to. You never address a raven — you ask Odin.
- **Huginn** is his exploration: transient, goes out, reads, reports.
- **Muninn** is his memory — and it's *yours*: a knowledge base of plain
  Markdown, links, and provenance in git, built to outlive any AI, any vendor,
  any tool. Each base explains itself in its own `MUNINN.md`.

So when this plugin "sets up a Muninn," it is giving you the raven that
remembers.

## What this is

A plugin **marketplace** hosting **Odin**: turn scattered documents — meeting
notes, contracts, PDFs, recipes, research — into a durable, provenance-tracked
knowledge base. AI is the enabler at authoring time; the knowledge persists
with **no AI and no vendor lock-in**, and the format contract it conforms to
ships right in this bundle (`odin/contracts/` + `odin/docs/muninn/SPEC.md`,
frozen at 1.0).

One dual-manifest bundle serves **both harnesses** — the same skill and the
same deterministic Core MCP server:

- **the skill** (`odin/skills/odin/`) — the judgment + orchestration layer;
- **the Core MCP server** (`odin/tools/odin_mcp.py`) — a neutral, deterministic
  transport that owns every write and guarantees the invariants ("the Muninn
  lints clean" is the definition of done).

## Prerequisite — `uv`

The bundled server launches via `uv run --script`, so the one prerequisite is
[uv](https://astral.sh/uv) — a single cross-platform binary; it provisions
Python + dependencies on first launch (no host `python3` needed):

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Install — Claude Code

```
/plugin marketplace add WillCAboutThat/odin-adapter
/plugin install odin@odin-adapter
```

## Install — Codex CLI

```
codex plugin marketplace add WillCAboutThat/odin-adapter
codex plugin add odin@odin-adapter
```

Verify the server with `codex mcp list` (Codex loads MCP tools lazily — asking
the model to list tools can say none while the server runs fine).

## First use

Start (or reload) a session — the `odin-core` MCP server auto-starts. Then just
talk: *"odin, set up a knowledge base here and remember this document…"*. Odin
will confirm **where the base lives**, capture your first source with
provenance, and the base explains itself from then on (see its `MUNINN.md`).

## Updating

- **Claude Code:** `/plugin update` (or opt-in auto-update).
- **Codex CLI:** `codex plugin marketplace upgrade`, then restart the session
  (Codex updates are pull-based).

> **Migrating from `odin@odin-claude`?** This repo was renamed from
> `odin-claude` (the old URL redirects). Re-add the marketplace under the new
> name and reinstall: `/plugin marketplace add WillCAboutThat/odin-adapter` →
> `/plugin install odin@odin-adapter`.

## About this repo

This repo is a **generated build artifact** — every file is produced and pushed
by CI from the `project-odin` source repository on each tagged release. Don't
send PRs here; nothing hand-edited survives the next publish.
