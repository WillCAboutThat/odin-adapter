## Challenge (devil's advocate — suspend trust-the-base, on the user's word)

**The warranty line first, because this verb exists to test what's outside it
(ADR-0040):** *provenance warrants derivation, not truth.* The base warrants
"faithfully what the source said, as of when, derived without chaining" —
whether the source was **right about the world** was never inside the
warranty. Your default trust in the base is correct and load-bearing (the
compounding value is *not re-deriving*); `challenge` is the named, consented
way OUT of that posture for one claim. Triggers: *"is that actually true?"*,
*"play devil's advocate"*, *"get a second opinion"*, *"challenge that."*

**Not `review`:** `review` is the maintenance sweep over derived docs (is our
memory still honest against its sources?); `challenge` is the adversarial
interrogation of ONE claim, and it may reach **outside** the base. Same engine,
different intents — when the user names a specific claim to attack, it's
`challenge`; "re-check our conclusions" broadly is `review`. **A broad
"challenge our assumptions" / "challenge everything" names no single claim, so
it does NOT invoke `challenge`:** do not run a base-wide adversarial sweep on
targets you picked — either ask *which claim*, or route to `review` (the
fidelity sweep) and say why. The word "challenge" without one identifiable claim
is not the verb (a 2026-07-22 routing probe caught adapters sweeping anyway —
T-191). (And neither is
`review-candidates`, which merely shares a word: that verb is **admission**
triage of staged inferences — "deal with the pending pile" — not an audit.
Three questions: `review` = fidelity · `challenge` = truth ·
`review-candidates` = admission.)

1. **Internal mode first, always** (cheap, reaches nothing; most bad claims die
   here). Re-read the cited sources adversarially: **quote** what they actually
   state; **dissolve** anything they don't; name the **weakest assurance link**
   in the chain (a reference-tier peer, a model-read rung, a mixed full+reference
   grounding — say which). This is the CHALLENGER discipline pointed at the
   user's own knowledge.
2. **External mode on the user's word** (it reaches outward, like explore /
   drift-check — never automatically). Treat the claim as a **hypothesis** and
   look outside for *disconfirming* evidence, not confirmation. Anything fetched
   that the user keeps goes through the full capture-fidelity discipline
   (full bits, tier honesty, anchors for excerpts).
3. **Fresh context where the harness allows it (ADR-0015):** run the internal
   pass in a **fresh subagent** that receives only the claim + the base path
   and reads from disk — an in-context source poisons its own check; a
   same-session devil's advocate may defend its own prior reading. Where a
   subagent isn't available, run in-session and **say the check is weakened.**
4. **Write nothing by default.** Running a challenge produces conversation.
   Each knowledge-product is its own consented act, offered, never assumed:
   a **counter-insight** or **caveat** (grounded, cited, no chaining) — or,
   when the claim is genuinely overturned, **offer `supersede`** with the
   replacement recorded first (ADR-0041). Never silently edit the challenged
   doc; never store a trust score anywhere.
   **When only internal mode ran, the close also offers the external rung
   (T-144):** *"want me to check the world too?"* — alongside the product and
   log offers, so the user never has to remember mode two exists. Make the
   offer explicit and prominent when the outcome is **weakened/refuted** or
   the weakest assurance link is **reference-tier or thin provenance** —
   internal evidence just showed the claim wobbling, and the world-check is
   exactly the next rung. An offer is not an invocation: external mode still
   runs **only on the user's word** (never on the strength of the offer
   alone).
5. **Close with the log line** (after any consented products): `… challenge-log
   <root> <target> --outcome survived|weakened|refuted [--detail …]` — history
   a future reader can consult, never a mark on the doc.
6. **Voice rule: challenge output is framed as challenge, never as base fact.**
   *"Under challenge, this claim weakens: the source states X, not Y"* — and a
   survival is reported as *"survived this challenge,"* never "verified true."

**Never:** auto-runs (the user mentioning doubt is not an invocation — ask);
runs a base-wide sweep off a broad "challenge …" that names no single claim
(ask which, or offer `review`); writes uninvited; reaches outside without the
user's word; rates truth.

