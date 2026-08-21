## Ask (cited reasoning)

1. **Retrieve first (ADR-0046).** Locate candidates with `retrieve`, which is
   semantic union literal with a mechanical degrade. Do not read `index.md`
   wholesale for this. The index is the *human* skim surface and costs O(base)
   context, roughly 0.5 KB per doc, which runs to tens of thousands of tokens on
   a mature base. Then read the matched sources and reason over them. Retrieval
   proposes; sources ground. The index skim stays the existence-question
   fallback, described under *Find* as "a miss is not absence", and that use is
   correct.
   - **Auditing the evidence behind selected docs?** The pipeline is
     `graph(centers=<your picks>, direction="outbound",
     relations=["grounded_by","evidence","superseded_by"])` then `read-many`
     (ADR-0052): one call discloses their declared sources, staleness, and
     connected decisions - bounded, directed, never interpretive. You still
     read and judge; the graph only shows what is formally declared.
2. **Answer, cited to sources.** Every asserted fact carries its source, as in
   "… net 30 [src-vendor-contract]." In chat the bare id label is fine. Anything
   *written into the base* uses linked citations per ADR-0038.
   - **The answer is spoken prose, so the plain register governs it (T-221).**
     The shared rules have their own section below. Rules 2, 3, and 5 are the
     ones an answer breaks most often: write arrows as words rather than as
     connectives, expand a term the first time it appears, and bold at most one
     thing per section. Rule 4 applies to the citation: put it at the end of the
     sentence it supports rather than mid-clause. Rule 4 changes position only.
     Per-span attribution is unchanged and ADR-0009 stands, so a sentence
     carrying two claims from two sources becomes two sentences.
   - **Quarantine model-knowledge; do not smuggle it (the ADR-0011 bright
     line).** Some questions invite knowledge the base doesn't hold, such as
     "what's typical for a dog *like* this?". The default there is quarantine,
     not refusal. Answer the grounded part first, cited. Then give the general
     knowledge in a clearly labeled, walled-off section marked *not from the
     Muninn*. That section carries the lowest assurance there is, below
     `model-read`, and it is never dressed up as a record. Offer to `ingest` a
     real source so a future answer is grounded. Refuse only when even a
     walled-off answer would mislead. Never silently blend model-knowledge into
     a cited answer.
   - **A structured source is answered from its bytes, not its aid, when the
     value is past the aid's reach (T-048).** The summary and the aid make
     you *aware* a workbook answers a question class; the specific value may
     live in rows the aid deliberately truncated. Where you have file tools,
     open the canonical source with a deterministic reader (openpyxl for
     `.xlsx`, plain parsing for CSV) and read the **targeted** cells - the
     summary's schema reading tells you the sheet, header row, and grain, so
     the read is aimed, never a trawl. Cite the source and name the
     coordinates ("Metrics!B31"). A lookup or an arithmetic roll-up (a sum, a
     count, a single month's value) is the computed-answer class: checkable,
     reproducible, `extracted`-rung, datum-plus-rule disclosed in the body.
     **Interpretation is not lookup**: "why did it drop," "is this trending
     well" - judgments over the data - are analyst work, not retrieval; say
     so and offer it as a deliverable (ADR-0044) or a labeled synthesis
     (ADR-0051), never as a cited fact. On a host with no file tools (the
     op-only surface, T-159), disclose the aid's truncation honestly instead
     of guessing past it.
3. **Too thin? Surface the gap and offer to dispatch Huginn (ADR-0021).** If
   memory can't support a good answer, say so and offer to `explore`. Let the
   survey inform the offer, since it knows which connector or source could hold
   the missing piece. This goes by offer; never auto-reach. Acquire the missing
   piece neutrally, rather than looking for support for X, because a dispatch
   aimed at a conclusion manufactures agreement. Stay willing to answer
   *differently* if the fetched source doesn't cooperate. Complete the answer
   only after a separately-consented `ingest`. Do not fabricate. "I don't know
   yet" is a valid and valuable answer.
4. **Assurance: surface the weakest link (ADR-0011).** Roll up two orthogonal
   axes into one honest line, taking the weakest value among the docs you cited.
   - **Derivation** has three rungs, strongest first. `extracted` rests on
     deterministic text. `model-read` rests on a model's reading of an image or
     scan, which is lower assurance. `synthesis` is the weakest, and it
     activates with `synthesize`. One cited `model-read` summary drags the whole
     answer to model-read. Mirror the Core's `weakest_derivation` ordering
     rather than averaging or hand-waving.
     - **Pick the rung by ADR-0011's definitions, not by vibes (T-107).**
       `synthesis` means specifically cross-source *generative* reasoning, such
       as an insight linking docs. A single-source deterministic computation is
       `extracted`. An age from a date of birth, or a total from line items, is
       such a computation: its result is checkable and reproducible, which is
       exactly what `extracted` denotes. It is neither cross-source nor
       generative, so `synthesis` is wrong there and would overstate the
       uncertainty. The transparency that it was computed rather than quoted
       lives in the body, as the datum plus the rule, per *Time-relative facts*.
       It does not live in the rung.
   - **Capture tier** is the second axis. If the answer rests on
     `reference`-tier sources, which the base does not hold in full, flag that
     too.
   Say the roll-up plainly. "Answered from deterministic text" is one form.
   "This rests on a model-read shelter photo, so treat it as lower assurance" is
   the other.
5. **Crystallize (optional).** If the answer is reusable, offer to save it as a
   `question` doc via `derive --type question`, grounded and cited. Offer it;
   don't clutter the base unasked. Run the coverage check first. That is the
   shared pre-authoring gate under *Map* (T-206). The base may already hold a
   doc covering this ground, and a conflicting one is elicited rather than
   siblinged. Never treat a derived doc as ground truth without the sources
   behind it.
   - A crystallized answer composes multiple sources, so run the composition
     self-check before writing (ADR-0015): *"do the sources state this, or do
     I?"* The durable question doc must not assert by arrangement what no cited
     span states. An ephemeral chat answer that overreached is harmless; one
     written into the base is not.
   - **The labeled-synthesis rung (ADR-0051; the T-240 G2 loss, closed).** A
     TRUE claim whose support is honest paraphrase across sources - no
     quotable span exists for it anywhere in the bytes - is **filed, not
     dropped**: write the leg as `synthesis over [src-a] + [src-b]: <claim>`
     instead of a quoted span, and stamp the doc `derivation: synthesis`
     (weakest link, ADR-0011 - `ask` then discloses the rung like any other).
     Three rules keep the rung from becoming a laundering channel: the
     composition self-check applies **per synthesis leg** (a leg the sources
     don't jointly support is dropped or labeled the inference it is, never
     quietly kept); span-verifiable claims still get spans - the rung is for
     claims that *cannot* quote, never for claims you'd rather not; and an
     answer whose value is mostly arch (most legs synthesis) is **staged on
     the candidates rail** rather than written directly - promotion stays a
     consented act (ADR-0033). A synthesis label always means *this
     adapter's* arch: operator knowledge never rides a synthesis leg - it
     enters as a decision or a chat-origin source and gets cited (the
     ADR-0051 colleague boundary; substance smuggled into a derived doc
     dies at its next regenerate, substance filed through the operator's
     doors survives every one).
   - Landing it is an authoring moment, so the plain register (T-221) binds the
     doc as well as the answer that produced it.
6. **Log the run — the close step, every time (T-152).**
   `… usage-log <root> ask --scope <the ids you actually read> [--tokens N]` —
   the Core can't see this verb, so the record is the only way `usage` measures
   it (rules: *Usage-logging rules* below; silent, best-effort, never a gate).

