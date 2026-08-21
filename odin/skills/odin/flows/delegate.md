## Delegate (scale the long verbs without losing the session — ADR-0045)

Some harnesses let you hand work to **subagents** — isolated contexts that run
in the background or in parallel (on Claude Code, the bundled `odin-ingest`,
`odin-scout`, `odin-map`, `odin-synthesize-discovery`, and `odin-review`
workers). Where yours does, use them for the long verbs; where it
doesn't, this section is inert — run the same work inline, in stages, and say
so (composition honesty, ADR-0015).

**When to delegate:** bulk ingest (several sources), a repo/folder/connector
sweep (`explore`'s legwork), a consented drift-check sweep (the scout's
second mission), map or synthesize discovery (rail-landing workers), a
review/broad-challenge audit, any job whose *reading* would flood this
session's context. The operator's session is for judgment and consent; the
bulk reading belongs in a worker. **Mechanics-out-of-view is a first-class
reason too:** a worker's flow reads, source walks, and retries land in its
own transcript, so the operator's session shows the outcome and the offer -
not two hundred tool calls. Delegation is the transparency mechanism, not
only the throughput one.

**The rules (non-negotiable, all of them ADR-0045):**

1. **Pass the Muninn root explicitly.** A worker that wasn't told the base
   refuses and reports back — it never guesses, never searches. If YOU don't
   know the root, resolve it with the user first (Locate the Muninn, above).
2. **Parallel inference, serial short writes.** Fan out the reading and
   authoring; every write lands as one brief Core op under the base's own
   write lock. Keep simultaneous writers modest — for write-dense phases
   (bulk capture with little reasoning between writes) that means 2–4, a
   measured bound, not a vibe (ADR-0045, refined 2026-07-29): on Windows,
   8 tight-loop writers queue to the lock's give-up threshold.
3. **Trust the gate, not the agent.** Worker output is verified the same way
   yours is: provenance pinned at capture, containment at derive, lint over
   the whole base. Don't re-review a worker's mechanics — check the gates'
   verdicts.
4. **Lower trust → the candidates rail.** An unattended or exploratory worker
   stages (`stage-candidate`); promotion stays here, serial and consented
   (ADR-0033). A scout never writes at all — it returns a worklist.
5. **Converge on lint.** The work is done when the base lints clean, not when
   the last worker returns. On Claude Code the plugin's hooks enforce this
   deterministically; elsewhere, run the lint yourself — the elicited floor.
6. **Delegate only what you can collect (refined 2026-08-16, from a measured
   loss).** A sub-task is never fire-and-forget: wait and poll until it
   actually resolves, and if the host loses or fails to resolve a worker,
   reclaim that work inline before ending. **Never end a session holding
   confirmed-but-uncommitted findings in context** — land them through the
   Core (consented), stage them on the candidates rail (rule 4, the durable
   home for exactly this), or write the draft to a scratch file *outside the
   base* and say so plainly. A finding that lives only in a session's context
   dies with the session (T-052 at the session level): the receipt is a real
   `map` pass whose delegated discovery was lost by the host — 18 minutes,
   30+ grounding reads, zero writes, everything re-done. Nested delegation
   (a worker spawning workers) is where hosts have measurably misrouted
   completions and misreported durations — prefer one level, and treat any
   depth-2 cost figures as unverified until checked
   (`scripts/adapter_eval/NESTED-AGENT-CHECK.md`).

