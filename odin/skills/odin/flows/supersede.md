## Supersede (the honest ending of a derived doc — ADR-0041)

Some pages don't need a refresh; they need an **ending**: a claim the user has
overturned, a doc mis-filed and re-recorded under the right type, a derivation
replaced by a better one. That is `… supersede <root> <id> [--by <replacement>]
[--reason <why>]` — never a hand-edit, never a delete.

- **Sequence: replacement first.** Record/derive the successor, then supersede
  the original pointing at it (`--by` must resolve). No successor? A reason is
  required — an ending has an explanation.
- **What it means:** the doc is **closed, not hidden** — still lints, still in
  the index (badged `superseded`), exempt from L4 staleness, skipped by `find`
  unless `--include-superseded`. Say this when you supersede: *"kept for the
  record, out of retrieval."*
- **Mistake path:** `--lift` restores `current` (logged). Offer it when the
  user says a supersession was wrong; never edit frontmatter by hand.
- **Refusals are honest:** deriving over a superseded id is refused (no silent
  resurrection — new id, or lift first); sources and decisions can't be
  superseded by this op (versioning and the decision record are their endings).
- **Consent:** superseding is the user's call, always offered, never a side
  effect of `regenerate`/`review`/`ask`. When a review or challenge overturns a
  claim, *offer* the supersede with the replacement in hand.

