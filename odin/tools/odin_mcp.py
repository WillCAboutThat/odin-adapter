# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
# ^ PEP-723 inline metadata (ADR-0031): `uv run --script` provisions Python + pyyaml
#   cross-platform, so the plugin's `.mcp.json` launches this with `command: uv` and
#   needs no `python3` on the host. The sibling Core modules resolve via the
#   sys.path.insert below (uv's isolated env doesn't block local imports).
"""Odin Core MCP server — a second, tool-neutral transport over the Core ops
(ADR-0022, T-071).

This is a **thin wrapper** with *no business logic of its own*. It imports
`muninn_core` and exposes its existing fat atomic ops as MCP tools. Every
guarantee still lives in the ops + the linter, never in this transport (ADR-0022
§2): an MCP client calling `capture` can violate an invariant no more than the
CLI can — the op rejects chaining, requires provenance, etc., and `lint` catches
the rest. The worst a naive MCP client does is produce a base that *lints dirty*,
which is surfaced, never silent.

Three layers, deliberately separated so the mapping is testable without a
transport:

  1. ``TOOLS``     — the declarative tool-schema surface (name, description,
                     JSON Schema for arguments) for every exposed op.
  2. ``dispatch``  — a PURE function ``(op, params) -> json-serializable``. It
                     maps MCP arguments onto the Core call, resolving the one
                     real mapping question (ADR-0022 build note): the CLI's
                     ``--file``/stdin *body* becomes a ``body`` string argument,
                     and ``--source-file`` becomes a ``source_file`` path the
                     server reads (both transports run local, same filesystem).
                     No MCP dependency — this is what the eval drives directly.
  3. the stdio loop — a stdlib-only JSON-RPC 2.0 server (initialize / tools/list
                     / tools/call) so the plugin needs no `mcp` wheel installed;
                     a process boundary + bundled Core is stronger encapsulation
                     than a shared-`site-packages` package (ADR-0022 Consequences).

Run as ``python3 odin_mcp.py`` (stdio). Bundled by the Claude/Codex plugins
(T-071b/T-072); also usable by any MCP client pointed at this command.
"""
import json
import os
import sys
from pathlib import Path

# Import the Core from THIS directory (the plugin bundles it here — ADR-0022:
# self-contained, imports nothing from a shared site-packages). If a plugin
# SessionStart hook bootstrapped deps (pyyaml) into the plugin data dir, honor
# that path too — a controlled per-process sys.path, not a global install (§c).
sys.path.insert(0, str(Path(__file__).resolve().parent))
_DEP_DIR = os.environ.get("ODIN_DEP_DIR")
if _DEP_DIR:
    sys.path.insert(0, _DEP_DIR)
import muninn_core as core  # noqa: E402
import muninn_lint  # noqa: E402
import muninn_semantic as semantic  # noqa: E402  (the disposable semantic tier, T-087)

SERVER_NAME = "odin-core"
SERVER_VERSION = core.FORMAT_VERSION
# Echoed to the client if it doesn't ask for a specific version; a recent stable
# MCP protocol revision. We echo the client's requested version when it sends one.
DEFAULT_PROTOCOL_VERSION = "2025-06-18"


# --------------------------------------------------------------------------- #
# 1. Tool-schema surface — one MCP tool per fat atomic op (ADR-0022 §1).
#    Descriptions carry the discipline so an MCP client/model wields the op
#    correctly; the op itself still enforces it.
# --------------------------------------------------------------------------- #
def _obj(properties, required=()):
    return {"type": "object", "properties": properties,
            "required": list(required), "additionalProperties": False}


_ROOT = {"type": "string", "description": "Path to the Muninn root directory."}

TOOLS = [
    {
        "name": "odin_init",
        "description": "Scaffold a new Muninn (manifest, layout, index, the "
                       "canonical global view). No-op if one already exists.",
        "inputSchema": _obj({
            "root": _ROOT,
            "name": {"type": "string", "description": "Display name (defaults to the dir name)."},
        }, required=["root"]),
    },
    {
        "name": "odin_capture",
        "description": "Capture a source (immutable, provenance-bearing). Provide "
                       "`body` for a text source, OR `source_file` for original "
                       "bytes (PDF/image/…; a text aid is extracted per ADR-0010). "
                       "Byte-identical content dedups; changed bytes of an existing "
                       "id make a new version. Changed bytes under a NEW id whose "
                       "origin_ref already belongs to a captured source are refused "
                       "(a silent lineage split, T-045) — capture under the matching "
                       "id to version it, or set force_new to declare the split. "
                       "Sources are authoritative and never chained from.",
        "inputSchema": _obj({
            "root": _ROOT,
            "id": {"type": "string", "description": "Stable source id (e.g. src-…)."},
            "origin_system": {"type": "string", "description": "Where it came from (file, url, connector…)."},
            "origin_ref": {"type": "string", "description": "The locator within that system (filename, URL, …)."},
            "body": {"type": "string", "description": "Text-source content. Mutually exclusive with source_file."},
            "source_file": {"type": "string", "description": "Path to a file whose ORIGINAL BYTES are the source."},
            "filename": {"type": "string", "description": "Canonical filename hint (defaults to source_file's name)."},
            "tier": {"type": "string", "enum": ["full", "reference"], "default": "full"},
            "reason": {"type": "string", "description": "Required for a reference-tier capture (ADR-0003)."},
            "recoverable": {"type": "boolean", "description": "Is the original re-fetchable via origin.ref? (self-heal, T-066)."},
            "force_new": {"type": "boolean", "description": "Deliberately start a NEW lineage although origin_ref matches an existing source (the split is logged; T-045)."},
        }, required=["root", "id", "origin_system", "origin_ref"]),
    },
    {
        "name": "odin_dedup_check",
        "description": "Dry-run dedup preview: report already-captured / changed / "
                       "new for a candidate WITHOUT writing (explore preview, "
                       "ADR-0020). Give `source_file` (content-hash rung) or "
                       "`origin_ref` (locator rung for reference-tier).",
        "inputSchema": _obj({
            "root": _ROOT,
            "id": {"type": "string", "description": "Candidate's intended id (enables changed-vs-new)."},
            "source_file": {"type": "string", "description": "Candidate file whose bytes to hash."},
            "filename": {"type": "string", "description": "Canonical filename hint."},
            "origin_ref": {"type": "string", "description": "Locator to match when no bytes are held."},
        }, required=["root"]),
    },
    {
        "name": "odin_source_status",
        "description": "Read-only deterministic facts about a source (tier, "
                       "version, whether bytes are held, recoverable, origin.ref) "
                       "— the ground truth a fetch/self-heal decision rests on (T-066).",
        "inputSchema": _obj({
            "root": _ROOT,
            "id": {"type": "string", "description": "The source id."},
        }, required=["root", "id"]),
    },
    {
        "name": "odin_derive",
        "description": "Write a derived doc (summary/entity/concept/question/"
                       "insight) grounded ONLY in sources. Core copies each "
                       "source's current hash into provenance; a provenance id "
                       "that is not a real source is rejected (I3, no chaining). "
                       "`body` is the adapter-authored content.",
        "inputSchema": _obj({
            "root": _ROOT,
            "id": {"type": "string", "description": "Stable derived-doc id."},
            "body": {"type": "string", "description": "The document body (adapter judgment)."},
            "sources": {"type": "array", "items": {"type": "string"},
                        "description": "Grounding source ids (≥1). Must be sources, never derived docs."},
            "title": {"type": "string"},
            "abstract": {"type": "string"},
            "type": {"type": "string",
                     "enum": ["summary", "entity", "concept", "question", "insight"],
                     "default": "summary"},
            "derivation": {"type": "string",
                           "enum": sorted(muninn_lint.DERIVATION_VALUES),
                           "description": "How it was derived (e.g. synthesis) — sets the integrity rung."},
            "as_of": {"type": "string",
                      "description": "ISO date a TIME-RELATIVE claim was true — surfaced/aged "
                                     "on-load by `status`, never by lint (ADR-0034). Prefer "
                                     "anchoring on the immutable datum + rule; this is the residual."},
        }, required=["root", "id", "body", "sources", "title"]),
    },
    {
        "name": "odin_stage_candidate",
        "description": "Stage an emergent grounded inference for later BATCHED review "
                       "(ADR-0033). NOT admitted to the base — grounded sources-only "
                       "(no chaining), deduped vs pending and vs declined tombstones "
                       "(a sticky decline won't re-nag unless a cited source advances).",
        "inputSchema": _obj({
            "root": _ROOT,
            "id": {"type": "string", "description": "Candidate id (must start 'cand-')."},
            "body": {"type": "string", "description": "The grounded inference, cited to its sources."},
            "sources": {"type": "array", "items": {"type": "string"},
                        "description": "Grounding source ids (≥1). Sources only — never a derived doc."},
            "title": {"type": "string"},
            "abstract": {"type": "string"},
            "proposed_kind": {"type": "string",
                              "enum": ["summary", "entity", "concept", "question", "insight"],
                              "default": "insight",
                              "description": "What it becomes on promote."},
            "derivation": {"type": "string", "enum": sorted(muninn_lint.DERIVATION_VALUES),
                           "description": "The honest rung — set it, don't presume: a "
                                          "single-source deterministic computation (an age) "
                                          "is `extracted`, not `synthesis` (cross-source "
                                          "generative). Unset → the reviewer sets it at "
                                          "promotion (T-107)."},
            "as_of": {"type": "string",
                      "description": "ISO date IF this candidate states a TIME-RELATIVE "
                                     "result — aged on-load once promoted as its OWN doc; "
                                     "such a candidate can't be folded (T-109). Prefer the "
                                     "datum + rule (no as_of)."},
        }, required=["root", "id", "body", "sources", "title"]),
    },
    {
        "name": "odin_list_candidates",
        "description": "List pending candidates + the declined count — the on-load / "
                       "review-candidates read (ADR-0033).",
        "inputSchema": _obj({"root": _ROOT}, required=["root"]),
    },
    {
        "name": "odin_promote_candidate",
        "description": "Admit a pending candidate into the base. Default: promote as a "
                       "new first-class derived doc (reuses derive; default an insight; "
                       "ADR-0033). Or `into=<doc-id>` to FOLD it into an existing derived "
                       "doc as a literal insert (append its authored block, union sources, "
                       "consume the candidate; ADR-0035) — `regenerate` re-coalesces later.",
        "inputSchema": _obj({
            "root": _ROOT,
            "id": {"type": "string", "description": "The cand-… id to promote."},
            "new_id": {"type": "string",
                       "description": "Target derived id for a NEW doc (default: swap cand- for the kind prefix)."},
            "into": {"type": "string",
                     "description": "Existing derived doc id to FOLD into instead of writing new (ADR-0035)."},
            "derivation": {"type": "string", "enum": sorted(muninn_lint.DERIVATION_VALUES)},
        }, required=["root", "id"]),
    },
    {
        "name": "odin_decline_candidate",
        "description": "Decline a pending candidate — a fingerprint-keyed tombstone "
                       "(never deleted; won't re-nag unless a cited source advances). ADR-0033.",
        "inputSchema": _obj({
            "root": _ROOT,
            "id": {"type": "string"},
            "reason": {"type": "string"},
        }, required=["root", "id"]),
    },
    {
        "name": "odin_status",
        "description": "On-load status surface (ADR-0034): freshness (fingerprint vs "
                       "last lint), stale docs, pending candidates, captures-since-lint, "
                       "and aged time-relative (`as_of`) docs — read-only, one call for a "
                       "single consolidated nudge. Pass `as_of` (today) to age as_of docs.",
        "inputSchema": _obj({
            "root": _ROOT,
            "as_of": {"type": "string",
                      "description": "Today's date (ISO) — enables date-aging of as_of docs."},
        }, required=["root"]),
    },
    {
        "name": "odin_index",
        "description": "Rebuild index.md as a pure projection of document "
                       "frontmatter (deterministic, idempotent). No prose authored.",
        "inputSchema": _obj({"root": _ROOT}, required=["root"]),
    },
    {
        "name": "odin_find",
        "description": "Deterministic retrieval: docs whose id/title/abstract/tags/"
                       "body contain ALL query terms (case-insensitive). The AI-free "
                       "floor (ADR-0014) — no embeddings, no AI. Optional `type` "
                       "restricts results (type='decision' is the `why` verb).",
        "inputSchema": _obj({
            "root": _ROOT,
            "query": {"type": "string", "description": "Whitespace-separated terms (empty lists all of `type`)."},
            "type": {"type": "string", "description": "Restrict to a frontmatter type."},
        }, required=["root", "query"]),
    },
    {
        "name": "odin_project",
        "description": "Create/update a project page — a curated VIEW, not a folder "
                       "(ADR-0002/0017). Members are links, not provenance. The body "
                       "is a deterministic projection of each member's own "
                       "title/abstract. Only group when the user asks — never auto-group.",
        "inputSchema": _obj({
            "root": _ROOT,
            "id": {"type": "string"},
            "title": {"type": "string", "description": "Required on create; kept on update if omitted."},
            "add_members": {"type": "array", "items": {"type": "string"},
                            "description": "Member ids to union in (order-stable)."},
            "scope": {"type": "string", "enum": sorted(muninn_lint.SCOPE_VALUES),
                      "description": "'global' views are always unioned into every scope."},
            "description": {"type": "string", "description": "A plain maintainer label (not a sourced claim)."},
            "maintained_by": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        }, required=["root", "id"]),
    },
    {
        "name": "odin_resolve",
        "description": "Resolve a scope to its working-set member ids — a named "
                       "project's members ∪ every global view (deterministic set "
                       "math; SPEC §5.6). Omit `project` for the whole base. The "
                       "read-side companion synthesize uses to learn its scope.",
        "inputSchema": _obj({
            "root": _ROOT,
            "project": {"type": "string", "description": "A project id; omit for the whole base."},
        }, required=["root"]),
    },
    {
        "name": "odin_record_decision",
        "description": "Record (or --amend) the owner's decision — AUTHORED, not "
                       "derived (SPEC §5.5, ADR-0019). Carries no provenance; links "
                       "informing `evidence` as (source id + version), never grounds "
                       "from it, so it can't chain. Write ONLY on explicit request — "
                       "never as an ask/synthesize side effect.",
        "inputSchema": _obj({
            "root": _ROOT,
            "id": {"type": "string", "description": "Stable slug id (dec-…)."},
            "body": {"type": "string"},
            "title": {"type": "string", "description": "Required when recording; kept on --amend if omitted."},
            "status": {"type": "string", "enum": sorted(muninn_lint.DECISION_STATUS_VALUES)},
            "evidence": {"type": "array", "items": {"type": "string"},
                         "description": "Informing source ids (a LINK, not provenance)."},
            "amend": {"type": "boolean", "description": "Prepend a dated AMENDED banner to an existing decision."},
        }, required=["root", "id", "body"]),
    },
    {
        "name": "odin_fingerprint",
        "description": "The content fingerprint over all registered docs (the "
                       "freshness hash; ADR-0005). Same value the linter computes.",
        "inputSchema": _obj({"root": _ROOT}, required=["root"]),
    },
    {
        "name": "odin_lint",
        "description": "Run every invariant check over the Muninn. Returns "
                       "{ok, errors, warnings, n_docs, fingerprint}. 'The Muninn "
                       "lints clean' is the definition of done — this is the backstop "
                       "that makes the MCP transport safe (ADR-0022 §2).",
        "inputSchema": _obj({"root": _ROOT}, required=["root"]),
    },
    {
        "name": "odin_reindex",
        "description": "(Re)build the DISPOSABLE semantic vector sidecar "
                       "(.odin/semantic.db) from the derived layer via a local "
                       "embedding model (T-087, ADR-0027). Inference, NOT a Core "
                       "transform — it only accelerates retrieval, never grounds "
                       "(ADR-0008 boundary). Incremental (re-embeds only changed "
                       "docs), prunes deleted docs, and rebuilds on a model change. "
                       "Run after ingest to keep `odin_search` fresh; safe to delete "
                       "the sidecar anytime — this rebuilds it. Needs a reachable "
                       "Ollama (ODIN_OLLAMA_URL); returns counts, never touches the base.",
        "inputSchema": _obj({
            "root": _ROOT,
            "model": {"type": "string", "description": "Embedding model (default nomic-embed-text / ODIN_EMBED_MODEL)."},
            "url": {"type": "string", "description": "Ollama base URL (default ODIN_OLLAMA_URL or http://localhost:11434)."},
        }, required=["root"]),
    },
    {
        "name": "odin_search",
        "description": "Semantic retrieval: top-k derived docs by cosine similarity "
                       "to the query, over the disposable embedding sidecar (T-087). "
                       "The AI-facing companion to the AI-free `odin_find` floor — it "
                       "crosses the reader-vocabulary gap find cannot (e.g. "
                       "'illness'->the vet exam; ADR-0014, T-044). It only PROPOSES "
                       "candidates (ADR-0027 §2): each hit is a doc to READ, never a "
                       "citation, never provenance — ground answers in the actual "
                       "sources. Empty until `odin_reindex` has run. Prefer `odin_find` "
                       "when the query is a literal token; reach here for meaning/synonyms.",
        "inputSchema": _obj({
            "root": _ROOT,
            "query": {"type": "string", "description": "A natural-language / concept query (meaning, not just tokens)."},
            "k": {"type": "integer", "description": "How many candidates to propose (default 10)."},
            "model": {"type": "string", "description": "Override the query model; the index's own model still wins for coherence."},
            "url": {"type": "string", "description": "Ollama base URL (default ODIN_OLLAMA_URL or http://localhost:11434)."},
        }, required=["root", "query"]),
    },
    {
        "name": "odin_retrieve",
        "description": "Unified retrieval — the DEFAULT way to find things: unions "
                       "semantic candidates (meaning) with `find` hits (literal), "
                       "deduped, so you never miss a synonym OR an exact token. It "
                       "ALWAYS answers and never errors on a down backend: the "
                       "fallback to the AI-free `find` floor is MECHANICAL (inside "
                       "the call), so it can't be forgotten. Transparent about it — "
                       "the result's `via`/`backend` say whether semantics ran or it "
                       "degraded to find (Ollama down / no index). Still proposes only "
                       "(ADR-0027 §2); read the sources to ground. Prefer this over "
                       "`odin_search`/`odin_find` unless you specifically want just one.",
        "inputSchema": _obj({
            "root": _ROOT,
            "query": {"type": "string", "description": "A natural-language or literal query — both retrievers run."},
            "k": {"type": "integer", "description": "Semantic candidates to union in (default 10); find hits are added whole."},
            "model": {"type": "string", "description": "Override the query model; the index's own model still wins for coherence."},
            "url": {"type": "string", "description": "Ollama base URL (default ODIN_OLLAMA_URL or http://localhost:11434)."},
        }, required=["root", "query"]),
    },
    {
        "name": "odin_usage_log",
        "description": "Record a usage entry for an AI-heavy ADAPTER verb — `ask`, "
                       "`review`, `synthesize` — that the Core never sees itself, so "
                       "the ledger can measure the real token spenders (T-088). Call "
                       "it AFTER the verb. Pass `scope` = the doc/source ids the verb "
                       "read; the Core computes their byte-footprint deterministically "
                       "as an honest cost proxy. Add `tokens` ONLY when the harness "
                       "actually exposes a real count (/cost, an API usage field, "
                       "subagent metadata) — never guess; omit it otherwise. Feeds "
                       "`odin usage`, so review cadence can be tuned by evidence.",
        "inputSchema": _obj({
            "root": _ROOT,
            "op": {"type": "string", "description": "The verb measured: ask | review | synthesize."},
            "scope": {"type": "array", "items": {"type": "string"},
                      "description": "Doc/source ids the verb read; Core sums their readable bytes."},
            "bytes_in": {"type": "integer", "description": "Override the computed scope byte-footprint."},
            "bytes_out": {"type": "integer", "description": "Bytes the verb produced (answer/insight length)."},
            "tokens": {"type": "integer", "description": "REAL token count when the harness exposes it; omit to leave null (do not estimate)."},
            "note": {"type": "string", "description": "Optional short label (e.g. the scope/project)."},
        }, required=["root", "op"]),
    },
    {
        "name": "odin_refresh",
        "description": "Best-effort **warm** of the disposable semantic index (T-091): "
                       "embed any doc changed since the last embed, prune the gone ones. "
                       "Call it at the END of an `ingest` so what you just added is "
                       "searchable *now* — the next `odin_retrieve` is instant instead of "
                       "paying a cold-load. WRITE-ONLY and NEVER errors: no backend → a "
                       "clean no-op with a status, so no try/except needed (unlike "
                       "`odin_reindex`, which raises). It is a pure optimization — safe to "
                       "skip, because `odin_retrieve` self-heals (T-090); this only moves "
                       "the embed cost off the first query. Returns {status: clean|current|"
                       "stale, embedded, pruned, warning}. Relay `warning` if present.",
        "inputSchema": _obj({
            "root": _ROOT,
            "model": {"type": "string", "description": "Embedding model (default nomic-embed-text / the index's own)."},
            "url": {"type": "string", "description": "Ollama base URL (default ODIN_OLLAMA_URL or http://localhost:11434)."},
        }, required=["root"]),
    },
]

_TOOL_NAMES = {t["name"] for t in TOOLS}


# --------------------------------------------------------------------------- #
# 2. dispatch — the pure MCP-args -> Core-call mapping (no transport here).
#    This is the layer the eval drives; it must produce exactly the same base a
#    CLI invocation of the same ops would (ADR-0022 deliverable d).
# --------------------------------------------------------------------------- #
def _capture(root, p):
    """capture vs capture_file, mirroring the CLI main() branch + recoverable override."""
    origin = {"system": p["origin_system"], "ref": p["origin_ref"]}
    if p.get("recoverable") is not None:
        origin["recoverable"] = p["recoverable"]
    when = core._now()
    if p.get("source_file"):
        src = Path(p["source_file"])
        return core.capture_file(root, p["id"], src.read_bytes(),
                                 p.get("filename") or src.name, origin=origin,
                                 tier=p.get("tier", "full"),
                                 capture_reason=p.get("reason"), when=when,
                                 force_new=bool(p.get("force_new")))
    if p.get("body") is None:
        raise ValueError("capture needs `body` (text source) or `source_file` (bytes)")
    return core.capture(root, p["id"], p["body"], origin=origin,
                        tier=p.get("tier", "full"),
                        capture_reason=p.get("reason"), when=when,
                        force_new=bool(p.get("force_new")))


def _lint(root):
    """Structured lint — the Linter's findings without the CLI's printing/exit-code.
    Same load+check the CLI `run()` does; shaped for a machine caller."""
    linter = muninn_lint.Linter(Path(root))
    linter.load()
    linter.check()
    errors = [{"rule": f.rule, "message": f.message, "path": f.path}
              for f in linter.findings if f.severity == "error"]
    warnings = [{"rule": f.rule, "message": f.message, "path": f.path}
                for f in linter.findings if f.severity == "warn"]
    n_docs = len([d for d in linter.docs if d.kind != "manifest"])
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "n_docs": n_docs, "fingerprint": linter.content_fingerprint()}


# op name -> (Core callable via a lambda over (root, params)); each returns
# a json-serializable result. Kept declarative so the surface is auditable.
_DISPATCH = {
    "odin_init": lambda root, p: core.init(root, name=p.get("name"), when=core._now()),
    "odin_capture": _capture,
    "odin_dedup_check": lambda root, p: core.dedup_check(
        root, id=p.get("id"), source_file=p.get("source_file"),
        filename=p.get("filename"), origin_ref=p.get("origin_ref")),
    "odin_source_status": lambda root, p: core.source_status(root, p["id"]),
    "odin_derive": lambda root, p: core.write_derived(
        root, p["id"], body=p["body"], sources=p["sources"], title=p["title"],
        abstract=p.get("abstract"), type=p.get("type", "summary"),
        derivation=p.get("derivation"), as_of=p.get("as_of"), derived_at=core._now()),
    "odin_stage_candidate": lambda root, p: core.stage_candidate(
        root, p["id"], body=p["body"], sources=p["sources"], title=p["title"],
        abstract=p.get("abstract"), proposed_kind=p.get("proposed_kind", "insight"),
        derivation=p.get("derivation"), as_of=p.get("as_of"), staged_at=core._now()),
    "odin_list_candidates": lambda root, p: core.list_candidates(root),
    "odin_status": lambda root, p: core.status(root, as_of=p.get("as_of")),
    "odin_promote_candidate": lambda root, p: core.promote_candidate(
        root, p["id"], new_id=p.get("new_id"), into=p.get("into"),
        derivation=p.get("derivation"), derived_at=core._now()),
    "odin_decline_candidate": lambda root, p: core.decline_candidate(
        root, p["id"], reason=p.get("reason"), declined_at=core._now()),
    "odin_index": lambda root, p: str(core.regenerate_index(root)),
    "odin_find": lambda root, p: core.find(root, p["query"], type=p.get("type")),
    "odin_project": lambda root, p: core.write_project(
        root, p["id"], title=p.get("title"), add_members=p.get("add_members"),
        scope=p.get("scope"), description=p.get("description"),
        maintained_by=p.get("maintained_by"), tags=p.get("tags"), when=core._now()),
    "odin_resolve": lambda root, p: core.resolve_scope(root, p.get("project")),
    "odin_record_decision": lambda root, p: core.record_decision(
        root, p["id"], body=p["body"], title=p.get("title"),
        status=p.get("status"), evidence=p.get("evidence"),
        amend=bool(p.get("amend")), when=core._now()),
    "odin_fingerprint": lambda root, p: core.fingerprint(root),
    "odin_lint": lambda root, p: _lint(root),
    "odin_reindex": lambda root, p: semantic.reindex(
        root, model=p.get("model") or semantic.DEFAULT_MODEL,
        url=p.get("url") or semantic.DEFAULT_URL),
    "odin_search": lambda root, p: semantic.search(
        root, p["query"], k=p.get("k", 10), model=p.get("model"),
        url=p.get("url") or semantic.DEFAULT_URL),
    "odin_retrieve": lambda root, p: semantic.retrieve(
        root, p["query"], k=p.get("k", 10), model=p.get("model"),
        url=p.get("url") or semantic.DEFAULT_URL),
    "odin_usage_log": lambda root, p: core.usage_log(
        root, p["op"], scope=p.get("scope"), bytes_in=p.get("bytes_in"),
        bytes_out=p.get("bytes_out", 0), tokens=p.get("tokens"), note=p.get("note")),
    "odin_refresh": lambda root, p: semantic.refresh(
        root, model=p.get("model"), url=p.get("url") or semantic.DEFAULT_URL),
}


def dispatch(op, params):
    """Invoke a Core op by MCP tool name. Pure: maps `params` onto the Core call
    and returns its json-serializable result. Raises KeyError for an unknown op
    and lets the Core's own ValueErrors (invariant rejections) propagate — the
    transport layer turns those into a tool error, never a silent success."""
    if op not in _DISPATCH:
        raise KeyError(f"unknown tool {op!r}")
    params = params or {}
    root = params.get("root")
    if root is None:
        raise ValueError("every op needs `root` (the Muninn directory)")
    return _DISPATCH[op](root, params)


def _note_usage(op, params):
    """Record the byte-footprint of a write op to the disposable usage ledger
    (ADR-0027) — the MCP transport's equivalent of the CLI `main()` hook, so the
    plugin path measures usage too. Best-effort; never affects the result and is
    kept OUT of `dispatch()` so that stays pure (the ADR-0022 equality test)."""
    try:
        root = (params or {}).get("root")
        if root is None:
            return
        if op == "odin_capture":
            body = params.get("body")
            if body is not None:
                n = len(body.encode("utf-8"))
            elif params.get("source_file"):
                n = Path(params["source_file"]).stat().st_size
            else:
                n = 0
            core.log_usage(root, "capture", bytes_out=n, id=params.get("id"))
        elif op == "odin_derive":
            srcs = params.get("sources") or []
            core.log_usage(root, "derive",
                           bytes_in=sum(core._source_bytes(root, s) for s in srcs),
                           bytes_out=len((params.get("body") or "").encode("utf-8")),
                           id=params.get("id"), type=params.get("type", "summary"))
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# 3. stdio JSON-RPC 2.0 loop — stdlib only, so the plugin ships no `mcp` wheel.
#    Handles the MCP lifecycle (initialize / tools/list / tools/call / ping).
# --------------------------------------------------------------------------- #
def _result(id, result):
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _error(id, code, message):
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def handle_message(msg):
    """Handle one JSON-RPC request/notification; return a response dict, or None
    for a notification (no reply). Kept pure/synchronous for direct testing."""
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        proto = params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION
        return _result(mid, {
            "protocolVersion": proto,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })

    # notifications (no `id`) — acknowledge by staying silent
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return _result(mid, {})

    if method == "tools/list":
        return _result(mid, {"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in _TOOL_NAMES:
            return _error(mid, -32602, f"unknown tool: {name!r}")
        try:
            out = dispatch(name, arguments)
        except Exception as exc:  # invariant rejection / bad args -> tool error,
            # surfaced to the client (never a silent success). ADR-0022 §2.
            return _result(mid, {
                "content": [{"type": "text",
                             "text": f"{type(exc).__name__}: {exc}"}],
                "isError": True,
            })
        _note_usage(name, arguments)  # disposable usage ledger (ADR-0027); best-effort
        text = json.dumps(out, ensure_ascii=False, default=str)
        return _result(mid, {
            "content": [{"type": "text", "text": text}],
            "structuredContent": out if isinstance(out, dict) else {"result": out},
            "isError": False,
        })

    # Unknown method. Only error on requests (with an id); ignore stray notifications.
    if mid is None:
        return None
    return _error(mid, -32601, f"method not found: {method!r}")


def serve(stdin=None, stdout=None):
    """Newline-delimited JSON-RPC over stdio (the MCP stdio transport). Reads one
    JSON message per line, writes one response per line."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for stream in (stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # codepage-independent (see CLI)
        except (AttributeError, ValueError):
            pass

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps(_error(None, -32700, "parse error")) + "\n")
            stdout.flush()
            continue
        response = handle_message(msg)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False, default=str) + "\n")
            stdout.flush()


def main(argv=None):
    serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
