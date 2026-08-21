## Regenerate (heal a gap or refresh a stale page)

`regenerate` is how the base **self-heals** — the repair half of "the linter
detects; a deliberate op repairs, never silently" (ADR-0013, I5). It is an
orchestration you run with the Core's `derive`, not a new Core op.

- **Heal a missing summary (L15).** `lint` flags a source with no summary. First
  check the deterministic facts: `… source-status <root> <id>` (tier · `has_bytes`
  · `recoverable` · `origin.ref`). Then:
  - **`has_bytes` true** (the common case — `full` capture, or any held bytes):
    read that source — **model-read it** if it is opaque (an image/scan captured
    bytes-only) — and `derive` its summary, stamping `--derivation model-read` for a
    model-read, plain `extracted` otherwise. No fetch.
  - **`has_bytes` false** (a `reference`-tier source whose bytes aren't held): if
    **`recoverable`** with an `origin.ref`, **fetch** the bytes via the connector
    (Huginn's single-target fetch, ADR-0020 §3), `capture` them to fill the source,
    then `derive`. If **not `recoverable`**, stop and say so — *"can't regenerate
    without the bytes; this source is a locator only"* — and **do not fabricate** a
    summary from the locator or metadata (ADR-0013 §4).
  Re-lint: the L15 error clears (or the honest gap is surfaced). A captured source
  with held bytes is a fixable gap, not a dead end.
- **Refresh a stale page.** When a source changed (a new version) and a derived
  doc is stale, re-`derive` that doc from the **current** source hashes — the Core
  stamps fresh provenance. Never edit the old doc in place; derive it anew.

Always **offer** the heal and show what you'll do; never silently rewrite memory.
Then re-`lint` and report clean.

- **Re-deriving a summary is quote-gated; first authoring is not (T-223).** When
  you re-derive a summary that already exists, the Core containment-verifies its
  quoted spans exactly as it does for an insight, and refuses the write on a
  mismatch. Authoring a summary for the first time, in ingest or when healing an
  L15 gap, stays ungated. The reason is supervision, not doc type: a re-derive is
  something a person asked for and is watching, while bulk ingest would be
  blocked by one inexact quote. So quote the literal source bytes when you
  re-derive. A refusal names the span to fix, and a span crossing the source's
  own `>` blockquote or `--` comment prefixes is the usual culprit: cut it into
  exact single-line spans rather than stripping the prefix, which is a source
  byte like any other.
- **Wrapping does not excuse a quote from the gate.** The check reads the
  paragraph you wrote, not the lines your editor emitted, so a quote and the
  citation that vouches for it count as together even when a wrap separates them.
  A quote sharing a paragraph with a citation must be verbatim in that source.

