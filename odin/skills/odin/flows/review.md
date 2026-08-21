## Review (honesty audit — re-check the base's own conclusions)

`review` is the **semantic sibling of the linter**: `lint` checks structural
health deterministically; `review` interrogates whether the derived layer is still
*honest* — a judgment no deterministic rule can make (entailment is semantic,
ADR-0015 §3; ADR-0026). It is the **proactive** form of ADR-0015's *reactive*
assurance net: run the same adversarial re-read it relies on, but
across a whole scope on demand instead of one claim by accident. It **detects and
surfaces**; the heal is `regenerate` — never silent (the same
detect→consent→repair loop as lint).

1. **Resolve the scope.** `… resolve <root> [project]` — whole base, a project, or
   a single named doc; every scope unions in the `global` views (ADR-0018).
   For the per-doc evidence map (declared sources, per-rung staleness, dangling
   references), `graph(centers=<docs>, direction="outbound")` discloses it in
   one bounded call (ADR-0052) — lint remains the integrity authority.
   Enumerate the derived docs in scope (summaries, entities, concepts, questions,
   insights).
2. **Be the grounded adversarial judge — default to skepticism.** For each derived
   doc, **re-read the actual bytes** of every source it cites (`sources/<id>/…` —
   the canonical file or its text aid), *not* the doc's paraphrase. A claim you
   can't ground from a quoted span is a finding, not a benefit of the doubt. This
   is the rubric's challenger (`scripts/adapter_eval/CHALLENGER.md`, ADR-0023)
   turned on the user's *own* base — **drop its grading-fixture isolation rules**
   (never-read-`*generator*` is for fair benchmarking), keep its default-to-fail.
3. **Check two things, and say which.**
   - **Authoring overreach** — a claim the sources don't state, or a corroboration
     *breadth* wider than its witnesses (count witnesses per claim, T-077). Re-read
     per composed claim: *"do the sources state this, or does the doc?"*
   - **Drift against new knowledge** — does the conclusion still hold against
     *everything the base now holds*, including sources ingested **after** this doc
     was derived? The linter can't see this — the newer source isn't in the doc's
     provenance, so no hash changed — so it's yours to catch. **Open `question`
     docs are this check's prime target (T-154):** for each abstract leading
     "OPEN — ", ask *does the base NOW answer it?* — a yes is a finding whose
     heal is `regenerate` into the answered form.
4. **Report a hedged second opinion — never a verdict.** For each finding: name the
   doc + the claim, quote the source span (or say plainly *no source attests this*),
   state the doubt in the reader's words, and default to *"a skeptical reader would
   question this."* **No deterministic-looking counts** ("3 errors") — apeing the
   linter would launder judgment as fact (the very overreach you're hunting). If two
   passes might disagree, say so.
5. **Offer `regenerate`, don't apply it.** Each finding ends by offering the heal;
   the user consents per finding. `review` **writes nothing** — it is **read-only**,
   with **no durable "reviewed" mark** on any doc (an AI blessing rots and invites
   false trust, ADR-0014; the durable audit stays provenance you can re-hash).
   `regenerate` does any write.
6. **Record the pass — the close step, every time (T-216).**
   `… review-log <root> clean|findings-surfaced [--scope <what>] [--detail
   "<one hedged line>"]`. This is the **only** way a review reaches `log.md`:
   never hand-write an entry (invariant 5). It records that the pass *ran*,
   never a verdict the format stores — no doc mark, no status field, no trust
   score, and **no finding count**, since a deterministic-looking tally would
   launder judgment as fact (the very overreach you were hunting). `clean`
   says what this pass reported, never that the docs are warranted.
7. **Log the cost too (T-152).**
   `… usage-log <root> review --scope <docs + sources re-read> [--tokens N]` —
   disposable operational state (ADR-0027), separate from the record above;
   rules: *Usage-logging rules* below.

**It is `review`, not `audit`** — "audit" already means the *deterministic* check
(re-read + re-hash provenance, ADR-0014); `review` is the subjective second
opinion. Keep the words distinct. On-demand and advisory — **never a gate**.

**Delegate the re-reading (ADR-0045; on Claude Code, the bundled
`odin-review` worker).** A whole-base or project-wide review's re-reads
belong in a worker: strictly read-only, findings return with receipts
(quote-the-span), and every heal remains this session's consented act. The
worker never logs the pass - the review-log close happens here, after the
operator has seen the findings.
