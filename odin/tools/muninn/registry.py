"""The op registry (T-113): ONE declarative table generating the CLI and the MCP surface.

Split from muninn_core.py (T-122); muninn_core remains the facade.
"""
import sys
import time
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from . import util  # noqa: E402  (module-attr access = the patch point)
from .candidates import decline_candidate, list_candidates, promote_candidate, stage_candidate  # noqa: E402
from .capture import anchor, anchor_check, capture, capture_file, capture_repo, dedup_check, log_drift_check, retier, source_status  # noqa: E402
from .decisions import lint_report, record_decision, status  # noqa: E402
from .derive import log_challenge, relink, stamp_derived, supersede, write_derived  # noqa: E402
from .projections import connector_projection, drift_worklist, find, fingerprint, read_doc, regenerate_index, reproject, resolve_scope, write_project  # noqa: E402
from .scaffold import init  # noqa: E402
from .usage import _source_bytes, log_usage, usage_html, usage_log, usage_report  # noqa: E402


# --------------------------------------------------------------------------- #
# CLI — the command surface the adapter Skill (and a human) invoke
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# The op registry (T-113) — ONE declarative table per module, from which BOTH
# public surfaces are generated: the CLI subcommands (below) and the MCP tool
# schemas + dispatch (odin_mcp.py). The same ~20 ops used to be hand-declared
# three times (argparse tree, MCP TOOLS, MCP _DISPATCH) and had already
# drifted — five CLI verbs had no MCP tool. Declared once, drift is
# structurally impossible; tests/test_op_registry.py pins the equality.
#
# Param spec keys: type/description/enum/items/default (the JSON-Schema
# projection) · required · cli {positional, nargs, flag, append, parse, join,
# tristate} (the argparse projection) · cli_only (never in the MCP schema).
# Op spec keys: description (MCP; model-facing) · help (short CLI line) ·
# params · handler(root, p) · usage(root, p, res) (best-effort ledger hook) ·
# presenter(res) (CLI human rendering) · cli {body_param, body_skip_if}.
# --------------------------------------------------------------------------- #
_ROOT_P = {"type": "string", "description": "Path to the Muninn root directory.",
           "required": True, "cli": {"positional": True}}


_ID_POS = {"type": "string", "description": "Stable doc/source id.",
           "required": True, "cli": {"positional": True}}


def _op_capture(root, p):
    """capture vs capture_file — the shared param→Core mapping both surfaces use."""
    origin = {"system": p["origin_system"], "ref": p["origin_ref"]}
    if p.get("recoverable") is not None:
        origin["recoverable"] = p["recoverable"]
    if p.get("captured_by"):
        origin["captured_by"] = p["captured_by"]
    if p.get("upstream_ref"):
        origin["upstream_ref"] = p["upstream_ref"]
    when = util._now()
    if p.get("source_file"):
        src = Path(p["source_file"])
        return capture_file(root, p["id"], src.read_bytes(),
                            p.get("filename") or src.name, origin=origin,
                            tier=p.get("tier", "full"),
                            capture_reason=p.get("reason"), when=when,
                            force_new=bool(p.get("force_new")),
                            upstream_identity=p.get("upstream_identity"))
    if p.get("body") is None:
        raise ValueError("capture needs `body` (text source) or `source_file` (bytes)")
    return capture(root, p["id"], p["body"], origin=origin,
                   tier=p.get("tier", "full"), capture_reason=p.get("reason"),
                   when=when, force_new=bool(p.get("force_new")),
                   upstream_identity=p.get("upstream_identity"))


def _usage_capture(root, p, res, duration_ms=None):
    body = p.get("body")
    if body is not None:
        n = len(body.encode("utf-8"))
    elif p.get("source_file"):
        n = Path(p["source_file"]).stat().st_size
    else:
        n = 0
    log_usage(root, "capture", bytes_out=n, id=p.get("id"), action=res.get("action"),
              **({"duration_ms": duration_ms} if duration_ms is not None else {}))


def _usage_derive(root, p, res, duration_ms=None):
    log_usage(root, "derive",
              bytes_in=sum(_source_bytes(root, s) for s in (p.get("sources") or [])),
              bytes_out=len((p.get("body") or "").encode("utf-8")),
              id=p.get("id"), type=p.get("type", "summary"),
              **({"duration_ms": duration_ms} if duration_ms is not None else {}))


def _op_usage(root, p):
    """The usage report; with the CLI-only `--html`, also write the self-contained
    HTML view of the ledger (T-123) and echo where it landed."""
    rep = usage_report(root)
    if p.get("html"):
        out = Path(p["html"])
        out.write_text(usage_html(root), encoding="utf-8")
        rep["html_report"] = str(out)
    return rep


def _show_list_candidates(rep):
    for c in rep["pending"]:
        print(f"{c['id']}  ({c['proposed_kind']})  {c['title']}")
    print(f"({rep['pending_count']} pending, {rep['declined_count']} declined)")


def _show_status(rep):
    print(f"freshness: {rep['freshness']}  ·  {rep['pending_candidates']} candidate(s) "
          f"·  {len(rep['stale'])} stale  ·  {rep['captures_since_lint']} capture(s) "
          f"since lint  ·  {len(rep['aged'])} aging")
    for a in rep["aged"]:
        print(f"  aging: {a['id']}  (as_of {a['as_of']}, {a['days_old']}d old)")
    for sid in rep["stale"]:
        print(f"  stale: {sid}")


def _show_find(res):
    for r in res["matches"]:
        print(f"{r['kind']:8} {r['id']}  —  {r['title']}")
    print(f"({res['count']} match(es))")


def _show_drift_worklist(r):
    """The T-145 'screen': one line per item, oldest contact first, and the
    scope disclosure the empty case must never lose (T-147)."""
    for it in r["items"]:
        when = it["last_checked"] or "never-checked"
        verdict = f" ({it['last_verdict']})" if it.get("last_verdict") else ""
        print(f"{it['id']}  {it['origin_system']}  tier={it['tier']}  "
              f"captured={it['captured_at']}  last-checked={when}{verdict}")
    tail = (f"({r['in_scope']} in scope [{r['scope']}]; "
            f"{r['outside_scope']} eligible outside scope")
    if r.get("age_filtered"):
        tail += f"; {r['age_filtered']} newer than the older-than cutoff"
    print(tail + ")")


def _show_resolve(r):
    for mid in r["members"]:
        print(mid)
    scope_label = r["scope"] if r["scope"] else "(whole base)"
    gv = ", ".join(r["global_views"]) or "(none)"
    print(f"({len(r['members'])} member(s); scope {scope_label}; "
          f"global views unioned: {gv})")


def _show_connectors(conns):
    for c in conns:
        ref = f" {c['ref']}" if c["ref"] else ""
        print(f"{c['system']}{ref}  <- {', '.join(c['referenced_by'])}")
    print(f"({len(conns)} connector(s) across the scope:global landscape)")


def _show_usage(rep):
    for op, agg in sorted(rep["by_op"].items()):
        tok = str(agg.get("tokens", 0)) if agg.get("tokens_n") else "n/a"
        print(f"{op:16} {agg['count']:>5}x  in={agg['bytes_in']:>10}  "
              f"out={agg['bytes_out']:>10}  tok={tok:>8}")
    print(f"({rep['total_ops']} op(s) logged)")


def _parse_connector(spec):
    system, _, ref = spec.partition("=")
    return {"system": system.strip(), "ref": ref.strip() or None}


def _parse_surface(spec):
    label, _, globs = spec.partition("=")
    return {"label": label.strip(),
            "globs": [g.strip() for g in globs.split(",") if g.strip()]}


OPS = {
    "init": {
        "help": "scaffold a new Muninn",
        "description": "Scaffold a new Muninn (manifest, layout, index, the "
                       "canonical global view). No-op if one already exists.",
        "params": {
            "root": _ROOT_P,
            "name": {"type": "string",
                     "description": "Display name (defaults to the dir name)."},
            "allow_tool_root": {"type": "boolean", "cli_only": True,
                                "description": "scaffold even if the target is inside "
                                               "ODIN's own checkout (overrides the "
                                               "soft-warn tool-repo guard; e.g. dogfooding)"},
        },
        "handler": lambda root, p: init(root, name=p.get("name"),
                                        allow_tool_root=bool(p.get("allow_tool_root")),
                                        when=util._now()),
    },
    "capture": {
        "help": "capture a source (text via --file/stdin, or original bytes "
                "via --source-file)",
        "description": "Capture a source (immutable, provenance-bearing). Provide "
                       "`body` for a text source, OR `source_file` for original "
                       "bytes (PDF/image/…; a text aid is extracted per ADR-0010). "
                       "Byte-identical content dedups; changed bytes of an existing "
                       "id make a new version. Changed bytes under a NEW id whose "
                       "origin_ref already belongs to a captured source are refused "
                       "(a silent lineage split, T-045) — capture under the matching "
                       "id to version it, or set force_new to declare the split. "
                       "Sources are authoritative and never chained from.",
        "params": {
            "root": _ROOT_P,
            "id": {"type": "string", "description": "Stable source id (e.g. src-…).",
                   "required": True, "cli": {"positional": True}},
            "origin_system": {"type": "string", "required": True,
                              "description": "Where it came from (file, url, connector…)."},
            "origin_ref": {"type": "string", "required": True,
                           "description": "The locator within that system (filename, URL, …)."},
            "body": {"type": "string",
                     "description": "Text-source content. Mutually exclusive with source_file."},
            "source_file": {"type": "string",
                            "description": "Path to a file whose ORIGINAL BYTES are the source."},
            "filename": {"type": "string",
                         "description": "Canonical filename hint (defaults to source_file's name)."},
            "tier": {"type": "string", "enum": ["full", "reference"], "default": "full",
                     "description": "full (copy held) or reference (locator only)."},
            "reason": {"type": "string",
                       "description": "Required for a reference-tier capture (ADR-0003)."},
            "recoverable": {"type": "boolean", "cli": {"tristate": True},
                            "description": "Is the original re-fetchable via origin.ref? "
                                           "(self-heal, T-066)."},
            "captured_by": {"type": "string",
                            "description": "Producer of this record, <faculty>/<tool>@<version> "
                                           "(ADR-0001). Mandatory disclosure when the body is a "
                                           "model rendering rather than the source's own data "
                                           "(T-131)."},
            "force_new": {"type": "boolean",
                          "description": "Deliberately start a NEW lineage although origin_ref "
                                         "matches an existing source (the split is logged; T-045)."},
            "upstream_ref": {"type": "string",
                             "description": "For a PARTIAL capture (an excerpt of a larger "
                                            "whole): the whole's clean locator (ADR-0039). "
                                            "Presence declares the source an excerpt; "
                                            "origin_ref itself must stay a distinct, "
                                            "excerpt-qualified locator (T-045)."},
            "upstream_identity": {"type": "string",
                                  "description": "The whole's content identity as of this "
                                                 "read — git-blob:<sha1> | sha256:<hex64> — "
                                                 "recorded per-version; makes drift-check "
                                                 "exact for this excerpt (ADR-0039). "
                                                 "Requires upstream_ref."},
        },
        "handler": _op_capture,
        "usage": _usage_capture,
        "cli": {"body_param": "body", "body_skip_if": ("source_file",)},
    },
    "dedup-check": {
        "help": "dry-run dedup: report already-captured/changed/new for a "
                "candidate WITHOUT writing (explore preview; ADR-0020)",
        "description": "Dry-run dedup preview: report already-captured / changed / "
                       "new for a candidate WITHOUT writing (explore preview, "
                       "ADR-0020). Give `source_file` (content-hash rung) or "
                       "`origin_ref` (locator rung for reference-tier).",
        "params": {
            "root": _ROOT_P,
            "id": {"type": "string",
                   "description": "Candidate's intended id (enables changed-vs-new)."},
            "source_file": {"type": "string",
                            "description": "Candidate file whose bytes to hash."},
            "filename": {"type": "string", "description": "Canonical filename hint."},
            "origin_ref": {"type": "string",
                           "description": "Locator to match when no bytes are held."},
        },
        "handler": lambda root, p: dedup_check(
            root, id=p.get("id"), source_file=p.get("source_file"),
            filename=p.get("filename"), origin_ref=p.get("origin_ref")),
    },
    "source-status": {
        "help": "report a source's deterministic facts (tier, bytes-present, "
                "recoverable, origin.ref) for fetch/self-heal decisions (T-066)",
        "description": "Read-only deterministic facts about a source (tier, "
                       "version, whether bytes are held, recoverable, origin.ref) "
                       "— the ground truth a fetch/self-heal decision rests on (T-066).",
        "params": {"root": _ROOT_P,
                   "id": {"type": "string", "description": "The source id.",
                          "required": True, "cli": {"positional": True}}},
        "handler": lambda root, p: source_status(root, p["id"]),
    },
    "retier": {
        "help": "deliberately correct a source's capture facts — tier "
                "(full|reference, T-134) and/or recoverable (the drift-check "
                "never-retry mark, T-136)",
        "description": "Correct a source's capture tier. The tier describes what "
                       "the base HOLDS (ADR-0003): full = the complete artifact "
                       "bytes are the canonical record (even when the upstream "
                       "record is live — evolution is versioning's job); "
                       "reference = only a locator and at most a stand-in are "
                       "held (requires reason). Changes ONLY capture/"
                       "capture_reason; bytes, hash, and history untouched, so "
                       "all provenance still verifies. Logged. Never hand-edit "
                       "meta.yml.",
        "params": {
            "root": _ROOT_P,
            "id": {"type": "string", "description": "The source id.",
                   "required": True, "cli": {"positional": True}},
            "tier": {"type": "string", "enum": ["full", "reference"],
                     "description": "The corrected tier."},
            "reason": {"type": "string",
                       "description": "capture_reason — required when tier is "
                                      "reference (ADR-0003 IFF)."},
            "recoverable": {"type": "boolean", "cli": {"tristate": True},
                            "description": "Correct origin.recoverable — False is "
                                           "the standing never-retry mark the "
                                           "drift-check sweep honors (T-136); flip "
                                           "True when the system returns."},
        },
        "handler": lambda root, p: retier(root, p["id"], p.get("tier"),
                                          reason=p.get("reason"),
                                          recoverable=p.get("recoverable")),
    },
    "anchor-check": {
        "help": "two-tier drift check of ONE anchored partial capture against "
                "a fetched upstream file (ADR-0039; read-only)",
        "description": "Check one anchored partial capture against its fetched "
                       "upstream whole (ADR-0039). Tier 1: recorded vs current "
                       "upstream_identity, raw opaque equality — equal → "
                       "upstream-unchanged (byte-certain, region included). "
                       "Tier 2 on mismatch: are the excerpt's chunks still in "
                       "the fetched text? All → upstream-changed-region-intact; "
                       "any missing → region-drifted (offer re-locate / "
                       "re-capture-as-version). No anchor → unanchored. "
                       "Read-only; fetching the upstream is the adapter's "
                       "consented reach (T-136).",
        "params": {
            "root": _ROOT_P,
            "id": _ID_POS,
            "upstream_file": {"type": "string", "required": True,
                              "description": "Path to the FETCHED current upstream "
                                             "whole (the adapter fetches; the Core "
                                             "compares)."},
        },
        "handler": lambda root, p: anchor_check(root, p["id"],
                                                upstream_file=p["upstream_file"]),
    },
    "anchor": {
        "help": "attach an upstream anchor to an existing partial capture "
                "(consented backfill; containment-verified FIRST; ADR-0039)",
        "description": "Attach an upstream anchor to an EXISTING partial capture "
                       "— the ADR-0039 backfill (relink/stamp precedent). Runs "
                       "the containment check FIRST and stamps origin."
                       "upstream_ref + the current version's upstream_identity/"
                       "anchored_at only when the held excerpt is contained in "
                       "the supplied upstream; a failure is reported, not "
                       "stamped (force + reason to overrule, logged). Bytes, "
                       "content_hash, version untouched — provenance verifies "
                       "unchanged. Idempotent.",
        "params": {
            "root": _ROOT_P,
            "id": _ID_POS,
            "upstream_ref": {"type": "string", "required": True,
                             "description": "Clean locator of the whole this "
                                            "excerpt was read from."},
            "upstream_file": {"type": "string", "required": True,
                              "description": "Path to the fetched current upstream "
                                             "whole to verify against and identify."},
            "form": {"type": "string", "enum": ["sha256", "git-blob"],
                     "default": "sha256",
                     "description": "Identity form to stamp (git-blob for "
                                    "git-backed upstreams: comparable against a "
                                    "remote with no fetch)."},
            "force": {"type": "boolean",
                      "description": "Stamp past a failed containment check "
                                     "(requires reason; logged)."},
            "reason": {"type": "string",
                       "description": "Why a forced anchor is honest (e.g. the "
                                      "missing chunks are the capture's own "
                                      "disclosure prose)."},
        },
        "handler": lambda root, p: anchor(root, p["id"],
                                          upstream_ref=p["upstream_ref"],
                                          upstream_file=p["upstream_file"],
                                          form=p.get("form", "sha256"),
                                          force=bool(p.get("force")),
                                          reason=p.get("reason")),
    },
    "drift-worklist": {
        "help": "enumerate the recoverable connector sources whose remote may "
                "have moved — the deterministic worklist for the consented "
                "drift-check sweep (T-136)",
        "description": "The drift-check sweep's deterministic worklist: "
                       "recoverable, connector-origin sources (local file/chat/"
                       "inbox never drift remotely). Default scope is EVERY "
                       "eligible source in the base (T-147); `project` narrows "
                       "to that project's members plus the global views (T-128). "
                       "The result always discloses `outside_scope` — eligible "
                       "sources the requested scope excluded — so a thin list "
                       "never reads as 'all current'. Items carry last_checked/"
                       "last_verdict joined from the drift log and sort oldest "
                       "contact first (T-145); `older_than` (e.g. '30d') keeps "
                       "only items due a check, counting what it drops in "
                       "`age_filtered`. Read-only: the fetch/compare/re-capture "
                       "that follow are adapter orchestration over fetch + "
                       "dedup-check + capture, always consented, never a daemon.",
        "params": {"root": _ROOT_P,
                   "project": {"type": "string",
                               "description": "Narrow to this project's members "
                                              "∪ the global views (T-128)."},
                   "older_than": {"type": "string",
                                  "description": "Keep only items whose last "
                                                 "contact (capture or check) is "
                                                 "older than this — <N>[d|w|h], "
                                                 "e.g. '30d'. The budget lever.",
                                  "cli": {"flag": "--older-than"}},
                   "all": {"type": "boolean",
                           "description": "Deprecated no-op (T-147): the full "
                                          "sweep is now the default."}},
        "handler": lambda root, p: drift_worklist(root, project=p.get("project"),
                                                  all=bool(p.get("all")),
                                                  older_than=p.get("older_than")),
        "presenter": _show_drift_worklist,
    },
    "drift-log": {
        "help": "record a completed drift-check sweep in the append-only log "
                "(the sweep's memory; T-136)",
        "description": "Append the drift-check outcome (same/changed/unreachable "
                       "counts + optional detail) to log.md — status reads the "
                       "latest entry for its quiet 'world last checked' line, and "
                       "the adapter reads recent entries to voice unreachable "
                       "streaks before offering the never-retry flip. Pass "
                       "`checked` with one <id>=<verdict> per item swept (T-145) "
                       "— it is what makes per-item last-checked ages "
                       "reconstructible; counts are tallied from it when omitted.",
        "params": {"root": _ROOT_P,
                   "same": {"type": "integer", "description": "Unchanged count "
                            "(tallied from `checked` when omitted)."},
                   "changed": {"type": "integer", "description": "Changed count "
                               "(tallied from `checked` when omitted)."},
                   "unreachable": {"type": "integer",
                                   "description": "Unreachable count (tallied "
                                                  "from `checked` when omitted)."},
                   "checked": {"type": "array", "items": {"type": "string"},
                               "description": "Per-item verdicts, one "
                                              "<id>=<verdict> each (same | "
                                              "changed | unreachable | a same-* "
                                              "variant), e.g. 'src-x=same'.",
                               "cli": {"flag": "--checked", "append": True}},
                   "detail": {"type": "string",
                              "description": "Optional ids/notes, e.g. "
                                             "'unreachable: src-x (2nd consecutive)'."}},
        "handler": lambda root, p: log_drift_check(
            root, same=p.get("same"), changed=p.get("changed"),
            unreachable=p.get("unreachable"), detail=p.get("detail"),
            checked=p.get("checked")),
    },
    "derive": {
        "help": "write a derived doc (body from --file or stdin)",
        "description": "Write a derived doc (summary/entity/concept/question/"
                       "insight) grounded ONLY in sources. Core copies each "
                       "source's current hash into provenance; a provenance id "
                       "that is not a real source is rejected (I3, no chaining). "
                       "`body` is the adapter-authored content. For an INSIGHT, "
                       "quoted spans are containment-verified (T-153): a "
                       "double-quoted span ≥15 chars on a line citing a "
                       "provenance source must appear in that source's text or "
                       "the write is refused — quote sources exactly, never "
                       "from a summary's paraphrase. A `question` doc may be "
                       "answered or explicitly OPEN (abstract leads 'OPEN — ', "
                       "T-154); regenerate re-derives it when answered.",
        "params": {
            "root": _ROOT_P,
            "id": {"type": "string", "description": "Stable derived-doc id.",
                   "required": True, "cli": {"positional": True}},
            "body": {"type": "string", "required": True,
                     "description": "The document body (adapter judgment)."},
            "sources": {"type": "array", "items": {"type": "string"}, "required": True,
                        "description": "Grounding source ids (≥1). Must be sources, "
                                       "never derived docs.",
                        "cli": {"flag": "--source", "append": True}},
            "title": {"type": "string", "required": True, "description": "Doc title."},
            "abstract": {"type": "string", "description": "Skimmable abstract."},
            "type": {"type": "string", "default": "summary",
                     "enum": ["summary", "entity", "concept", "question", "insight"],
                     "description": "Derived doc type."},
            "derivation": {"type": "string",
                           "enum": ["extracted", "model-read", "synthesis"],
                           "description": "How it was derived (e.g. synthesis) — sets "
                                          "the integrity rung."},
            "connectors": {"type": "array", "items": {"type": "object"},
                           "description": "Connectors this landscape doc references "
                                          "but hasn't ingested from — [{system, ref}] "
                                          "(ADR-0021 §2 / T-070).",
                           "cli": {"flag": "--connector", "append": True,
                                   "parse": _parse_connector,
                                   "metavar": "system[=ref]"}},
            "as_of": {"type": "string",
                      "description": "ISO date a TIME-RELATIVE claim was true — "
                                     "surfaced/aged on-load by `status`, never by lint "
                                     "(ADR-0034). Prefer anchoring on the immutable "
                                     "datum + rule; this is the residual."},
        },
        "handler": lambda root, p: write_derived(
            root, p["id"], body=p["body"], sources=p["sources"], title=p["title"],
            abstract=p.get("abstract"), type=p.get("type", "summary"),
            derivation=p.get("derivation"), as_of=p.get("as_of"),
            connectors=p.get("connectors") or None, derived_at=util._now()),
        "usage": _usage_derive,
        "cli": {"body_param": "body"},
    },
    "stage-candidate": {
        "help": "stage an emergent grounded inference for review (NOT admitted "
                "to the base; deduped vs pending + declined; ADR-0033)",
        "description": "Stage an emergent grounded inference for later BATCHED "
                       "review (ADR-0033). NOT admitted to the base — grounded "
                       "sources-only (no chaining), deduped vs pending and vs "
                       "declined tombstones (a sticky decline won't re-nag unless "
                       "a cited source advances).",
        "params": {
            "root": _ROOT_P,
            "id": {"type": "string", "description": "Candidate id (must start 'cand-').",
                   "required": True, "cli": {"positional": True}},
            "body": {"type": "string", "required": True,
                     "description": "The grounded inference, cited to its sources."},
            "sources": {"type": "array", "items": {"type": "string"}, "required": True,
                        "description": "Grounding source ids (≥1). Sources only — "
                                       "never a derived doc.",
                        "cli": {"flag": "--source", "append": True}},
            "title": {"type": "string", "required": True, "description": "Title."},
            "abstract": {"type": "string", "description": "Skimmable abstract."},
            "proposed_kind": {"type": "string", "default": "insight",
                              "enum": ["summary", "entity", "concept", "question",
                                       "insight"],
                              "description": "What it becomes on promote."},
            "derivation": {"type": "string",
                           "enum": ["extracted", "model-read", "synthesis"],
                           "description": "The honest rung — set it, don't presume: a "
                                          "single-source deterministic computation (an "
                                          "age) is `extracted`, not `synthesis` "
                                          "(cross-source generative). Unset → the "
                                          "reviewer sets it at promotion (T-107)."},
            "as_of": {"type": "string",
                      "description": "ISO date IF this candidate states a TIME-RELATIVE "
                                     "result — aged on-load once promoted as its OWN "
                                     "doc; such a candidate can't be folded (T-109). "
                                     "Prefer the datum + rule (no as_of)."},
        },
        "handler": lambda root, p: stage_candidate(
            root, p["id"], body=p["body"], sources=p["sources"], title=p["title"],
            abstract=p.get("abstract"),
            proposed_kind=p.get("proposed_kind", "insight"),
            derivation=p.get("derivation"), as_of=p.get("as_of"), staged_at=util._now()),
        "cli": {"body_param": "body"},
    },
    "list-candidates": {
        "help": "list pending candidates + declined count (the on-load / "
                "review-candidates read; ADR-0033)",
        "description": "List pending candidates + the declined count — the "
                       "on-load / review-candidates read (ADR-0033).",
        "params": {"root": _ROOT_P},
        "handler": lambda root, p: list_candidates(root),
        "presenter": _show_list_candidates,
    },
    "promote-candidate": {
        "help": "admit a pending candidate into the base as a derived doc "
                "(reuses write_derived; ADR-0033)",
        "description": "Admit a pending candidate into the base. Default: promote "
                       "as a new first-class derived doc (reuses derive; default "
                       "an insight; ADR-0033). Or `into=<doc-id>` to FOLD it into "
                       "an existing derived doc as a literal insert (append its "
                       "authored block, union sources, consume the candidate; "
                       "ADR-0035) — `regenerate` re-coalesces later.",
        "params": {
            "root": _ROOT_P,
            "id": {"type": "string", "description": "The cand-… id to promote.",
                   "required": True, "cli": {"positional": True}},
            "new_id": {"type": "string",
                       "description": "Target derived id for a NEW doc (default: swap "
                                      "cand- for the kind prefix)."},
            "into": {"type": "string",
                     "description": "Existing derived doc id to FOLD into instead of "
                                    "writing new (ADR-0035)."},
            "derivation": {"type": "string",
                           "enum": ["extracted", "model-read", "synthesis"],
                           "description": "The honest rung, set at promotion (T-107)."},
        },
        "handler": lambda root, p: promote_candidate(
            root, p["id"], new_id=p.get("new_id"), into=p.get("into"),
            derivation=p.get("derivation"), derived_at=util._now()),
    },
    "decline-candidate": {
        "help": "decline a pending candidate — a fingerprint-keyed tombstone in "
                "candidates/declined/ (never deleted; ADR-0033)",
        "description": "Decline a pending candidate — a fingerprint-keyed "
                       "tombstone (never deleted; won't re-nag unless a cited "
                       "source advances). ADR-0033.",
        "params": {
            "root": _ROOT_P,
            "id": {"type": "string", "description": "The cand-… id to decline.",
                   "required": True, "cli": {"positional": True}},
            "reason": {"type": "string", "description": "Why (recorded on the tombstone)."},
        },
        "handler": lambda root, p: decline_candidate(
            root, p["id"], reason=p.get("reason"), declined_at=util._now()),
    },
    "status": {
        "help": "on-load status surface: freshness · stale · pending candidates "
                "· captures-since-lint · aged time-relative facts (ADR-0034)",
        "description": "On-load status surface (ADR-0034): freshness (fingerprint "
                       "vs last lint), stale docs, pending candidates, "
                       "captures-since-lint, and aged time-relative (`as_of`) docs "
                       "— read-only, one call for a single consolidated nudge. "
                       "Pass `as_of` (today) to age as_of docs.",
        "params": {
            "root": _ROOT_P,
            "as_of": {"type": "string",
                      "description": "Today's date (ISO) — enables date-aging of "
                                     "as_of docs."},
        },
        "handler": lambda root, p: status(root, as_of=p.get("as_of")),
        "presenter": _show_status,
    },
    "index": {
        "help": "rebuild index.md as a pure projection of frontmatter (SPEC §5.3)",
        "description": "Rebuild index.md as a pure projection of document "
                       "frontmatter (deterministic, idempotent). No prose authored.",
        "params": {"root": _ROOT_P},
        "handler": lambda root, p: str(regenerate_index(root)),
    },
    "fingerprint": {
        "help": "the content fingerprint over all registered docs (ADR-0005)",
        "description": "The content fingerprint over all registered docs (the "
                       "freshness hash; ADR-0005). Same value the linter computes.",
        "params": {"root": _ROOT_P},
        "handler": lambda root, p: fingerprint(root),
    },
    "lint": {
        "help": "run every invariant check over the Muninn",
        "description": "Run every invariant check over the Muninn. Returns {ok, "
                       "errors, warnings, n_docs, fingerprint}. 'The Muninn lints "
                       "clean' is the definition of done — this is the backstop "
                       "that makes the MCP transport safe (ADR-0022 §2).",
        "params": {"root": _ROOT_P},
        "handler": lambda root, p: lint_report(root),
    },
    "stamp": {
        "help": "backfill derived-doc self_hashes (self-heal a base whose docs "
                "predate self-hashing; ADR-0029)",
        "description": "Backfill `self_hash` on every derived doc that lacks one, "
                       "from its CURRENT content (ADR-0029) — the lightweight "
                       "self-heal for a base whose docs predate self-hashing. "
                       "Deterministic, no model, no content change; idempotent. "
                       "Never re-stamps a doc that already has one (a mismatch "
                       "there is a real out-of-band edit for L19 to flag).",
        "params": {"root": _ROOT_P},
        "handler": lambda root, p: stamp_derived(root),
    },
    "reproject": {
        "help": "re-render every project page: seed the global hub if missing + "
                "refresh the Always-in-scope pointer (T-057)",
        "description": "Regenerate-class maintenance op (T-057): re-render every "
                       "project page from its members' own title/abstract, seed "
                       "the canonical global hub if missing, and refresh each "
                       "page's Always-in-scope pointer. Deterministic projection "
                       "— no authored prose is touched; safe to run anytime.",
        "params": {"root": _ROOT_P},
        "handler": lambda root, p: reproject(root),
    },
    "relink": {
        "help": "upgrade bare [id] citation spans to linked citations "
                "[id](path) across derived docs + decisions (ADR-0038)",
        "description": "Regenerate-class maintenance op (ADR-0038): rewrite bare "
                       "`[known-id]` citation spans in derived docs and decisions "
                       "into linked citations `[id](relative-path)` — id stays "
                       "the label, the target is the doc's readable file. "
                       "Idempotent; already-linked spans and unknown ids are "
                       "untouched; `self_hash` is re-stamped on edited docs so "
                       "L19 stays clean. Run once to upgrade a base that predates "
                       "linked citations; the fingerprint moves (lint after).",
        "params": {"root": _ROOT_P},
        "handler": lambda root, p: relink(root),
    },
    "capture-repo": {
        "help": "capture a repo as a constitution-grounded reference source "
                "(README/ARCHITECTURE/ADRs/contract/manifests/topology; ADR-0028)",
        "description": "Capture a repository as a REFERENCE-tier source grounded "
                       "in its constitution (ADR-0028): a deterministic manifest "
                       "of the repo's intent-bearing surfaces (README, "
                       "ARCHITECTURE, in-repo ADRs, public contract, identity "
                       "manifests, top-level shape) — NOT its full tree, NOT "
                       "HEAD. Its content_hash moves on a constitutional "
                       "amendment and stays flat under implementation churn. "
                       "Building the manifest is a faithful transform; the "
                       "mental-model inference is the adapter's model-read.",
        "params": {
            "root": _ROOT_P,
            "id": {"type": "string", "description": "Stable source id (e.g. src-…).",
                   "required": True, "cli": {"positional": True}},
            "repo": {"type": "string", "description": "Path to the repository.",
                     "required": True, "cli": {"positional": True}},
            "origin_ref": {"type": "string",
                           "description": "Durable locator (remote URL); defaults to "
                                          "the absolute path."},
            "head": {"type": "string",
                     "description": "Optional commit stamp (recorded, never the "
                                    "staleness trigger)."},
            "surfaces": {"type": "array", "items": {"type": "object"},
                         "description": "Adapter-chosen surfaces that AUGMENT the "
                                        "default floor — [{label, globs}] (ADR-0028 §6).",
                         "cli": {"flag": "--surface", "append": True,
                                 "parse": _parse_surface,
                                 "metavar": "LABEL=glob[,glob...]"}},
        },
        "handler": lambda root, p: capture_repo(
            root, p["id"], p["repo"], origin_ref=p.get("origin_ref"),
            head=p.get("head"),
            extra_surfaces=[(s["label"], s["globs"])
                            for s in (p.get("surfaces") or [])] or None),
    },
    "connectors": {
        "help": "project the distinct connectors the scope:global landscape "
                "references (ADR-0021 §2 / T-070); --project unions a "
                "project's own references in (T-128)",
        "description": "Project the distinct connectors the scope:global "
                       "landscape references (origin-union + explicit "
                       "`connectors:` fields; ADR-0021 §2 / T-070) — the "
                       "deterministic read `explore` consults to know which "
                       "systems this base's world touches. With `project`, "
                       "the roster is that project's members unioned with the "
                       "global layer (T-128), matching resolve_scope's "
                       "project-plus-global reading; global-only stays the "
                       "default.",
        "params": {"root": _ROOT_P,
                   "project": {"type": "string",
                               "description": "Project id whose members to union "
                                              "with the global roster (the "
                                              "working-inside-a-project view)."}},
        "handler": lambda root, p: connector_projection(root,
                                                        project=p.get("project")),
        "presenter": _show_connectors,
    },
    "usage": {
        "help": "report the disposable usage ledger (ADR-0027)",
        "description": "Report the disposable usage ledger (ADR-0027): per-op "
                       "counts, byte-footprints, and wall-time (plus REAL token "
                       "counts where a harness exposed them) — the evidence that "
                       "tunes review cadence (T-088) and baselines perf (T-123). "
                       "Operational state, never knowledge.",
        "params": {
            "root": _ROOT_P,
            # cli_only: a file-writing path never enters the MCP schema (the model
            # shouldn't aim writes at arbitrary paths); the CLI user already can.
            "html": {"type": "string", "cli_only": True, "cli": {"flag": "--html"},
                     "description": "Also render the ledger as one self-contained "
                                    "HTML page at this path (T-123)."},
        },
        "handler": _op_usage,
        "presenter": _show_usage,
    },
    "usage-log": {
        "help": "append a usage record for an adapter verb — ask/review/"
                "synthesize (T-088)",
        "description": "Record a usage entry for an AI-heavy ADAPTER verb — "
                       "`ask`, `review`, `synthesize` — that the Core never sees "
                       "itself, so the ledger can measure the real token spenders "
                       "(T-088). Call it AFTER the verb. Pass `scope` = the "
                       "doc/source ids the verb read; the Core computes their "
                       "byte-footprint deterministically as an honest cost proxy. "
                       "Add `tokens` ONLY when the harness actually exposes a "
                       "real count — never guess; omit it otherwise.",
        "params": {
            "root": _ROOT_P,
            "op": {"type": "string", "required": True, "cli": {"positional": True},
                   "description": "The verb measured: ask | review | synthesize."},
            "scope": {"type": "array", "items": {"type": "string"},
                      "description": "Doc/source ids the verb read; Core sums their "
                                     "readable bytes.",
                      "cli": {"append": True}},
            "bytes_in": {"type": "integer",
                         "description": "Override the computed scope byte-footprint."},
            "bytes_out": {"type": "integer", "default": 0,
                          "description": "Bytes the verb produced (answer/insight "
                                         "length)."},
            "tokens": {"type": "integer",
                       "description": "REAL token count when the harness exposes it; "
                                      "omit to leave null (do not estimate)."},
            "note": {"type": "string",
                     "description": "Optional short label (e.g. the scope/project)."},
        },
        "handler": lambda root, p: usage_log(
            root, p["op"], scope=p.get("scope"), bytes_in=p.get("bytes_in"),
            bytes_out=p.get("bytes_out", 0), tokens=p.get("tokens"),
            note=p.get("note")),
    },
    "challenge-log": {
        "help": "record a completed challenge's outcome in the append-only "
                "log (history, never a stored verdict; ADR-0040)",
        "description": "Record a completed challenge in the append-only log "
                       "(ADR-0040): 'challenge | <target>: survived|weakened|"
                       "refuted [detail]'. History a reader can consult, never "
                       "a verdict the format stores — no doc mark, no status "
                       "field, no trust score. Run it once per completed "
                       "challenge, after any consented knowledge-products "
                       "(counter-insight / caveat / supersede) are written.",
        "params": {
            "root": _ROOT_P,
            "target": {"type": "string", "required": True,
                       "cli": {"positional": True},
                       "description": "The challenged doc id (or a short claim "
                                      "slug for an unwritten claim)."},
            "outcome": {"type": "string", "required": True,
                        "enum": ["survived", "weakened", "refuted"],
                        "description": "What the challenge concluded."},
            "detail": {"type": "string",
                       "description": "One line of context (what was checked, "
                                      "what was recorded)."},
        },
        "handler": lambda root, p: log_challenge(root, p["target"],
                                                 outcome=p["outcome"],
                                                 detail=p.get("detail")),
    },
    "supersede": {
        "help": "mark a derived doc superseded (the honest ending; reversible "
                "with --lift; ADR-0041)",
        "description": "Mark a derived document SUPERSEDED (ADR-0041) — the "
                       "honest ending: status: superseded + a one-way pointer "
                       "(superseded_by) and/or a reason, stamped superseded_at. "
                       "Consented, logged, idempotent; touches only these machine "
                       "fields (provenance and authored content untouched, so "
                       "everything still verifies). A superseded doc still lints, "
                       "stays in the index badged, is exempt from L4 staleness, "
                       "and is skipped by find unless asked. Derived docs only: "
                       "never sources (immutable, versioned) or decisions (their "
                       "own supersession record). lift=true reverses a mistaken "
                       "mark. Use when a claim is refuted (challenge), a doc was "
                       "mis-filed and re-recorded, or a better derivation replaced "
                       "it — never a hand-edit, never a delete.",
        "params": {
            "root": _ROOT_P,
            "id": _ID_POS,
            "by": {"type": "string",
                   "description": "Id of the replacement doc (must exist first)."},
            "reason": {"type": "string",
                       "description": "Why this doc is ended (required when no "
                                      "replacement is named)."},
            "lift": {"type": "boolean",
                     "description": "Reverse a mistaken supersession (status back "
                                    "to current; fields removed; logged)."},
        },
        "handler": lambda root, p: supersede(root, p["id"], by=p.get("by"),
                                             reason=p.get("reason"),
                                             lift=bool(p.get("lift"))),
    },
    "find": {
        "help": "retrieve docs matching a query (deterministic; the AI-free floor)",
        "description": "Deterministic retrieval: docs whose id/title/abstract/"
                       "tags/body contain ALL query terms (case-insensitive); "
                       "sources also match their origin locators (origin.ref / "
                       "upstream_ref — T-141), so a captured filename or URL is "
                       "a valid query. The AI-free floor (ADR-0014) — no "
                       "embeddings, no AI. Optional `type` restricts results "
                       "(type='decision' is the `why` verb). A zero-hit means "
                       "these literal terms don't appear — never 'not in the "
                       "base'; degrade the query or check the index before "
                       "reporting absence (T-142).",
        "params": {
            "root": _ROOT_P,
            "query": {"type": "string", "required": True,
                      "description": "Whitespace-separated terms (empty lists all "
                                     "of `type`).",
                      "cli": {"positional": True, "nargs": "*", "join": True}},
            "type": {"type": "string",
                     "description": "Restrict to a frontmatter type."},
            "include_superseded": {"type": "boolean",
                                   "description": "Include superseded (closed) docs "
                                                  "— skipped by default (ADR-0041)."},
        },
        # ONE result shape on both surfaces (T-113): the CLI's T-106 wrapper
        # {matches, count} wins — self-describing beats a bare list; the MCP
        # tool previously returned the bare list (a live drift this closes).
        "handler": lambda root, p: (lambda hits: {"matches": hits,
                                                  "count": len(hits)})(
            find(root, p["query"], type=p.get("type"),
                 include_superseded=bool(p.get("include_superseded")))),
        "presenter": _show_find,
    },
    "project": {
        "help": "create/update a project page (a curated view; ADR-0002/0017)",
        "description": "Create/update a project page — a curated VIEW, not a "
                       "folder (ADR-0002/0017). Members are links, not provenance. "
                       "The body is a deterministic projection of each member's "
                       "own title/abstract. Only group when the user asks — never "
                       "auto-group. `remove_members` takes ids OUT of the view "
                       "(T-148): links only — the doc itself is untouched and "
                       "stays findable; never hand-edit a members list.",
        "params": {
            "root": _ROOT_P,
            "id": {"type": "string", "description": "Stable project id.",
                   "required": True, "cli": {"positional": True}},
            "title": {"type": "string",
                      "description": "Required on create; kept on update if omitted."},
            "add_members": {"type": "array", "items": {"type": "string"},
                            "description": "Member ids to union in (order-stable).",
                            "cli": {"flag": "--member", "append": True}},
            "remove_members": {"type": "array", "items": {"type": "string"},
                               "description": "Member ids to remove from the view "
                                              "(idempotent — an absent id is a "
                                              "no-op; applied after any adds). "
                                              "Removal is a link change only.",
                               "cli": {"flag": "--remove-member", "append": True}},
            "scope": {"type": "string", "enum": ["global", "project"],
                      "description": "'global' views are always unioned into every "
                                     "scope."},
            "description": {"type": "string",
                            "description": "A plain maintainer label (not a sourced "
                                           "claim)."},
            "maintained_by": {"type": "string", "description": "Maintainer label."},
            "tags": {"type": "array", "items": {"type": "string"},
                     "description": "Tags.", "cli": {"flag": "--tag", "append": True}},
        },
        "handler": lambda root, p: write_project(
            root, p["id"], title=p.get("title"), add_members=p.get("add_members"),
            remove_members=p.get("remove_members"),
            scope=p.get("scope"), description=p.get("description"),
            maintained_by=p.get("maintained_by"), tags=p.get("tags"), when=util._now()),
    },
    "read": {
        "help": "return a doc's stored text, paged — the read-back primitive "
                "for hosts without filesystem access (T-159)",
        "description": "Return a doc's stored text verbatim, paged. For a "
                       "SOURCE: its readable text (the extracted aid, else a "
                       "text-native canonical — the same text find/index/"
                       "derivation read); a bytes-only source returns empty "
                       "content with text_form 'none' (grounding then needs a "
                       "model-read of the original bytes — never a guess). For "
                       "a derived doc/project/decision: the file's content. "
                       "This is the read half of 'anyone reads, the Core "
                       "writes' for hosts that have only the op surface — use "
                       "it to ground summaries, quote sources (T-153), and "
                       "re-read for review/challenge. Read-only.",
        "params": {
            "root": _ROOT_P,
            "id": {"type": "string", "required": True,
                   "description": "Any doc id (source, derived, project, decision).",
                   "cli": {"positional": True}},
            "offset": {"type": "integer",
                       "description": "Character offset to start from (paging)."},
            "limit": {"type": "integer",
                      "description": "Max characters returned (default 20000); "
                                     "`truncated: true` means more remains."},
        },
        "handler": lambda root, p: read_doc(root, p["id"],
                                            offset=p.get("offset") or 0,
                                            limit=p.get("limit") or 20000),
    },
    "resolve": {
        "help": "resolve a scope to its working-set member ids (a project ∪ "
                "every global view; SPEC §5.6)",
        "description": "Resolve a scope to its working-set member ids — a named "
                       "project's members ∪ every global view (deterministic set "
                       "math; SPEC §5.6). Omit `project` for the whole base. The "
                       "read-side companion synthesize uses to learn its scope.",
        "params": {
            "root": _ROOT_P,
            "project": {"type": "string",
                        "description": "A project id; omit for the whole base.",
                        "cli": {"positional": True, "nargs": "?"}},
        },
        "handler": lambda root, p: resolve_scope(root, p.get("project")),
        "presenter": _show_resolve,
    },
    "record-decision": {
        "help": "record the owner's decision — AUTHORED, not derived (only on "
                "explicit request; body from --file/stdin)",
        "description": "Record (or --amend) the owner's decision — AUTHORED, not "
                       "derived (SPEC §5.5, ADR-0019). Carries no provenance; "
                       "links informing `evidence` as (source id + version), never "
                       "grounds from it, so it can't chain. Write ONLY on explicit "
                       "request — never as an ask/synthesize side effect.",
        "params": {
            "root": _ROOT_P,
            "id": {"type": "string", "description": "Stable slug id (dec-…).",
                   "required": True, "cli": {"positional": True}},
            "body": {"type": "string", "required": True,
                     "description": "The decision text (owner-authored)."},
            "title": {"type": "string",
                      "description": "Required when recording; kept on --amend if "
                                     "omitted."},
            "status": {"type": "string", "enum": ["accepted", "proposed"],
                       "description": "proposed | accepted (default: accepted)."},
            "evidence": {"type": "array", "items": {"type": "string"},
                         "description": "Informing source ids (a LINK, not "
                                        "provenance).",
                         "cli": {"append": True}},
            "amend": {"type": "boolean",
                      "description": "Prepend a dated AMENDED banner to an existing "
                                     "decision."},
        },
        "handler": lambda root, p: record_decision(
            root, p["id"], body=p["body"], title=p.get("title"),
            status=p.get("status"), evidence=p.get("evidence"),
            amend=bool(p.get("amend")), when=util._now()),
        "cli": {"body_param": "body"},
    },
}


def mcp_tools(ops, prefix="odin_"):
    """Project an op registry into the MCP tool-schema surface (T-113). The
    JSON-Schema keys (type/description/enum/items/default) pass through; the
    argparse projection (`cli`) and cli_only params are stripped."""
    tools = []
    for verb, spec in ops.items():
        props, req = {}, []
        for name, ps in spec["params"].items():
            if ps.get("cli_only"):
                continue
            props[name] = {k: v for k, v in ps.items()
                           if k in ("type", "description", "enum", "items",
                                    "default")}
            if ps.get("required"):
                req.append(name)
        tools.append({"name": prefix + verb.replace("-", "_"),
                      "description": spec["description"],
                      "inputSchema": {"type": "object", "properties": props,
                                      "required": req,
                                      "additionalProperties": False}})
    return tools


# Verbs whose ledger entry is never the wrapper's job: reading the ledger must not
# grow it (observer effect), and `usage-log`'s handler records the ADAPTER's verb
# itself — a second wrapper record would double-count.
UNTIMED_VERBS = frozenset({"usage", "usage-log"})


def run_op(ops, verb, root, params):
    """Invoke a registry op by CLI verb name — the shared param→Core mapping.
    Fires the op's best-effort usage hook after a successful call, carrying the
    handler's wall-time (T-123); unhooked ops get a minimal timed record so the
    read path (find/status/lint — where T-116 lives) has a perf baseline. Timing
    is always-on: one clock read on a write that already happens, into the
    disposable ledger no guarantee rests on."""
    spec = ops[verb]
    t0 = time.perf_counter()
    res = spec["handler"](root, params)
    duration_ms = round((time.perf_counter() - t0) * 1000, 3)
    try:
        hook = spec.get("usage")
        if hook is not None:
            hook(root, params, res, duration_ms=duration_ms)
        elif verb not in UNTIMED_VERBS:
            log_usage(root, verb, duration_ms=duration_ms)
    except Exception:
        pass
    return res
