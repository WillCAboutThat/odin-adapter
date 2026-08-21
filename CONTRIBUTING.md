# Contributing

Thanks for your interest in Odin. Odin ships from this repository as a plugin
for **Claude Code and Codex CLI**, and **this repository is a build
artifact**: everything in `odin/`, plus this repo's README and manifests, is
generated and published by CI from an upstream source repository. Pull
requests that edit the bundle are overwritten by the next release, so we
can't merge them.

The channels that work:

- **Bug reports and feature requests → Issues, right here.** Include your
  plugin version (`/plugin` → odin in Claude Code, or `codex plugin list` in
  Codex CLI), the `serverInfo.version` string for MCP issues, and `lint`
  output for base-health problems. Real-use reports have driven nearly every
  release.
- **Security concerns → see [SECURITY.md](SECURITY.md)**, not a public issue.

Fixes land upstream and reach this repo with the next published version —
watch the Releases page for what changed.
