## Why (a recorded decision + its rationale)

`why <topic>` is `find` scoped to the **owner's decisions** (SPEC §5.5) — present a
recorded decision with the reasoning and consequences behind it, not just a link.
It is distinct from `find` because "why did we decide…" is high-value and a
decision carries a known ADR shape (context · decision · consequences · status).

1. **Retrieve** the relevant decisions — a deterministic type-scoped `find`:
   `python <ODIN>/tools/muninn_core.py find <root> <topic> --type decision`
   (omit the topic to list every recorded decision).
2. **Present** each match by **reading the decision doc**: state its **decision**,
   the **context** that forced it, and its **consequences**/status, in plain terms.
   These are decisions the *KB owner* recorded as knowledge — distinct from
   ODIN-the-tool's own ADRs. If a decision cites sources as evidence, surface them.
3. **No decision recorded?** Say so plainly — a `why` with no match is an honest
   "we haven't recorded a decision on that." Offer `ask`/`find` for related sources,
   or **`record a decision`** (below) to capture it. **Never invent a rationale** the
   `decisions/` don't hold — the no-fabrication rule binds here too.

