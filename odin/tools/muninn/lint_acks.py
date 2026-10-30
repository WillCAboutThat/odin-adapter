"""Lint-warning acknowledgment (ADR-0053, T-262).

An acknowledgment is an OPERATOR judgment - "this warning is expected here;
stop restating it" - made durable: `lint-acks.yml` at the Muninn root,
Core-owned, git-tracked, paths stored relative so the record is portable
across clones. Warning-only by construction: `ack` refuses any (rule, path)
that is not a CURRENT warn-severity finding, so an error can never be
acknowledged - failures stay loud.

Acknowledged findings are never silently dropped. `lint` reports them in a
distinct `acknowledged` bucket (reason, date, and whether the warning still
fires); only the live `warnings` list stops carrying them. The linter ENGINE
stays ack-unaware - the standalone floor reports raw findings - and the
partition lives here, applied at the op layer (`lint_report`) and by the web
viewer through the same helper.

State + history split: this file holds current state; `log.md` holds the
history (`lint-ack` / `lint-unack` entries, in the L23 vocabulary).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from . import util

ACKS_FILE = "lint-acks.yml"

_HEADER = (
    "# Acknowledged lint warnings (ADR-0053). Operator judgments: each entry\n"
    "# says a specific WARNING is expected and stops reports restating it.\n"
    "# Errors can never be acknowledged. Managed by `lint-ack`/`lint-unack`;\n"
    "# hand-edits are legible but the ops keep this file consistent.\n"
)


def _rel(root: Path, path: str) -> str:
    """A finding/param path normalized to the root-relative POSIX form acks
    are stored in. Absolute paths inside the root are relativized; anything
    else is kept as given (already relative, or foreign)."""
    p = Path(path)
    if p.is_absolute():
        try:
            return p.relative_to(Path(root)).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix()


def load_acks(root) -> list[dict]:
    """The recorded acknowledgments, oldest-first as stored. Missing or empty
    file means none; entries missing their key fields are ignored rather than
    crashing a lint over a hand-mangled file (the report stays available)."""
    p = Path(root) / ACKS_FILE
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    entries = data.get("acknowledged") or []
    return [e for e in entries
            if isinstance(e, dict) and e.get("rule") and e.get("path")]


def _save(root, acks: list[dict]) -> None:
    """Deterministic write: sorted by (rule, path), atomic tmp -> replace."""
    p = Path(root) / ACKS_FILE
    body = yaml.safe_dump(
        {"acknowledged": sorted(acks, key=lambda a: (a["rule"], a["path"]))},
        allow_unicode=True, sort_keys=False)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(_HEADER + body, encoding="utf-8")
    util.atomic_replace(tmp, p)


def _current_findings(root):
    """Raw findings from the side-effect-free engine (never the recording op)."""
    import muninn_lint
    linter = muninn_lint.Linter(Path(root))
    linter.load()
    linter.check()
    return linter.findings


@util._locked
def ack(root, rule: str, path: str, reason: str, when: str | None = None) -> dict:
    """Record that a CURRENT lint warning is expected (ADR-0053).

    Refuses: an empty reason (the judgment must be legible), a target matching
    an error (failures fail loudly - there is no path to acknowledging one),
    a target matching no current finding (no speculative acks), and a
    duplicate. Appends a `lint-ack` history entry to log.md."""
    rule = (rule or "").strip()
    rel = _rel(root, (path or "").strip())
    reason = (reason or "").strip()
    if not rule or not rel:
        raise ValueError("lint-ack needs both a rule (e.g. L10) and the finding's path")
    if not reason:
        raise ValueError(
            "lint-ack requires a reason - the record is the operator's judgment, "
            "and a judgment without a why is not legible to the next reader")

    findings = _current_findings(root)
    match = next((f for f in findings
                  if f.rule == rule and _rel(root, f.path) == rel), None)
    if match is None:
        raise ValueError(
            f"no current lint finding matches ({rule}, {rel}) - acknowledgments "
            f"target what the linter actually reports; run lint and use the "
            f"finding's rule and path verbatim")
    if match.severity == "error":
        raise ValueError(
            f"({rule}, {rel}) is an ERROR, not a warning - errors are the base "
            f"failing its invariants and always fail loudly; they cannot be "
            f"acknowledged (ADR-0053). Heal it (regenerate / the proper verb) "
            f"instead")

    acks = load_acks(root)
    for a in acks:
        if a["rule"] == rule and a["path"] == rel:
            raise ValueError(
                f"({rule}, {rel}) is already acknowledged "
                f"(reason: {a.get('reason', '?')}, {a.get('date', '?')})")

    when = when or util._now()
    entry = {"rule": rule, "path": rel, "reason": reason, "date": when}
    acks.append(entry)
    _save(root, acks)
    util._append_log(Path(root), when, f"lint-ack | {rule} {rel} | {reason}")
    return {"action": "acknowledged", **entry}


@util._locked
def unack(root, rule: str, path: str, when: str | None = None) -> dict:
    """Withdraw an acknowledgment - the warning surfaces live again on the
    next lint. Also the cleanup path for acks whose warning no longer fires."""
    rule = (rule or "").strip()
    rel = _rel(root, (path or "").strip())
    acks = load_acks(root)
    keep = [a for a in acks if not (a["rule"] == rule and a["path"] == rel)]
    if len(keep) == len(acks):
        raise ValueError(f"no acknowledgment recorded for ({rule}, {rel})")
    _save(root, keep)
    when = when or util._now()
    util._append_log(Path(root), when, f"lint-unack | {rule} {rel}")
    return {"action": "withdrawn", "rule": rule, "path": rel,
            "remaining": len(keep)}


def partition(root, warnings: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split a lint report's warning dicts ({rule, message, path}) into
    (live, acknowledged-view). The acknowledged view carries every recorded
    ack - `matched` says whether its warning currently fires (a matched entry
    borrows the live message; an unmatched one is stale and removable by
    `lint-unack`). Errors never pass through here by construction: the caller
    partitions only its warn-severity list."""
    acks = load_acks(root)
    if not acks:
        return warnings, []
    by_key = {(a["rule"], a["path"]): a for a in acks}
    live, hits = [], {}
    for w in warnings:
        key = (w["rule"], _rel(root, w["path"]))
        if key in by_key:
            hits[key] = w
        else:
            live.append(w)
    acked_view = []
    for a in sorted(acks, key=lambda a: (a["rule"], a["path"])):
        key = (a["rule"], a["path"])
        hit = hits.get(key)
        acked_view.append({
            "rule": a["rule"], "path": a["path"],
            "reason": a.get("reason", ""), "date": a.get("date", ""),
            "matched": hit is not None,
            "message": hit["message"] if hit else None,
        })
    return live, acked_view
