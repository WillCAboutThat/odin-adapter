## Synthesize (inward discovery — the differentiator)

`synthesize` is the mirror of `explore`: `explore` reaches *outward* for new
sources; `synthesize` looks *inward* for new **connections** already latent in
memory. It answers the question the user *didn't know to ask* — shared entities,
date/deadline dependencies, contradictions, causal or thematic links across
sources (ADR-0009). Full behavior: `docs/odin/SKILLS.md` §5.

**Proactive (on load).** Beyond user-invocation, offer this on load when the base
*grew*: the freshness ritual (`MUNINN.md` / ADR-0005) recomputes the fingerprint, and
if the change **added new sources**, **offer** — once — *"N new sources since last
check; want me to look for connections they form with what's already here?"* Run the
flow (steps 1–6) **only on a yes — never synthesize unasked** (it's one of your real
token spends; proposing-not-writing extends to proposing-not-scanning). Skip the offer
on a derived-only change (a `regenerate` adds nothing new to connect).

1. **Resolve scope.** Ask the Core for the working set:
   `… resolve <root> [prj-<slug>]` — it returns the member ids to reason over.
   **Default is the named/current project**; "across everything / all projects"
   omits the project arg for the whole base. Either way the Core **always unions in
   the `scope: global` hub** (ADR-0018) — the cross-cutting layer the user never has
   to remember. Restrict candidate discovery (step 2) to the returned members. An
   unknown project name errors — surface it and ask which project, don't silently
   fall back to the whole base.
2. **Discover candidates from the resolved members (ADR-0046).** This verb
   needs breadth, not relevance, so its instrument is the step-1 `resolve`
   result: read the member docs' `title`/`abstract` **selectively** to find
   threads worth pulling — not an `index.md` wholesale read, which costs
   O(base) context and duplicates what `resolve` already returned. (`retrieve`
   helps chase a specific suspected thread.) This is what summaries are *for*
   (speed). Summaries find the thread; **sources prove it**.
3. **Ground every connection in sources (I2/I3).** For each candidate connection,
   **read the actual sources** and confirm it. Attribute **per span** — each claim
   cites the specific source that supports it, e.g. *"the rabies booster is due
   2025-07-02 [src-vet-visit] — and the vaccination record lists the same date
   [src-vaccinations]."* Sources are **peers**: no primary, no ordering.
   - **Drop unsupported proposals — don't narrate them.** A connection the sources
     don't back is not surfaced. Never assert a link on the authority of a
     *summary* (that's chaining, I3 — the Core rejects it anyway).
   - **Incomplete ≠ unsupported — surface the gap, offer to explore (ADR-0021).** A
     connection the sources don't *yet* support may be **wrong** (drop it) or merely
     **incomplete** — real, with one leg simply missing from memory. For the
     incomplete case, don't silently drop it: **surface the gap and offer to send
     Huginn** to fetch the missing leg — a third path beside ground-it and drop-it,
     closing inward discovery back into outward. Acquire **neutrally** and stay
     willing to **dissolve** the connection if the fetched source doesn't support it
     (ADR-0015) — a dispatch sent to "confirm a hunch" manufactures agreement.
     Crystallize only after a separately-consented `ingest` supplies the leg.
     **And offer the gap a durable home (T-154):** a real question the sources
     raise but don't settle is knowledge worth keeping — offer to record it as
     an **open `question` doc**: `… derive <root> q-<slug> --type question
     --title "<the question>" --abstract "OPEN — <what's unresolved and which
     sources raise it>" --source <the raising sources> --file <body>`. The
     abstract **leads with "OPEN — "** so the index skim doubles as the
     open-questions register (ADR-0012). Consented, never auto; a **direct
     derive, never the candidates pile** (that channel holds inferences
     awaiting admission, not gaps — T-129 boundary). An open question is
     Huginn's shopping list — `explore` can be dispatched at it later — and
     when the resolving source lands, **`regenerate` re-derives it into its
     answered form**: the question's honest lifecycle, no new machinery.
   *(MCP transport - the norm for plugin installs: a `--file`/stdin body becomes the **`body` param carrying the literal text, never a file path**; `--source-file` becomes the **`source_file`** path param. Same op, same other args - the kernel's Setup section has the full mapping.)*
   - **The composition can lie even when every span is true.** Accurately-cited
     bricks can still build an arch the sources never state — e.g. placing an
     unrelated consequence clause under "why this breach matters" asserts a
     causal tie by *structure*. Before crystallizing, run the adversarial
     self-check **per composed claim**: *"do the sources state this link, or do
     I?"* If it's your inference, either drop it or label it (rule below). The
     linter cannot catch this — citations and lint verify the bricks, never the
     arch; only this discipline does.
   - **Delegating the connection hunt (ADR-0045; on Claude Code, the bundled
     `odin-synthesize-discovery` worker)? Land connections as you go.** The
     worker stages each grounded connection on the candidates rail as it is
     confirmed (staging is unconsented-safe, ADR-0033); the proposal list
     below is then assembled from `list-candidates`, and the nod promotes.
     A connection held only in a worker's context dies with the worker
     (T-052; delegate rule 6) - the rail is what makes a lost worker cost
     minutes, never the pass.
4. **Propose, don't commit (§3.7) — and every proposal carries its evidence
   (T-153).** Present each connection **with verbatim quoted spans from the
   source files, one per leg** — `"…the exact words…" [src-x]` — never a
   summary's paraphrase. A connection you cannot quote is one you haven't
   grounded yet: back to step 3, or the gap path. The format IS the
   discipline (quotes force the source re-read the 2026-07-16 dogfood showed
   gets skipped), and the Core enforces it downstream: at crystallize, **a
   quoted span that isn't in its cited source refuses the write**. Write
   **nothing** durable unasked.
   - **One deliberate exception — the labeled-synthesis rung (ADR-0051).** A
     leg that is TRUE as honest paraphrase across sources but has no
     quotable span anywhere in the bytes ("A and B develop the same theme")
     is presented as `synthesis over [src-a] + [src-b]: <claim>` — labeled,
     not dropped, and not disguised as a quote. The per-leg self-check from
     step 3 still applies; a rung leg the sources don't jointly support is
     an inference to drop or label as such. The rung is for claims that
     *cannot* quote, never for claims you'd rather not — span-verifiable
     legs still quote, and the T-240 G2 session that dropped four true
     theme-pairings while correctly killing a fabricated date is the receipt
     for both halves of that line.
5. **Crystallize on the nod.** For each connection the user keeps, run the
   **coverage check first** (its section below, T-206) — `query` by cites and
   claim vocabulary finds the extends-case mechanically and surfaces any
   conflicting doc before a sibling gets minted. Then: if it
   **extends a doc the base already holds** — a source now supports an existing
   insight (or entity/concept) it doesn't yet cite — **fold, don't duplicate**:
   stage it `--into <that-id>` so `promote-candidate --into` unions the new
   source into provenance and literal-inserts the quote-verified block (ADR-0035;
   `regenerate` re-coalesces later if it accretes). This is the sanctioned heal
   for a widened-provenance connection — lint won't flag it (it checks the
   fidelity of *cited* sources, not the relevance of *uncited* ones; recall is
   this deliberate pass's job). Otherwise write a new
   **`insight`** doc via the Core, grounded in its N peer sources and stamped
   **`--derivation synthesis`** (the third integrity rung — an insight is the
   least deterministic derivation; `ask` will roll it up as the weakest link):
   `… derive <root> ins-<slug> --type insight --title "<t>" --abstract "<a>" \
      --source src-A --source src-B [--source …] --derivation synthesis --file <body>`
   Author the body in the reader's vocabulary (ADR-0012), with the per-span
   citations from step 3 and carrying the step-4 quoted spans. The Core
   containment-verifies every double-quoted span of 15 characters or more that
   sits on a line citing a provenance source, checking it against that source's
   actual text. It refuses the write on a mismatch (T-153). A fabricated or
   paraphrased "quote" cannot enter the base. Quote the literal source bytes.
   Markdown syntax such as `**` and `` ` ``, punctuation, and letter case are
   all part of the source and must be reproduced. Only whitespace, line
   wrapping, and smart-versus-straight quotes are normalized for you, so a
   refusal means the quote is wrong rather than the gate.

   Author under the plain register (T-221; its section is below) and under these
   authoring rules from ADR-0015, which were learned from a real overreach that
   passed author, reviewer, and lint alike:
   - **The abstract may not assert a link the sources don't state.** It is the
     index-projected and most-skimmed span. "A breach *tied to* the return
     clause" plants a false tie in every reader who only skims. If the link is
     your inference, the abstract must say so or must not say it.
   - **Corroboration breadth is itself a claim, so count witnesses per claim
     rather than per insight.** An insight grounded in N peer sources does not
     make every trait N-corroborated. An abstract or facet may claim agreement
     only across the sources that attest *that specific* trait. If two of three
     sources say "gentle" and all three say "good with cats," say which:
     *"all three agree she's good with cats. Two of them add gentle and
     food-motivated."* Never round the breadth up to the source count. This is
     the sibling of the rule above. There the tie was invented; here the tie is
     real but its breadth is inflated, and it inflates in exactly the
     most-skimmed span. The adapter rubric surfaced it (ADR-0023, T-075), and it
     extends ADR-0015.
   - **Label the inferential step in the body.** Where the insight connects what
     the sources leave separate, write the boundary in: *"the contract does not
     link these. The connection is this insight's inference."* Pre-empt the
     fused reading at the source instead of correcting it downstream.
   - **No model-knowledge in a derived body, ever.** The quarantine rule from
     *Ask* step 2 applies *a fortiori* to durable writes. A span like "legally
     required in most jurisdictions" with no source behind it is smuggling.
     Ground it, or cut it.
   - **Facets advertise only what the doc actually grounds.** A Covers or
     Answers entry routes readers here as the authority on that question, so
     don't offer "what happens under clause X" if your account of clause X is
     inference.
   Then run `… index <root>` and `… lint <root>`, which must report 0 errors. A
   multi-source insight goes stale if *any* grounding source changes (L4).
   Surface that, and offer `regenerate`.
6. **Report** the insights written (ids, the sources each connects) and note the
   `synthesis` assurance rung — an insight is a reasoned connection over sources,
   not a fact copied from one.
7. **Log the run — the close step, every time (T-152).**
   `… usage-log <root> synthesize --scope <every id read in steps 2–3> [--tokens N]`
   — a synthesize that skips this is invisible to `usage` (the 2026-07-16 ledger
   read found exactly that); rules: *Usage-logging rules* below.

