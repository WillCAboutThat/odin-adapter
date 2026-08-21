## Map (the enrichment layer — a deliberate pass, never an ingest side-effect; ADR-0043)

`map` is `synthesize`'s sibling: synthesize proposes **connections** (insights);
`map` proposes the **derived-type layer** — the entities, concepts, and open
questions latent across sources. Ingest never authors these (its derive scope is
exactly the summary); they are authored here, on the user's word. The verb
exists because the optional path demonstrably under-fires: 50 rich
single-subject sources once produced 50 summaries and zero entities — an
optional per-source judgment call is structurally skipped, so the act is
deliberate now.

1. **Resolve scope.** Default is the **whole base**; `--project <id>` or a
   named doc narrows. Same `resolve` call as synthesize — the `scope: global`
   hub is always unioned in.
2. **Discover from the resolved members; ground in sources (I2/I3, ADR-0046).**
   Breadth verb, same instrument as synthesize: from the step-1 member ids,
   skim titles/abstracts **selectively** for candidates (not an `index.md`
   wholesale read — O(base) context), then **read the actual sources** to
   ground every proposal — never author from a summary (chaining; the Core
   rejects it). What earns a doc:
   - **Entity — a cross-source join key, never a findability duplicate.** A
     summary facet already answers *"who is Galen Clark"* (ADR-0012); an
     `ent-` doc earns its place only by carrying what a facet cannot — stable
     identity and aliases, relationships, membership across **two or more
     sources** (or one source plus a clearly recurring role). Someone mentioned
     once, fully covered by their summary → **no entity; skipping is correct,
     not debt.**
   - **Concept — a recurring idea that spans sources** (a clause pattern, a
     method, a theme): the one-place explanation multiple summaries would
     otherwise each half-repeat, `see_also`-linkable from all of them.
   - **Question — the proactive sweep** of what the sources raise but don't
     settle. Generalizes the synthesize gap path (T-154): same doc type, same
     **"OPEN — "** abstract convention, so the index doubles as the
     open-questions register; `regenerate` re-derives it answered when the
     resolving source lands.
   - **Delegating the discovery reads (ADR-0045; on Claude Code, the bundled
     `odin-map` worker)? Land findings as you go —
     the candidates rail is the crash-tolerant path (refined 2026-08-16).**
     A delegated discovery worker `stage-candidate`s each grounded proposal
     *as it is confirmed* (delegate rule 4 — staging is unconsented-safe by
     design, ADR-0033), so a lost or stalled worker strands minutes, never
     the pass: staged candidates survive in the base, and step 3's manifest
     is then assembled FROM the rail (`list-candidates`), with the nod
     promoting each survivor (`promote-candidate`, ADR-0035). Discovery held
     only in a worker's context is not discovery — the receipt is a real
     pass whose delegated reads were lost by the host with zero writes.
     Inline (undelegated) discovery may still assemble the manifest
     directly; if the session is long, draft it to a scratch file outside
     the base as you go, never context-only.
3. **Propose as ONE manifest — strike-outs welcome, one nod.** Before
   assembling, run the **coverage check** (its section below, T-206) on each
   proposed doc: a compatible hit re-routes the item to a *"fold into <id>"*
   manifest line; a conflicting hit becomes the conflict elicitation, never a
   sibling doc. Then present the
   whole pass as a single itemized offer — *"12 entities · 3 concepts · 2 open
   questions — write them?"* — each item one line: proposed id · title · the
   sources it joins · a **verbatim quoted span** for each claim-bearing line
   (T-153). The user strikes items, then approves **once**. Never per-doc
   consent theater; never a silent write.
4. **Write on the nod** via `derive --type entity|concept|question`. Each doc is
   grounded in its own sources with per-span linked citations (ADR-0038). The
   Core containment-verifies every quoted span in these types, which is the
   T-153 gate, and it refuses fabrication. That is why the manifest skim can
   trust the evidence. Quote the literal bytes: markdown, punctuation, and
   letter case all count, and only whitespace and smart quotes are normalized. A
   refusal names the quote to fix; it is not a check to work around.
   - **Author in the plain register (T-221; its section is below).** Rules 1 and
     3 bite hardest in this layer. An entity or concept doc exists to explain a
     term to someone who does not yet know it, so a term used before it is
     expanded defeats the doc's whole purpose. And a join stated inside a
     parenthetical is a claim hiding in an aside, which is the one place rule 1
     is not merely a style preference.
   - **Extends a doc the base already holds → fold, don't duplicate.** When a
     proposed entity/concept restates one the base already carries but with a
     new source, stage it `--into <that-id>` and `promote-candidate --into`
     unions the source into provenance and literal-inserts the quote-verified
     block (ADR-0035) — rather than minting a near-duplicate; `regenerate`
     re-coalesces if it accretes. Lint stays silent on this by design (it
     checks *cited*-source fidelity, not *uncited*-source relevance).
   - **The join is an arch — run the composition self-check on it (ADR-0015).**
     The T-153 gate verifies each quoted span (the *bricks*); it cannot see the
     claim made by *arrangement* — that these spans name one identity, that a
     membership spans those sources, that a concept recurs across them. Before
     writing each doc, ask **"do the sources state this join, or do I?"** A
     cross-source membership no single source attests, an alias equating two
     names the sources never equate, a concept knitted from incidental
     co-occurrence — drop it, or label it the inference it is. `map` is the
     **highest-arch-risk verb** (entities and concepts *are* cross-source
     joins), so it carries the same discipline `synthesize` and `record-decision`
     do — the linter cannot catch an over-reaching join; only this can.
   Then `index` + `lint` — 0 errors.
5. **Log the pass — both records, every time.** The pass's memory:
   `… map-log <root> [--scope <what>] --entities N --concepts N --questions N`
   — `status` computes enrichment debt from it, so **log even a
   nothing-warranted pass** ("checked, nothing earned a doc" is knowledge too).
   And the usage record, per the shared rules below:
   `… usage-log <root> map --scope <every id read in step 2>`.

**Proactive (on load).** When `status` shows `captures_since_map > 0` — or
`last_map` null with sources present and `enrichment_counts` all zero —
**offer** the pass, once: *"8 sources have arrived since the enrichment layer
was last mapped — want me to propose the entities, concepts, and open questions
they hold?"* Offer only; **never map unasked** — it is a real token spend, and
proposing-not-writing extends to proposing-not-scanning, exactly as with
synthesize.

