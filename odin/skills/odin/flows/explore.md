## Explore (outward discovery — Huginn reaches, never remembers)

`explore` is the **mirror of `synthesize`**: synthesize looks *inward* for new
connections; explore reaches *outward* — to a repo, drive, site, or connector — for
new **sources** (ADR-0020). The load-bearing rule: **explore is transient. Huginn
discovers; it does not remember.** Nothing reaches durable memory during an explore;
it **ends by *offering* `ingest`** — the sole path to memory, where capture consent
lives (ADR-0007). Think **explore : ingest :: deliberation : decision** — an explore
is cheap and reversible *because* it commits nothing.

1. **Precondition.** Locate the Muninn (offer `init` if none, as at the top). The
   base gives dedup context, and the terminal act is an `ingest` offer.
2. **Survey, then reach (ADR-0021).** *Before* reaching, **survey** what you can
   reach and reason which connector/source fits the need. Capability knowledge comes
   from three places: **(a)** your available **MCP/tool self-descriptions** (the
   mechanism — "this is a Drive/web connector"); **(b)** the **user's steer** ("the
   contracts live in Drive"); **(c)** the durable **resource-landscape layer** in the
   `scope: global` hub (SPEC §5.6) — grounded docs describing what systems/connectors/
   **repos** exist and what each holds ("vendor comms live in Slack #vendor"; a repo
   **mental model** = what that codebase is *for*). These are ordinary grounded facts,
   **never connector infrastructure**, so **read** them to route — run `… connectors <root>`
   for the computed **roster** of connectors your world touches (origin-union + asserted;
   T-070), and **working within a project, `… connectors <root> --project <id>`** for the
   project ∪ global roster (T-128; a project-scoped assertion is invisible to the global
   list by design). When the layer is thin, *offer to build it*: a repo mental model, or a
   landscape note that **asserts** a connector via `… derive … --connector <system>=<ref>` —
   and **ask the scoping question at registration**: an org-wide fact ("contracts live in
   Drive") is asserted on a **global** landscape doc; a fact specific to one project ("the
   GDPR project's tickets live in this ClickUp list") is asserted on a doc that is a
   **member of that project**, where the scoped roster carries it. The
   survey is a **transient reasoning act,
   not a stored registry** (survey ≠ registry — same content, opposite
   ownership/lifetime). It also **pre-flights the candidate set** — reachability,
   redirects, and dedup-preview *across the whole set before ingest* — so a
   404/403/redirect surprises you **once, up front**, not one-by-one mid-loop.
   Then **reach — adapter-native, uncapped:** the connector is whatever **MCP/tool
   you already have** and authorized — **no ODIN registry**, no held credentials
   (ADR-0020 §2). **Can't reach it?** Say so plainly and do nothing — no partial
   reach, no silent failure. Don't cap the crawl by rule: reason about what's
   "enough," and let the user send you back for more; an over-broad reach only wastes
   time (nothing is committed).
3. **Discover** candidate sources from the target — transient, **write nothing.**
4. **Dedup-preview each candidate via the Core** (you **never** compute a hash —
   fabrication risk; hashing is deterministic Core work):
   - **Fetchable candidate:** `fetch` its bytes (your single-target MCP primitive),
     then `… dedup-check <root> --source-file <tmp> [--id src-<guess>]` →
     *already-captured / changed / new*.
   *(MCP transport - the norm for plugin installs: a `--file`/stdin body becomes the **`body` param carrying the literal text, never a file path**; `--source-file` becomes the **`source_file`** path param. Same op, same other args - the kernel's Setup section has the full mapping.)*
   - **Reference-tier candidate** (bytes you can't hold): `… dedup-check <root>
     --origin-ref <ref>` (locator match). You **may** additionally *propose* a
     fuzzy near-dup by content similarity — always **flagged as a guess, never a
     silent merge** (T-045 ladder).
5. **Assemble the transient preview (write nothing).** A fetchable candidate is
   shown by what it is + its dedup status; a **reference-tier candidate** (no
   bytes) is shown as a **preview summary you author** — what it is, what it
   covers, its `origin.ref`. That preview is **yours (Huginn's), not a durable
   `summary` doc** — it never enters `summaries/`, and it is routing information
   for the user's decision, never a capturable artifact. (This step is not
   "staging": staging is the candidates verb, and explore findings never go
   there.)
6. **Report — chat or park, and say which.** Either **present the findings in
   chat**, or — on a **one-time explicit opt-in** ("park these for later") —
   **park** them in the Muninn's `inbox/` for async review. `inbox/` is
   pre-capture staging, **not** memory (ADR-0006), so parking there is *not* a
   write to the Muninn. Park a fetchable candidate as its bytes; a
   reference-tier one as your preview note. Never park without the explicit
   opt-in. **When reporting in chat, state the disposition and name the
   options**: these findings are transient and nothing has been written; the
   user can say "park these" to hold them in `inbox/`, or pick items to ingest
   now (each fetched in full from its source). Never say you "staged" what you
   only presented: staging is the candidates verb (and explore findings never
   go there), parking is `inbox/`, and a chat report is neither (T-129).
7. **Offer to `ingest`.** The terminal act. On the user's selection, hand those
   findings to the **Ingest** flow above in connector mode — which **re-fetches
   and re-derives from the real source: the complete source data, full bits**
   (the raw item/page/file per the connector rule in Ingest step 2, with its
   linked artifacts surfaced as their own candidates); the durable summary is
   minted at ingest. Your explore-time preview is **routing information only:
   never promoted verbatim, and never captured as the source** (derivation
   honesty, ADR-0015; fidelity, T-131). Declined findings leave no trace.

**Never:** write to the durable Muninn during an explore; capture anything as a
source mid-explore (ingest is the only path in, and it fetches full bits — never
your preview prose); compute or assert a hash;
promote a preview summary into memory unverified; park to `inbox/` without an
explicit opt-in. **Writes:** nothing durable — only, on the opt-in, transient
`inbox/` staging. Memory changes only when a separate `ingest` is requested.

