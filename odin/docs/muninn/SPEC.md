# Muninn — Knowledge Format Specification

**Status:** Frozen — additive-only evolution (ADR-0037)
**Version:** 1.0
**Layer:** Muninn (Memory) — the durable knowledge layer of Project ODIN
**Machine-readable contract:** `contracts/*.schema.json` (the frontmatter shapes
as JSON Schema; see `contracts/README.md` for how the three layers — this SPEC,
the schemas, the linter — divide the contract)
**Aligned with:** ADR-0001 (Odin is the interface), ADR-0002 (one Muninn,
projects as views), ADR-0003 (source-capture policy), ADR-0009 (synthesize /
insights), ADR-0010 (canonical bytes + pluggable extraction), ADR-0011
(generative summaries, model-read sources, derivation provenance), ADR-0012
(retrieval-serving summaries), ADR-0013 (structural completeness — summary per
source)

---

## 0. Purpose and scope

Muninn is the **durable memory** of Project ODIN. Where the Huginn faculty
explores and the synthesis faculty reasons, Muninn *remembers* — it holds
canonical, versioned, inspectable knowledge that accumulates over time. (Odin is
the interface exercising these faculties; ADR-0001.)

This document specifies the **on-disk format** of Muninn: the directory
layout, the document types, the required metadata, and the rules that keep the
knowledge trustworthy. It is deliberately **tool-neutral**. Nothing here
depends on a particular LLM product, editor, or CLI. Muninn is plain Markdown
and links in a Git repository, readable by any human and any reasoning system,
now and in the future.

Muninn is maintained *through* Odin, the system's interface. Odin exercises its
faculties — Huginn for exploration, Muninn for memory — via a tool-specific
**adapter** that reads and writes this format (see ADR-0001). Adapters may be
tool-specific; the format is not. An adapter is correct if and only if the
knowledge it produces satisfies the invariants in §2 and passes the lint rules
in §7. The first reference adapter is specified separately and does not
constrain this document.

---

## 1. The central problem: summary chaining

The pattern Muninn descends from — an LLM incrementally maintaining a wiki of
summaries — has one dangerous failure mode. When summaries are derived from
other summaries, and those from still others, the knowledge base becomes a
lossy compression of itself. Each generation drifts a little further from what
the sources actually said. Nobody can tell which claims are grounded and which
are hallucinated echoes. This is **summary chaining**, and it is the thing
Muninn exists to prevent.

Muninn's answer is structural, not procedural. It is not "please be careful."
It is a set of invariants, enforced by lint, that make chaining *representable
as an error* rather than an accident waiting to happen.

The guiding principle:

> **Source documents stay sources. Summaries reference and link to the sources
> they are derived from. The index and summaries exist to speed retrieval and
> synthesis — never to replace source documents.**

---

## 2. Invariants

These five invariants define a valid Muninn. They are enforced by the linter
(§7). A repository that violates any of them is not a conformant Muninn.

### I1 — Sources are immutable and authoritative

A **source** is the record of ground truth — of any kind: a meeting note, a
PDF, an email, a contract, a recipe, a research paper, as much as an ADR from
another system, an API response, a commit, or a Jira export. Sources are
captured once and never edited in place. If the underlying record changes, a
*new version* of the source is captured; the old one is retained. Authority
always flows from sources.

### I2 — Every derived document declares its provenance

A **derived document** (summary, entity page, concept page, answered question)
must declare, in its frontmatter, the exact sources it was grounded in — by
stable id and content hash. A derived document with no provenance is an error
(an "orphan"). Provenance is a required field, not documentation.

### I3 — Derivation is one-way: source → derived, never derived → derived

A derived document may be grounded **only** in sources, never in other derived
documents. This is the invariant that structurally forbids chaining.

A derived document *may* **link to** another derived document for navigation
(a `see_also` relationship). It may **not** list another derived document as
provenance. Links are for readers; provenance is for grounding. The linter
distinguishes the two and rejects any derived document that appears in another
derived document's `sources` list.

### I4 — Derived documents are regenerable and verifiable

Because a derived document names its sources and their hashes, its claims can
be checked against those sources at any time, and it can be regenerated from
them. Derived content is never the only copy of anything. Deleting every
derived document must lose *speed*, never *knowledge*.

What the format guarantees is **transparency of derivation, not determinism of
it** (ADR-0011). Summaries have always been generative — re-summarizing even a
plain text file yields different words — and a *model-read* of a captured image is
no less regenerable. So the promise is that **how** a document was grounded is
legible (the `derivation` stamp, §5.2) and that the **captured bytes remain the
checkable ground truth**. Softness in a generated conclusion is made visible, not
pretended away.

### I5 — Staleness is flagged, never silently repaired

When a source changes (its content hash no longer matches what a derived
document recorded), every derived document grounded in it is **flagged stale**.
Stale documents are surfaced by lint and left in place for review. They are
**never** silently rewritten. A human or an adapter decides whether and how to
regenerate.

---

## 3. Directory layout

The Muninn **is** the directory a user points Odin at (ADR-0002); it can be
named anything and lives at a user-designated path, separate from ODIN-the-tool.
In Cowork or a launched editor, the working directory itself is the Muninn — the
entries below live at its root, not under a wrapping `muninn/` folder.

```text
<your-muninn>/          # the directory you point Odin at; named anything
├── muninn.yml          # manifest — marks this dir as a Muninn; records format version (§5.7)
├── MUNINN.md           # tool-neutral instruction/schema doc; scaffolded by init (§5.8)
├── inbox/              # OPTIONAL, transient — pre-capture staging: dropped docs + explore preview notes (ADR-0006, 0020); not durable
├── candidates/         # OPTIONAL, transient — reasoning-time staging: emergent grounded inferences awaiting review (ADR-0033); not durable
│   └── declined/       # Fingerprint-keyed decline tombstones + a regenerable declined-index.md; never the base index
├── sources/            # Immutable captured records (I1). Never edited in place.
│   └── <source-id>/
│       ├── source.pdf         # Current canonical BYTES — the source of record (any ext; ADR-0010)
│       ├── source.v1.pdf      # Prior versions' bytes, retained and never overwritten (I1, §4.3)
│       ├── source-text.md     # OPTIONAL non-authoritative extracted-text aid (current version)
│       ├── source-text.v1.md  # Prior versions' text aids, retained in lockstep
│       └── meta.yml           # Origin, hash, capture tier, version ledger (canonical + aid per version)
├── summaries/          # Derived: condensed, source-grounded write-ups
├── entities/           # Derived: one page per entity (a person, place, product, org, system…)
├── concepts/           # Derived: one page per concept or term
├── questions/          # Derived: answered questions of any kind (a policy, a recipe, an API…)
├── insights/           # Derived: cross-source connections found by `synthesize` (ADR-0009)
├── projects/           # Curated *view* pages — "projects" as index over sources (ADR-0002)
│   ├── global.md       # The one canonical always-in-scope view, seeded at init (ADR-0018)
│   └── <project>.md    # Links to member sources/derived docs; a source may be in many
├── decisions/          # The KB owner's own recorded decisions (their ADRs), as knowledge
├── index.md            # Content-oriented catalog. Links to sources first.
└── log.md              # Append-only chronological record of all operations
```

Notes:

- `sources/` is the only immutable tree. Everything else is derived and
  regenerable.
- `inbox/` (optional) is **transient staging** for pre-capture material
  (ADR-0006, extended by ADR-0020). It holds two kinds: **documents dropped** for
  the inbox ingest mode, and **preview-summary notes** that `explore` parks for a
  reference-tier candidate on the one-time inbox opt-in (a candidate with no bytes
  to stage; SKILLS §5). Both are captured into `sources/` on `ingest` and
  cleared. Neither is part of the durable knowledge; both are ignored by the
  invariants and the linter. `explore` writing a preview note here is **not** a
  write to memory — `inbox/` is not the Muninn's durable tree.
- `candidates/` (optional) is the **reasoning-time sibling of `inbox/`** (ADR-0033).
  Where `inbox/` stages *bytes on the way to `sources/`*, `candidates/` stages
  *emergent grounded inferences on the way to a derived doc*: when a reasoning turn
  produces a cited inference of durable value, it is staged here — grounded
  sources-only (I2/I3, un-chainable) — **not** written into the base as an
  `ask`/`synthesize` side effect. A deliberate, batched review **promotes** a
  candidate (it becomes an ordinary derived doc, default an insight) or **declines**
  it. A decline is a **fingerprint-keyed tombstone** under `candidates/declined/`
  (never deleted — so the same inference does not re-stage and re-nag, unless a cited
  source advances and changes the fingerprint). Like `inbox/`, none of
  `candidates/` — including its regenerable `declined-index.md` — is durable
  knowledge; all of it is **ignored by the invariants and the linter**. Staging a
  candidate is **not** a write to memory.
- **Versions live beside the source (§4.3).** A changed source becomes a new
  `source.md`; the prior body is retained as `source.v<N>.md` in the same
  directory, and `meta.yml` records the version ledger. Old bytes are never
  overwritten (I1). Keeping versions as sibling *files* holds the store to ≈2
  levels.
- **Projects are views, not folders (ADR-0002).** A `projects/<name>.md` page
  links to its member sources; a source may belong to many projects. Membership
  lives on the project page, **never on the source** — sources are immutable
  (§I1), so adding one to a project must not edit it.
- **One canonical global view, seeded at init (ADR-0018).** `projects/global.md`
  is the always-in-scope home for cross-cutting context; it ships empty with a new
  Muninn and every scope unions it in (§5.6).
- **Navigate by index, not by depth.** The store stays shallow (≈2 levels).
  Reach any source in a click or two from a project page or `index.md`, never by
  spelunking a deep tree.
- `decisions/` holds decisions the **KB owner** records as knowledge (their own
  ADRs). This is distinct from ODIN-the-tool's ADRs, which live in the tool repo
  (`docs/decisions/`, ADR-0000). ADRs *imported from other systems* are sources
  and live under `sources/`.
- The layout is a starting point, not a cage. New derived categories may be
  added; `sources/` semantics and the invariants may not be relaxed.

---

## 4. Document identity and hashing

### 4.1 Stable ids

Every document has a stable `id` that never changes for the life of the
document. Recommended form: a slug plus a short disambiguator, e.g.
`src-vendor-contract`, `ent-acme-corp`, `con-summary-chaining`. Ids are
referenced by links and by provenance, so they must be stable.

### 4.2 Content hashes

Provenance and staleness depend on a content hash of each **source**.

- The hash is computed over the **canonical captured content** — the *bytes* of
  the source of record (ADR-0010). For a **binary** source (`source.pdf`, …)
  that is the raw file bytes. For a **text** source the canonical content is the
  body of `source.md`/`source.txt`, with any minimal frontmatter excluded (so
  re-tagging does not invalidate what is grounded in it) — and a text body's
  UTF-8 bytes *are* those canonical bytes, so text hashes are unchanged from
  earlier versions. A text body's line endings are **normalized to LF**
  (CRLF/CR → LF) before hashing, so the same text has one content identity across
  platforms; `capture` and `lint` compute this identically (they route through a
  single function), and a pure line-ending change is therefore *not* a new
  version (resolves the §9 hash-normalization question for newlines). The stored
  bytes on disk are still the untouched original; only the *hash* normalizes. The
  extracted-text aid (§5.1) is **never** hashed; it carries no authority.
- Algorithm: SHA-256, recorded as `sha256:<hex>`.
- The hash is stored in the source's `meta.yml` and *copied into* each derived
  document's provenance entry at derivation time. Staleness (I5) is exactly the
  condition: `derived.sources[i].hash != current hash of source[i]`.

### 4.3 Versions on disk

A source's `id` is stable across versions; its **content changes create new
versions** (I1). On disk, within `sources/<source-id>/`:

- `source.<ext>` always holds the **current** version's canonical bytes.
- When new content supersedes it, the prior bytes are retained as
  `source.v<N>.<ext>` (e.g. `source.v1.pdf`) — never overwritten or deleted.
- The extracted-text aid, when present, is versioned **in lockstep**:
  `source-text.md` (current) / `source-text.v<N>.md` (prior). The aid is retained
  rather than re-derived because re-extraction is not guaranteed reproducible —
  AI/OCR extraction is non-deterministic and even deterministic extractors drift
  across versions, so a superseded derived doc must keep the exact text it read
  (ADR-0010).
- `meta.yml` carries a **version ledger**: for each version, its `content_hash`,
  `captured_at`, canonical `file`, optional `text_aid` (+ `extracted_by`), and
  what it `supersedes`. `version` names the current one.

Because derived documents record the specific `hash` they were grounded in, a
summary keeps pointing at the exact version it was derived from even after the
source advances — which is precisely what surfaces as staleness (I5) rather than
silent drift.

### 4.4 Content fingerprint (lint freshness)

A single hash that answers "has anything changed since the last lint?"
(ADR-0005). It is `sha256` over the newline-joined, lexicographically sorted
list of `<id>\t<hash>` for every registered document:

- **sources** contribute their `content_hash` (so re-tagging a source, which
  does not change its body, does not move the fingerprint);
- **derived / project / decision / manifest** docs contribute a hash of their
  file bytes;
- `index.md` and `log.md` are **excluded** — they are regenerable / append-only
  byproducts (including `log.md` would make every lint change the fingerprint).

Lint is **stale** when the current fingerprint differs from the one recorded in
the last lint entry (§5.4). This is a meta-check about lint, not a lint rule.
A git-backed Muninn MAY additionally track the linted commit SHA as a fast path,
but the content fingerprint is authoritative and works for every Muninn.

---

## 5. Document types and frontmatter

All documents are Markdown with YAML frontmatter. Fields marked **required**
are enforced by lint. Unknown fields are permitted (forward-compatible).

### 5.1 Source (`sources/<id>/source.<ext>` [+ `source-text.md`] + `meta.yml`)

`meta.yml`:

```yaml
id: src-vendor-contract         # required, stable
type: source                    # required
origin:                         # required — where this came from
  system: file                  # e.g. file, url, chat, gist, jira, confluence, teams, api, repo
  ref: contracts/acme-msa-2026.pdf   # canonical locator
  captured_by: huginn/claude-code@v1   # optional — <faculty>/<tool>@<version> (ADR-0001)
  recoverable: true             # true when the original bytes are held (set by capture, ADR-0010);
                                # false when the original can't be re-fetched (e.g. chat, ADR-0003)
  upstream_ref: null            # optional (format 1.1, ADR-0039) — for a PARTIAL capture (an
                                # excerpt of a larger whole: one clause of a contract, a section
                                # of a wiki page, a region of a repo file): the WHOLE's clean
                                # locator. Presence declares the excerpt; absence = undeclared,
                                # never "full". The excerpt's own `ref` must stay distinct
                                # (whole + excerpt qualifier — T-045: no two excerpts share a ref)
capture: full                   # required — full | reference (ADR-0003)
capture_reason: null            # required IFF capture: reference — e.g. licensed, too-large, live, private
captured_at: 2026-07-03T00:00:00Z   # required (ISO 8601, UTC)
content_hash: sha256:<hex>          # required — hash of the current version's canonical BYTES (§4.2)
version: 1                          # required — current version number (I1)
history:                            # required — the version ledger (§4.3); one entry per version
  - version: 1
    content_hash: sha256:<hex>
    captured_at: 2026-07-03T00:00:00Z
    file: source.pdf              # canonical file: source.<ext> for current; source.v<N>.<ext> for prior
    text_aid: source-text.md      # optional — the extracted-text aid for this version (§4.3); absent if none
    extracted_by: pypdf@6.14.2    # optional — which extractor produced the aid (present iff text_aid)
    supersedes: null              # version number this replaced, or null
    upstream_identity: null       # optional (format 1.1, ADR-0039) — the upstream WHOLE's content
                                  # identity as of THIS version's read, form-tagged:
                                  # git-blob:<sha1> | sha256:<hex64>. Raw opaque equality, never
                                  # normalized. Anchors describe read events, so they live per-version
    anchored_at: null             # optional (format 1.1, ADR-0039) — present ONLY when the anchor
                                  # was attached later by the consented `anchor` backfill
                                  # (containment-verified first); absent = as of captured_at
tags: [contract, vendor]            # optional
```

Capture tiers (ADR-0003):

- `capture: full` — the source bytes are held as the canonical `source.<ext>`;
  summaries are fully verifiable against them. Text sources use `source.md`; a
  PDF `source.pdf`; and so on. Chat/transcribed sources are `full` (the
  transcription is all there will ever be) with `origin.recoverable: false`.
- `capture: reference` — we hold a locator plus an optional excerpt, not the
  whole source. `capture_reason` is required and states why. A reference capture
  is a weaker source (§7, L10).

**Partial captures and upstream anchors (format 1.1, ADR-0039).** An excerpt of
a larger upstream whole (typically `capture: reference`, with the excerpt as the
held evidence) may carry a machine-checkable **anchor**: `origin.upstream_ref`
(the whole's clean locator; presence *declares* the partial capture) plus a
per-version `history[].upstream_identity` (the whole's content identity as of
that read). This closes the gap that the content hash warrants only the excerpt
bytes while the excerpt's relation to its whole was prose-only. The drift check
is two-tier: **identity** (raw opaque equality; unchanged → the excerpted region
is unchanged, byte-certain, no content fetch for `git-blob`) then **containment**
(are the excerpt's chunks — fenced-block contents when the body has fences, else
the whole body — still present in the fetched whole, LF-canonicalized both sides
per §4.2, leading BOM stripped on the fetched side, no other normalization?).
Verdicts: `upstream-unchanged` · `upstream-changed-region-intact` (an unrelated
edit elsewhere in the whole is not staleness) · `region-drifted` (surface it;
never silently repair, I5) · `unanchored` (no claim — every pre-1.1 base). All
anchor fields are optional; anchoring never gates capture. Existing partial
captures are anchored by the consented `anchor` backfill op, which verifies
containment **before** stamping. One upstream per source: an anchor records a
read event; corroboration across places belongs to derivation (ADR-0009).

**Repo sources (`origin.system: repo`, ADR-0028).** A repository is captured as a
**reference** source whose held text is its **constitution manifest** — a deterministic
enumeration of its intent-bearing surfaces (README, agent contract, ARCHITECTURE / in-repo
ADRs, public contract, identity manifests, orchestration (`docker-compose` for infra repos),
and the top-level *shape*) — **not** its full
tree and **not** `HEAD`. Building the manifest is a faithful transform (`capture-repo`);
the *mental model* an adapter authors from it is `model-read` (ADR-0028 §6). Because the
held text is only the constitution, the source's `content_hash` (§4.2) — and any mental
model grounded in it — changes on a **constitutional amendment** (re-architecture,
repurpose, split/merge, ownership) and stays flat under implementation churn. `HEAD` may
be recorded in the manifest as a human-readable stamp, never as the staleness trigger.
The default surface set is the **AI-free floor** (a constitution builds with no model); an
adapter may **augment** it per repo (ADR-0028 §6) — *choosing* which files matter is judgment
(a frontier model does it well), *hashing* them stays the Core's faithful transform, and the
choice is recorded in the manifest (legible, re-checkable).

**Canonical bytes vs. text aid (ADR-0010).** The canonical `source.<ext>` is the
authoritative record. A **text source** (`source.md`/`source.txt`) *is* its own
text — no aid is written, and its hash covers the body below any minimal
frontmatter. A **binary source** (`source.pdf`, …) stores the original bytes and,
when an extractor is available, a **non-authoritative** `source-text.md` aid —
the plain text that `find`/`ask`/`synthesize` and derivations actually read. If a
format has no registered extractor, the source is captured **bytes-only** (still
conformant); the aid is regenerable convenience, never ground truth, and if bytes
and aid ever disagree the bytes win.

**Opaque sources are understood via a `model-read` summary, not a fabricated aid
(ADR-0011).** A bytes-only source (an image, a scanned PDF) gets **no**
`source-text.md` — fabricating one would conflate deterministic extraction with
interpretation, and the aid slot must stay deterministic-only. Its understanding
is instead carried by its **summary** (§5.2), drafted at ingest by the adapter's
multimodal model and stamped `derivation: model-read`. For such a source the
summary is **load-bearing**: it is the only text handle, so `find` can surface the
source at all. (Every source carries a summary regardless — §5.2, ADR-0013.)

### 5.2 Derived document (summaries, entities, concepts, questions, insights)

```yaml
id: sum-vendor-contract         # required, stable
type: summary                   # required: summary | entity | concept | question | insight
title: Acme vendor contract — key terms  # required — short label
abstract: Payment terms, renewal window, and liability caps in the Acme master agreement.  # optional — one skim line (§5.3)
sources:                        # required, non-empty (I2). Sources only (I3).
  - id: src-vendor-contract
    hash: sha256:<hex>          # hash recorded at derivation time (I5)
    spans:                      # optional but encouraged — where in the source
      - "§4 Payment terms"
derived_at: 2026-07-03T00:10:00Z    # required
derived_by: odin/claude-code@v1     # optional — <faculty>/<tool>@<version> (ADR-0001)
see_also:                       # optional — navigation links to OTHER derived docs
  - ent-acme-corp               # links, NOT provenance (I3)
status: current                 # required: current | stale | draft | superseded (format 1.2, ADR-0041)
superseded_by: null             # optional (format 1.2, ADR-0041) — one-way pointer to the replacement,
                                # recorded on the ENDED doc; must resolve (L21)
superseded_at: null             # optional (format 1.2) — when; required iff status: superseded (L21)
supersede_reason: null          # optional (format 1.2) — why; required when no superseded_by (L21)
derivation: extracted           # optional — HOW this doc was grounded (§ below):
                                #   extracted  (default) — via deterministic text (a text source or its aid)
                                #   model-read — the model read the source bytes directly (image/scan)
                                #   synthesis  — cross-source generative reasoning (an insight, ADR-0009)
as_of: 2026-07-11               # optional — the date a TIME-RELATIVE claim was true (ADR-0034):
                                #   surfaced/aged on-load by `status`, NEVER by lint (which stays
                                #   change-based/reproducible, ADR-0005). Prefer anchoring on the
                                #   immutable datum + rule so none is needed; this is the residual.
tags: [contract, vendor]        # optional
```

**A superseded doc is closed, not hidden (format 1.2, ADR-0041).** `status:
superseded` is the honest ending of a derived doc — refuted (a challenge),
mis-filed and re-recorded, or replaced by a better derivation — written only by
the consented `supersede` operation (reversible with its lift), never a
hand-edit and never a delete. A closed record still lints (provenance never
expires), is exempt from L4 staleness exactly as `stale` is, stays in the index
badged `superseded`, is skipped by `find` unless asked
(`--include-superseded`), and cannot be silently resurrected: deriving over a
superseded id is refused. The pointer is one-way, on the ended doc; the
replacement carries nothing (one fact, recorded once, where the ending
happened).

`abstract` (optional) is a **single human-readable line** describing what this
document is, for skimming. It is authored at derivation time from the *same*
sources this document is grounded in — it rides this document's provenance and is
not a separate derivation, so it cannot chain (I3). It is what `index.md` (and
project pages) project so a reader can scan the catalog without opening every
doc (§5.3). It complements `title` (a short label); it does not replace the body.

**`derivation` (optional, ADR-0011)** records **how** a document was grounded,
orthogonal to the `capture:` tier of its sources (§5.1): `extracted` (default —
grounded in deterministic text, a text source or its aid), `model-read` (the model
read the source bytes directly — an image or scan), or `synthesis` (cross-source
generative reasoning — an `insight`, ADR-0009). It defaults to `extracted`, so
every pre-0.6 document is valid unchanged. It is the integrity signal `ask` rolls
up (weakest link) so a reader knows whether an answer rests on deterministic text
or on a generative read. Lint checks it against this enum (L14); it cannot judge
whether a `model-read` stamp is *honest* — that is the adapter's gate.

**Faceted digest (the summary shape, ADR-0011 / ADR-0012).** A `summary` is an
`abstract` (one skim line) plus a body of a few **universal, labeled facets**:
**What it is** · **Covers** (the questions this source answers) · **Key
specifics** (concrete and source-grounded — "2.3 lb, coccidia positive," not
"discusses health") · **Answers** (direct answers, cited). The skeleton is
**universal** (the same shape fits a contract, a recipe, an image), **concrete**
(filler is the failure mode), and **adapter-guided** (the Core enforces
provenance, never facet quality). The facets are **prose, not a machine `topics:`
field** (ADR-0012). Authoring them in the *reader's* vocabulary — a "from the
shelter" record also saying "adopted" — is the findability discipline that makes
the deterministic `find` succeed (ADR-0012).

**Every source carries a summary (structural completeness, ADR-0013).** Regardless
of capture tier or extraction outcome — text, extracted-binary, or bytes-only —
every source is grounded by **at least one `summary`**, derived at ingest. The
summary is the universal reasoning/retrieval handle; a source with none is stored
but unfindable. This is enforced by lint (**L15**, an error), and a gap is healed
by `regenerate` (which *creates* the missing summary — model-read for a bytes-only
source), never by silently mutating during lint (I5). An un-summarized source is a
**transient/degraded** state to be surfaced and repaired, not an accepted resting
state.

Body conventions for derived documents:

- Claims should be **traceable**. Where a claim rests on a specific source
  span, cite it inline, e.g. `... caps liability at 12 months' fees [src-vendor-contract §4]`.
- Do not restate a source at length. A summary earns its place by
  *condensing and connecting*, and it always points back.
- References to other derived documents use ordinary Markdown links and are
  for the reader's navigation only.

**Multi-source derivation (peers, per-span citation).** A derived document may be
grounded in **several sources at once** — the `sources[]` list is an **unordered
set of peers**; nothing in it implies one source is primary. When a claim rests on
a specific source, the inline citation names *that* source's span, so a
multi-source document attributes each claim to its own ground (e.g. `...A slips
past the freeze [src-1on1-notes §2] while B depends on it [src-projb-plan
§Timeline]`). This resolves the multi-source-derivation question of §9 (ADR-0009)
and is the normal shape of an **`insight`** document.

**`insight`** is a derived document that records a **connection discovered across
sources** — the output of `synthesize` (ADR-0009), Odin's inward-discovery verb.
It is an ordinary derived document in every structural respect (provenance
required, grounded only in sources, regenerable, flags stale when any grounding
source changes), and is typically multi-source per the paragraph above. It exists
so a durable cross-source finding has a home without pretending it is a source.

### 5.3 Index (`index.md`)

A content-oriented catalog, organized by category. It is a map for retrieval,
not a replacement for reading.

The index is a **deterministic projection of document frontmatter** — it is
*computed*, never hand-authored, and carries no content that isn't already in a
document it points to. For each derived document it renders the `title` and, when
present, the one-line `abstract` (§5.2), so a reader skims descriptions rather
than clicking every link. It **links to sources first**, then to the derived
documents that summarize them; a source's line borrows its description from the
summary that covers it (a source→summary join), so the immutable source (§I1) is
never annotated in place. A source not yet summarized shows its `origin` locator —
but that is a **transient/degraded** state the linter flags (L15, ADR-0013), not
an accepted resting state: every source is meant to carry a summary.

**The card-catalogue marker layer (T-056).** Because project pages carry the
human-readable per-scope skim (§5.6; ADR-0017), `index.md` specializes the other
way — a dense catalogue card whose title+abstract stays human-skimmable while a
compact, legible **marker layer** serves the AI librarian (the "understanding for
humans *and* AI" principle, ADR-0011/0014). Each derived-doc line carries, projected
from frontmatter: the **assurance rung** (`extracted` = faithful · `model-read` = an
AI read an opaque source · `synthesis` = a reasoned connection, the weakest rung),
the **corroboration breadth** (`N source(s)`), and — only when true — `stale`
(recorded vs current source hash, the same comparison as L4). A reference-tier source
line is marked `reference`; a `scope: global` project page is marked `global`. The
markers are a **pure deterministic projection** — frontmatter plus the hash
comparison the linter already makes, no authored prose — so the index stays *rebuilt,
not maintained* and can never drift.

Because it is fully regenerable from frontmatter, the index is **rebuilt, not
maintained**: producing it requires no generation and no judgment, so it can be
written mechanically and can never drift from the documents. It is excluded from
the freshness fingerprint (§4.4) as a regenerable byproduct and kept complete by
lint L8. (How the reference adapter divides this deterministic write from the
generative authoring of `abstract` is ADR-0008; the format only requires that the
index be a faithful projection.)

### 5.4 Log (`log.md`)

An append-only, chronological record of every operation: source captures,
derivations, lint passes, staleness events, regenerations. Each entry carries a
timestamp, the operation, the affected document ids, and the acting adapter.
The log is never rewritten, only appended to. It is the audit trail that makes
the whole memory inspectable.

Entries begin with a consistent, greppable prefix. The **lint** entry is
standardized (ADR-0005) so freshness (§4.4) can be read back mechanically:

```
## [2026-07-03] lint | pass | 0 errors 1 warn | fingerprint=sha256:ab12…
```

`grep "] lint |" log.md | tail -1` yields the last lint's result and the
fingerprint of the state it checked.

### 5.5 Decision / ADR (`decisions/<id>.md`)

Decisions the **knowledge base owner** records as durable knowledge — their own
architecture (or personal, or business) decisions — in a standard ADR shape
(context, decision, consequences, status). These are authored, not derived, so
they do not require a `sources` list, but they may cite sources as evidence.
(Distinct from ODIN-the-tool's own ADRs, which live in the tool repo per
ADR-0000.)

```yaml
id: dec-cat-adoption-after-vaccines   # required, stable (dec-<slug>)
type: decision                        # required
title: Adopt a cat only once vaccines are current   # required
status: accepted                      # required: proposed | accepted (L17)
date: 2026-07-06                       # required (ISO 8601) — the date the decision was made
evidence:                              # optional — informing sources (LINKS, not provenance)
  - id: src-strudel-vaccinations       #   each entry: a source id …
    version: 1                          #   … + the source VERSION seen at record time (not a hash)
  - id: src-strudel-adoption-contract
    version: 1
tags: []                               # optional
```

**Authored, not derived — the contract (ADR-0019).** A decision is the owner's own
judgment, written by Odin **only on explicit request** (never as a `synthesize`/
`ask` side effect). It carries **no `sources` provenance**: `evidence` is a list of
**links** (source id + the `version` seen when the decision was recorded — a
hash-free change baseline), semantically like a project's `members`, *not* a
grounding hash. So a decision **can never chain** (I2/I3 do not apply — there is no
provenance) and is **never L4-stale**. When a cited source's `version` later
advances past the recorded one, lint emits a **soft informational note** (L17 warn,
never an error): the owner decides whether to revisit — a judgment made at a point
in time does not become "wrong" because its basis moved.

**Revision is append-only amend-in-place, not supersession.** A decision is revised
by prepending a dated `**AMENDED (YYYY-MM-DD):**` banner to its body; the prior text
is **never deleted or overwritten** (Core-enforced), and `date` stays fixed at the
original decision. The whole history of one decision stays in one skimmable file —
deliberately lighter than ODIN-the-tool's ADR-0000 immutable-by-supersession model,
which governs a shared codebase. A genuinely *different* decision is simply a new
`dec-…` doc; Muninn decisions carry no `supersedes`/`superseded_by` links.

Decisions are **retrieved** by `find --type decision` (the `why` verb). They are
**written** by the Core `record-decision` op — `derive --type decision` is
intentionally *not* a path (decisions are authored, and `derive` only writes
grounded, hashed, derived docs).

### 5.6 Project (`projects/<name>.md`)

A curated **view** over the knowledge base (ADR-0002): a human- and
AI-legible page that gathers the sources and derived docs relevant to a project,
life-area, or theme. A source may appear in many projects.

```yaml
id: prj-marketing-q3            # required, stable
type: project                   # required
title: Marketing — Q3           # required
description: Q3 go-to-market working set   # optional — a plain maintainer LABEL (not a sourced claim)
members:                        # required — ids this project gathers (links, not provenance)
  - src-competitor-teardown
  - sum-competitor-teardown
scope: project                  # optional — project (default) | global
maintained_by: odin/claude-code@v1   # optional — <faculty>/<tool>@<version>
tags: [marketing]               # optional
```

**The page body is a deterministic projection, not authored prose (ADR-0017).**
Each member link renders the member's *own* title/abstract — a source borrows its
covering summary's title (the same source→summary join the index uses) — so the
page is a **self-describing, skimmable view**, and the per-scope skim surface that
keeps the global `index.md` from having to carry every summary. `title` and the
optional `description` are plain maintainer **labels** (same status as a title —
never read as a sourced claim). A project page carries **no generative project-
level prose**: anything worth saying about *why* a set of sources coheres is an
`insight` (ADR-0009) — grounded and cited — never editorial text smuggled onto a
view. Nothing ungrounded ever enters a project page.

A project is a view, not a container: **membership lives here, never on the
member** — sources stay immutable (§I1). Listing an id under `members` is a
*link* for navigation, not provenance (it does not ground anything and cannot
cause chaining). `members` is required but **may be empty** — an empty view is
valid (e.g. a freshly-seeded hub). Project pages are regenerable/reorganizable at
will.

**Always-in-scope pointer.** A non-global project page also renders a computed
**"Always in scope"** section linking to the global view (below) — a *reference*
to the page, not a copy of its members, so the global layer stays a single source
of truth and the human skimming this page in isolation still sees it applies here.
Like the rest of the body it is a deterministic projection, not authored prose.
Because it is projected at **write time**, a page written before a *second*
`scope: global` view was added shows a stale pointer until re-rendered; the
regenerate-class **`reproject`** op (T-057) re-renders every project page from
current state — refreshing the pointer (and each member's projected blurb) — and
seeds the canonical `global` hub on a base predating it. `resolve_scope` is always
correct regardless (it unions every global view live), so this is *page-layer*
consistency, never a retrieval guarantee.

**`scope: global`** marks a view whose members are **cross-cutting** — context
that bears on *every* project, not one (an organizational constraint, a company
business model, a personal standing commitment). `synthesize` (ADR-0009) **unions
every global-scope view into its working set regardless of the requested scope**,
so project-scoped discovery still sees the constraints that cut across everything.
Global is a property of the **view**, not the source — the immutable source is
never marked (§I1, ADR-0002); a source becomes "global" only by membership in a
global view. `scope` defaults to `project` when absent.

**One canonical global view (ADR-0018).** `init` seeds exactly one global view,
`projects/global.md` (id `global`), as an empty placeholder — *the* home for
cross-cutting context, discoverable from the moment a Muninn is created. Standing
context is added as **members of this one hub**, not as new global pages; because
the hub's id is fixed at `init`, every project page's always-in-scope pointer
references a page that already exists, so it never drifts. Retrieval stays
defensive — `resolve_scope` unions *every* `scope: global` page, so a hand-authored
second global view is still honored, it simply forfeits the pointer's no-drift
guarantee.

**The resource-landscape layer (ADR-0028, extending ADR-0021 §1c).** The global view is
also the home for **landscape docs** — ordinary grounded derived docs (**no new doc
type**) that describe the organization's *resource topology*: what systems, connectors,
and repositories exist and **what each is *for*** ("the SRE knowledge base holds
runbooks"; "vendor comms live in Slack #vendor"). A **repo mental model** (a §5.1 repo
source → `model-read` summary) is a landscape entry too — it describes a codebase's
identity. The layer is **descriptive knowledge, not a registry** (the ADR-0021 §5 bright
line): nothing operational depends on it, Odin holds no credentials and authorizes
nothing, and a vanished connector leaves a *stale fact*, not a broken dependency. Because
it lives in the always-unioned global view, it is what Huginn's **survey** reads before
reaching (ADR-0021 §1c) — turning "explore *where?*" from a guess into a grounded route —
and what `ask`/`synthesize` consult when memory is thin and they offer to dispatch Huginn.
The **connector projection** (the `connectors` op, T-070) computes the distinct connectors
these docs reference — a deterministic view like `index.md`, the *skeleton* to the landscape
docs' authored *flesh*. It unions two grounded, faithful inputs over `scope: global` members
(no inference, no registry): **(a)** the `origin.{system, ref}` of **source** members — the
connectors your durable knowledge came *from* (a repo mental model's source contributes
`repo:<url>` for free; local `file`/`chat` origins are not connectors), and **(b)** an
optional **`connectors: [{system, ref}]`** field on a **derived** landscape doc — a connector
it *asserts* but hasn't ingested from ("contracts live in Drive"). Like any projection, it
goes stale with its inputs and is never a durable registry (ADR-0021 §5).

### 5.7 Manifest (`muninn.yml`)

A small file at the Muninn root that **marks the directory as a Muninn** and
records which format version it conforms to (ADR-0002). It is how Odin, pointed
at a directory, recognizes a valid knowledge base and knows which rules apply.

```yaml
muninn: 1.0                     # required — Muninn format version this KB conforms to
name: My Knowledge Base         # optional — human-friendly name
created_at: 2026-07-03T00:00:00Z    # optional
```

The manifest is authored/maintained, carries no provenance, and is the one file
Odin may rely on to distinguish a Muninn from an ordinary folder.

**Versions 0.2 → 0.5 are backward-compatible** — each release only *adds* optional
capability, never removes or tightens: 0.3 added the optional `abstract` field
(§5.2) and stated the index projection (§5.3); 0.4 adds the `insight` derived type
(§5.2), the optional `scope` field on views (§5.6), and records the multi-source
resolution (§9); 0.5 generalizes a source's canonical file from `source.md` to
`source.<ext>` (original bytes as the record), adds the optional `source-text.md`
extracted-text aid and the ledger's `text_aid`/`extracted_by` fields, and has
`capture` write `origin.recoverable` (ADR-0010). A pre-0.5 text Muninn — all
`source.md`, no aids — remains conformant unchanged. Adopting the new capabilities
is opt-in.

**1.0 is frozen (ADR-0037); 1.1 is additive under that freeze (ADR-0039):** it
adds only the *optional* upstream-anchor fields (`origin.upstream_ref`,
`history[].upstream_identity` / `anchored_at`, §5.1), the `anchor` /
`anchor-check` operations (§6), and the **opt-in** L20 (§7). To a 1.0 reader the
new fields are §5-permitted unknown fields: every 1.0-conformant base remains
conformant, readable, and verifiable, unchanged, and a base that never anchors
never changes at all.

**1.2 is additive the same way (ADR-0041):** the *optional* supersession fields
(`superseded_by` / `superseded_at` / `supersede_reason`, §5.2), one new derived
`status` value (`superseded`), the `supersede` operation (§6), and L21 (§7,
always-on but unfailable by any pre-1.2 base). A base that never supersedes
never changes at all.

**1.0 is the freeze, not a capability (ADR-0037).** 0.6 → 1.0 adds no new format
requirement; it makes the additive pattern above the *promise*. From 1.0 the
format evolves **additively only** — new optional fields, new enum values, new
document types, opt-in capabilities gated by this manifest version — and never
removes, renames, re-means, or tightens. Every 1.0-conformant Muninn remains
conformant, readable, and verifiable under every 1.x rule set, unchanged. A base
adopts new capability by opting in and bumping its own `muninn:` version; it is
never migrated implicitly. Anything that cannot keep that promise is a 2.0 with
its own ADR and an explicit migration story.

### 5.8 Instructions (`MUNINN.md`)

A tool-neutral **instruction / schema document** at the Muninn root, scaffolded
by `init` (ADR-0005). It is the descendant of the "schema" file in the pattern
Muninn comes from — the document that makes an assistant a disciplined Odin
rather than a generic chatbot. It records the KB's conventions and the behaviors
Odin should follow, including the **on-load freshness check**: recompute the
content fingerprint (§4.4) and, if it differs from the last lint entry, tell the
user the base changed since it was last checked and suggest `odin lint`.

`MUNINN.md` is authored/maintained and carries no provenance. A specific adapter
may bridge its own convention to it (e.g. a Claude Code `CLAUDE.md` that points
at `MUNINN.md`), but `MUNINN.md` is the tool-neutral source.

---

## 6. Operations (adapter contract)

Adapters implement these operations. The format does not mandate *how*; it
mandates that the result conforms.

- **Capture** (Huginn): fetch a record, **hash first** to dedup against existing
  sources, then write an immutable source under `sources/` — choosing `full` or
  `reference` tier (ADR-0003) — record its `content_hash`, and append to
  `log.md`. Same content ⇒ one source with multiple origins; changed content ⇒ a
  new version that `supersedes` the prior (I1). Changed content under a **new id**
  whose `origin.ref` already belongs to a captured source is **refused** — the
  deterministic rung of the T-045 identity ladder: a re-download at a known
  locator is that source's next version, and capturing it as a fresh source would
  silently split the lineage (versioning and staleness stop propagating). The
  caller captures under the matching id to version it, or explicitly declares a
  new lineage (`--force-new`), which is recorded in `log.md` — **no silent merges
  or splits**. Capture is visible to the user.
- **Dedup-check** (Huginn, preview): a **dry-run** of Capture's dedup — hash a
  candidate (or, for a reference-tier candidate with no bytes, match its
  `origin.ref`) against existing sources and report *already-captured / changed /
  new* **without writing** (no source, no version, no `log.md` entry). A
  bytes-carrying candidate whose hash misses but whose `origin.ref` matches an
  existing source reports *changed* (method `origin.ref`) — the same locator rung
  Capture enforces. These are the deterministic dedup rungs `explore` previews on
  before offering `ingest` (ADR-0020); the fuzzy similarity rung is agentic
  (adapter-side, proposes only), and **no AI computes the hash**.
- **Anchor-check** (read-only, ADR-0039): the two-tier drift check of one
  anchored partial capture against a **fetched** current upstream (the fetch is
  the adapter's consented reach, T-136; the comparison is the Core's faithful
  transform). Returns the verdicts of §5.1's partial-capture block.
- **Anchor** (consented backfill, ADR-0039): attach an upstream anchor to an
  *existing* partial capture — containment is verified **first** and the anchor
  is stamped only when the held excerpt satisfies it (a failure is reported,
  not stamped; a declared `force` requires a reason and is logged). Bytes,
  `content_hash`, `version`, and history structure are untouched, so all
  provenance verifies unchanged. Idempotent; the migration companion of the
  format-1.1 fields (the `relink`/`stamp` precedent).
- **Source-status** (read-only): report a source's deterministic facts — tier,
  version, whether its **current canonical bytes are held** (`has_bytes`),
  `recoverable`, and `origin.ref`. Writes nothing. This is the ground truth the
  adapter's fetch / self-heal decisions rest on: `has_bytes: false` is the trigger
  for `regenerate`'s re-fetch limb (below); the split keeps *detecting* the gap
  deterministic (Core) while *fetching* and healing stay adapter judgment (ADR-0008).
- **Derive** (Odin): read one or more **sources**, write or update a derived
  document with a complete `sources` provenance list copied from those sources'
  current hashes (I2, I3), update `index.md`, append to `log.md`.
- **Supersede** (consented, ADR-0041): mark a derived document ended —
  `status: superseded` + `superseded_by` and/or `supersede_reason`, stamped
  `superseded_at`; reversible (lift). Touches only these machine fields;
  provenance and authored content are untouched, so everything still verifies.
  Derived docs only (sources are immutable + versioned; decisions carry their
  own supersession record).
- **Lint**: run the checks in §7, report violations, and flag staleness. The
  pure checker is **read-only** and reports the content fingerprint (§4.4); the
  `lint` *skill* flags `status: stale` and appends the standardized lint entry
  to `log.md` (ADR-0005). Lint never edits derived content (I5).
- **Regenerate**: for a stale document, re-derive from current sources
  (producing fresh hashes), or **create a missing** summary for a source (ADR-0013),
  or retire it. Always a deliberate operation. When the source's bytes are not held
  (`source-status` reports `has_bytes: false`) and the origin is `recoverable`,
  Huginn **fetches** the bytes via `origin.ref` before deriving; if not
  `recoverable`, the gap is surfaced honestly, never healed from the locator alone.

---

## 7. Lint rules (enforcement)

The linter is the guardian of the invariants. Rules, with the invariant each
protects:

| Rule | Checks | Enforces |
|------|--------|----------|
| L1 orphan | Every derived doc has a non-empty `sources` list | I2 |
| L2 no-chaining | No id in any `sources` list resolves to a derived doc | I3 |
| L3 source-exists | Every `sources[i].id` resolves to a real source | I2 |
| L4 hash-current | For each `sources[i]`, recorded hash == source's current hash; else flag `stale` | I5 |
| L5 immutable-source | No source's `content_hash` changed without a version bump + `supersedes` | I1 |
| L6 id-unique | All `id`s are unique across the repository | 4.1 |
| L7 link-resolves | Every `see_also` / Markdown cross-link resolves to a real doc | — |
| L8 index-complete | Every document appears in `index.md`; index has no dangling entries | 5.3 |
| L9 required-fields | All **required** frontmatter fields present and well-formed | §5 |
| L10 reference-assurance | Flag (warn) any derived doc whose `sources` are *all* `capture: reference` | ADR-0003 |
| L11 project-members-resolve | Every source/doc a `projects/` page links to resolves | ADR-0002 |
| L12 manifest-valid | A `muninn.yml` exists at the root with a `muninn:` format version | ADR-0002, §5.7 |
| L13 version-ledger | Each source's `meta.yml` `history` covers every `source*.md` file present, and vice versa | §4.3 |
| L14 derivation-enum | If `derivation` is present, its value is one of `extracted` \| `model-read` \| `synthesis` | §5.2, ADR-0011 |
| L15 source-has-summary | Every `source` is grounded by ≥1 derived `summary` (**error**; healed by `regenerate`, not by lint) | §5.2, ADR-0013 |
| L16 scope-enum | If a `projects/` page's `scope` is present, its value is one of `project` \| `global` | §5.6, ADR-0002 |
| L17 decision-integrity | A `decisions/` doc has `id`/`type`/`title`/`status`/`date`, `status` ∈ `proposed` \| `accepted`, and every `evidence` id resolves to a real source (**error**); an evidence source whose `version` has advanced past the recorded one is a **soft note** (warn), never stale | §5.5, ADR-0019 |
| L18 summary-compression | A `summary`'s readable length (abstract + body) is **not** greater than its source(s)' text — a summary *compresses* (**warn**); enrich for findability, not length. Exempt: sources with no text layer (a `model-read` of an opaque image) and already-terse sources below a small floor (a short table/note is *already* summary-length) | §5.2, I4 |
| L19 derived-integrity | A derived doc's `self_hash` matches its authored content (title + abstract + body), else it was edited **out of band** (**error**, only when enforced). The Core **always stamps** `self_hash` (accurate metadata every write, incl. `regenerate`, keeps current); the **opt-in** flag `integrity.derived_self_hash: true` governs only whether L19 **enforces** — so enabling it is instant and complete, and never false-positives on a legit regenerate. The one in-format signal for a hand-edited *derived* doc (sources are covered by L5). A doc with no `self_hash` (predates the feature) is skipped; `stamp` backfills them. Honesty tooling, not tamper-proofing (an adversary rewrites the hash too) | ADR-0029, I5 |
| L20 anchor-coherence | **Opt-in** (`integrity.upstream_anchors: true`, the L19 posture): a partial capture's anchor fields cohere — `upstream_identity` matches a known form (`git-blob:<sha1>` \| `sha256:<hex64>`) and implies `origin.upstream_ref`; `anchored_at` implies an identity; a **declared** partial capture (`upstream_ref` present) is anchored at its current version (**error**, only when enforced). Off by default: a base with no anchor fields anywhere is simply *undeclared* — pre-1.1 bases never fail | ADR-0039, I5 |
| L21 supersession-coherence | **Always-on** (no existing base carries the fields, so none can fail it): `superseded_by` resolves and is not the doc itself; the supersession fields appear only with `status: superseded`; a superseded doc carries `superseded_at` and a successor and/or a reason (**error**) | ADR-0041, I5 |

L2 is the heart of the specification. It is the rule that makes summary
chaining impossible to introduce without the linter rejecting it. L10 keeps a
different kind of honesty: it surfaces knowledge resting on sources Muninn does
not hold in full, rather than letting it pass as fully grounded. L15 keeps a third:
it refuses to let a source sit captured-but-unfindable — every source must carry a
summary. Like all rules, L15 only **detects**; the linter never repairs. The gap
is healed by the deliberate `regenerate` operation (ADR-0004/0013), which *creates*
the missing summary (a model-read for a bytes-only source) — so the error is a
one-step path to conformance, not a dead end.

---

## 8. What Muninn is not

- **Not a cache of model outputs.** Derived documents are grounded artifacts
  with provenance, not disposable generations.
- **Not the source of truth.** Sources are. If a summary and its source
  disagree, the source wins and the summary is stale.
- **Not tool-coupled.** Any tool that can read and write Markdown and compute
  a hash can maintain a Muninn. The reference adapter is one implementation,
  not the definition.

---

## 9. Open questions (for follow-up ADRs)

- ~~Span citation format~~ — **resolved (ADR-0038):** freeform **linked
  citations** — the stable id (optionally plus a span note) as the Markdown
  link label, the cited doc's readable file as the target. Convention, not
  format: no lint rule parses spans, and bare `[src-…]` spans remain valid
  (the `relink` maintenance op upgrades them). Structured ranges/anchors stay
  future work if a measured need appears.
- Whether entity/concept pages need a typed relationship graph beyond
  `see_also`.
- ~~Multi-source derivation~~ — **resolved (ADR-0009):** the `sources[]` list is an
  unordered set of peers (no primacy), with claims attributed per span (§5.2).
- Hashing normalization (whitespace, encoding) to keep hashes stable across
  trivial capture differences.

These are deliberately left open here and will be resolved in `decisions/`.
```
