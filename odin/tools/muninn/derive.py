"""Derived-doc writes with provenance — grounding-in-sources-only enforced at the boundary (I3, no chaining).

Split from muninn_core.py (T-122); muninn_core remains the facade.
"""
import os
import re
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import muninn_lint  # noqa: E402
from . import util  # noqa: E402  (module-attr access = the patch point)
from .util import _append_log, _dump_yaml, _load_yaml, _locked, _valid_id  # noqa: E402


# --------------------------------------------------------------------------- #
# write_derived — the deterministic half of derive (the Core/adapter handoff)
# --------------------------------------------------------------------------- #
_TYPE_DIR = {"summary": "summaries", "entity": "entities", "concept": "concepts",
             "question": "questions", "insight": "insights"}


def stamp_derived(root):
    """Backfill: stamp `self_hash` on every derived doc that lacks one, from its CURRENT
    content — the lightweight self-heal for a base whose docs predate self-hashing (no
    model, no content change, faithful). Idempotent. **Never re-stamps a doc that already
    has a self_hash** — a mismatch there is a real out-of-band edit for L19 to flag, not
    something to launder by overwriting. Returns {stamped, skipped}."""
    root = Path(root)
    stamped, skipped = 0, 0
    for dirname in muninn_lint.DERIVED_DIRS:
        d = root / dirname
        if not d.is_dir():
            continue
        for md in sorted(d.glob("*.md")):
            text = md.read_text(encoding="utf-8")
            fm, body = muninn_lint.split_frontmatter(text)
            if fm is None or "self_hash" in fm:
                skipped += 1
                continue
            fm["self_hash"] = muninn_lint.derived_content_hash(
                fm.get("title"), fm.get("abstract"), body or "")
            tmp = md.parent / f".{md.name}.tmp"
            tmp.write_text("---\n" + _dump_yaml(fm) + "---\n" + (body or ""), encoding="utf-8")
            tmp.replace(md)
            stamped += 1
    return {"stamped": stamped, "skipped": skipped}


def _link_target(root, doc_id):
    """The readable file a citation of `doc_id` should link to, or None. A source
    links to its text aid (else its canonical file); any other doc links to its
    own `.md`. Mirrors the read path a human or AI actually follows."""
    root = Path(root)
    sdir = root / "sources" / doc_id
    if sdir.is_dir():
        aid = sdir / "source-text.md"
        if aid.exists():
            return aid
        cands = [p for p in sorted(sdir.glob("source.*"))
                 if p.is_file() and not p.name.startswith("source.v")]
        return cands[0] if cands else None
    for dirname in (*muninn_lint.DERIVED_DIRS, "decisions", "projects"):
        p = root / dirname / f"{doc_id}.md"
        if p.exists():
            return p
    return None


@_locked
def relink(root):
    """Upgrade bare `[known-id]` citation spans to linked citations (ADR-0038) —
    `[src-x]` → `[src-x](relative/path)` — across the authored derived layer
    (derived docs + decisions; projects are computed and regenerate instead).

    A regenerate-class maintenance repair (I5: deliberate and consented, never
    automatic): idempotent — an already-linked span (`[id](…)`) is left alone, an
    unknown id is not a citation and is untouched — and it re-stamps `self_hash`
    on any derived doc it edits, so an L19-enforcing base stays clean (this is a
    sanctioned Core edit, not an out-of-band one). Body bytes change → the content
    fingerprint moves → the base reads `drifted` until the next lint; that is
    correct surfacing. Returns {relinked, spans, unchanged}."""
    root = Path(root)
    ids = {}
    for sdir in sorted((root / "sources").glob("*")) if (root / "sources").is_dir() else []:
        if sdir.is_dir():
            ids[sdir.name] = _link_target(root, sdir.name)
    for dirname in (*muninn_lint.DERIVED_DIRS, "decisions", "projects"):
        d = root / dirname
        if d.is_dir():
            for md in d.glob("*.md"):
                ids[md.stem] = md
    known = {i: t for i, t in ids.items() if t is not None}
    if not known:
        return {"relinked": 0, "spans": 0, "unchanged": 0}
    span_re = re.compile(r"\[(" + "|".join(re.escape(i) for i in sorted(known, key=len,
                                                                        reverse=True))
                         + r")\](?!\()")
    relinked = spans = unchanged = 0
    for dirname in (*muninn_lint.DERIVED_DIRS, "decisions"):
        d = root / dirname
        if not d.is_dir():
            continue
        for md in sorted(d.glob("*.md")):
            text = md.read_text(encoding="utf-8")
            fm, body = muninn_lint.split_frontmatter(text)
            if fm is None or not body:
                unchanged += 1
                continue

            def _sub(m):
                rel = os.path.relpath(known[m.group(1)], start=md.parent)
                return f"[{m.group(1)}]({rel.replace(os.sep, '/')})"

            new_body, n = span_re.subn(_sub, body)
            if n == 0:
                unchanged += 1
                continue
            if "self_hash" in fm:  # keep L19 truthful about this sanctioned edit
                fm["self_hash"] = muninn_lint.derived_content_hash(
                    fm.get("title"), fm.get("abstract"), new_body)
            tmp = md.parent / f".{md.name}.tmp"
            tmp.write_text("---\n" + _dump_yaml(fm) + "---\n" + new_body,
                           encoding="utf-8")
            tmp.replace(md)
            relinked += 1
            spans += n
    return {"relinked": relinked, "spans": spans, "unchanged": unchanged}


@_locked
def write_derived(root, id, *, body, sources, type="summary", title,
                  abstract=None, status="current", see_also=None,
                  derivation=None, derived_at=None, connectors=None,
                  as_of=None):
    """Write a derived document with provenance — the write half of derivation.

    The adapter supplies judgment (title/abstract/body, and *which* sources);
    Core writes the file, copying each source's CURRENT `content_hash` into the
    provenance list (so the doc is born fresh, L4-clean), and enforces
    grounding-in-sources-only at the boundary: a provenance id that is not a real
    source raises ValueError (I3 — no chaining). Atomic single-file write.

    Returns {"id", "type", "path", "sources"}.
    """
    root = Path(root)
    _valid_id(id, what="derived-doc id")
    derived_at = derived_at or util._now()
    if type not in _TYPE_DIR:
        raise ValueError(f"unknown derived type {type!r}")
    if not sources:
        raise ValueError("a derived document needs at least one source (I2)")
    if derivation is not None and derivation not in muninn_lint.DERIVATION_VALUES:
        raise ValueError(f"derivation {derivation!r} not one of "
                         f"{' | '.join(sorted(muninn_lint.DERIVATION_VALUES))} (L14)")

    prov = []
    for sid in sources:
        meta_p = root / "sources" / sid / "meta.yml"
        if not meta_p.exists():
            raise ValueError(
                f"provenance id {sid!r} is not a source — derivation must be grounded "
                f"only in sources (I3, no chaining)")
        prov.append({"id": sid, "hash": _load_yaml(meta_p).get("content_hash")})

    fm = {"id": id, "type": type, "title": title}
    if abstract:
        fm["abstract"] = abstract
    fm["sources"] = prov
    fm["derived_at"] = derived_at
    # A doc that states a TIME-RELATIVE result (ADR-0034 / T-104) declares the date
    # its claim was true. It is surfaced/aged on-load by `status`, NOT by lint (which
    # stays time-independent, ADR-0005). The authoring default is still to anchor on the
    # immutable datum + derivation rule so no as_of is needed; this is the residual.
    if as_of:
        fm["as_of"] = as_of
    if see_also:
        fm["see_also"] = see_also
    # A landscape doc may ASSERT connectors it references but hasn't ingested from
    # (ADR-0028 / ADR-0021 §2) — an adapter-authored `[{system, ref}]` list. Ingested
    # connectors need not be listed here; they come free from source `origin` in the
    # connector projection. Not self-hashed content (a machine/landscape field).
    if connectors:
        fm["connectors"] = [c for c in connectors if isinstance(c, dict) and c.get("system")]
    fm["status"] = status
    if derivation:
        fm["derivation"] = derivation
    # Always stamp a self-hash over the authored content (ADR-0029): cheap, always-accurate
    # metadata that every write (incl. `regenerate`) keeps current. The muninn.yml
    # `integrity.derived_self_hash` flag governs only whether the linter ENFORCES it (L19).
    # Decoupling stamp from enforce makes enabling enforcement later instant and complete —
    # every doc is already stamped — and never false-positives on a legit regenerate.
    fm["self_hash"] = muninn_lint.derived_content_hash(title, abstract, body)

    body_text = body if body.endswith("\n") else body + "\n"
    doc_text = "---\n" + _dump_yaml(fm) + "---\n" + body_text

    ddir = root / _TYPE_DIR[type]
    ddir.mkdir(exist_ok=True)
    target = ddir / f"{id}.md"
    tmp = ddir / f".{id}.md.tmp"
    tmp.write_text(doc_text, encoding="utf-8")
    tmp.replace(target)  # atomic replace into place
    _append_log(root, derived_at, f"derive | {type} | {id} <- {', '.join(sources)}")
    return {"id": id, "type": type, "path": str(target),
            "sources": [p["id"] for p in prov]}
