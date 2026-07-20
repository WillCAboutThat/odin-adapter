<!-- GENERATED FILE - do not edit by hand.
     Rendered from the op registries (muninn_core.OPS + muninn_semantic.OPS)
     by scripts/gen_verb_reference.py (T-149). The same tables generate the
     CLI and the MCP schemas (T-113), so this page cannot drift from either.
     tests/test_verbs_reference_generated.py enforces freshness. -->

# The ops - every switch, every default (generated)

One entry per op, straight from the registry. The CLI form is
`odin <verb> ...` (or `python tools/muninn_core.py <verb> ...`); the MCP tool
is the same op with underscores (`odin_<verb>`), same-named parameters, and
byte-identical behavior (ADR-0022). Every op takes `<root>` (the Muninn
directory) first; it is omitted from the tables below. Defaults and behavior
are stated in each description - what you read here is exactly what the CLI
`--help` and the MCP schema carry.

Zero-setup invocation: every entry point carries a PEP-723 header, so
`uv run --script tools/muninn_core.py <verb> ...` provisions Python + pyyaml
automatically - no pip, no venv (T-150). With a Python that has pyyaml,
plain `python3` works identically.

## Deterministic Core (`muninn_core`)

### `init` · MCP `odin_init`

Scaffold a new Muninn (manifest, layout, index, the canonical global view). No-op if one already exists.

| Switch | | What it does |
|---|---|---|
| `--name <value>` | optional | Display name (defaults to the dir name). |
| `--allow-tool-root` | optional · CLI-only | scaffold even if the target is inside ODIN's own checkout (overrides the soft-warn tool-repo guard; e.g. dogfooding) |

### `capture` · MCP `odin_capture`

Capture a source (immutable, provenance-bearing). Provide `body` for a text source, OR `source_file` for original bytes (PDF/image/…; a text aid is extracted per ADR-0010). Byte-identical content dedups; changed bytes of an existing id make a new version. Changed bytes under a NEW id whose origin_ref already belongs to a captured source are refused (a silent lineage split, T-045) — capture under the matching id to version it, or set force_new to declare the split. Sources are authoritative and never chained from.

| Switch | | What it does |
|---|---|---|
| `<id>` | required | Stable source id (e.g. src-…). |
| `--origin-system <value>` | required | Where it came from (file, url, connector…). |
| `--origin-ref <value>` | required | The locator within that system (filename, URL, …). |
| `--body <value>` | optional | Text-source content. Mutually exclusive with source_file. |
| `--source-file <value>` | optional | Path to a file whose ORIGINAL BYTES are the source. |
| `--filename <value>` | optional | Canonical filename hint (defaults to source_file's name). |
| `--tier <value>` | optional | full (copy held) or reference (locator only). One of: full, reference. |
| `--reason <value>` | optional | Required for a reference-tier capture (ADR-0003). |
| `--recoverable` | optional | Is the original re-fetchable via origin.ref? (self-heal, T-066). |
| `--captured-by <value>` | optional | Producer of this record, <faculty>/<tool>@<version> (ADR-0001). Mandatory disclosure when the body is a model rendering rather than the source's own data (T-131). |
| `--force-new` | optional | Deliberately start a NEW lineage although origin_ref matches an existing source (the split is logged; T-045). |
| `--upstream-ref <value>` | optional | For a PARTIAL capture (an excerpt of a larger whole): the whole's clean locator (ADR-0039). Presence declares the source an excerpt; origin_ref itself must stay a distinct, excerpt-qualified locator (T-045). |
| `--upstream-identity <value>` | optional | The whole's content identity as of this read — git-blob:<sha1> \| sha256:<hex64> — recorded per-version; makes drift-check exact for this excerpt (ADR-0039). Requires upstream_ref. |

### `dedup-check` · MCP `odin_dedup_check`

Dry-run dedup preview: report already-captured / changed / new for a candidate WITHOUT writing (explore preview, ADR-0020). Give `source_file` (content-hash rung) or `origin_ref` (locator rung for reference-tier).

| Switch | | What it does |
|---|---|---|
| `--id <value>` | optional | Candidate's intended id (enables changed-vs-new). |
| `--source-file <value>` | optional | Candidate file whose bytes to hash. |
| `--filename <value>` | optional | Canonical filename hint. |
| `--origin-ref <value>` | optional | Locator to match when no bytes are held. |

### `source-status` · MCP `odin_source_status`

Read-only deterministic facts about a source (tier, version, whether bytes are held, recoverable, origin.ref) — the ground truth a fetch/self-heal decision rests on (T-066).

| Switch | | What it does |
|---|---|---|
| `<id>` | required | The source id. |

### `retier` · MCP `odin_retier`

Correct a source's capture tier. The tier describes what the base HOLDS (ADR-0003): full = the complete artifact bytes are the canonical record (even when the upstream record is live — evolution is versioning's job); reference = only a locator and at most a stand-in are held (requires reason). Changes ONLY capture/capture_reason; bytes, hash, and history untouched, so all provenance still verifies. Logged. Never hand-edit meta.yml.

| Switch | | What it does |
|---|---|---|
| `<id>` | required | The source id. |
| `--tier <value>` | optional | The corrected tier. One of: full, reference. |
| `--reason <value>` | optional | capture_reason — required when tier is reference (ADR-0003 IFF). |
| `--recoverable` | optional | Correct origin.recoverable — False is the standing never-retry mark the drift-check sweep honors (T-136); flip True when the system returns. |

### `anchor-check` · MCP `odin_anchor_check`

Check one anchored partial capture against its fetched upstream whole (ADR-0039). Tier 1: recorded vs current upstream_identity, raw opaque equality — equal → upstream-unchanged (byte-certain, region included). Tier 2 on mismatch: are the excerpt's chunks still in the fetched text? All → upstream-changed-region-intact; any missing → region-drifted (offer re-locate / re-capture-as-version). No anchor → unanchored. Read-only; fetching the upstream is the adapter's consented reach (T-136).

| Switch | | What it does |
|---|---|---|
| `<id>` | required | Stable doc/source id. |
| `--upstream-file <value>` | required | Path to the FETCHED current upstream whole (the adapter fetches; the Core compares). |

### `anchor` · MCP `odin_anchor`

Attach an upstream anchor to an EXISTING partial capture — the ADR-0039 backfill (relink/stamp precedent). Runs the containment check FIRST and stamps origin.upstream_ref + the current version's upstream_identity/anchored_at only when the held excerpt is contained in the supplied upstream; a failure is reported, not stamped (force + reason to overrule, logged). Bytes, content_hash, version untouched — provenance verifies unchanged. Idempotent.

| Switch | | What it does |
|---|---|---|
| `<id>` | required | Stable doc/source id. |
| `--upstream-ref <value>` | required | Clean locator of the whole this excerpt was read from. |
| `--upstream-file <value>` | required | Path to the fetched current upstream whole to verify against and identify. |
| `--form <value>` | optional | Identity form to stamp (git-blob for git-backed upstreams: comparable against a remote with no fetch). One of: sha256, git-blob. |
| `--force` | optional | Stamp past a failed containment check (requires reason; logged). |
| `--reason <value>` | optional | Why a forced anchor is honest (e.g. the missing chunks are the capture's own disclosure prose). |

### `drift-worklist` · MCP `odin_drift_worklist`

The drift-check sweep's deterministic worklist: recoverable, connector-origin sources (local file/chat/inbox never drift remotely). Default scope is EVERY eligible source in the base (T-147); `project` narrows to that project's members plus the global views (T-128). The result always discloses `outside_scope` — eligible sources the requested scope excluded — so a thin list never reads as 'all current'. Items carry last_checked/last_verdict joined from the drift log and sort oldest contact first (T-145); `older_than` (e.g. '30d') keeps only items due a check, counting what it drops in `age_filtered`. Read-only: the fetch/compare/re-capture that follow are adapter orchestration over fetch + dedup-check + capture, always consented, never a daemon.

| Switch | | What it does |
|---|---|---|
| `--project <value>` | optional | Narrow to this project's members ∪ the global views (T-128). |
| `--older-than <value>` | optional | Keep only items whose last contact (capture or check) is older than this — <N>[d\|w\|h], e.g. '30d'. The budget lever. |
| `--all` | optional | Deprecated no-op (T-147): the full sweep is now the default. |

### `drift-log` · MCP `odin_drift_log`

Append the drift-check outcome (same/changed/unreachable counts + optional detail) to log.md — status reads the latest entry for its quiet 'world last checked' line, and the adapter reads recent entries to voice unreachable streaks before offering the never-retry flip. Pass `checked` with one <id>=<verdict> per item swept (T-145) — it is what makes per-item last-checked ages reconstructible; counts are tallied from it when omitted.

| Switch | | What it does |
|---|---|---|
| `--same <value>` | optional | Unchanged count (tallied from `checked` when omitted). |
| `--changed <value>` | optional | Changed count (tallied from `checked` when omitted). |
| `--unreachable <value>` | optional | Unreachable count (tallied from `checked` when omitted). |
| `--checked <value> (repeatable)` | optional | Per-item verdicts, one <id>=<verdict> each (same \| changed \| unreachable \| a same-* variant), e.g. 'src-x=same'. |
| `--detail <value>` | optional | Optional ids/notes, e.g. 'unreachable: src-x (2nd consecutive)'. |

### `derive` · MCP `odin_derive`

Write a derived doc (summary/entity/concept/question/insight) grounded ONLY in sources. Core copies each source's current hash into provenance; a provenance id that is not a real source is rejected (I3, no chaining). `body` is the adapter-authored content. For an INSIGHT, quoted spans are containment-verified (T-153): a double-quoted span ≥15 chars on a line citing a provenance source must appear in that source's text or the write is refused — quote sources exactly, never from a summary's paraphrase. A `question` doc may be answered or explicitly OPEN (abstract leads 'OPEN — ', T-154); regenerate re-derives it when answered.

| Switch | | What it does |
|---|---|---|
| `<id>` | required | Stable derived-doc id. |
| `--body <value>` | required | The document body (adapter judgment). |
| `--source <value> (repeatable)` | required | Grounding source ids (≥1). Must be sources, never derived docs. |
| `--title <value>` | required | Doc title. |
| `--abstract <value>` | optional | Skimmable abstract. |
| `--type <value>` | optional | Derived doc type. One of: summary, entity, concept, question, insight. |
| `--derivation <value>` | optional | How it was derived (e.g. synthesis) — sets the integrity rung. One of: extracted, model-read, synthesis. |
| `--connector <value> (repeatable)` | optional | Connectors this landscape doc references but hasn't ingested from — [{system, ref}] (ADR-0021 §2 / T-070). |
| `--as-of <value>` | optional | ISO date a TIME-RELATIVE claim was true — surfaced/aged on-load by `status`, never by lint (ADR-0034). Prefer anchoring on the immutable datum + rule; this is the residual. |

### `stage-candidate` · MCP `odin_stage_candidate`

Stage an emergent grounded inference for later BATCHED review (ADR-0033). NOT admitted to the base — grounded sources-only (no chaining), deduped vs pending and vs declined tombstones (a sticky decline won't re-nag unless a cited source advances).

| Switch | | What it does |
|---|---|---|
| `<id>` | required | Candidate id (must start 'cand-'). |
| `--body <value>` | required | The grounded inference, cited to its sources. |
| `--source <value> (repeatable)` | required | Grounding source ids (≥1). Sources only — never a derived doc. |
| `--title <value>` | required | Title. |
| `--abstract <value>` | optional | Skimmable abstract. |
| `--proposed-kind <value>` | optional | What it becomes on promote. One of: summary, entity, concept, question, insight. |
| `--derivation <value>` | optional | The honest rung — set it, don't presume: a single-source deterministic computation (an age) is `extracted`, not `synthesis` (cross-source generative). Unset → the reviewer sets it at promotion (T-107). One of: extracted, model-read, synthesis. |
| `--as-of <value>` | optional | ISO date IF this candidate states a TIME-RELATIVE result — aged on-load once promoted as its OWN doc; such a candidate can't be folded (T-109). Prefer the datum + rule (no as_of). |

### `list-candidates` · MCP `odin_list_candidates`

List pending candidates + the declined count — the on-load / review-candidates read (ADR-0033).

_Takes only `<root>`._

### `promote-candidate` · MCP `odin_promote_candidate`

Admit a pending candidate into the base. Default: promote as a new first-class derived doc (reuses derive; default an insight; ADR-0033). Or `into=<doc-id>` to FOLD it into an existing derived doc as a literal insert (append its authored block, union sources, consume the candidate; ADR-0035) — `regenerate` re-coalesces later.

| Switch | | What it does |
|---|---|---|
| `<id>` | required | The cand-… id to promote. |
| `--new-id <value>` | optional | Target derived id for a NEW doc (default: swap cand- for the kind prefix). |
| `--into <value>` | optional | Existing derived doc id to FOLD into instead of writing new (ADR-0035). |
| `--derivation <value>` | optional | The honest rung, set at promotion (T-107). One of: extracted, model-read, synthesis. |

### `decline-candidate` · MCP `odin_decline_candidate`

Decline a pending candidate — a fingerprint-keyed tombstone (never deleted; won't re-nag unless a cited source advances). ADR-0033.

| Switch | | What it does |
|---|---|---|
| `<id>` | required | The cand-… id to decline. |
| `--reason <value>` | optional | Why (recorded on the tombstone). |

### `status` · MCP `odin_status`

On-load status surface (ADR-0034): freshness (fingerprint vs last lint), stale docs, pending candidates, captures-since-lint, and aged time-relative (`as_of`) docs — read-only, one call for a single consolidated nudge. Pass `as_of` (today) to age as_of docs.

| Switch | | What it does |
|---|---|---|
| `--as-of <value>` | optional | Today's date (ISO) — enables date-aging of as_of docs. |

### `index` · MCP `odin_index`

Rebuild index.md as a pure projection of document frontmatter (deterministic, idempotent). No prose authored.

_Takes only `<root>`._

### `fingerprint` · MCP `odin_fingerprint`

The content fingerprint over all registered docs (the freshness hash; ADR-0005). Same value the linter computes.

_Takes only `<root>`._

### `lint` · MCP `odin_lint`

Run every invariant check over the Muninn. Returns {ok, errors, warnings, n_docs, fingerprint}. 'The Muninn lints clean' is the definition of done — this is the backstop that makes the MCP transport safe (ADR-0022 §2).

_Takes only `<root>`._

### `stamp` · MCP `odin_stamp`

Backfill `self_hash` on every derived doc that lacks one, from its CURRENT content (ADR-0029) — the lightweight self-heal for a base whose docs predate self-hashing. Deterministic, no model, no content change; idempotent. Never re-stamps a doc that already has one (a mismatch there is a real out-of-band edit for L19 to flag).

_Takes only `<root>`._

### `reproject` · MCP `odin_reproject`

Regenerate-class maintenance op (T-057): re-render every project page from its members' own title/abstract, seed the canonical global hub if missing, and refresh each page's Always-in-scope pointer. Deterministic projection — no authored prose is touched; safe to run anytime.

_Takes only `<root>`._

### `relink` · MCP `odin_relink`

Regenerate-class maintenance op (ADR-0038): rewrite bare `[known-id]` citation spans in derived docs and decisions into linked citations `[id](relative-path)` — id stays the label, the target is the doc's readable file. Idempotent; already-linked spans and unknown ids are untouched; `self_hash` is re-stamped on edited docs so L19 stays clean. Run once to upgrade a base that predates linked citations; the fingerprint moves (lint after).

_Takes only `<root>`._

### `capture-repo` · MCP `odin_capture_repo`

Capture a repository as a REFERENCE-tier source grounded in its constitution (ADR-0028): a deterministic manifest of the repo's intent-bearing surfaces (README, ARCHITECTURE, in-repo ADRs, public contract, identity manifests, top-level shape) — NOT its full tree, NOT HEAD. Its content_hash moves on a constitutional amendment and stays flat under implementation churn. Building the manifest is a faithful transform; the mental-model inference is the adapter's model-read.

| Switch | | What it does |
|---|---|---|
| `<id>` | required | Stable source id (e.g. src-…). |
| `<repo>` | required | Path to the repository. |
| `--origin-ref <value>` | optional | Durable locator (remote URL); defaults to the absolute path. |
| `--head <value>` | optional | Optional commit stamp (recorded, never the staleness trigger). |
| `--surface <value> (repeatable)` | optional | Adapter-chosen surfaces that AUGMENT the default floor — [{label, globs}] (ADR-0028 §6). |

### `connectors` · MCP `odin_connectors`

Project the distinct connectors the scope:global landscape references (origin-union + explicit `connectors:` fields; ADR-0021 §2 / T-070) — the deterministic read `explore` consults to know which systems this base's world touches. With `project`, the roster is that project's members unioned with the global layer (T-128), matching resolve_scope's project-plus-global reading; global-only stays the default.

| Switch | | What it does |
|---|---|---|
| `--project <value>` | optional | Project id whose members to union with the global roster (the working-inside-a-project view). |

### `usage` · MCP `odin_usage`

Report the disposable usage ledger (ADR-0027): per-op counts, byte-footprints, and wall-time (plus REAL token counts where a harness exposed them) — the evidence that tunes review cadence (T-088) and baselines perf (T-123). Operational state, never knowledge.

| Switch | | What it does |
|---|---|---|
| `--html <value>` | optional · CLI-only | Also render the ledger as one self-contained HTML page at this path (T-123). |

### `usage-log` · MCP `odin_usage_log`

Record a usage entry for an AI-heavy ADAPTER verb — `ask`, `review`, `synthesize` — that the Core never sees itself, so the ledger can measure the real token spenders (T-088). Call it AFTER the verb. Pass `scope` = the doc/source ids the verb read; the Core computes their byte-footprint deterministically as an honest cost proxy. Add `tokens` ONLY when the harness actually exposes a real count — never guess; omit it otherwise.

| Switch | | What it does |
|---|---|---|
| `<op>` | required | The verb measured: ask \| review \| synthesize. |
| `--scope <value> (repeatable)` | optional | Doc/source ids the verb read; Core sums their readable bytes. |
| `--bytes-in <value>` | optional | Override the computed scope byte-footprint. |
| `--bytes-out <value>` | optional | Bytes the verb produced (answer/insight length). |
| `--tokens <value>` | optional | REAL token count when the harness exposes it; omit to leave null (do not estimate). |
| `--note <value>` | optional | Optional short label (e.g. the scope/project). |

### `challenge-log` · MCP `odin_challenge_log`

Record a completed challenge in the append-only log (ADR-0040): 'challenge | <target>: survived|weakened|refuted [detail]'. History a reader can consult, never a verdict the format stores — no doc mark, no status field, no trust score. Run it once per completed challenge, after any consented knowledge-products (counter-insight / caveat / supersede) are written.

| Switch | | What it does |
|---|---|---|
| `<target>` | required | The challenged doc id (or a short claim slug for an unwritten claim). |
| `--outcome <value>` | required | What the challenge concluded. One of: survived, weakened, refuted. |
| `--detail <value>` | optional | One line of context (what was checked, what was recorded). |

### `map-log` · MCP `odin_map_log`

Append a completed map pass (entity/concept/question docs written + the scope it covered) to log.md — `status` reads the latest entry for `last_map` and counts captures arriving after it (`captures_since_map`), the deterministic enrichment-debt facts behind the on-load map offer (ADR-0043). Log even a pass that wrote nothing: 'checked, nothing warranted' is worth remembering.

| Switch | | What it does |
|---|---|---|
| `--scope <value>` | optional | What the pass covered — 'base' (default), a project id, or a doc id. |
| `--entities <value>` | optional | Entity docs written this pass. |
| `--concepts <value>` | optional | Concept docs written this pass. |
| `--questions <value>` | optional | Question docs written this pass. |
| `--detail <value>` | optional | One optional line of context (e.g. items struck from the manifest). |

### `supersede` · MCP `odin_supersede`

Mark a derived document SUPERSEDED (ADR-0041) — the honest ending: status: superseded + a one-way pointer (superseded_by) and/or a reason, stamped superseded_at. Consented, logged, idempotent; touches only these machine fields (provenance and authored content untouched, so everything still verifies). A superseded doc still lints, stays in the index badged, is exempt from L4 staleness, and is skipped by find unless asked. Derived docs only: never sources (immutable, versioned) or decisions (their own supersession record). lift=true reverses a mistaken mark. Use when a claim is refuted (challenge), a doc was mis-filed and re-recorded, or a better derivation replaced it — never a hand-edit, never a delete.

| Switch | | What it does |
|---|---|---|
| `<id>` | required | Stable doc/source id. |
| `--by <value>` | optional | Id of the replacement doc (must exist first). |
| `--reason <value>` | optional | Why this doc is ended (required when no replacement is named). |
| `--lift` | optional | Reverse a mistaken supersession (status back to current; fields removed; logged). |

### `find` · MCP `odin_find`

Deterministic retrieval: docs whose id/title/abstract/tags/body contain ALL query terms (case-insensitive); sources also match their origin locators (origin.ref / upstream_ref — T-141), so a captured filename or URL is a valid query. The AI-free floor (ADR-0014) — no embeddings, no AI. Optional `type` restricts results (type='decision' is the `why` verb). A zero-hit means these literal terms don't appear — never 'not in the base'; degrade the query or check the index before reporting absence (T-142).

| Switch | | What it does |
|---|---|---|
| `<query>…` | required | Whitespace-separated terms (empty lists all of `type`). |
| `--type <value>` | optional | Restrict to a frontmatter type. |
| `--include-superseded` | optional | Include superseded (closed) docs — skipped by default (ADR-0041). |

### `project` · MCP `odin_project`

Create/update a project page — a curated VIEW, not a folder (ADR-0002/0017). Members are links, not provenance. The body is a deterministic projection of each member's own title/abstract. Only group when the user asks — never auto-group. `remove_members` takes ids OUT of the view (T-148): links only — the doc itself is untouched and stays findable; never hand-edit a members list.

| Switch | | What it does |
|---|---|---|
| `<id>` | required | Stable project id. |
| `--title <value>` | optional | Required on create; kept on update if omitted. |
| `--member <value> (repeatable)` | optional | Member ids to union in (order-stable). |
| `--remove-member <value> (repeatable)` | optional | Member ids to remove from the view (idempotent — an absent id is a no-op; applied after any adds). Removal is a link change only. |
| `--scope <value>` | optional | 'global' views are always unioned into every scope. One of: global, project. |
| `--description <value>` | optional | A plain maintainer label (not a sourced claim). |
| `--maintained-by <value>` | optional | Maintainer label. |
| `--tag <value> (repeatable)` | optional | Tags. |

### `read` · MCP `odin_read`

Return a doc's stored text verbatim, paged. For a SOURCE: its readable text (the extracted aid, else a text-native canonical — the same text find/index/derivation read); a bytes-only source returns empty content with text_form 'none' (grounding then needs a model-read of the original bytes — never a guess). For a derived doc/project/decision: the file's content. This is the read half of 'anyone reads, the Core writes' for hosts that have only the op surface — use it to ground summaries, quote sources (T-153), and re-read for review/challenge. Read-only.

| Switch | | What it does |
|---|---|---|
| `<id>` | required | Any doc id (source, derived, project, decision). |
| `--offset <value>` | optional | Character offset to start from (paging). |
| `--limit <value>` | optional | Max characters returned (default 20000); `truncated: true` means more remains. |

### `resolve` · MCP `odin_resolve`

Resolve a scope to its working-set member ids — a named project's members ∪ every global view (deterministic set math; SPEC §5.6). Omit `project` for the whole base. The read-side companion synthesize uses to learn its scope.

| Switch | | What it does |
|---|---|---|
| `<project>` | optional | A project id; omit for the whole base. |

### `record-decision` · MCP `odin_record_decision`

Record (or --amend) the owner's decision — AUTHORED, not derived (SPEC §5.5, ADR-0019). Carries no provenance; links informing `evidence` as (source id + version), never grounds from it, so it can't chain. Write ONLY on explicit request — never as an ask/synthesize side effect.

| Switch | | What it does |
|---|---|---|
| `<id>` | required | Stable slug id (dec-…). |
| `--body <value>` | required | The decision text (owner-authored). |
| `--title <value>` | optional | Required when recording; kept on --amend if omitted. |
| `--status <value>` | optional | proposed \| accepted (default: accepted). One of: accepted, proposed. |
| `--evidence <value> (repeatable)` | optional | Informing source ids (a LINK, not provenance). |
| `--amend` | optional | Prepend a dated AMENDED banner to an existing decision. |

## Semantic tier (`muninn_semantic`) — disposable, never load-bearing (ADR-0027)

### `reindex` · MCP `odin_reindex`

(Re)build the DISPOSABLE semantic vector sidecar (.odin/semantic.db) from the derived layer via a local embedding model (T-087, ADR-0027). Inference, NOT a Core transform — it only accelerates retrieval, never grounds (ADR-0008 boundary). Incremental (re-embeds only changed docs), prunes deleted docs, and rebuilds on a model change. Run after ingest to keep `odin_search` fresh; safe to delete the sidecar anytime — this rebuilds it. Needs a reachable Ollama (ODIN_OLLAMA_URL); returns counts, never touches the base.

| Switch | | What it does |
|---|---|---|
| `--model <value>` | optional | Embedding model (default nomic-embed-text / ODIN_EMBED_MODEL). |
| `--url <value>` | optional | Ollama base URL (default ODIN_OLLAMA_URL or http://localhost:11434). |

### `search` · MCP `odin_search`

Semantic retrieval: top-k derived docs by cosine similarity to the query, over the disposable embedding sidecar (T-087). The AI-facing companion to the AI-free `odin_find` floor — it crosses the reader-vocabulary gap find cannot (e.g. 'illness'->the vet exam; ADR-0014, T-044). It only PROPOSES candidates (ADR-0027 §2): each hit is a doc to READ, never a citation, never provenance — ground answers in the actual sources. Empty until `odin_reindex` has run. Prefer `odin_find` when the query is a literal token; reach here for meaning/synonyms.

| Switch | | What it does |
|---|---|---|
| `--query <value>` | required | A natural-language / concept query (meaning, not just tokens). |
| `--k <value>` | optional | How many candidates to propose (default 10). |
| `--model <value>` | optional | Override the query model; the index's own model still wins for coherence. |
| `--url <value>` | optional | Ollama base URL (default ODIN_OLLAMA_URL or http://localhost:11434). |

### `retrieve` · MCP `odin_retrieve`

Unified retrieval — the DEFAULT way to find things: unions semantic candidates (meaning) with `find` hits (literal), deduped, so you never miss a synonym OR an exact token. It ALWAYS answers and never errors on a down backend: the fallback to the AI-free `find` floor is MECHANICAL (inside the call), so it can't be forgotten. Transparent about it — the result's `via`/`backend` say whether semantics ran or it degraded to find (Ollama down / no index). Still proposes only (ADR-0027 §2); read the sources to ground. Prefer this over `odin_search`/`odin_find` unless you specifically want just one.

| Switch | | What it does |
|---|---|---|
| `--query <value>` | required | A natural-language or literal query — both retrievers run. |
| `--k <value>` | optional | Semantic candidates to union in (default 10); find hits are added whole. |
| `--model <value>` | optional | Override the query model; the index's own model still wins for coherence. |
| `--url <value>` | optional | Ollama base URL (default ODIN_OLLAMA_URL or http://localhost:11434). |

### `refresh` · MCP `odin_refresh`

Best-effort **warm** of the disposable semantic index (T-091): embed any doc changed since the last embed, prune the gone ones. Call it at the END of an `ingest` so what you just added is searchable *now* — the next `odin_retrieve` is instant instead of paying a cold-load. WRITE-ONLY and NEVER errors: no backend → a clean no-op with a status, so no try/except needed (unlike `odin_reindex`, which raises). It is a pure optimization — safe to skip, because `odin_retrieve` self-heals (T-090); this only moves the embed cost off the first query. Returns {status: clean|current|stale, embedded, pruned, warning}. Relay `warning` if present.

| Switch | | What it does |
|---|---|---|
| `--model <value>` | optional | Embedding model (default nomic-embed-text / the index's own). |
| `--url <value>` | optional | Ollama base URL (default ODIN_OLLAMA_URL or http://localhost:11434). |
