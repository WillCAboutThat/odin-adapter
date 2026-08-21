## Orient the base — bootstrap or repair the resource landscape

**Three triggers, one flow (T-146):** right after a fresh `init` (the first-run
case); **on the user's word at any time** ("orient this base", "record the
landscape", "add ClickUp to the landscape"); or on the on-load
`unmapped_connector_systems` offer (above) — the retroactive case for a base
that predates its landscape or was never oriented. Never a silent write. This
is how an enterprise Muninn avoids per-resource authoring. You already know
what **connectors** you have (your MCP/tool self-descriptions) and can see the
repos in reach, so **propose the whole landscape map at once**, then let the
user confirm in one pass:

1. **Survey your connectors + repos.** Enumerate the connectors you hold (Jira, Drive, Slack,
   a KB, code hosts) and any repositories in reach. This is transient reasoning over what
   *this adapter* has — not stored state.
2. **Propose the map — one landscape entry per resource.** "I can see Jira, Google Drive, a
   Confluence KB, and the `pmt-core` / `infra` repos. Want me to record a landscape of what
   each holds?" **Draft, then confirm** — don't dump your tool list as fact.
3. **Author the durable entries the user keeps** — but ground each in a **fact about their
   world**, not in your transient tool list (the tool set changes next session; the fact
   shouldn't). Precedence, same as repo surfaces (ADR-0028 §6):
   - **(a)** the connector's own self-description (what the MCP says it is) + **the user's
     confirmation/steer** ("Jira PLAT is our platform work") → the grounded source;
   - **(b)** a *light* survey (list top-level projects/spaces) to enrich "what it holds" —
     **flagged as sampled**, low assurance, not authoritative;
   - a **repo** → `capture-repo` its constitution and author its mental model (see *Ingest a
     repository*).
   For each: `derive` a short landscape summary, **assert the connector** with
   `--connector <system>=<ref>`, and place it (+ its source) in the **`global` view**
   (`… project <root> global --scope global --member …`) so it's always in scope.
   **Three rules that make the entry real, not just readable (T-175 — learned
   from the first live orientation, which produced a maximal prose landscape
   and cleared nothing):**
   - **The assertion is what clears the orientation debt.** A landscape entry
     without `--connector` leaves `unmapped_connector_systems` unchanged and
     the orientation offer re-firing every session, however good the prose.
   - **Coverage is per `origin.system`, and the strings must match exactly.**
     One `url=<ref>` assertion covers EVERY web source, present and future;
     asserting a prettier name (`web=...`) for sources whose system is `url`
     covers nothing. Check the sources' actual `origin.system` first.
   - **Map standing wells, never a census.** Entries are the places worth
     routing a future `explore` back to, each grounded by 1-2 attesting
     captures. One-off captures get NO entry: their `origin.ref` and the
     base-wide drift worklist (T-147) already track them fully, and a
     many-source landscape stales whenever ANY grounding source versions.
4. **Show the roster and hand off.** `… connectors <root>` prints the computed map; tell the
   user it grows as they ingest and refines on their word. **Never gate `init` on this** —
   offer it, do it on the nod, and a user who declines just has an empty landscape to fill later.

**Keep the landscape current — opportunistically.** The first-run survey is best-effort and
**cannot enumerate every connector**: MCP tools self-describe, but a **host CLI** (`gh`,
`aws`, `kubectl`, `psql`), a plain HTTP API you call, or a connector added later does **not**
— you only learn you have it by *using* it. So don't lean on setup alone. **Whenever you
reach a connector during a task that isn't in the landscape** (check `… connectors <root>`,
adding `--project <id>` when working inside a project, T-128),
and it's a **durable resource** worth mapping (a code host, an issue tracker, a cloud
account — not a one-off `curl`), **notice it and offer to record it**: *"I used `gh` to reach
GitHub, which isn't in your landscape — want me to add it?"* Judge durability; **offer, get
approval, never a silent write**. This is how the map catches what the survey structurally
can't — the same reasoning the survey uses (a self-description you *observed by using it*),
just deferred to the moment you learn the connector exists.

**Recording the landscape means authoring domain knowledge, never snapshotting your
tool list (T-127).** When the user asks to durably record explored or available
connectors, author (or extend) **landscape docs** stating what each system *holds for
this org* ("work items live in ClickUp"; "the Data Team's ADRs live in ADO"), one
entry per system where granular staleness matters, each asserting via `--connector` —
never a roster of "connectors currently active/callable." Reachability is per-machine,
per-session, OAuth-state-dependent **survey output that evaporates by design**
(ADR-0021 §1); a durable snapshot of it reads as standing fact on any other machine or
day. If the user insists on keeping a reachability observation, keep it honestly: a
**dated point-in-time observation** ("observed callable on <date> from
<environment>", never "active"), captured with **`--captured-by
<faculty>/<model>@<version>`** — it is an **Odin-authored record with no external
referent**, legitimate the way a person's meeting note is, but the authorship
disclosure is mandatory and everything derived from it stamps `model-read`.

**Repairing a pre-T-127 landscape (the legacy-roster case, T-146).** A base
oriented by an older session may hold exactly that anti-pattern: one
"active connectors" roster doc bundling every system, its prose claiming base
or reachability state ("nothing ingested yet", "callable without auth") that
rots by construction. The honest repair, all consented: author the per-system
landscape entities (grounded in the user's steer captured as a source, each
asserting `--connector`), member them into `global`, then **`supersede` the
roster** with a reason naming its replacements — never regenerate it in place
(a fresh roster is the same trap, fresh paint: any authored sentence about
base state duplicates what the `connectors` projection computes live).

