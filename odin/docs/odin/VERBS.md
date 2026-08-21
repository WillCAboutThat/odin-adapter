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
| `--allow-large` | optional | Deliberately hold >=25 MB of source bytes in a full-tier capture (T-233). Without it, oversized captures are refused with the reference-tier alternative named — immutable bytes live in git history forever. |
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

### `reextract` · MCP `odin_reextract`

Backfill `source-text.md` aids from bytes the base already holds, for sources captured bytes-only before their format's extractor existed (T-226). Deterministic decode — no inference, no fetch, NO new version (bytes and content_hash unchanged); the current ledger entry gains text_aid/extracted_by. Never overwrites an existing aid and never re-stamps derivations (`regenerate` is the consented path for that). With `id` targets one source; without, sweeps the base and reports per-source outcomes.

| Switch | | What it does |
|---|---|---|
| `<id>` | optional | One source to backfill (raises if absent); omit to sweep every source. |

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

Write a derived doc (summary/entity/concept/question/insight) grounded ONLY in sources. Core copies each source's current hash into provenance; a provenance id that is not a real source is rejected (I3, no chaining). `body` is the adapter-authored content. For an INSIGHT, quoted spans are containment-verified (T-153): a double-quoted span ≥15 chars on a line citing a provenance source must appear in that source's text or the write is refused — quote sources exactly, never from a summary's paraphrase (whitespace and smart quotes are normalized for you; markdown syntax, punctuation, and letter case are literal source bytes you must reproduce). A `question` doc may be answered or explicitly OPEN (abstract leads 'OPEN — ', T-154); regenerate re-derives it when answered.

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

### `queue-list` · MCP `odin_queue_list`

Enumerate the work queue (`queue/`, ADR-0048): tasks awaiting an executor session, pending first. A task is scoped consent — it authorizes exactly the named operations on the named inputs; results land as candidates, never direct base writes. Read-only.

| Switch | | What it does |
|---|---|---|
| `--status <value>` | optional | Filter to one lifecycle state. One of: pending, blocked, done, declined, cancelled. |

### `queue-create` · MCP `odin_queue_create`

Author a work-queue task (`queue/`, ADR-0048). Authoring IS the scoped consent act: the task authorizes exactly the named operations on the named inputs; executor results land on the candidates rail, never as direct base writes. Never overwrites.

| Switch | | What it does |
|---|---|---|
| `<type>` | required | What kind of work this is. One of: ingest, synthesize, map, explore, drift-check, ask, review, other. |
| `--outcome <value>` | required | The requested outcome, in the owner's words (prose or an op list). |
| `--input <value> (repeatable)` | optional | Immutable input refs: inbox items, source ids, a URL, a question. |
| `--created-by <value>` | optional | Authoring surface (web, an adapter session…; default core). |

### `queue-restatus` · MCP `odin_queue_restatus`

Move a work-queue task through its lifecycle (pending → done | declined | blocked | cancelled; blocked may resume). Rewrites the status line and appends one log line to the task's own ## Log — tasks are re-statused, NEVER deleted, and illegal transitions are refused. Executors set done/declined/blocked when they finish, decline, or park a task.

| Switch | | What it does |
|---|---|---|
| `<id>` | required | The task-… id to re-status. |
| `<status>` | required | The new lifecycle state. One of: pending, blocked, done, declined, cancelled. |
| `--note <value>` | optional | Appended to the log line (why, or a pointer to the results — candidate ids). |
| `--actor <value>` | optional | Who is re-statusing (web, an executor session…; default core). |

### `status` · MCP `odin_status`

On-load status surface (ADR-0034): freshness (fingerprint vs last lint), stale docs, pending candidates, pending work-queue tasks (ADR-0048), captures-since-lint, and aged time-relative (`as_of`) docs — read-only, one call for a single consolidated nudge. Pass `as_of` (today) to age as_of docs.

| Switch | | What it does |
|---|---|---|
| `--as-of <value>` | optional | Today's date (ISO) — enables date-aging of as_of docs. |

### `index` · MCP `odin_index`

Rebuild the projection artifacts from document frontmatter (deterministic, idempotent, no prose authored): index.md for the human skim, index.jsonl for no-AI tooling (ADR-0046), llms.txt for generic agents (T-168).

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

### `repo-coverage` · MCP `odin_repo_coverage`

Project the honest FOOTPRINT of what this base holds about a repository (T-196) — the repo analog of `connectors`. A deterministic, faithful read of stored provenance and manifest text: it never walks the repo and never infers what SHOULD be covered. Repo-sourced material is every `origin.system: repo` source (ADR-0028 + the T-196 convention); its locator groups it — the constitution carries the bare `<repo>`, evidence captures qualify it `#<path>[#<slug>]`. Per repo it reports: the `constitution` (mental-model source + the surfaces it holds), `covered` (dedicated file/excerpt evidence captures — the current, quotable sources), `concepts` (derived docs grounded in the repo's sources), and `references_not_captured` (constitution-named surfaces with no dedicated capture — the PARTIAL frontier a code question falls into: the subsystem is located, fetch the live file to ground). With `repo` it scopes to one locator and ALWAYS returns one entry — all-empty is the honest UNKNOWN answer, never an error (gap detection is a thin adapter classification on top). Read-only; a projection like index.md — goes stale, never a durable registry.

| Switch | | What it does |
|---|---|---|
| `<repo>` | optional | A repo locator (the constitution's origin.ref) to scope to; omit for the roster of every repo the base knows. |

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

### `attention` · MCP `odin_attention`

Join the disposable usage ledger's per-doc touch records against the current base: per doc, the last strong touch (read / grounded in) and weak touch (surfaced in a result list) with counts and its readable-byte footprint; plus the aggregate that would justify or refute a dormancy design — how many docs, and how many bytes, went untouched inside each window (30/60/90d). Honest about its own limits: the ledger is per-clone (this machine's attention only), and any window the ledger hasn't lived through is marked meaningful:false rather than reported as dormancy. Read-only; time enters only via as_of.

| Switch | | What it does |
|---|---|---|
| `--as-of <value>` | optional | Today (ISO date) — the windows' anchor; defaults to now. |

### `review-log` · MCP `odin_review_log`

Record a completed `review` pass in the append-only log: 'review | scope=<scope>: clean|findings-surfaced [detail]'. The challenge-log precedent — history a reader can consult ("this scope was re-read adversarially, on these dates"), never a verdict the format stores: no doc mark, no status field, no trust score, because an AI blessing rots (ADR-0014). The outcome is deliberately QUALITATIVE, never a finding count — a deterministic-looking tally would launder judgment as fact (ADR-0026), which is the overreach review exists to hunt. `clean` records what the pass reported, never a warranty. Run it as the close step of a review, after any consented heals.

| Switch | | What it does |
|---|---|---|
| `<outcome>` | required | What the pass reported: clean (nothing a skeptical reader would question) or findings-surfaced. One of: clean, findings-surfaced. |
| `--scope <value>` | optional | What was reviewed (a project id, a doc id, or omit for the whole base). |
| `--detail <value>` | optional | One line of context in the reviewer's own hedged words (what was re-read, what was offered). |

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

Deterministic retrieval: docs whose id/title/abstract/tags/body contain ALL query terms (case-insensitive); sources also match their origin locators (origin.ref / upstream_ref — T-141), so a captured filename or URL is a valid query. Ordered by how much of the query the doc's NAME carries (id/title/tags/locators, and a source's HELD format: a .sql filename or a held .html canonical is a name), then kind, then id: being named by the query beats mentioning it. The AI-free floor (ADR-0014) — no embeddings, no AI. Optional `type` restricts results (type='decision' is the `why` verb). A zero-hit means these literal terms don't appear — never 'not in the base'; degrade the query or check the index before reporting absence (T-142). LITERAL MATCHING ONLY: when the query is about MEANING rather than exact tokens, reach for `retrieve` instead — it unions this floor with semantic candidates and degrades back to it mechanically, so it never recalls less (measured 2026-07-30: find 43% vs retrieve 100%@10 on reader-vocabulary probes). This op stays the AI-free durability floor (ADR-0014), not the default strategy.

| Switch | | What it does |
|---|---|---|
| `<query>…` | required | Whitespace-separated terms (empty lists all of `type`). |
| `--type <value>` | optional | Restrict to a frontmatter type. |
| `--include-superseded` | optional | Include superseded (closed) docs — skipped by default (ADR-0041). |
| `--project <value>` | optional | Restrict hits to this project's resolved working set (members ∪ global views — the same set math as `resolve`). Unknown project errors; never a silent whole-base fallback. |

### `query` · MCP `odin_query`

Query the disposable catalog accelerator (.odin/catalog.db, SQLite+FTS5): full-text `fts` terms AND structured filters (type, kind, cites=<source-id>, origin_system, status). Self-heals (refreshes changed docs before ranking) and degrades MECHANICALLY to the AI-free `find` walk on any catalog failure — the result's `via` says which surface answered (T-090 pattern). Proposes candidates to read, never grounds (ADR-0027 §2); the file walk stays the arbiter. This is the FACETED lane, and it is NOT part of `retrieve`'s union: the structured filters (cites/origin_system/status/kind) express the class of question neither `find` nor `retrieve` can ask, so reach here for 'which docs cite src-x' — not as a synonym for search (measured 2026-07-30: structured filters 7/7 exact, at ~34x less context than an index read; its `fts` lane scored 55% vs semantic's 100% on vocabulary gaps, so `fts` is not the synonym tool).

| Switch | | What it does |
|---|---|---|
| `--fts <value>` | optional | Full-text terms (AND-joined, matched as literal phrases over title/abstract/tags/body). |
| `--type <value>` | optional | Restrict to a derived-doc frontmatter type (summary, entity, insight, ...). |
| `--kind <value>` | optional | Restrict to a doc kind: source \| derived \| project \| decision. |
| `--cites <value>` | optional | Only derived docs whose provenance cites this source id. |
| `--origin-system <value>` | optional | Only sources captured from this origin system (url, repo, file, ...). |
| `--status <value>` | optional | Restrict to a frontmatter status (current, superseded, ...). |
| `--limit <value>` | optional | Max hits (default 50, cap 500). |
| `--project <value>` | optional | Restrict hits to this project's resolved working set (post-filter over the same set math as `resolve`; unknown project errors). |

### `graph` · MCP `odin_graph`

Project the base's EXPLICIT relationship graph as neutral, renderer-agnostic JSON (odin.graph.v1) — THE op for EVIDENCE disclosure, PROVENANCE audit, and CITATION tracing: for selected docs, what sources they declare, whether that grounding is current or stale, and which decisions connect. The audit pipeline (ADR-0052): retrieve → you select seeds → graph(centers=…, direction='outbound', relations=['grounded_by','evidence','superseded_by']) → read-many → you read and judge. Every edge is a frontmatter fact — grounded_by (provenance, with per-rung staleness), see_also, member_of, evidence, superseded_by, excerpt_of (ADR-0039), from_repo (T-196) — never an inference (no title-mention or similarity edges; ADR-0015). Direction follows the stored edge; 'both' (default) is the undirected neighborhood. Capped results say so honestly: `complete` means complete for THESE seeds/relations/direction/depth/caps — never complete evidence for a question, never base validity (lint is the authority; `unresolved_edges` is courtesy diagnostics). `unexpanded_frontier` ids are re-seedable — that IS the continuation; no cursor. Read-only; `cache_key` is a stat-sweep change detector for layout caches, not a content hash.

| Switch | | What it does |
|---|---|---|
| `--center <value>` | optional | Restrict to this doc's neighborhood (unknown id errors; exclusive with centers). |
| `--center-id <value> (repeatable)` | optional | Several seed docs — the deduped union of their neighborhoods (ADR-0052; you choose the seeds, the Core never does). |
| `--depth <value>` | optional | Hops from the seeds (default 1; ignored without seeds). |
| `--direction <value>` | optional | Traversal along the STORED edge: outbound = source-field→target (a derived doc's grounded_by reaches its sources and stops); inbound = the reverse; both (default) = undirected. Undirected relations (see_also) behave the same in every mode. One of: both, outbound, inbound. |
| `--max-nodes <value>` | optional | Cap on traversed nodes (depth bounds path length, not fan-out). Capped ⇒ complete:false + re-seedable frontier. |
| `--max-edges <value>` | optional | Cap on returned edges (stable order decides survival, never relevance). |
| `--project <value>` | optional | Annotate nodes with in_scope against this project's resolved working set — annotation, NEVER suppression: out-of-scope grounding sources stay disclosed. |
| `--kind <value> (repeatable)` | optional | Keep only these node kinds (source \| derived \| project \| decision); seeds always survive. |
| `--relation <value> (repeatable)` | optional | Keep only these edge relations (grounded_by, see_also, member_of, evidence, superseded_by, excerpt_of, from_repo). Filters apply BEFORE the walk. |

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
| `--limit <value>` | optional | Max characters returned (default 20000); `truncated: true` means more remains. `chars` is always the FULL length — probe with limit=1 to size before reading. |
| `--find-text <value>` | optional | Case-insensitive LITERAL search inside the doc: returns matches [{offset, excerpt}] (cap 20) instead of a page — a deterministic jump aid; read the offsets to ground. |
| `--section <value>` | optional | Return the markdown section whose heading contains this text (to the next same-or-higher heading). Result offset is the section's true offset. |

### `read-many` · MCP `odin_read_many`

Read several docs in ONE call under a shared character budget — the mechanical round-trip saver for evidence gathering (2026-08-19 adapter feedback). Reads ids in the caller's order until max_total_chars is spent; each doc carries the same fields as `read` plus `status` and, for derived docs, `sources` (provenance ids). Ids the budget never reached return in `not_read` with their sizes for deliberate paging. Deliberately NOT a relevance-ranking packet assembler: what to read and what it means stay the caller's judgment (ADR-0014). Reserved ids (@instructions/@manifest/@index) work here too. Read-only.

| Switch | | What it does |
|---|---|---|
| `<ids>` | required | Doc ids, read in this order. |
| `--max-total-chars <value>` | optional | Shared budget across all docs (default 100000). |

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

Semantic retrieval: top-k derived docs by cosine similarity to the query, over the disposable embedding sidecar (T-087). The AI-facing companion to the AI-free `odin_find` floor — it crosses the reader-vocabulary gap find cannot (e.g. 'illness'->the vet exam; ADR-0014, T-044). It only PROPOSES candidates (ADR-0027 §2): each hit is a doc to READ, never a citation, never provenance — ground answers in the actual sources. Empty until `odin_reindex` has run. Prefer `odin_find` when the query is a literal token — and note most callers want `odin_retrieve` instead of either: it unions this with `find` so nothing is missed either way and it survives a down backend. Reach for bare `search` only when you specifically want semantic candidates ALONE (measured 2026-07-25: every gap probe chose retrieve, never bare search).

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
| `--project <value>` | optional | Restrict ranked hits to this project's resolved working set (same set math as `resolve`; unknown project errors). The top few out-of-scope hits still return under the labeled `outside_scope` key. |
| `--model <value>` | optional | Override the query model; the index's own model still wins for coherence. |
| `--url <value>` | optional | Ollama base URL (default ODIN_OLLAMA_URL or http://localhost:11434). |

### `refresh` · MCP `odin_refresh`

Best-effort **warm** of the disposable semantic index (T-091): embed any doc changed since the last embed, prune the gone ones. Call it at the END of an `ingest` so what you just added is searchable *now* — the next `odin_retrieve` is instant instead of paying a cold-load. WRITE-ONLY and NEVER errors: no backend → a clean no-op with a status, so no try/except needed (unlike `odin_reindex`, which raises). It is a pure optimization — safe to skip, because `odin_retrieve` self-heals (T-090); this only moves the embed cost off the first query. Returns {status: clean|current|stale, embedded, pruned, warning}. Relay `warning` if present.

| Switch | | What it does |
|---|---|---|
| `--model <value>` | optional | Embedding model (default nomic-embed-text / the index's own). |
| `--url <value>` | optional | Ollama base URL (default ODIN_OLLAMA_URL or http://localhost:11434). |
