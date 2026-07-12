"""Derived-doc writes with provenance — grounding-in-sources-only enforced at the boundary (I3, no chaining).

Split from muninn_core.py (T-122); muninn_core remains the facade.
"""
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
