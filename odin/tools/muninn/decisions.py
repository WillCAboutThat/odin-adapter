"""Owner-authored decisions (ADR-0019), the on-load status surface (ADR-0034), and the structured lint report.

Split from muninn_core.py (T-122); muninn_core remains the facade.
"""
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


def _captures_since_last_lint(root: Path) -> int:
    """Count `capture` log entries after the most recent `lint` entry — a deterministic
    'what's arrived since the last check' from the append-only log (ADR-0005 record)."""
    logp = root / "log.md"
    if not logp.exists():
        return 0
    entries = [s.strip() for s in logp.read_text(encoding="utf-8").splitlines()
               if s.strip().startswith("## [") and "]" in s]

    def _op(s):
        return s.split("]", 1)[1].split("|", 1)[0].strip()

    last_lint = max((i for i, s in enumerate(entries) if _op(s) == "lint"), default=-1)
    return sum(1 for s in entries[last_lint + 1:] if _op(s) == "capture")


def status(root, as_of=None, aging_window_days=_AS_OF_WINDOW_DAYS):
    """The on-load status surface (ADR-0034). Read-only; composes the signals worth
    raising on load into one summary the adapter renders as a single nudge:

      - freshness  : never-linted | fresh | drifted (fingerprint vs last lint, ADR-0005)
      - stale      : ids of derived docs whose cited source hash advanced (the L4 condition)
      - pending_candidates : count awaiting review (ADR-0033)
      - captures_since_lint: sources captured since the last lint (the synthesize nudge)
      - aged       : {id, as_of, days_old} for `as_of` docs older than the window (T-104)

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

    return {
        "freshness": freshness,
        "fingerprint": current_fp,
        "stale": stale,
        "pending_candidates": list_candidates(root)["pending_count"],
        "captures_since_lint": _captures_since_last_lint(root),
        "aged": aged,
        "as_of": as_of,
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
    _append_log(root, util._now(),
                f"lint | {'pass' if ok else 'fail'} | {n_errors} errors "
                f"{n_warnings} warn | fingerprint={fingerprint}")


def lint_report(root) -> dict:
    """Structured lint — the Linter's findings without printing/exit-code; the
    shape `odin_lint` (MCP) and `lint --json` (CLI) both return. Records the
    ADR-0005 baseline entry (T-124); the Linter ENGINE stays side-effect-free —
    recording lives here, at the op layer."""
    linter = muninn_lint.Linter(Path(root))
    linter.load()
    linter.check()
    errors = [{"rule": f.rule, "message": f.message, "path": f.path}
              for f in linter.findings if f.severity == "error"]
    warnings = [{"rule": f.rule, "message": f.message, "path": f.path}
                for f in linter.findings if f.severity == "warn"]
    n_docs = len([d for d in linter.docs if d.kind != "manifest"])
    fingerprint = linter.content_fingerprint()
    record_lint_entry(root, ok=not errors, n_errors=len(errors),
                      n_warnings=len(warnings), fingerprint=fingerprint)
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "n_docs": n_docs, "fingerprint": fingerprint}
