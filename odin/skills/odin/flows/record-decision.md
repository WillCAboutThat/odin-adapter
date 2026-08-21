## Record a decision (the owner's own knowledge — authored, not derived)

The counterpart to `why`: `why` retrieves, this records. A decision is the **owner's
own knowledge** (SPEC §5.5, ADR-0019), so record one **only on an explicit request**
("log this as a decision", "record that we decided…") — **never** as a side effect
of `ask`/`synthesize`. Odin is the scribe, not the author.

1. **Author the ADR-shaped body** — Context · Decision · Consequences — in the
   owner's terms. Cite informing sources inline as linked citations
   `[src-…](../sources/src-…/source-text.md)` (ADR-0038).
   - **The composition can lie even in an authored decision (ADR-0015).** The
     bricks are the owner's words; the *arch* is your tidying of them. When the
     owner bundles several sources in one breath ("the trailhead and
     seasonal-closure footing across both"), resist splitting it into a clean
     one-source-per-clause structure that reads tidier than the evidence. Run
     the per-clause self-check **before writing** — *"does **this** cited source
     state this, or am I tidying?"* A reader-vocabulary gloss (ADR-0012) is
     welcome, but attach it to the source that actually carries the word: a term
     the cited source never uses belongs on its sibling, or left unattached —
     never split one-to-one onto the source that happens to sit beside it. The
     linter cannot catch this (every evidence link still resolves and provenance
     stays intact); only this discipline does.
2. **Write it through the Core** (the Core owns the write; you never hand-edit):
   `python <ODIN>/tools/muninn_core.py record-decision <root> dec-<slug>
   --title "<t>" --status accepted [--evidence src-A --evidence src-B] --file <body>`
   `--evidence` are **links, not provenance** — the Core stores each source's
   *version* (a hash-free change baseline), so a decision **never chains and never
   goes stale**; an evidence source that later changes surfaces as a *soft lint note*,
   not an error. **Do not** reach for `derive --type decision` — the Core rejects it
   by design (decisions are authored, not derived).
   *(MCP transport - the norm for plugin installs: a `--file`/stdin body becomes the **`body` param carrying the literal text, never a file path**; `--source-file` becomes the **`source_file`** path param. Same op, same other args - the kernel's Setup section has the full mapping.)*
3. **Amend, don't supersede.** To revise a recorded decision, add `--amend` with the
   change note: the Core prepends a dated `**AMENDED (date):**` banner and **never
   deletes the prior text** (append-only). Its original `date` stays fixed. A
   genuinely different decision is just a new `dec-…` doc.
4. `index` and `lint` (must be 0 errors), then report what you recorded (id, status,
   any evidence links) with the file link.

