# Odin — Skill Contract

**Status:** Draft
**Version:** 0.1
**Aligned with:** ADR-0001 (Odin is the interface), ADR-0002 (one Muninn,
projects as views), ADR-0003 (source-capture policy), and the Muninn format
spec (`docs/muninn/SPEC.md`).

---

## 0. What this is

This is the **behavior contract** for Odin's skills — what actually happens when
a user invokes Odin. It sits between the decisions (ADRs) and the reference
adapter that implements them. It is tool-neutral in spirit: it specifies
*behavior and guarantees*, not a particular runtime. An implementation is
correct if invoking these skills leaves the Muninn conformant to the spec (its
invariants hold, its lint passes).

**How the reference adapter implements this contract is ADR-0008:** a
tool-neutral, deterministic **Core** (code) owns every file write and every
guaranteed operation as an atomic step; a tool-specific **adapter** (for Claude,
a Skill) supplies judgment and orchestration. Core owns all writes; the adapter
passes generated content in as frontmatter data. This contract stays
tool-neutral — the split only concerns the reference adapter.

Odin is the interface; Huginn (exploration) and Muninn (memory) are the
faculties each skill draws on. The user speaks only to Odin.

### Skill surface

The user-facing verbs (ADR-0001, extended by ADR-0009, ADR-0019, ADR-0026,
ADR-0027, and ADR-0033):

`ingest` · `ask` · `explore` · `find` · `search` · `retrieve` · `why` · `record a decision` · `lint` · `synthesize` · `review` · `review-candidates` · `drift-check` · `challenge`

Operational verbs that maintain the knowledge base (ADR-0004) and its disposable
indexes (ADR-0027), plus the on-load surface (ADR-0034):

`init` · `regenerate` · `reindex` · `status` · `retier` · `supersede`

---

## 1. Invocation model

Every skill works in **two registers**, and they must behave identically:

- **Conversational** — the average user, in Cowork or a chat, pastes a document
  or asks in plain language. "Remember this." "What do we know about the vendor
  contract?" No terminal required.
- **Explicit** — `odin <verb> <args>`, for users who want precision or scripting.

Natural language maps to verbs:

| The user says… | Verb |
|----------------|------|
| "remember this", "add this to memory", "capture this", "ingest the inbox" | `ingest` |
| "what do we know about…", "can you reason about…" | `ask` |
| "go look at…", "scan the repo/drive/site…" | `explore` |
| "find…", "pull up the source for…", "where's the doc on…" | `find` |
| "why did we decide…", "what's the rationale for…" | `why` |
| "log this as a decision", "record that we decided…", "amend that decision" | `record a decision` |
| "find connections", "what links…", "look across everything for…", "any date dependencies/patterns across projects" | `synthesize` |
| "is our memory healthy?", "check for drift" | `lint` |
| "is this still true?", "re-check these conclusions", "audit my notes", "does what we wrote about X still hold?" | `review` |
| "is that actually true?", "play devil's advocate", "get a second opinion on this", "challenge that claim" | `challenge` |
| "set up a knowledge base here", "start/initialize a Muninn" | `init` |
| "update this page/summary", "refresh…", "re-derive…", "this is out of date" | `regenerate` |
| "for the Q3 project", "start a project for…", "group these under…", "this is a standing/company-wide constraint" | `project` (a view) — usually a modifier on `ingest` (`--project`), not a standalone verb |

When intent is ambiguous, Odin asks one clarifying question rather than
guessing. These disambiguations matter most:

- `ask` vs `find`: `ask` may reason/explore; `find` is pure retrieval.
- `ask` vs `synthesize`: `ask` answers a **specific question** you bring;
  `synthesize` is **open cross-source discovery** — it finds connections you
  didn't ask about (ADR-0009). "What do we know about X?" is `ask`; "what
  connects across all this?" is `synthesize`.
- `lint` vs `review`: `lint` checks **structural** health — citations, hashes,
  staleness — deterministically; `review` challenges **semantic honesty** —
  whether a derived doc's claims still hold against its sources and the rest of
  the base. Lint verifies the *bricks*; review questions the *arch* (ADR-0026).
  "Is our memory valid?" is `lint`; "is what we concluded still trustworthy?" is
  `review`.
- `review` vs `challenge`: `review` sweeps derived docs against their **sources**
  (maintenance, inward); `challenge` adversarially interrogates **one claim** and
  may reach **outside** the base for disconfirming evidence (ADR-0040). "Re-check
  our conclusions" is `review`; "is that specific claim actually true?" is
  `challenge`.
- **"update"** is overloaded. "Update the summary of X" / "X is out of date" —
  meaning re-derive an existing page from current sources — is `regenerate`.
  "Update our knowledge on X" with *new* material is `ingest`. When unclear
  which, Odin asks.
- **Projects are the user's curation, never Odin's.** Odin creates or adds to a
  project **only when the user names one** ("…for the Q3 project"); how knowledge is
  organized into views is the user's call (ADR-0002). Odin never invents a project
  or auto-groups sources on its own. Un-grouping is the same consented act: the
  `project` op removes members as well as adding them (T-148) — a link change only,
  the doc untouched and findable as ever; a members list is never hand-edited.
  "Standing / company-wide / applies-to-everything" context is added to the
  always-in-scope **`global`** hub (ADR-0018), which every scope unions in — so the
  user need not remember to include it. Global membership carries a cost (it rides
  into *every* working set), so the test is "in scope for **every** question?" —
  when unsure, prefer a project view (T-146's membership discipline).

## 2. Preconditions: locating the Muninn

Every skill except `init` operates on a Muninn. Odin locates it by finding a
`muninn.yml` manifest (§5.7) at, or above, the working directory, or at a
user-configured path (ADR-0002).

- **No Muninn found:** Odin does not silently create one. It explains that no
  knowledge base is present and offers `init`. The **first-run contract** (ADR-0032):
  - **Resolve + confirm the location.** Default the target to the working directory
    (a user-named path is used as given), but **always state and confirm where the
    base will live** — the user must always know. Never scaffold at a location nobody
    chose.
  - **Tool-repo guard (soft-warn).** `init` returns `action: "warn"` and writes
    nothing when the target sits inside ODIN's own checkout (a `.odin-tool-root`
    sentinel is found at/above it) — a knowledge base lives **separately** from the
    tool (ADR-0002). Odin surfaces the warning and picks another location; a
    deliberate in-repo init (dogfooding) passes `--allow-tool-root`. The consented op
    still proceeds — surface, don't block.
  - **Non-interactive / headless.** A missing Muninn is an **error, never a silent
    create**, unless consent was explicit — a prior `init`, or `ingest --init <path>`
    (initiating ingest consents to *capture*, not to *scaffolding a base here*,
    ADR-0007).
  - **Orient after a triggered init.** Before continuing into the ingest report,
    surface — tightly — **where** the new base lives, that it's durable Markdown + git
    separate from the tool, and that its `MUNINN.md` explains it.
- **Manifest version newer than the adapter understands:** Odin refuses to write
  and says so, rather than risk corrupting a format it doesn't fully grasp.

**On load, check lint freshness (ADR-0005).** When Odin opens a Muninn, it
recomputes the content fingerprint (SPEC §4.4) and compares it to the last lint
entry in `log.md`. If they differ, the base has changed since it was last
checked — Odin says so and suggests `odin lint`. If they match, it stays quiet.
This is a change-based nudge, not a time-based one; a reference adapter may
implement it as a SessionStart hook for determinism. **Proactive synthesize (on
load).** When the change **added new sources**, Odin may additionally **offer** —
once — to look for the connections they form with existing memory, running
`synthesize` only on acceptance (never unasked; it is a real token spend, and
proposing-not-writing extends to proposing-not-scanning). A derived-only change (a
`regenerate`) is skipped. This is `synthesize`'s **proactive on-load** mode
(ADR-0009 §6, riding ADR-0005). **Git-backed base (T-167).** When the base root
is a git repository with a remote tracking branch, the on-load nudge folds in one
quiet clause from a local-only `git status -sb` read (uncommitted changes,
unpushed commits, known behind-ness) — and **never fetches or pulls on load**:
contacting the remote is an outward reach, always the user's deliberate act (the
drift-check posture), so pulling is an offer taken only on the nod. Silence means
"current as of the last fetch," never "current."

**Close a session (T-169).** The on-load ritual has no session-end twin: no
dependable hook fires when work ends, so settling always waited for the next
open - and on a git-backed base, unpushed work becomes the next machine's
stale-clone problem. The user saying "close out" / "wrap up" / "settle the
base" IS the end-of-session signal, and the flow it triggers is all offers:
(1) pending candidates -> offer `review-candidates` (the batch moment, second
chance); (2) `lint` -> 0 errors is the closing posture; findings surfaced with
heals offered, never silently fixed; a declined heal closes imperfect but
never uninformed; (3) `inbox/` -> anything still parked is named (its meaning
is exactly "still pending"); (4) git-backed base -> offer the commit + push
with a plain session summary message - the load nudge's other half: the nudge
catches the stale clone next time, the close-settle prevents it this time.
**Settle git LAST** (content steps first, or the push loops), and never
commit or push without the nod. (5) One-paragraph close report from
`log.md`'s tail: what changed, what stays open. The reference adapter ships
this as a bundled skill/command; any adapter honors the phrases.

## 3. Cross-cutting guarantees

These hold for *every* skill. They are the spirit of the invariants, made
operational:

1. **No summary chaining.** Derivation is grounded only in sources, never in
   other derived docs (SPEC §I3). Odin will not build a summary from a summary.
2. **Provenance or it doesn't ship.** Every derived doc Odin writes names its
   sources and their hashes (§I2). No orphans.
3. **Visible, consented capture.** Ingesting stores a durable copy; Odin says
   what it stored and where (ADR-0003). For material that looks sensitive
   (secrets, personal data), Odin confirms before storing rather than assuming.
4. **Traceable answers.** Anything Odin *asserts* as known is cited back to a
   source. If Odin is reasoning beyond the sources, it says so. If it doesn't
   know, it says that too — and offers to `explore`.
5. **Honest assurance.** Answers or summaries resting only on `reference`
   captures (sources Muninn doesn't hold in full) are flagged as lower-assurance
   (SPEC L10).
6. **Sources and staleness are never silently touched.** Odin does not edit a
   source (§I1) and does not silently rewrite a stale doc (§I5).
7. **The human validates.** The knowledge cycle is "Huginn → human + AI
   synthesis → Muninn." Capture (storing truth) is safe to do immediately;
   *derived* knowledge is offered for validation and is always regenerable, so
   nothing Odin writes is a point of no return.
8. **Grounded in captured bytes — the bright line (ADR-0011).** Everything Odin
   asserts *as remembered* traces to the user's captured material. Reading a
   captured image is in bounds (`model-read`, flagged); answering from the
   **model's own training beyond the sources** (`model-knowledge`) is never
   stamped as grounded and never written to the base. When a question genuinely
   invites it (e.g. "what's typical for a dog *like* this?"), the default is to
   **quarantine, not refuse**: answer the grounded part first (cited), then give
   the general knowledge in a **clearly labeled, walled-off section** marked *not
   from the Muninn*, carried at the **lowest assurance** (below `model-read`) and
   never presented as a record — and **offer to `ingest`** a real source so a
   future answer can be grounded. Refusal is the fallback, for when even a
   quarantined answer would mislead. What Odin must never do is **silently blend**
   model-knowledge into a cited answer. This is what keeps Odin a knowledge system
   and not a chatbot with citations.

## 4. The flagship: `ingest`

**Intent:** "Remember this." Bring a new source into memory and derive
initial understanding from it.

**Inputs:** one or many sources, arriving by any of three **acquisition modes**
(ADR-0006). All three converge on the *same* capture→derive pipeline below —
the mode only changes how bytes are acquired and what `origin` records.
Optionally a target project (`--project marketing-q3` / "…for the Q3 project").

- **Direct** — a pasted document, an attachment, a file path, or a URL. The
  average-user path; no terminal required.
- **Connector (external)** — Odin (Huginn) pulls from a source system through an
  adapter-specific connector (an MCP server or API): a Slack thread, a Drive or
  Notion doc, a Jira issue, a database query. `origin.system` names the
  connector; `origin.ref` is the canonical locator; `recoverable` reflects
  whether it can be re-fetched. `explore` discovers candidates from such systems
  and hands them to `ingest`; `ingest <ref>` captures a known one directly. The
  connector must be available/authorized to the adapter. **Fidelity rule
  (T-131): what gets captured is the source system's DATA** — the raw
  payload/export the connector returns — **never the adapter's own rendering of
  it**. A rendering may stand in as the body only when no raw representation is
  available, and then it is disclosed, not silent: `capture: reference` (+
  `capture_reason`), `recoverable` with the real locator, `origin.captured_by`
  naming the producing faculty/tool (ADR-0001), and `derivation: model-read` on
  everything derived from it. Artifacts the item links (attachments, supporting
  documents) are surfaced as their own capture candidates, never silently
  dropped.
- **Inbox** — the user drops documents into the Muninn's `inbox/` folder,
  singly or in **bulk**, and runs `odin ingest` (or "ingest the inbox"). Odin
  processes each pending file through the pipeline. This is the batch,
  lower-supervision path (see the validation note below).

**Behavior:**

1. **Acquire** (Huginn). Read the bytes via the mode above. Record how they
   arrived: `origin.system` (`file`, `chat`, `url`, `inbox`, or a named
   connector like `slack`), and whether the original is `recoverable`. A
   document pasted into chat is transcribed to a markdown source with
   `recoverable: false` — the transcription is the record of truth (ADR-0003).
2. **Hash first, then dedup.** Compute the content hash. If identical content is
   already a source, do not duplicate — record the new origin and report it. If
   it is changed content of an existing source id, capture a **new version**
   that supersedes the prior (old bytes retained as `source.v<N>.md`; §4.3).
   If the Core **refuses** a capture because the `origin.ref` already belongs to
   another source (the T-045 locator rung — changed content at a known locator
   under a new id), that is the same evolving source: **re-capture under the
   matching id** so it versions. Only pass `force_new` when the user confirms it
   is genuinely a different source that happens to share the locator — the split
   is logged, never silent.
3. **Choose the capture tier.** Prefer `full` — copy the bytes into
   `sources/<id>/`. Use `reference` only when a full copy is genuinely
   infeasible (licensed, too large, private, or *live* in the narrow sense of
   having no stable byte form to hold — a dashboard, a query surface), and then
   require a `capture_reason` (ADR-0003). **The tier describes what the base
   holds, never who owns the truth (T-134):** a complete raw payload or export
   held verbatim is `full` even though the upstream record lives elsewhere and
   keeps evolving — evolution is versioning's job (§4.3, the updated-lease
   case) and re-fetchability is `recoverable`'s. A lossy stand-in (a model
   rendering, an excerpt) is what `reference` is for. A misjudged tier is
   corrected with the deliberate `retier` op (§7), never an out-of-band edit.
   **An excerpt of a larger whole is anchored (ADR-0039):** verbatim excerpted
   content in fenced blocks (disclosure prose outside them), a distinct
   excerpt-qualified `origin.ref` (two excerpts of one whole never share a
   ref, T-045), `upstream_ref` naming the whole, and `upstream_identity`
   (`git-blob:`/`sha256:`) identifying it as of the read — that is what lets
   `drift-check` answer for the excerpt *exactly* instead of hedging. An
   existing unanchored excerpt gets the consented `anchor` backfill, which
   verifies containment before stamping anything.
4. **Write the source** — immutable, with `meta.yml` (origin, hash, tier,
   version ledger). Never overwrites a prior version.
5. **Derive** (synthesis). Produce a summary grounded **only** in this source
   (and, if genuinely relevant, other *sources* — never derived docs). Record
   full provenance: `sources[]` with hashes and, where possible, spans. Give it a
   `title` and a one-line **`abstract`** for skimming (SPEC §5.2), and author it
   **for findability** (see the discipline below, ADR-0012). Set
   `status: current`. Where an entity or concept is clearly touched, offer to
   create/update those derived pages too — each independently grounded.
6. **Place it.** Regenerate `index.md` as a deterministic **projection** of
   frontmatter — `title` + `abstract`, sources first, each source joined to its
   summary (SPEC §5.3); no free-text is authored into the index. **Only if the user
   named a project**, add the source *and* its summary to that `projects/<name>.md`
   view — editing the *project page*, never the source (ADR-0002). Odin never
   invents a project or auto-groups; grouping is the user's curation. Cross-cutting
   *standing* context is added to the always-in-scope `global` hub (ADR-0018).
   **Optionally warm the semantic index** here (best-effort `refresh`, T-091) so the
   docs just added are searchable *now* rather than paying a cold model-load on the
   next query. It is write-only and skippable — `retrieve` self-heals (T-090) and it
   no-ops with no backend — a latency optimization, never a correctness step.
7. **Clear the inbox (inbox mode only).** Once a source is durably written, its
   pending file is removed from `inbox/` — its immutable copy now lives in
   `sources/`. Dedup (step 2) means a re-dropped file is recognized, not
   duplicated. `inbox/` is transient staging, not part of the durable knowledge
   (SPEC §3); it is never linted as sources.
8. **Log** the capture and derivation to `log.md`.
9. **Report.** Tell the user: what was captured (id, tier, where it lives), what
   was derived, and surface anything notable — a dedup hit, a new version, or a
   staleness cascade this change triggered.

**Authoring summaries for findability (ADR-0012).** A summary is not only
*faithful* to its source — it is the layer retrieval reads, so it must be
*findable*. `find` is deterministic substring (ADR-0001; §5): it surfaces a
summary only when that summary literally contains the searcher's words. So author
in the **reader's vocabulary, not only the source's** — phrase the questions a
human or AI would actually bring, in the words they'd use. Shape the summary as
the **faceted digest** (SPEC §5.2, ADR-0011): an `abstract` plus a few universal
labeled facets — **What it is** · **Covers** (the questions this source answers) ·
**Key specifics** (concrete, source-grounded) · **Answers** (direct answers,
cited). The `Covers`/`Answers` facets are where reader-vocabulary matters most:

- **Reader's words, not the document's.** A record that a pet came "from the
  shelter" should also say she was **adopted** — because "adopted" is how people
  ask. In the Ellie eval this single gap was the difference between
  `find("adopted")` → 0 and → the right summary, *matcher untouched*.
- **Answer the question, don't restate the field.** If the source gives a
  "Birthday" and the reader asks "how old / age," state the computed **age** and
  carry both words — don't make the reader already know the document's term.
- **Carry the inflected form the reader types.** `find` is *literal* substring, not
  stemmed, so "rescue" in a summary does not match a query for **rescued**. When a
  key term has an inflection a reader would search (rescue → rescued, adopt →
  adopted/adoption), author that form too, grounded in this source. In the Ellie eval
  `find("rescued")` → 0 while the summary said only "rescue" — the last residual gap
  of retrieval-serving summaries (T-044), the same class as the `adopted` fix.
- **Ground everything; invent nothing.** Every added word must be supported by
  *this* source (I2/I3). A fact that lives only in an unreadable source (e.g. an
  un-OCR'd image) stays out — findability never licenses fabrication; that fact is
  the model-read path's job (ADR-0011), not a guessed keyword.
- **Compress — a summary is shorter than its source (L18).** A summary that runs
  *longer* than its source is paraphrase-bloat, not a summary. Enrich by adding
  reader-vocabulary facets, **not** by restating the source's content in different
  words. A source that is *already* terse — a small table, a one-line note — is
  itself basically a summary: give it a minimal abstract + a facet and stop; don't
  stretch a short source into a long retelling. Its worth is the reader-vocabulary
  facet, not a longer paraphrase. (The linter warns via **L18**; the sole exemption
  is an opaque source with no text layer — a `model-read` of an image — which has no
  length to be shorter than.)
- **It's an iterative, measurable loop.** A curated question set is the
  findability check (T-039): re-run `find` after authoring; a query that still
  returns nothing means the digest is **under-worded**, not that retrieval is
  broken.

This is authored judgment (adapter), not a Core guarantee — the Core enforces
provenance (I2/I3); findability *quality* is the Skill's job (ADR-0008). The
faceted-digest skeleton is the convention (SPEC §5.2); this discipline is how its
facets are worded.

**Read every source, including opaque ones (ADR-0011).** When a capture is
**bytes-only** (no `source-text.md` aid — an image or scan), do **not** skip it:
read the bytes with your multimodal model and draft the same faceted summary,
stamping `derivation: model-read`. A source grounded in deterministic text stamps
`derivation: extracted` (the default). Capture stays deterministic and AI-free
(ADR-0008); the model-read is a *derive*-step act.

**Every source gets a summary — no exceptions (ADR-0013).** Text, extracted-binary,
or bytes-only: each source is summarized at ingest, or it sits captured and
unfindable. Lint enforces this (L15, an error); if a gap exists (e.g. a source
ingested before this rule), `lint` surfaces it and offers `regenerate`, which
*creates* the missing summary (a model-read for a bytes-only source). Lint never
writes the summary itself (I5) — detection and repair stay separate.

**Writes:** a source (+ version files), one or more derived docs, `index.md`,
optionally a project page, `log.md`.

**Returns:** a plain-language confirmation with the stored location and the
draft summary, offered for validation.

**Bulk / supervision:** direct single-source ingest stays interactive — Odin
shows the draft summary for validation. Bulk inbox or connector ingest is the
lower-supervision path: capture is always safe (it stores truth), and Odin
derives for every item but reports a **digest** for review rather than gating on
each one. **Capture itself is never gated:** initiating `ingest` is consent to
copy, so Odin does not pause to ask "may I copy this?" (ADR-0007). It stays
visible after the fact (§3.3, ADR-0003 §5) and, on the *first* ingest into a
Muninn, may note once that ingesting copies bytes into the base — silent
thereafter, and skipped entirely by adapters that can't cheaply detect
first-ingest.

**Honors:** I1 (immutable/versioned), I2/I3 (provenance, no chaining), ADR-0003
(tiers, dedup, visible capture), ADR-0006 (acquisition modes).

**Repositories — a *mental model*, not a file census (ADR-0028).** A codebase is
ingested by capturing its **constitution** (`capture-repo` builds a deterministic manifest
of its intent-bearing surfaces — README, agent contract, ARCHITECTURE / in-repo ADRs, public
contract, identity manifests, orchestration, top-level shape — reference-tier,
`origin.system: repo`), then authoring a **`model-read` mental model**: what the repo is
*for*, its role, boundaries, public contract, ownership — grounded only in those surfaces,
never in code the adapter didn't read. The **default surface set is the AI-free floor**; the
adapter may **augment** it per repo (choosing what matters is judgment; hashing is the Core's
faithful transform). Because the held text is only the constitution, the mental model goes
**stale on a constitutional amendment**, not on every commit. **Generated agent-wiki
layers** in a repo (`openwiki/` and kin, T-133) are transient routing input for the
survey, **never** constitution surfaces and **never** the mental model's grounding
(ungrounded generated prose; grounding in it is summarizing summaries); their pages are
capturable as honestly-framed machine-generated secondary sources only when the wiki
itself is the object of memory. A generator's one-time pointer written into `AGENTS.md`
(a constitution surface) is a legitimate amendment: the stale flag it raises is correct.

## 5. The rest of the surface

### `ask "<question>"`

**Intent:** "What do we know / can you reason about…?" This is where Odin is
most clearly more than a summarizer.

**Behavior:** retrieve by **reasoning over the legible layer** (ADR-0014) — locate
candidates via the index + summaries (a `find` pre-filter helps), then read the
matched sources and reason over them; retrieval here is reading the base, not a
single matcher call. Synthesize an answer **cited to sources**. If memory is
too thin to answer well, Odin says so and — **informed by the survey** (which
connector could hold the missing piece) — **offers to dispatch Huginn** rather than
inventing (ADR-0021): **by offer, never auto-reach**, and the acquisition is
**neutral** (fetch the missing piece, not "support for the hunch"), staying willing
to answer differently if the source doesn't cooperate. A genuinely reusable answer
may be crystallized as a `question`
document (a derived doc with full provenance) — Odin offers this; it does not
clutter memory unasked. Assurance is signaled (§3.5).

**Integrity signal (weakest link, ADR-0011).** `ask` rolls up the **weakest
`derivation`** among the docs it cites into one user-facing line — the same
"weakest link flags it" logic as the reference-tier assurance (L10). "Answered
from deterministic text ✓" versus "rests on a **model-read** image — treat as
lower assurance." The two axes are orthogonal and both surfaced: capture tier
(full vs `reference`, L10) and derivation (`extracted` vs `model-read` vs
`synthesis`). *(The `synthesis` rung activates with `synthesize`, T-042; until then
`ask` rolls up `extracted`/`model-read`.)*


**Close (T-152):** append the usage record — `usage-log ask --scope <ids read> [--tokens <real count only>]` — as the flow's final step. Disposable operational state (ADR-0027), never a base write; the Core cannot see this verb, so the record is the only measurement there is, and the `usage` report discloses when it's missing.

**Never:** fabricates, or answers from derived docs as if they were ground truth
without the underlying sources supporting the claim; or asserts from
`model-knowledge` beyond the captured sources (§3, bright line).

### `synthesize [scope]`

**Intent:** "Turn what we know into wisdom." Surface **non-obvious connections
across existing memory** — the **inward mirror of `explore`** (which reaches
*outward* for new sources; `synthesize` looks *inward* for new connections).
Distinct from `ask`: `ask` answers a question you have; `synthesize` finds the one
you didn't know to ask (ADR-0009).

**Scope:** **project by default**; "across everything / all projects" crawls the
whole base. Either way, Odin **always unions in every `scope: global` view** —
cross-cutting context (org constraints, business model) that bears on all projects
(SPEC §5.6). The user never has to remember to include the global layer.

**Behavior:** scan `index.md` and derived docs' `title`/`abstract` for **fast
candidate discovery** (what the summary layer is *for*), then propose connections —
shared entities, date/deadline dependencies, contradictions, causal or thematic
links. **Every proposed connection is grounded in and cited to sources** (I2/I3),
as an unordered set of **peers** with **per-span** citations (SPEC §5.2) — and
**every proposal carries verbatim quoted spans from the source files, one per
leg** (T-153): a connection that cannot be quoted has not been grounded, and
the quote is not decoration — at crystallize the Core **containment-verifies
each quoted span against its cited source's text and refuses the write on a
mismatch**, so a summary-paraphrase "quote" cannot enter the base. An
unsupported proposal is **dropped, not narrated**. A proposal that is **incomplete
rather than wrong** — a real connection with one leg simply missing from memory — is
*not* silently dropped: Odin **surfaces the gap and offers to dispatch Huginn** to
fetch the missing leg (a third path beside ground-it and drop-it), acquiring
**neutrally** and staying willing to **dissolve** the connection if the fetched source
doesn't support it (ADR-0021, ADR-0015). A gap worth keeping is **offered a durable
home** (T-154): an **open `question` doc** — grounded in the sources that raise it,
abstract leading **"OPEN — "** so the index doubles as the open-questions register —
consented, a direct derive (never the candidates pile), later re-derived into its
answered form by `regenerate` when the resolving source lands. Assurance is signaled (§3.5).
Synthesize **proposes; it does not commit** (§3.7): on the user's nod, kept
connections crystallize into `insight` documents (multi-source, fully provenanced)
and/or `see_also` enrichments on concept/entity pages.

**Proactive (on load).** Besides being user-invoked, `synthesize` has an on-load
mode (ADR-0009 §6): when the on-load freshness check (ADR-0005) shows the base
**grew with new sources**, Odin **offers** — once — to look for the connections they
form, running the flow only on acceptance. It **never synthesizes unasked** —
synthesize is a real token spend, so proposing-not-writing extends to
proposing-not-scanning; a derived-only change (a `regenerate`) is skipped.

**Composition honesty (ADR-0015; learned from a real overreach).** Per-span citations and
lint verify the *bricks*, never the *arch*: accurately-cited spans can still be
composed into a claim no source states (e.g. presenting an unrelated consequence
clause as "why a breach matters" asserts a causal tie by structure — and the
system's own reviewer endorsed it before a source re-read caught it). So the
authoring discipline is load-bearing: before crystallizing, check *per composed
claim* whether the sources state the link or the insight does; the **abstract**
(the index-projected span) may not assert an ungrounded link; an inferential step
is **labeled in the body** ("the sources do not connect these — this is the
insight's inference"); **no `model-knowledge` in a derived body** (the §3.8
quarantine applies *a fortiori* to durable writes); and Covers/Answers facets
advertise only what the doc actually grounds. And **corroboration breadth is itself
a claim**: an abstract or facet may assert agreement only across the sources that
attest the *specific* trait — count witnesses *per claim*, not per insight (two of
three sources noting a trait is two-source corroboration, and the doc must say which
agree). This is distinct from the ungrounded *tie* above — the tie can be real yet
its **breadth** inflated in the skimmable layer — and was surfaced by the adapter
rubric (ADR-0023, T-075) after the T-042 arc. The `derivation: synthesis` stamp is
what lets a later `ask` distrust the paraphrase and re-read the bytes — that
safety net is *reactive*; these rules are the proactive half.


**Close (T-152):** append the usage record — `usage-log synthesize --scope <ids read> [--tokens <real count only>]` — as the flow's final step. Disposable operational state (ADR-0027), never a base write; the Core cannot see this verb, so the record is the only measurement there is, and the `usage` report discloses when it's missing.

**Never:** asserts a connection on the authority of a summary (no chaining, I3),
or writes an `insight` unasked.

**Writes (only on validation):** `insight` docs, `see_also` links, `index.md`,
`log.md`.

### `explore <target>`

**Intent:** "Go look at this." Send Huginn out to a repo, API, URL, directory, or
connector for new **sources** — the **outward mirror of `synthesize`** (which
looks inward for new connections). It closes the discovery duality (ADR-0020).

**The boundary (load-bearing):** `explore` is **transient — Huginn discovers, it
does not remember.** Nothing reaches durable memory during an explore; it **ends by
*offering* `ingest`**, which is the sole path to memory and where capture consent
lives (ADR-0007). The analogy: **explore : ingest :: deliberation : decision** —
exploration is cheap and reversible *because* it commits nothing.

**Survey first (ADR-0021).** Before reaching, Huginn **surveys** what it can reach
and reasons which connector/source fits the need — a **transient reasoning act, not a
stored registry** (survey ≠ registry: same content, opposite ownership and lifetime).
Its capability knowledge comes from three sources: **(a)** the adapter's own MCP/tool
self-descriptions (the mechanism), **(b)** the user's conversational steer, and
**(c)** the durable **resource-landscape layer** placed in the `scope: global` hub
(SPEC §5.6) — grounded docs of what systems/connectors/**repos** exist and what each
holds ("contracts live in Drive; vendor comms in Slack #vendor"; a repo **mental model**
= what a codebase is *for*), ordinary grounded knowledge, never operational connector
state, so the base stays agnostic (a vanished connector leaves a stale *fact*, not a
broken dependency). Read it to route; when it is thin, *offer to build it* (a landscape
note or a repo mental model). The computed roster (`connectors`, T-070) reads globally
by default and **unions a named project's own references when working inside one**
(T-128, matching `resolve_scope`'s project-plus-global reading); landscape assertions
carry a **scope choice** — org-wide facts on the global hub, project-specific facts on
that project's members — and the adapter **asks which** when registering. The survey
also **pre-flights the candidate
set** — reachability, redirects, and dedup-preview *across the whole set before any
ingest* — so a block or redirect surfaces once, up front, not one at a time mid-loop.

**Landscape entries bind through assertions, not prose (T-175).** The
`--connector` assertion is what clears orientation debt — an entry without one
leaves the offer re-firing forever. Coverage is per `origin.system` and the
strings must match the sources' actual system exactly (one `url=<ref>` covers
every web source, present and future; a prettier alias covers nothing). And the
landscape maps **standing wells** — places worth routing a future `explore` to,
each grounded by one or two attesting captures — never a census: one-off
captures get no entry (their `origin.ref` and the base-wide drift worklist
already track them), and a many-source landscape stales whenever any grounding
source versions.

**First-run setup — bootstrap the map from connector awareness.** An enterprise Muninn
should not be built resource-by-resource. Right after `init`, the adapter — which already
knows its connectors (MCP/tool self-descriptions) and the repos in reach — **proposes the
whole landscape map at once** and the user confirms in one pass. The connector awareness is
transient (source (a)); the **durable** entries are grounded in *facts about the user's
world* the user confirms ("Jira PLAT is our platform work"), **not** a dump of the adapter's
current tool list — so the map survives the tool set changing (kept clear of the
survey-≠-registry line). It is **offered, never a silent write**, and grows as the user
ingests. And **route via `retrieve`, not bare `find`** — the landscape is derived docs, so
semantic ∪ find locates the right resource where literal substring is brittle. The survey
**cannot enumerate every connector** — MCP tools self-describe, but a **host CLI** (`gh`,
`aws`, `kubectl`), an HTTP API, or a later-added connector does not — so the map is also kept
current **opportunistically**: when the adapter reaches a durable connector during a task that
isn't in the landscape (checked against `connectors`), it **offers to record it**, never a
silent write. Setup bootstraps; use enriches. **Recording is authoring domain knowledge,
never snapshotting the tool list (T-127):** durable entries state what each system *holds
for this org*, asserted per system via the `connectors` field; a roster of "currently
active/callable" connectors is per-machine, per-session survey output that evaporates by
design (ADR-0021 §1) and never becomes a standing doc. A reachability observation the
user insists on keeping is a **dated point-in-time record** authored by Odin itself — an
Odin-authored source with no external referent, legitimate the way a meeting note is, and
therefore disclosed: `origin.captured_by` names the faculty/model, and everything derived
from it stamps `model-read`.

**Reach (connectors).** A connector is whatever MCP the adapter already has
available and authorized (ADR-0006) — ODIN keeps **no registry and no
credentials**; the reach lives in the adapter, keeping the base vendor-agnostic
(ADR-0008). If the adapter cannot reach the target, Odin **says so plainly and does
nothing** — no partial reach, no silent failure. Reach is uncapped: a capable model
judges how deep is "enough," and the user can send Huginn out for more; over-broad
reach only wastes time, it never corrupts memory (nothing is committed).

**Behavior:**
1. **Discover** candidate sources from the target — transient, nothing written.
2. **Dedup-preview** each candidate against memory via the **deterministic Core
   dry-run dedup** (an AI never computes a hash — fabrication risk): content-hash →
   *already-captured / new / changed* for a fetchable candidate; `origin.ref` match
   for one whose bytes can't be held. A fuzzy content-similarity call may **propose**
   a reference-tier near-dup, always flagged, **never a silent merge** (T-045 ladder).
3. **Stage & present.** A fetchable candidate stages as its bytes; a **reference-tier
   candidate** (no bytes) stages as a **transient preview summary** — what it is, what
   it covers, its `origin.ref` — summary-shaped because that is what helps a human
   *and* an AI decide whether to ingest. This preview is Huginn's, **not** a durable
   `summary` doc.
4. **Report or park.** Huginn may **return to chat** with findings, or — on a
   **one-time explicit opt-in** — **park** selected findings in `inbox/` for async
   review. `inbox/` is pre-capture staging, **not** memory (ADR-0006), so parking
   there is not a write to the Muninn. A chat report **states its own
   disposition**: findings are transient, nothing has been written, and the park
   and ingest options are named so the user need not know them in advance
   (T-129). (Whether the adapter runs the explore detached/long is an adapter
   capability; the contract promises only these two outcomes.)
5. **Offer `ingest`.** The terminal act. On the user's request, selected findings
   are handed to the `ingest` pipeline in connector mode — which **re-fetches and
   re-derives** from the real source (ADR-0011): the **complete source data, per
   the fidelity rule in §4** (full bits, linked artifacts surfaced). The
   explore-time preview is **routing information only — never promoted verbatim,
   never captured as the source** (ADR-0015, T-131). Declined findings
   leave no trace.

**Never:** writes to the durable Muninn; computes or asserts a hash; promotes a
preview summary into memory unverified; parks to `inbox/` without an explicit opt-in.

**Writes:** nothing durable. Only — on the one-time opt-in — transient preview
notes into `inbox/` (pre-capture, linter-excluded). Memory changes only when a
separate `ingest` is requested.

### `fetch <ref>` — Huginn's single-target primitive (not a user verb)

**Intent:** get the bytes of one *specific, named* target. Distinct from `explore`
(open-ended discovery — you don't know what you'll find) and from `find`/`ask`
(retrieval/reasoning over existing memory): `fetch` reaches a **known** `origin.ref`
through a connector and returns its bytes. It is the **atom** three callers reuse
(ADR-0020 §3):

- **`explore`** fetches each candidate it decides to preview or stage.
- **direct `ingest <ref>`** fetches a known target, then captures it.
- **`regenerate`** re-fetches a `reference`-tier source whose bytes aren't held —
  the ADR-0013 §4 self-heal limb (see `regenerate`).

`fetch` is **adapter-side** (MCP): like connectors, ODIN keeps no fetch registry —
the reach lives in the adapter, so nothing durable depends on it (ADR-0008). It
reads bytes only; it **never writes to memory** (only `capture`/`ingest` commits).

### `find <query>`

**Intent:** "Just retrieve it." Pure retrieval, no synthesis.

**Behavior:** search the Muninn (index, tags, content — and, for sources, the
**origin locator**: `origin.ref` / `origin.upstream_ref`, T-141, so a captured
filename or URL is a valid query) and return matches — **sources first**, then
derived docs, with links. Never fabricates; if there is no match, it says so —
**as a literal miss, never as absence (T-142)**: before any "the base doesn't
have it," the adapter degrades the query (strip extensions, split separators),
prefers `retrieve` where the semantic tier exists, and skims `index.md` — the
index answers existence questions; one grep never does. This is the fast,
trustworthy path with no reasoning layer between the user and the record.

`find` is deterministic substring — the **AI-free floor** (ADR-0014): the
guarantee the base is retrievable with no AI and no vendor, forever, and the way a
human or a later tool gets in with no model. It is **not** the strategy for AI
retrieval — an AI (and `ask`) reason over the summaries and sources instead
(§ `ask`). Because it matches **literally**, its quality rides on summaries
authored in the reader's vocabulary (§4, ADR-0012) — retrieval improves by
enriching the **summary**, not the matcher. *(T-052 is not a generative stage
bolted onto this matcher; it is the separate discipline of moving emergent
augmentation into durable, cited derived docs — ADR-0014.)*

### `search <query>`

**Intent:** "Find it by meaning, not the exact word." Semantic retrieval — the
**AI-facing companion** to the `find` floor (ADR-0014, T-087, ADR-0027).

**Behavior:** rank derived docs by embedding similarity, so a reader's word reaches
the author's — `search "illness"` surfaces the vet-exam summary that never says
"illness", where `find` returns nothing (the reader-vocabulary gap of §4 / T-044).
Returns scored candidates, best first.

It lives in the **disposable-index tier**, which fixes two invariants (ADR-0027):

- **Proposes, never grounds.** A hit is a doc to **read** — never a citation, never
  provenance, never written into the knowledge layer. The answer is still grounded in
  the source bytes (§ `ask`); an embedding can rank a doc near a query it does not
  support. `find` remains the AI-free floor; `search` never replaces it, and the base
  stays fully retrievable with no AI (an embedding backend is optional).
- **Choose by task.** A literal token or id → `find`; meaning, a synonym, "the thing
  about…" → `search`. They answer different questions; use both and merge.

The vector store is a git-ignored, rebuildable sidecar (`.odin/`), not knowledge —
kept current **automatically** (`retrieve` self-heals; see `reindex`/`refresh` below).

**Degradation is graceful *and transparent* (§I5).** The tier is optional; the base
stays fully retrievable via `find` without it. But an unreachable backend must never
masquerade as an empty result:

- **Backend down/unreachable** → `search` raises a typed `BackendUnavailable` (naming
  the backend and the `find` fallback), which the adapter reports in one line and then
  **falls back to `find`** — never a silent empty, never a raw crash, never a block.
- **No index built** → a plain empty (offer `reindex`, or use `find`).
- **Backend up, nothing similar** → a real empty semantic result; a literal `find`
  may still match.

This keeps the disposable tier honest: it accelerates when present and steps aside
*visibly* when absent, so the AI-free floor is always the dependable answer.

### `retrieve <query>`

**Intent:** "Just find it, and don't make me choose how." The **default** retrieval
verb — prefer it over bare `find`/`search` unless one is specifically wanted.

**Availability (transport).** `retrieve`/`search` are the **semantic tier** — the MCP
tools `odin_retrieve`/`odin_search`, or `muninn_semantic.py` (ADR-0027). The **bare Core
CLI** exposes only `find`, the AI-free floor (ADR-0014). So "prefer `retrieve`" holds
wherever the semantic tier is present (the MCP path, the norm); an adapter on the raw CLI
without it uses `find` directly — the degrade-to-`find` is by hand there, not by the op.

**Behavior:** union `search` (meaning) with `find` (literal), deduped and tagged by
which retriever surfaced each, so a single call misses neither a synonym nor an exact
token. It **always answers and never crashes**: the fallback to the AI-free floor is
*mechanical* — inside the call — not a discipline the adapter must remember. On a down
backend or an unbuilt index it returns `find` alone rather than raising or feigning
"no matches."

Transparency is structural (§I5): the result names `via` (`semantic+find` | `find`)
and `backend` (`up` | `unavailable` | `no-index`), so a reader always knows whether
the semantic lift applied or the floor answered alone. Like its parts, it **proposes
only** (ADR-0027 §2) — every hit is a doc to read, never a citation. This is why the
tier can be optional without the retrieval experience becoming conditional: `retrieve`
gives one dependable entry point whose worst case is exactly the deterministic floor.

### `why <topic>`

**Intent:** "What did we decide, and why?" `find` scoped to decisions and
rationale.

**Behavior:** retrieve the relevant `decisions/` entries (and any grounded
rationale), and present the decision with its context and consequences. Distinct
from `find` because "why" is a high-value question and decisions carry a known
shape.

### `record a decision`

**Intent:** "Log this as a decision." The counterpart to `why` — `why` retrieves;
this records. A decision is the **owner's own knowledge** (SPEC §5.5, ADR-0019):
authored, not derived.

**Behavior:** on an **explicit** user request (never as a `synthesize`/`ask` side
effect — Odin does not mint decisions on the owner's behalf), write the decision
via the Core `record-decision` op in the ADR shape (context · decision ·
consequences · status). It carries **no `sources` provenance**: cite informing
sources as **`evidence` links** (source id + version, not a grounding hash), so a
decision never chains and never goes stale — an evidence source that later changes
is a *soft note*, not a staleness error. Revise a decision by **amending in place**
(a dated `AMENDED` banner, append-only), not by writing a new one. Do **not** use
`derive --type decision` — the Core rejects it by design; `record-decision` is the
only path.

### `lint`

**Intent:** "Is our memory healthy?"

**Behavior:** run L1–L17 (SPEC §7). Report violations and flag staleness. Lint
**mutates only** `status: stale` markers and the log — it never edits derived
content (§I5). It surfaces what drifted and *offers* `regenerate`; it never
repairs silently. On completion it appends the **standardized lint entry** to
`log.md` with the content fingerprint (ADR-0005), so freshness can be read back
later. (The underlying `muninn_lint.py` checker is read-only; recording is the
skill's job.)

**Returns:** a health report — orphans, chaining attempts, stale docs,
reference-only assurance warnings, broken links, manifest/ledger issues, and
**un-summarized sources** (L15). On an un-summarized source, Odin offers to
`regenerate` it — a captured source with no summary is a fixable gap, not a dead
end (ADR-0013).

**Three verbs, three questions (T-143).** They blur in speech; they must not
blur in routing. `review` asks **fidelity** — *is our memory honest to its
sources?* (scope-wide, inward, read-only; heals via `regenerate`). `challenge`
asks **truth** — *is this ONE claim right about the world?* (a consented
suspension of trust-the-base; may reach outward on a further word).
`review-candidates` asks **admission** — *what enters memory?* (batch triage of
staged inferences; not an audit at all). The word **"challenge" belongs to the
`challenge` verb alone** (ADR-0040): a user saying it of a specific claim means
`challenge`; "re-check our conclusions" broadly means `review`; "deal with the
pending pile" means `review-candidates`. (`review-candidates` keeps its name —
T-143 weighed a rename and rejected it: breaking installed adapters over a
vocabulary nit; the differentiation lives here and in the routing probes,
`scripts/adapter_eval/VERB-ROUTING.md`.)

### `review [scope]`

**Intent:** "Is what I wrote down still trustworthy?" An on-demand **honesty
audit** of the derived layer — the **semantic sibling of `lint`** and the
proactive form of ADR-0015's *reactive* assurance net, which until now fired
only when a user happened to interrogate one claim. `review` : `regenerate` :: `lint`
: `regenerate`, one layer up: it **detects and surfaces**, then hands each
finding to `regenerate` (§I5; principle 5 — *surface, never silently repair*).
Distinct from `lint`: lint verifies the *bricks* (citations, hashes, structure),
`review` interrogates the *arch* — the claim made by composition, which entailment
being semantic no deterministic rule can check (ADR-0015 §3). Distinct from
`ask`: `ask` answers a question you bring; `review` interrogates the base's *own*
prior conclusions. It is **`review`, not `audit`** — ADR-0014 owns "audit" for
the *deterministic* re-read-and-re-hash sense; keep the words distinct (ADR-0026).

**Scope:** reuses `resolve` — whole base, a project, or a single doc — so a
`review` is a cheap spot-check or a full sweep. Like every scope, it unions in
each `scope: global` view (SPEC §5.6).

**Engine (ADR-0026):** the same **grounded adversarial challenger** the adapter
rubric uses (ADR-0023), repointed from grading fixtures to the user's own base
(its grading-fixture isolation rules dropped — they exist for fair benchmarking,
not for auditing your own memory). For each derived doc in scope Odin **re-reads
the cited source bytes** (never the doc's paraphrase) and, defaulting to
skepticism, checks two things — **naming which**:
- **Authoring overreach** — a claim the sources don't state, or a corroboration
  *breadth* wider than its witnesses (the T-042 / T-077 family): counted *per
  composed claim*.
- **Drift against new knowledge** — does the conclusion still hold against
  *everything the base now contains*, including sources ingested **after** the
  doc was derived? This is invisible to `lint` by construction — the undermining
  source isn't in the doc's provenance, so no hash changed (L4 sees nothing).

**Output — a hedged second opinion, never a verdict.** `review` writes **nothing
durable**; it is transient like `synthesize`'s proposals and `explore`'s
findings, and there is **no `reviewed ✓` stamp, ever** (that would be *audit the
lookup*, not *audit the knowledge* — ADR-0014 — an AI blessing that rots and
invites false trust; the durable audit stays derivation provenance, re-read and
re-hash). Each finding names the doc and the claim, quotes the source span (or
says plainly *no source attests this*), states the doubt in the reader's
vocabulary, and defaults to *"a skeptical reader would question this"* — **no
deterministic-looking counts** ("3 errors"): presenting subjective judgment as
fact would be composition overreach one level up, the verb committing the sin it
catches. That two passes may disagree is **disclosed, not hidden**. Each finding
ends by *offering* `regenerate` — the consented heal path.

**Not a gate.** `review` is **read-only, on-demand, and advisory** —
non-deterministic and AI-dependent, so it is deliberately not lint-enforced, not
CI-gated, not a release gate (consistent with ADR-0015 §3 and ADR-0023's "manual
benchmark, not a flaky gate"). The deterministic floor (`lint`, the oracle) is
what gates; `review` advises.


**Close (T-152):** append the usage record — `usage-log review --scope <ids read> [--tokens <real count only>]` — as the flow's final step. Disposable operational state (ADR-0027), never a base write; the Core cannot see this verb, so the record is the only measurement there is, and the `usage` report discloses when it's missing.

**Never:** edits a source or a derived doc (§I1/§I5 — it only reads and reports);
writes a durable "reviewed" mark; presents its judgment with false precision; or
gates anything.

**Writes:** nothing. On the user's nod to a finding, the `regenerate` it offers
does the write — `review` itself is read-only.

### `challenge <claim | doc-id>`

**Intent:** the consented suspension of trust-the-base for ONE claim
(ADR-0040). The base's warranty is *derivation, not truth*: provenance
guarantees a doc faithfully reflects what its sources said, never that the
sources were right about the world. The default reading posture (base as
settled fact) is correct and load-bearing; `challenge` is the named way out of
it, on the user's word only.

**Behavior:** two modes, in order. *Internal* always runs first — re-read the
cited sources adversarially (quote what they state, dissolve what they don't,
name the weakest assurance link, including a mixed full+reference grounding).
*External* runs only on the user's word — treat the claim as a hypothesis and
seek **disconfirming** evidence outside the base (Huginn's reach; anything
kept passes the full capture-fidelity discipline). When only internal mode
ran, the close **offers** the external rung alongside the product offers
(T-144) — emphatically when the outcome is weakened/refuted or the weakest
assurance link is reference-tier — and the offer is never itself an
invocation: mode two still waits for the user's word. Fresh-context discipline
per ADR-0015: a fresh subagent where the harness supports one (an in-context
source poisons its own check); otherwise in-session with the weakening said
aloud. Output is **framed as challenge, never as base fact**; a survival is
"survived this challenge," never "verified true."

**Products (each its own consented act):** a counter-insight or caveat
(grounded, cited, no chaining), or — for a genuinely overturned claim — an
offered `supersede` with the replacement recorded first (ADR-0041). The
completed challenge is recorded once in the append-only log
(`challenge-log <target> --outcome survived|weakened|refuted`): history a
reader can consult, never a mark on the doc, never a trust score (skepticism
is an operation, not a format axis).

**Never:** auto-runs; writes uninvited; reaches outside without consent;
stores any truth rating. **Writes:** only the `challenge-log` entry, plus
whatever knowledge-products the user explicitly consents to.

### `review-candidates`

**Intent:** admit — or reject — the **emergent grounded inferences** Odin staged
while reasoning (ADR-0033). During `ask`/`synthesize`, a capable model routinely
makes a *cited* new inference the base doesn't hold (an age from a date of birth, a
consequence two sources imply). That understanding must not be **written into the
base as an `ask` side effect** (consent-of-surprise; bloat), nor forced through a
per-inference *"save this?"* prompt (a model augments constantly — that nags). So it
is **staged** as a *candidate* — grounded sources-only (I2/I3, un-chainable), parked
in transient `candidates/`, ignored by the invariants and the linter — and admitted
by this **batched** review.

**Channel boundary (T-129/T-131).** The pile admits **only inferences over sources
already in the base**. `explore` findings never route here (outward findings
commit only via `ingest`, which fetches the full source data), and a source's
**summary** never routes here (a summary is mandatory at capture — L15 — and is
derived in the ingest pipeline, not parked for optional review). At promote, the
derivation rung is set against what the cited source *is*: a body that is a model
rendering grounds `model-read`, never `extracted`.

**Staging (not a user verb).** `stage-candidate` writes the inference to
`candidates/`, keyed by a **fingerprint** over its sources' current hashes + its
claim. The Core dedups: an equivalent pending candidate is a no-op; one matching a
**declined tombstone** is skipped — a *sticky* decline that won't nag again **unless
a cited source advances** (new hash → new fingerprint → a legitimately fresh
candidate; the ADR-0019 evidence-advance logic). Staging is silent.

**Cadence — on-load primary.** The reliable review moment is **session start**: the
`MUNINN.md` on-load instruction offers, once, to review any pending candidates
(surfaced as *one* nudge alongside staleness/synthesize offers). This rides an
instruction, **not** a session-end hook — session-end interception is neither
portable nor dependable. `review-candidates` is also invocable on demand. Warm
context isn't required: each candidate carries its grounding and is re-checked
against **source bytes** at review (the ADR-0026 challenger discipline).

**Per candidate:** re-read the cited bytes, then **promote** (`promote-candidate` →
a first-class derived doc, default an **insight**, then `index` + `lint`) or
**decline** (`decline-candidate` → a tombstone, remembered, never deleted). Set the
**honest derivation rung** at promotion (T-107): a single-source deterministic
computation (an age from a DOB) is **`extracted`** — checkable/reproducible, per
ADR-0011 — **not** `synthesis`, which is *cross-source generative* reasoning; staging
leaves the rung unset so the choice is made deliberately here.

**Two promotion targets.** `promote-candidate` writes a **new** derived doc by default;
`--into <doc-id>` **folds** the candidate into an existing derived doc (an age onto
`ent-strudel`) instead. The fold is a **literal insert** (ADR-0035): the Core appends the
candidate's authored block byte-preserving the existing content, unions its new sources
(keeping the target's existing provenance as recorded, so it never masks staleness),
drops the doc to the weakest derivation rung, and consumes the candidate. Fold **adds
surgically**; `regenerate` (ADR-0004) is the complementary **re-coalescing** pass that
tidies an accreted doc — so literal-insert stays within the "regenerable from sources"
precedent. Author candidate bodies to be **self-contained** so they read cleanly in place.
Fold only **timeless** facts (a datum + rule, a historically-dated measurement): a candidate
staged with `--as-of` (a *decaying* result) **can't be folded** — a doc-level `as_of` can't
describe one line of a card — so it promotes as **its own aged doc** instead (T-109,
Core-enforced).

**Never:** writes a candidate into the base unreviewed; deletes a declined candidate
(it is remembered so it won't re-nag); grounds a candidate in a derived doc (no
chaining, enforced at the staging boundary).

### `drift-check [--project <id>] [--older-than <30d>]`

**Intent:** currency with the **world** (T-136). Hash staleness (§I5, L4)
measures the base against itself — a remote system's update is invisible until
someone reaches out. `drift-check` is that reach: a **deliberate, consented
sweep**, never automatic and never a daemon (the base must verify with no
connectivity, forever; ADR-0008).

**Behavior:** the Core enumerates the deterministic worklist (`drift-worklist`:
recoverable, connector-origin sources; **default scope is every eligible source
in the base** — view membership was never designed to scope drift, and a
well-curated landscape global holds no sweepable sources (T-147); `--project`
narrows to that project's members ∪ the global views per the scoped-roster
semantics). Items arrive **oldest contact first**, each carrying its
`last-checked` age and last verdict from prior sweeps (T-145); `--older-than`
(e.g. `30d`) is the budget lever — sweep what is due, not everything, every
time. Whatever the scope, the worklist **discloses `outside_scope` and
`age_filtered`** — what the requested view excluded — so a thin or empty list
is never voiced as "all current" (the T-142 discipline, in a Core return
value). Huginn re-fetches each item through the adapter's own connector (one
bounded retry); the **Core compares** (never a model diff) — via `dedup-check`
for a whole-source capture, via **`anchor-check`** for an anchored partial
capture (ADR-0039: identity first — a `git-blob` anchor is byte-certain against
a remote with **zero fetch** — then containment of the excerpt's chunks;
`upstream-changed-region-intact` reports as *current*, because an unrelated
edit elsewhere in the whole is not staleness). A hash mismatch that
normalizes away (`same-after-newline-normalization`, T-140) is reported as an
artifact in the *same* column, never drift. An **unanchored** excerpt is the
honestly hedged case, and the consented **`anchor`** backfill is offered
(containment verified before anything is stamped); a refusal is handled with
evidence (extract the verbatim chunks, verify presence, then force with the
grounded reason, logged), and the durable repair for a prose-mixed body is a
fenced re-capture-as-version.
One report — *same / changed / unreachable* — is recorded to the append-only
log (`drift-log`) **with per-item verdicts** (`checked: <id>=<verdict>, …` —
counts tally themselves; the segment is what makes per-item ages
reconstructible across sweeps of differing scopes, T-145), which is the
sweep's memory: `status` reads it for a quiet
*"world unchecked since <date>"* mention on load (a mention, never an
auto-run), and unreachable **streaks** are voiced from recent entries.

A **changed** item is offered a re-capture under its same id — versioning then
cascades L4 staleness onto every dependent doc, and `regenerate` heals on the
user's word. **Unreachable is a transport fact, never a drift conclusion**:
after a visible streak the standing never-retry mark is offered (`retier
--no-recoverable`, logged, reversible when the system returns). Cadence belongs
to the user — suggested before load-bearing decisions and periodically for
active bases; meanwhile, answers grounded in connector snapshots voice *"as
captured <date>"* so the reader inherits the epistemic state.

**Never:** runs unasked; concludes drift from a fetch failure; re-captures
without a per-item nod. **Writes:** only the `drift-log` entry; all else is
offers.

## 6. Output conventions

- **Citations** are **linked** (ADR-0038): the stable id (plus span) as the
  label, the doc's readable file as the target —
  `… per [src-vendor-contract §4.2](../sources/src-vendor-contract/source-text.md)`.
  The id stays grep-able exactly as before; the link makes the provenance edge
  visible in any Markdown renderer (Obsidian's graph included). Bare `[src-…]`
  spans in older docs remain valid — upgrade a base with the `relink` op.
- **Assurance** is stated when it isn't full: "grounded in a reference-only
  source — I don't hold the original."
- **Provenance surfaced on request:** any answer can be expanded to "show your
  sources," listing the exact source versions behind it.
- Odin speaks plainly. The average user should never need to know the words
  "Huginn," "invariant," or "frontmatter" to use it well.

## 7. Operational verbs

ADR-0001 named six user-facing verbs; ADR-0004 ratifies two **operational**
verbs that maintain the knowledge base itself. They are invoked the same way
(`odin <verb>`); the distinction is descriptive — user-facing verbs answer "what
do I want from my knowledge?", operational verbs keep the base healthy:

### `init [path]`

Bootstrap a Muninn: write a `muninn.yml` manifest, a tool-neutral `MUNINN.md`
instruction doc (§5.8 of the spec — including the on-load freshness check), and
scaffold the standard layout (`sources/`, `summaries/`, `entities/`,
`concepts/`, `questions/`, `projects/`, `decisions/`, `index.md`, `log.md`).
No-op with a report if the directory is already a Muninn. This is the "initial
setup" ADR-0002 anticipated. **Soft-warn tool-repo guard (ADR-0032):** if the target
is inside ODIN's own checkout, `init` returns `action: "warn"` and writes nothing —
the caller re-runs elsewhere, or passes `--allow-tool-root` to scaffold there anyway
(the consented op proceeds; surface, don't block).

### `regenerate <id>`

Re-derive a stale (or explicitly named) derived doc from its **current** sources,
producing fresh hashes — or retire it. This is the SPEC §6 "Regenerate"
operation as a deliberate, user-invoked act. It is the *only* sanctioned way a
stale doc gets rewritten (§I5), which is why it is explicit and never automatic.

It also **creates a missing summary** — the heal path for an L15 gap (ADR-0013).
First ask the Core for the deterministic facts the heal decision rests on —
`source-status <id>` (tier · **has_bytes** · `recoverable` · `origin.ref`) — then:

- **`has_bytes` true** (the `full`-capture common case, and any source whose bytes
  are still held): derive locally — a **model-read** for a bytes-only source
  (reading the bytes directly), an ordinary derive otherwise. **No fetch.**
- **`has_bytes` false** (a `reference`-tier source whose bytes aren't held — a
  future prune (T-046) or a locator-only capture): if **`recoverable`** and an
  `origin.ref` exists, **`fetch`** the bytes through the connector, `capture` them
  (filling the source), then derive. If **not `recoverable`**, this is an honest
  dead end — surface *"can't regenerate without the bytes; this source is a locator
  only"* and **do not fabricate** a summary from the locator or metadata (I4/§3.4).

The trigger (`has_bytes`) is a deterministic Core fact; the `fetch` and the heal
are the adapter's judgment — the spine/judgment split (ADR-0008).

### `retier <id> --tier full|reference [--reason <why>]`

Deliberately correct a source's **capture tier** (T-134) — the consented repair
for a misjudged tier, which otherwise has no path at all: an identical-byte
re-capture dedups to a no-op, and a hand-edit of `meta.yml` is the forbidden
out-of-band write. The tier describes what the base *holds* (ADR-0003): `full`
when the complete artifact bytes are the canonical record; `reference` when only
a locator and at most a stand-in are held (then `--reason` is required — the
schema's IFF). The op changes ONLY `capture`/`capture_reason`; bytes,
`content_hash`, version, and history are untouched, so every derived doc's
provenance still verifies unchanged. The correction is logged (§I5: a deliberate
operation, never a silent mutation).

### `supersede <id> [--by <replacement-id>] [--reason <why>] [--lift]`

The honest **ending** of a derived document (ADR-0041) — refuted (a
challenge), mis-filed and re-recorded under the right type, or replaced by a
better derivation. Marks `status: superseded` with a one-way pointer
(`superseded_by`, on the ended doc) and/or a reason, stamped `superseded_at`.
**Consented, logged, idempotent, reversible** (`--lift` restores `current` —
the retier precedent: a mistaken mark must have a deliberate path back, or the
hand-edit temptation returns). Touches only these machine fields; provenance
and authored content are untouched, so every re-verification still passes and
`self_hash` (L19) stays valid.

A superseded doc is **closed, not hidden**: it still lints, stays in the index
badged `superseded`, is exempt from L4 staleness (a closed record tracks
nothing), and is skipped by `find` unless `--include-superseded`. Deriving over
a superseded id is refused (no silent resurrection). Scope: derived docs only —
never sources (immutable, versioned; retention is T-046) and never decisions
(their own supersession record). **Sequence: record the replacement first,
then supersede the original pointing at it.** Never a hand-edit; never a
delete.

### `reindex` / `refresh`

(Re)build the **disposable** semantic index that `search` reads — the vector
sidecar (`.odin/`), embedded from the derived layer via a local model (ADR-0027,
T-087). It is **inference**, so its *output* carries no Core guarantee; but the
**refresh is Core-invokable** (ADR-0027, refined 2026-07-09): the deterministic read
path may call the accelerator **write-only** to keep the index current — staleness
*detection* is a model-free hash comparison, only *healing* needs the backend.

**Freshness is therefore automatic.** `retrieve` runs a best-effort `refresh` before
ranking, so a doc ingested since the last embed is searchable on the next retrieve —
no manual step. It re-embeds only what changed, prunes deleted docs, rebuilds on an
embedding-model change, and **never blocks**: backend absent → the docs behind stay
`find`-reachable and the result carries a `warning`. `reindex` (full) and `refresh`
(best-effort, never-raising) remain for a proactive warm; the base loses no guarantee
without a backend, because `find` is the floor and this tier is optional.

### `status [--as-of <today>] [--json]`

The **on-load surface** (ADR-0034). One read-only op the adapter runs when a base is
opened, composing the signals worth raising into a single result the adapter renders
as **one consolidated nudge** (not competing prompts — T-103): `freshness`
(never-linted / fresh / drifted, the ADR-0005 fingerprint vs. the last `lint`),
`stale` (derived docs whose source hash advanced — the L4 condition), `pending_
candidates` (ADR-0033), `captures_since_lint` (feeds the synthesize offer), and
`aged` (time-relative `as_of` docs older than the window — T-104). It is a **pure
function of `(bytes, as_of)`** — `as_of` (today) is injected, never wall-clock — so it
stays faithful and reproducible-given-inputs; it writes nothing. **Time enters here,
never in `lint`:** the linter stays change-based and reproducible (ADR-0005), so the
one time-based signal (`aged`) lives on this session surface, which alone knows
"today". Complements `review` (ADR-0026): `status` surfaces *hash* staleness and
*date* aging deterministically; `review` catches *semantic* drift with the challenger.
Over **MCP** the result is a structured object; on the **CLI**, `--json` emits the same
object (machine-readable) instead of the human summary — the read verbs `find`,
`resolve`, and `list-candidates` take `--json` too (T-106).

**Time-relative facts (T-104).** A fact whose truth depends on *today* (an age,
"overdue", "expired") decays silently — no source changes, so `lint` can't catch it.
The authoring rule: **state the immutable datum + the derivation rule, not the
perishable result** ("DOB 2022-05-04; age = today − DOB", not "4 years old"), so it
recomputes on read and never goes stale. Only a *result* that must be written anyway
carries `as_of: <date>` (`derive --as-of`), which `status` ages on load.

---

## 8. Open questions (for follow-up)

- **Validation gate:** ~~should `ingest`/`ask` commit derived docs immediately
  (regenerable) or hold them for confirmation?~~ **Resolved (ADR-0007).**
  Capture needs no approval gate — initiating `ingest` is consent to copy — and
  derived docs commit immediately (regenerable). Validation is offered, never
  required; visibility (§3.3, ADR-0003 §5) and the sensitive-material confirm
  remain as honesty guards, not gates.
- **`explore` connectors:** ~~which sources Huginn can reach~~ **Resolved
  (ADR-0020).** Connectors are adapter-native MCP; ODIN keeps no registry and no
  auth. The contract only requires that findings arrive as stageable, ingestable
  candidates (`origin.ref` + `recoverable`). Registration/scoping mechanics stay
  adapter-specific (T-038).
- **Batch ingest** ergonomics (a directory or a dozen files at once) and how
  much derivation to do eagerly vs. on demand.
