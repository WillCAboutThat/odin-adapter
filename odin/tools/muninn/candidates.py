"""Staging for emergent augmentation (ADR-0033/0035) — stage, review, promote/fold, sticky declines.

Split from muninn_core.py (T-122); muninn_core remains the facade.
"""
import hashlib
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import muninn_lint  # noqa: E402
from . import util  # noqa: E402  (module-attr access = the patch point)
from .derive import _TYPE_DIR, verify_quoted_spans, write_derived  # noqa: E402
from .util import _append_log, _dump_yaml, _load_yaml, _load_yaml_frontmatter, _locked, _read_doc, _valid_id  # noqa: E402


# --------------------------------------------------------------------------- #
# candidates — staging for emergent augmentation (ADR-0033 / T-052)
#
# When a reasoning turn produces a grounded inference of durable value, it is NOT
# written into the base as an `ask`/`synthesize` side effect (consent-of-surprise,
# base bloat). It is STAGED in `candidates/` — the reasoning-time sibling of `inbox/`
# (ADR-0006): non-durable, ignored by the invariants and the linter (which scans only
# DERIVED_DIRS/projects/decisions/sources), nothing may ground in it. Admission is a
# deliberate, BATCHED review (`promote_candidate`), never a per-item prompt. A decline
# is remembered (a fingerprint-keyed tombstone in `candidates/declined/`) so the same
# inference does not re-stage and re-nag — unless a cited source advances, which changes
# the fingerprint and legitimately re-surfaces it (ADR-0019 evidence-advance logic).
# --------------------------------------------------------------------------- #
_CANDIDATES = "candidates"


_DECLINED = "candidates/declined"


_KIND_PREFIX = {"summary": "sum", "entity": "ent", "concept": "con",
                "question": "q", "insight": "ins"}


def _candidate_fingerprint(source_pairs, title, abstract, body) -> str:
    """The identity of a staged inference, over BOTH its grounding and its claim:
    the sorted `(source_id, content_hash)` pairs plus a content hash of the authored
    claim (title/abstract/body). A cited source advancing (new hash) => new fingerprint
    => the "same" inference over new bytes is a legitimately fresh candidate, not a
    re-nag (ADR-0033 Decision 9). A reworded claim over the same sources is also new."""
    claim_h = muninn_lint.derived_content_hash(title, abstract, body)
    basis = "\n".join(f"{sid}:{h}" for sid, h in sorted(source_pairs)) + "\n" + claim_h
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _source_prov(root: Path, sources):
    """[(id, current content_hash)] for real sources only — the grounding half of a
    candidate, enforcing sources-only at the staging boundary too (I3, no chaining:
    a candidate may cite only sources, never another derived doc or candidate)."""
    pairs = []
    for sid in sources:
        meta_p = root / "sources" / sid / "meta.yml"
        if not meta_p.exists():
            raise ValueError(
                f"grounding id {sid!r} is not a source — a candidate may cite only "
                f"sources (I3, no chaining even pre-admission)")
        pairs.append((sid, _load_yaml(meta_p).get("content_hash")))
    return pairs


def _fingerprints_in(d: Path) -> set:
    """The set of candidate fingerprints already present in a directory (pending or
    declined) — the cheap dedup lookup the stager runs before writing."""
    seen: set = set()
    if not d.is_dir():
        return seen
    for md in sorted(d.glob("cand-*.md")):
        fp = _load_yaml_frontmatter(md).get("fingerprint")
        if fp:
            seen.add(fp)
    return seen


@_locked
def stage_candidate(root, id, *, body, sources, title, abstract=None,
                    proposed_kind="insight", staged_at=None, derivation=None, as_of=None):
    """Stage an emergent grounded inference into `candidates/` for later review.

    Grounded and cited (sources + their current hashes, I2/I3) but NOT admitted to the
    base. Deduped by fingerprint against BOTH the pending set and the declined
    tombstones: a duplicate of a pending candidate is a no-op; a match of a declined one
    is skipped (the sticky decline — no re-nag) unless a cited source advanced. Returns
    `{action: staged|skipped, ...}`.
    """
    root = Path(root)
    staged_at = staged_at or util._now()
    _valid_id(id, what="candidate id")
    if not id.startswith("cand-"):
        raise ValueError(f"candidate id must start with 'cand-' (got {id!r})")
    if proposed_kind not in _TYPE_DIR:
        raise ValueError(f"proposed_kind {proposed_kind!r} not a derived type")
    pairs = _source_prov(root, sources)
    if not pairs:
        raise ValueError("a candidate needs at least one grounding source (I2)")
    if proposed_kind == "insight":
        # T-153(d): the same quote-containment gate as write_derived — a staged
        # inference with a fabricated quote must not wait in the pile looking
        # grounded (promote would catch it via write_derived, but the honest
        # refusal belongs at first write).
        _, problems = verify_quoted_spans(root, body, sources)
        if problems:
            detail = "; ".join(f'"{s}…" cited to {", ".join(c)}' for s, c in problems[:3])
            raise ValueError(
                f"quoted span(s) not found in the cited source(s) (T-153): {detail}")
    fp = _candidate_fingerprint(pairs, title, abstract, body)

    cdir = root / _CANDIDATES
    ddir = root / _DECLINED
    if fp in _fingerprints_in(ddir):
        return {"action": "skipped", "id": id, "reason": "declined",
                "note": "matches a declined tombstone; not re-staged (grounding unchanged)"}
    if fp in _fingerprints_in(cdir):
        return {"action": "skipped", "id": id, "reason": "already-pending",
                "note": "an equivalent candidate is already awaiting review"}

    fm = {"id": id, "type": "candidate", "proposed_kind": proposed_kind, "title": title}
    if abstract:
        fm["abstract"] = abstract
    fm["sources"] = [{"id": sid, "hash": h} for sid, h in pairs]
    if derivation:
        fm["derivation"] = derivation
    # A candidate that states a TIME-RELATIVE result carries `as_of` (T-104/ADR-0034).
    # It is aged on-load by `status` once promoted **as its own doc** — such a candidate
    # must NOT be folded (a doc-level `as_of` can't describe one line of a multi-fact
    # card); `promote --into` rejects it (T-109).
    if as_of:
        fm["as_of"] = as_of
    fm["fingerprint"] = fp
    fm["staged_at"] = staged_at
    fm["status"] = "pending"
    body_text = body if body.endswith("\n") else body + "\n"
    doc_text = "---\n" + _dump_yaml(fm) + "---\n" + body_text

    cdir.mkdir(parents=True, exist_ok=True)
    target = cdir / f"{id}.md"
    tmp = cdir / f".{id}.md.tmp"
    tmp.write_text(doc_text, encoding="utf-8")
    tmp.replace(target)
    _append_log(root, staged_at, f"stage-candidate | {proposed_kind} | {id} <- "
                                 f"{', '.join(sid for sid, _ in pairs)}")
    return {"action": "staged", "id": id, "path": str(target),
            "proposed_kind": proposed_kind, "fingerprint": fp}


def list_candidates(root):
    """Enumerate pending candidates + the declined count — the read the on-load
    elicitation and `review-candidates` sweep both use (ADR-0033 Decision 7). Emitted as
    one signal among possibly several (staleness, review-drift) so a future unified
    session-boundary surface can fold it in (T-103)."""
    root = Path(root)
    cdir = root / _CANDIDATES
    pending = []
    if cdir.is_dir():
        for md in sorted(cdir.glob("cand-*.md")):
            fm = _load_yaml_frontmatter(md)
            pending.append({"id": fm.get("id", md.stem),
                            "proposed_kind": fm.get("proposed_kind"),
                            "title": fm.get("title"),
                            "sources": [s.get("id") for s in (fm.get("sources") or [])]})
    declined = len(list((root / _DECLINED).glob("cand-*.md"))) if (root / _DECLINED).is_dir() else 0
    return {"pending": pending, "pending_count": len(pending), "declined_count": declined}


@_locked
def decline_candidate(root, id, *, declined_at=None, reason=None):
    """Decline a candidate: move it to `candidates/declined/` as a fingerprint-keyed
    tombstone (never delete — a sticky decline is what stops the re-nag, and honors the
    append-only *surface, never erase* discipline). Regenerates the declined index."""
    root = Path(root)
    declined_at = declined_at or util._now()
    _valid_id(id, what="candidate id")
    src = root / _CANDIDATES / f"{id}.md"
    if not src.exists():
        raise ValueError(f"no pending candidate {id!r} to decline")
    fm, body = _read_doc(src)
    fm["status"] = "declined"
    fm["declined_at"] = declined_at
    if reason:
        fm["decline_reason"] = reason
    doc_text = "---\n" + _dump_yaml(fm) + "---\n" + (body if body.endswith("\n") else body + "\n")
    ddir = root / _DECLINED
    ddir.mkdir(parents=True, exist_ok=True)
    (ddir / f"{id}.md").write_text(doc_text, encoding="utf-8")
    src.unlink()
    _append_log(root, declined_at, f"decline-candidate | {id}")
    regenerate_declined_index(root)
    return {"action": "declined", "id": id, "path": str(ddir / f"{id}.md")}


def _find_derived_doc(root: Path, doc_id: str):
    """The path of a derived doc by id (summary/entity/concept/question/insight), or
    None. Folds target only derived docs — never a source, decision, or project."""
    for d in _TYPE_DIR.values():
        p = root / d / f"{doc_id}.md"
        if p.exists():
            return p
    return None


def _fold_candidate_into(root, cand_id, target_id, when):
    """Fold a candidate into an existing derived doc as a **literal insert** (ADR-0035):
    append the candidate's already-authored block to the target's body, **byte-preserving
    the existing content** (the Core moves authored content, it does not re-author —
    ADR-0008). Union the candidate's *new* source(s) at their current hash while keeping
    the target's existing provenance **exactly as recorded** — so a fold never silently
    heals staleness (I5). Drop the doc to the **weakest** derivation rung, re-stamp the
    self-hash, and consume the candidate. `regenerate` re-coalesces later."""
    cand_path = root / _CANDIDATES / f"{cand_id}.md"
    if not cand_path.exists():
        raise ValueError(f"no pending candidate {cand_id!r} to fold")
    target_path = _find_derived_doc(root, target_id)
    if target_path is None:
        raise ValueError(f"no derived doc {target_id!r} to fold into (must be an existing "
                         f"summary/entity/concept/question/insight)")

    cand_fm = _load_yaml_frontmatter(cand_path)
    # A dated (time-relative) candidate must not be folded: `as_of` is a doc-level signal
    # `status` ages the WHOLE doc by, but only this one line would be time-relative in a
    # multi-fact card (T-109). Route it to its own doc instead (promote as new, with as_of).
    if cand_fm.get("as_of"):
        raise ValueError(
            f"candidate {cand_id!r} carries as_of={cand_fm['as_of']!r} (a time-relative "
            f"result); it can't be folded — a doc-level as_of can't describe one line of "
            f"{target_id!r}. Promote it as its own doc (no --into), or re-anchor the "
            f"candidate on the immutable datum + rule so it needs no as_of (T-104).")
    cand_block = _read_doc(cand_path)[1].strip()
    t_fm, t_body = _read_doc(target_path)

    # Union sources: keep the target's existing entries AS RECORDED (don't re-freshen —
    # masking staleness would violate I5); add only the candidate's NEW sources, at their
    # current hash.
    merged = list(t_fm.get("sources") or [])
    existing_ids = {s.get("id") for s in merged}
    for s in (cand_fm.get("sources") or []):
        sid = s.get("id")
        if sid not in existing_ids:
            meta = _load_yaml(root / "sources" / sid / "meta.yml")
            merged.append({"id": sid, "hash": meta.get("content_hash")})
    t_fm["sources"] = merged

    new_body = t_body.rstrip("\n") + "\n\n" + cand_block + "\n"

    rungs = [d for d in (t_fm.get("derivation"), cand_fm.get("derivation")) if d]
    if rungs:
        t_fm["derivation"] = muninn_lint.weakest_derivation(rungs)
    t_fm["derived_at"] = when
    t_fm["self_hash"] = muninn_lint.derived_content_hash(
        t_fm.get("title"), t_fm.get("abstract"), new_body)

    doc_text = "---\n" + _dump_yaml(t_fm) + "---\n" + (new_body if new_body.endswith("\n") else new_body + "\n")
    tmp = target_path.parent / f".{target_id}.md.tmp"
    tmp.write_text(doc_text, encoding="utf-8")
    tmp.replace(target_path)
    cand_path.unlink()
    _append_log(root, when, f"fold-candidate | {cand_id} -> {target_id}")
    return {"action": "folded", "candidate": cand_id, "into": target_id,
            "type": t_fm.get("type"), "path": str(target_path),
            "sources": [s["id"] for s in merged]}


@_locked
def promote_candidate(root, id, *, new_id=None, into=None, derived_at=None,
                      derivation=None):
    """Admit a pending candidate into the base.

    Default — **promote as a new derived doc** (kind = the candidate's `proposed_kind`,
    an insight): reuses `write_derived`, fully subject to lint/index/provenance; the
    candidate is removed once admitted.

    `into=<doc-id>` — **fold into an existing derived doc** as a literal insert
    (ADR-0035): append the candidate's authored block, union its new sources, consume the
    candidate. `regenerate` re-coalesces the doc later.
    """
    root = Path(root)
    derived_at = derived_at or util._now()
    _valid_id(id, what="candidate id")
    if new_id is not None:
        _valid_id(new_id, what="derived-doc id")
    if into is not None:
        _valid_id(into, what="target doc id")
        return _fold_candidate_into(root, id, into, derived_at)
    src = root / _CANDIDATES / f"{id}.md"
    if not src.exists():
        raise ValueError(f"no pending candidate {id!r} to promote")
    fm, body = _read_doc(src)
    kind = fm.get("proposed_kind", "insight")
    if new_id is None:
        prefix = _KIND_PREFIX.get(kind, kind)
        new_id = f"{prefix}-{id[len('cand-'):]}" if id.startswith("cand-") else id
    sources = [s["id"] for s in (fm.get("sources") or [])]
    res = write_derived(root, new_id, body=body, sources=sources, type=kind,
                        title=fm.get("title"), abstract=fm.get("abstract"),
                        derivation=derivation or fm.get("derivation"),
                        as_of=fm.get("as_of"), derived_at=derived_at)
    src.unlink()
    _append_log(root, derived_at, f"promote-candidate | {id} -> {new_id} ({kind})")
    return {"action": "promoted", "promoted_from": id, **res}


def regenerate_declined_index(root):
    """Project `candidates/declined/` into a regenerable `declined-index.md` — a cheap
    comprehension + dedup view (ADR-0017 discipline), NOT authored state and NOT the base
    `index.md`; the linter neither builds nor checks it. Losing it costs nothing."""
    root = Path(root)
    ddir = root / _DECLINED
    if not ddir.is_dir():
        return {"action": "noop", "reason": "no declined candidates"}
    rows = []
    for md in sorted(ddir.glob("cand-*.md")):
        fm = _load_yaml_frontmatter(md)
        rows.append((fm.get("id", md.stem), fm.get("title", ""),
                     fm.get("declined_at", ""), fm.get("decline_reason", ""),
                     fm.get("fingerprint", "")))
    lines = ["# Declined candidates (regenerable view — ADR-0033; not base knowledge)", ""]
    if not rows:
        lines.append("_None._")
    else:
        lines.append("| id | title | declined_at | reason |")
        lines.append("|----|-------|-------------|--------|")
        for cid, title, when, reason, _fp in rows:
            lines.append(f"| {cid} | {title} | {when} | {reason} |")
    (ddir.parent / "declined-index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"action": "projected", "declined": len(rows)}
