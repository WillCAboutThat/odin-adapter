## Stage & review candidates (channel emergent augmentation — ADR-0033)

While reasoning you will make **grounded new inferences** the base doesn't yet hold
— computing an age from a date of birth, spotting a consequence two sources imply.
That understanding is worth keeping, but **do not author it into the base as a side
effect of `ask`** (consent-of-surprise; base bloat). And do **not** stop to ask
"save this?" per inference (a capable model augments constantly — that nags).

**Channel boundary (T-129/T-131): this pile holds inferences over sources already
in the base — nothing else.** Never stage `explore` findings (outward findings
live in chat or `inbox/` and enter memory only through `ingest`, which fetches
full bits), and never stage a source's **summary** (a summary is mandatory at
capture — L15, an error — and is derived in the Ingest flow, not parked for
optional review). At **promote**, re-read the cited source bytes (never trust
the staged text) and set the rung against what the source *is*: a body that is
a model rendering grounds `model-read`, never `extracted` (T-069). Instead:

1. **Stage it.** `stage-candidate cand-<slug> --title "…" [--abstract "…"]
   --source <src-…> [--source …]` with the grounded inference as the body, cited to
   its sources. It lands in `candidates/` — **not** durable knowledge — grounded
   sources-only (the Core rejects grounding in a derived doc: no chaining, even here).
   The Core dedups: an equivalent pending or already-**declined** inference is not
   re-staged (a sticky decline won't nag again — unless a cited source has since
   changed). Staging is silent; don't announce each one.
2. **Review in a batch (`review-candidates`), not per item.** On load, if
   `list-candidates` shows any pending, **offer once** to run **`review-candidates`**
   over them (this is the reliable moment — it rides the MUNINN.md on-load check; there
   is no dependable session-*end* hook). For each candidate, **re-read its cited source
   bytes** (borrow the Review discipline below — never trust the staged text) and decide:
   - **promote (new doc)** → `promote-candidate cand-<slug>` writes it into the base as a
     first-class derived doc (default an **insight**; `--new-id`/`--proposed-kind` to
     steer), then `index` + `lint`. **Set the honest derivation rung here** (having
     re-read the source): a single-source deterministic computation is `extracted`,
     a cross-source connection is `synthesis` (see *Ask* §4). Staging leaves it unset.
   - **fold (into an existing doc)** → `promote-candidate cand-<slug> --into <doc-id>`
     when the fact belongs *on* an existing doc (an age onto `ent-strudel`), not as a
     standalone. This is a **literal insert** (ADR-0035): the Core appends the
     candidate's block byte-preserving the rest, unions its sources, drops the doc to the
     weakest rung, and consumes the candidate. **Prefer folding over re-authoring the
     target** — you don't rewrite the doc; you add to it. If a folded card later reads as
     an accreted list, `regenerate` re-coalesces it cleanly (fold *adds*; regenerate
     *re-derives*). Then `index` + `lint`. Fold **timeless** facts (a datum + rule, a
     historically-dated measurement); a candidate stating a *decaying* result (one staged
     with `--as-of`) **can't be folded** — a doc-level `as_of` can't describe one line of
     a card, so the Core routes it to **promote-as-new** (its own aged doc) instead (T-109).
   - **decline** → `decline-candidate cand-<slug> --reason "…"`; it becomes a
     tombstone (remembered, never deleted).
3. **Distinct from Crystallize (ask §5):** Crystallize offers to save the *answer the
   user asked for*; staging captures an *incidental inference* you made along the way,
   without interrupting, for later batched review. Both keep grounding honest; neither
   ever writes to the base unreviewed.

**Author candidate bodies to be self-contained**, so they read cleanly when folded in
place (a fact that stands on its own, cited — not a fragment that needs surrounding prose).

