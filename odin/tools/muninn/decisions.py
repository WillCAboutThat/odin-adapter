"""Owner-authored decisions (ADR-0019), the on-load status surface (ADR-0034), and the structured lint report.

Split from muninn_core.py (T-122); muninn_core remains the facade.
"""
import os
import sys
from datetime import datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import muninn_lint  # noqa: E402
from . import snapshot, util  # noqa: E402  (module-attr access = the patch point)
from .candidates import list_candidates  # noqa: E402
from .util import _append_log, _dump_yaml, _load_yaml, _locked, _valid_id  # noqa: E402


# --------------------------------------------------------------------------- #
# status — the deterministic on-load surface (ADR-0034 / T-103, T-104)
#
# One read-only op the adapter calls on load and renders as a SINGLE consolidated
# nudge, instead of the freshness / new-source / candidate strands each prompting
# separately. Pure function of (bytes, as_of): `as_of` (today) is an EXPLICIT arg —
# never hidden wall-clock — so the op stays faithful and reproducible-given-inputs
# (the Core boundary holds; time is injected, like `util._now()`). Writes nothing.
# --------------------------------------------------------------------------- #
_AS_OF_WINDOW_DAYS = 30  # conservative default; tunable (ADR-0034 §5)


def _days_old(as_of_str, today_str):
    """Whole days from an `as_of` date to `today` (both ISO; date part only), or None
    if either won't parse. Negative if as_of is in the future."""
    try:
        a = datetime.fromisoformat(str(as_of_str)[:10])
        t = datetime.fromisoformat(str(today_str)[:10])
    except (ValueError, TypeError):
        return None
    return (t - a).days


def _log_entries(root: Path):
    """(timestamp, op) per entry of the append-only ADR-0005 log, in order —
    the shared parse behind every 'since the last X' status fact."""
    logp = root / "log.md"
    if not logp.exists():
        return []
    out = []
    for s in logp.read_text(encoding="utf-8").splitlines():
        s = s.strip()
        if s.startswith("## [") and "]" in s:
            ts = s[len("## ["):].split("]", 1)[0]
            op = s.split("]", 1)[1].split("|", 1)[0].strip()
            out.append((ts, op))
    return out


def _captures_since_last(root: Path, op: str) -> int:
    """Count `capture` log entries after the most recent `op` entry — a
    deterministic 'what's arrived since the last check'. Never checked →
    every capture counts."""
    entries = _log_entries(root)
    last = max((i for i, (_, o) in enumerate(entries) if o == op), default=-1)
    return sum(1 for _, o in entries[last + 1:] if o == "capture")


def _last_op(root: Path, op: str):
    """Timestamp of the most recent `op` log entry, or None — the memory of a
    deliberate pass (drift-check T-136; map T-177) lives in the same
    append-only ADR-0005 log as lint's."""
    last = None
    for ts, o in _log_entries(root):
        if o == op:
            last = ts
    return last


def status(root, as_of=None, aging_window_days=_AS_OF_WINDOW_DAYS):
    """The on-load status surface (ADR-0034). Read-only; composes the signals worth
    raising on load into one summary the adapter renders as a single nudge:

      - freshness  : never-linted | fresh | drifted (fingerprint vs last lint, ADR-0005)
      - stale      : ids of derived docs whose cited source hash advanced (the L4 condition)
      - pending_candidates : count awaiting review (ADR-0033)
      - captures_since_lint: sources captured since the last lint (the synthesize nudge)
      - aged       : {id, as_of, days_old} for `as_of` docs older than the window (T-104)
      - unmapped_connector_systems : systems the base's sources came from that no
        global landscape entry covers (T-146 — the retroactive-orientation trigger)
      - caller_can_write : can THIS context write the base? False on an
        ownership-hardened deployment (T-155, docs/odin/HARDENING.md)

    `aged` is empty unless `as_of` (today) is supplied — time only enters here, never lint.

    CHEAP by design (T-116): runs on the loaded snapshot (recorded hashes only —
    no canonical byte re-hashing, no full rule sweep). The L4 staleness condition
    is computed directly from frontmatter, which is all it ever needed. Integrity
    of the bytes themselves (L5 etc.) is `lint`'s job — the deliberate check, not
    the on-load read. On the 130-source Yosemite base this took status from
    ~950ms to a few ms warm.
    """
    root = Path(root)
    linter = snapshot.load_snapshot(root)   # loaded, never check()ed (read-only)

    current_fp = linter.content_fingerprint()
    recorded_fp = muninn_lint.last_lint_fingerprint(root)
    freshness = ("never-linted" if recorded_fp is None
                 else "fresh" if recorded_fp == current_fp else "drifted")

    # the L4 condition, straight from frontmatter: a cited source's CURRENT
    # recorded hash advanced past the provenance hash, and the doc isn't flagged
    stale = []
    for d in linter.docs:
        if d.kind != "derived" or d.data.get("status") == "stale":
            continue
        for s in (d.data.get("sources") or []):
            if not isinstance(s, dict) or not s.get("hash"):
                continue
            src = linter.by_id.get(s.get("id"))
            if (src is not None and src.kind == "source"
                    and src.data.get("content_hash")
                    and s["hash"] != src.data["content_hash"]):
                stale.append(d.id)
                break
    stale = sorted(set(stale))

    aged = []
    if as_of:
        for d in linter.docs:
            if d.kind != "derived":
                continue
            av = d.data.get("as_of")
            if not av:
                continue
            days = _days_old(av, as_of)
            if days is not None and days > aging_window_days:
                aged.append({"id": d.id, "as_of": str(av), "days_old": days})
        aged.sort(key=lambda a: -a["days_old"])

    # the world-currency facts (T-136): how many sources COULD drift remotely,
    # and when the world was last deliberately checked — so the on-load nudge
    # can add one quiet clause (mention, never an auto-run).
    _local = {"file", "chat", "inbox"}
    recoverable_connectors = sum(
        1 for d in linter.docs
        if d.kind == "source"
        and (d.data.get("origin") or {}).get("system") not in _local
        and (d.data.get("origin") or {}).get("system")
        and (d.data.get("origin") or {}).get("recoverable") is True)

    # orientation debt (T-146): systems this base's sources came FROM that the
    # global landscape doesn't cover — the deterministic trigger for the
    # retroactive orientation offer. The first-run orientation is init-gated;
    # without this signal an existing base has no catch-up path (the
    # opportunistic mid-task offer is a second net, not a guarantee). Coverage
    # mirrors the connector projection's two grounded inputs over the global
    # views (ADR-0021 §2/T-070): a global member source's own origin, or a
    # `connectors:` assertion on a global member doc.
    base_systems = {(d.data.get("origin") or {}).get("system")
                    for d in linter.docs if d.kind == "source"}
    base_systems.discard(None)
    base_systems -= _local
    global_members: set = set()
    for d in linter.docs:
        if d.kind == "project" and d.data.get("scope") == "global":
            global_members.update(d.data.get("members") or [])
    covered = set()
    for d in linter.docs:
        if d.id not in global_members:
            continue
        if d.kind == "source":
            sysname = (d.data.get("origin") or {}).get("system")
            if sysname and sysname not in _local:
                covered.add(sysname)
        for c in (d.data.get("connectors") or []):
            if isinstance(c, dict) and c.get("system"):
                covered.add(c["system"])
    unmapped = sorted(base_systems - covered)

    # enrichment-debt facts (T-177 / ADR-0043): how populated the derived-type
    # layer is, and what has arrived since the last deliberate `map` pass — the
    # deterministic trigger for the on-load map OFFER (the adapter voices it,
    # never runs it; the observatory's 50-summaries-zero-entities night is the
    # gap this signal exists to catch). Facts, not a verdict.
    enrichment_counts = {"entity": 0, "concept": 0, "question": 0}
    for d in linter.docs:
        if d.kind == "derived" and d.data.get("type") in enrichment_counts:
            enrichment_counts[d.data["type"]] += 1

    return {
        "freshness": freshness,
        "fingerprint": current_fp,
        "stale": stale,
        "pending_candidates": list_candidates(root)["pending_count"],
        "captures_since_lint": _captures_since_last(root, "lint"),
        "aged": aged,
        "as_of": as_of,
        "last_drift_check": _last_op(root, "drift-check"),
        "last_map": _last_op(root, "map"),
        "captures_since_map": _captures_since_last(root, "map"),
        "enrichment_counts": enrichment_counts,
        "recoverable_connector_sources": recoverable_connectors,
        "unmapped_connector_systems": unmapped,
        # T-155: whether THIS process context can write the base. False on an
        # ownership-hardened deployment (docs/odin/HARDENING.md) — the adapter
        # should expect writes to go through the privileged Core invocation and
        # not be surprised by permission errors. A fact, not a signal: standing
        # deployment state, never nudged.
        "caller_can_write": os.access(root, os.W_OK),
    }


# --------------------------------------------------------------------------- #
# record_decision — the owner records a decision (AUTHORED, not derived; ADR-0019)
# --------------------------------------------------------------------------- #
def _source_version(root, sid):
    """Current version of a source id, or None if it does not resolve."""
    meta_p = Path(root) / "sources" / sid / "meta.yml"
    if not meta_p.exists():
        return None
    return int(_load_yaml(meta_p).get("version", 1))


@_locked
def record_decision(root, id, *, body, title=None, status=None, evidence=None,
                    amend=False, when=None):
    """Record (or amend) an owner's decision — AUTHORED, not derived (SPEC §5.5).

    A decision is the knowledge-base owner's own knowledge, written **only on
    explicit request** (the adapter enforces that consent — the Core just writes).
    Unlike `write_derived`, it carries **no `sources` provenance**: it links
    informing `evidence` as (source id + the source's current `version` — a
    hash-free change baseline), never grounds/derives from it. So a decision can
    never chain (I3) and is never L4-stale; a later evidence-version advance is a
    SOFT lint note (L17 warn), not staleness.

    Create writes a fresh `decisions/<id>.md`. `amend=True` **prepends** a dated
    `**AMENDED (date):**` banner to the existing body and never deletes prior text
    (append-only, Core-enforced — the ADR-0019 alternative to multi-file
    supersession); it may update `status` and union in new `evidence`.

    Returns {"id", "type", "path", "status", "evidence", "action"}.
    """
    root = Path(root)
    when = when or util._now()
    _valid_id(id, what="decision id")
    ddir = root / "decisions"
    dpath = ddir / f"{id}.md"

    existing_fm, existing_body = {}, ""
    if dpath.exists():
        existing_fm, existing_body = muninn_lint.split_frontmatter(
            dpath.read_text(encoding="utf-8"))
        existing_fm = existing_fm or {}

    if amend and not dpath.exists():
        raise ValueError(f"cannot amend {id!r}: no decisions/{id}.md to amend")
    if not amend and dpath.exists():
        raise ValueError(f"decision {id!r} already exists — use --amend to revise it "
                         f"(decisions are append-only; ADR-0019)")

    # Resolve evidence to {id, version}; a dangling id is an error (links must
    # point at real sources). Store the VERSION, not a hash (ADR-0019).
    new_evidence = []
    for sid in (evidence or []):
        v = _source_version(root, sid)
        if v is None:
            raise ValueError(f"evidence {sid!r} is not a source — a decision links "
                             f"informing sources, which must exist (ADR-0019)")
        new_evidence.append({"id": sid, "version": v})

    if amend:
        title = title or existing_fm.get("title")
        status = status or existing_fm.get("status") or "accepted"
        date = existing_fm.get("date") or when[:10]      # decision date is FIXED
        evidence_list = list(existing_fm.get("evidence") or [])
        have = {e["id"] for e in evidence_list if isinstance(e, dict)}
        evidence_list += [e for e in new_evidence if e["id"] not in have]  # union
    else:
        status = status or "accepted"
        date = when[:10]
        evidence_list = new_evidence

    if not title:
        raise ValueError("a decision needs a title")
    if status not in muninn_lint.DECISION_STATUS_VALUES:
        raise ValueError(f"status {status!r} not one of "
                         f"{' | '.join(sorted(muninn_lint.DECISION_STATUS_VALUES))}")

    fm = {"id": id, "type": "decision", "title": title, "status": status, "date": date}
    if evidence_list:
        fm["evidence"] = evidence_list
    if existing_fm.get("tags"):
        fm["tags"] = existing_fm["tags"]

    if amend:
        banner = f"**AMENDED ({when[:10]}):** {body.strip()}\n"
        new_body = banner + "\n" + existing_body.lstrip("\n")
        action = "amended"
        log_line = f"decision | amended | {id}"
    else:
        new_body = body if body.endswith("\n") else body + "\n"
        action = "recorded"
        joined = ", ".join(e["id"] for e in evidence_list)
        log_line = f"decision | recorded | {id}" + (f" <- {joined}" if joined else "")

    doc_text = "---\n" + _dump_yaml(fm) + "---\n" + new_body
    ddir.mkdir(exist_ok=True)
    tmp = ddir / f".{id}.md.tmp"
    tmp.write_text(doc_text, encoding="utf-8")
    tmp.replace(dpath)  # atomic replace into place
    _append_log(root, when, log_line)
    return {"id": id, "type": "decision", "path": str(dpath), "status": status,
            "evidence": [e["id"] for e in evidence_list], "action": action}


def record_lint_entry(root, *, ok, n_errors, n_warnings, fingerprint) -> None:
    """Append the standardized ADR-0005 lint entry to `log.md` — the freshness
    baseline `status` compares against. A faithful record of a result lint just
    computed deterministically (T-124): before this, the entry had NO writer on
    the CLI/MCP paths (only adapter prose), so real bases read `never-linted`
    forever. Guarded: never writes into a directory that isn't a Muninn. Safe by
    construction: log.md is excluded from the content fingerprint (SPEC §4.4),
    so recording a lint never itself causes drift."""
    root = Path(root)
    if not (root / "muninn.yml").exists():
        return
    payload = (f"lint | {'pass' if ok else 'fail'} | {n_errors} errors "
               f"{n_warnings} warn | fingerprint={fingerprint}")
    # Idempotent (T-174): if the LAST lint entry already records this exact
    # result, appending again adds zero information (ADR-0005 freshness is
    # change-based, never time-based) and dirties a just-settled git tree —
    # the close-session loop: verify after the push, and the verification
    # itself un-cleans the tree. Re-linting an unchanged base is a no-op on
    # disk; any real change (fingerprint, counts, verdict) still appends.
    logp = root / "log.md"
    if logp.exists():
        last_lint = None
        for line in logp.read_text(encoding="utf-8").splitlines():
            if "] lint | " in line:
                last_lint = line.split("] ", 1)[1]
        if last_lint == payload:
            return
    _append_log(root, util._now(), payload)


def lint_report(root) -> dict:
    """Structured lint — the Linter's findings without printing/exit-code; the
    shape `odin_lint` (MCP) and `lint --json` (CLI) both return. Records the
    ADR-0005 baseline entry (T-124); the Linter ENGINE stays side-effect-free —
    recording lives here, at the op layer."""
    linter = muninn_lint.Linter(Path(root))
    with muninn_lint.prefetched(root):  # T-187: concurrent read-prefetch accelerator
        linter.load()
        linter.check()
        fingerprint = linter.content_fingerprint()
    errors = [{"rule": f.rule, "message": f.message, "path": f.path}
              for f in linter.findings if f.severity == "error"]
    warnings = [{"rule": f.rule, "message": f.message, "path": f.path}
                for f in linter.findings if f.severity == "warn"]
    n_docs = len([d for d in linter.docs if d.kind != "manifest"])
    record_lint_entry(root, ok=not errors, n_errors=len(errors),
                      n_warnings=len(warnings), fingerprint=fingerprint)
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "n_docs": n_docs, "fingerprint": fingerprint}
