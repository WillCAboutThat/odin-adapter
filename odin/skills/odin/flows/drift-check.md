## Drift-check (currency with the WORLD — a deliberate, consented sweep; T-136)

Hash staleness (L4) measures the base **against itself**: a remote system's
update is invisible until someone reaches out. `drift-check` is that reach —
**on the user's word, never automatic, never a daemon** (a base must verify
with no connectivity forever, ADR-0008; reaching is Huginn's consented act).

1. **Worklist (Core, deterministic).** `… drift-worklist <root> [--project <id>]
   [--older-than 30d]` — the recoverable, connector-origin sources whose remote
   may have moved. **Default scope is every eligible source in the base**
   (T-147); `--project` narrows to that project's members ∪ the global views
   (T-128). Items arrive **oldest contact first**, each carrying
   `last_checked`/`last_verdict` from prior sweeps (T-145) — present the ages;
   that IS the "what's due a check?" view. **`--older-than` is the budget
   lever**: sweep only what's actually stale-prone instead of everything, every
   time. The result always reports **`outside_scope`** (eligible sources the
   requested scope excluded) and **`age_filtered`** — relay them: a narrowed or
   empty list must never be voiced as "all current."
2. **Reach and compare, per item.** `fetch` the current remote (your connector,
   one bounded retry on a transient failure), then the **Core compares** — by
   the strongest rung the source carries:
   - **Anchored partial capture** (`upstream_ref`/`upstream_identity` in the
     worklist row, ADR-0039): for a `git-blob` identity, compare the remote's
     blob sha first — equal means **byte-certain unchanged, zero fetch**.
     Otherwise fetch the whole and run `… anchor-check <root> <src-id>
     --upstream-file <fetched>` → `upstream-unchanged` /
     `upstream-changed-region-intact` (the whole moved but the excerpted region
     stands — report it as *current*, not changed) / `region-drifted` (the
     region itself moved → the *changed* column, offer re-capture). You never
     eyeball-diff.
   - **Whole-source capture:** `… dedup-check <root> --source-file <fetched>
     --id <src-id>` → *already-captured* (same) / *changed* /
     *same-after-newline-normalization* (T-140: a code/text file whose fetch
     differs only by CRLF/LF line endings) / *same-after-extraction* (T-171: an
     HTML/PDF page whose bytes moved but whose **extracted text is identical** —
     page furniture: ads, analytics, dynamic chrome, the `script`/`style`/`head`
     the deterministic extractor already drops). Both `same-after-*` verdicts are
     **computed by the Core** and reported in the **same** column, named as the
     artifact, never as drift. You never hash or eyeball-diff.
   *(MCP transport - the norm for plugin installs: a `--file`/stdin body becomes the **`body` param carrying the literal text, never a file path**; `--source-file` becomes the **`source_file`** path param. Same op, same other args - the kernel's Setup section has the full mapping.)*
   - **The furniture residual on *visible* text is yours to voice, never a Core
     verdict (T-171).** `same-after-extraction` fires only when the extracted text
     is byte-identical; visible-text chrome the extractor keeps by design (a
     rotated sidebar headline, a changed nav label) still reads *changed*. If you
     judge such a change furniture-only, you may **say so — as judgment, offered**
     (*"the only change is a rotated promo headline — re-capture?"*), but never log
     it as a deterministic `same-*` verdict. Inference stays labeled; the Core's
     column stays faithful.
   - A locator-only reference source gets a reachability check; a
     stand-in-bodied one compares against the stand-in — **say so** when
     reporting it. An **unanchored excerpt** (partial capture, no identity)
     is the hedged case: report honestly that only prose relates it to its
     whole, and **offer the `anchor` backfill** — fetch the whole, then
     `… anchor <root> <src-id> --upstream-ref <whole> --upstream-file
     <fetched> [--form git-blob]`; the Core verifies containment FIRST and
     refuses to stamp what the held bytes don't satisfy. **Handle a refusal
     with evidence, not a shrug (T-140):** extract the verbatim chunks from
     the body yourself, search the fetched upstream for each, and present
     what you found — *"the missing chunks are the capture's own disclosure
     prose; the actual code is present verbatim"* — THEN overrule with
     `--force --reason <that evidence>` (the owner's judgment, logged). A
     force-stamped anchor fixes the identity tier permanently but the
     unfenced body stays containment-opaque, so also **offer the durable
     repair: a fenced re-capture-as-version** (verbatim content inside fence
     blocks, disclosure outside; anchor at capture) — containment then checks
     deterministically forever.
3. **Report the sweep**: one table — **same / changed / unreachable** — then
   record it **per item**: `… drift-log <root> --checked <id>=<verdict>
   [--checked …] [--detail …]` (one `--checked` per item swept; the counts
   tally themselves from the verdicts). The per-item segment is what makes
   `last-checked` ages reconstructible when sweeps have differing scopes
   (T-145) — a counts-only entry loses WHICH items were verified, so always
   pass `--checked`. The log is the sweep's memory (`status` reads it for the
   quiet "world unchecked since" line; you read recent entries to voice
   **streaks**: *"src-x unreachable, 3rd consecutive sweep"*).
4. **Changed → offer re-capture, per item.** A consented re-capture under the
   **same id** versions the source, and L4 then flags every dependent doc
   automatically — the flags do the rest; heal with `regenerate` on the user's
   word. Never re-capture unasked.
5. **Unreachable is a transport fact, not a drift conclusion.** Report it,
   never write from it. After a visible streak, **offer** the standing
   never-retry mark: `… retier <root> <id> --no-recoverable` (drops it from
   future worklists; the flip is logged and reverses with `--recoverable` if
   the system returns). Retiring the source or its dependents is a separate,
   also-consented conversation.

**Cadence is the user's** (the cost of freshness stays explicit): suggest it
before load-bearing decisions and periodically for active bases — never
schedule it yourself. **Voice the snapshot age meanwhile**: an answer grounded
in a connector source that a fresh reader might assume is live cites *"as
captured <date>"* so the reader inherits the epistemic state.

**Never:** run a sweep unasked; conclude drift from a fetch failure; re-capture
without the per-item nod; compute a hash yourself. **Writes:** only the
`drift-log` entry — everything else is offers.

**Delegate the sweep (ADR-0045; on Claude Code, `odin-scout`'s second
mission).** Once the operator consents to the sweep, the fetch-and-compare
legwork belongs in the scout: outward, read-only, returning per-item
unchanged/changed/unreachable - computed, never guessed. The re-capture
offer stays HERE and only for CHANGED items (nothing compared means nothing
to offer); consent to sweep is never consent to re-capture.

**The handoff is verified, never trusted (T-258 — found by dogfood: the seam
worked by judgment, not design).** The scout's report names, per changed
item, its fetched artifact's path and sha256. Before a consented re-capture
uses those bytes, **re-hash the artifact yourself and compare against the
scout's reported value** — match: it is the named capture input; mismatch
or missing: re-fetch, never capture. A truncated or stale artifact written
under a trusted id would carry full provenance with nobody the wiser — the
one failure this computed check closes.

**Sources-current is not derived-docs-current.** A clean sweep says the
SWEPT SOURCES match their upstreams — nothing more. Derived docs may rest
on unswept sources (the scout's blind-spots section names these from
provenance) or on repo-state facts no source carries (a marker count, a
directory listing), which no source sweep can refresh. Voice the
distinction when reporting a clean sweep; "all current" without that scope
is the flattening this verb exists to prevent.
