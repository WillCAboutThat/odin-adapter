"""Source capture, versioning, dedup, lineage (I1/I2, ADR-0003/0010, T-045) — crash-consistent per T-115.

Split from muninn_core.py (T-122); muninn_core remains the facade.
"""
import shutil
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import extractors  # noqa: E402  (the document-processing extension point, ADR-0010)
import repo_constitution  # noqa: E402  (constitution enumerator, ADR-0028)
from muninn_lint import (  # noqa: E402  (shared model + hashing)
    TEXT_SUFFIXES,
    content_hash_of_canonical,
    current_canonical,
)
from . import util  # noqa: E402  (module-attr access = the patch point)
from .util import _append_log, _dump_yaml, _load_yaml, _locked, _valid_id  # noqa: E402


def capture(root, id, body, *, origin, tier="full", capture_reason=None,
            when=None, force_new=False):
    """Capture a **text** source (backward-compatible entry point).

    A text source's canonical bytes are the UTF-8 of `body`; the canonical file is
    `source.md` and no separate text aid is written (it *is* the text). For binary
    sources (PDF, images, …) use `capture_file`.
    """
    if not isinstance(body, str):
        raise ValueError("body must be a string")
    when = when or util._now()
    return _capture(root, id, raw=body.encode("utf-8"), canonical_name="source.md",
                    origin=origin, tier=tier, capture_reason=capture_reason,
                    when=when, text=None, extracted_by=None, force_new=force_new)


def capture_file(root, id, raw, filename, *, origin, tier="full",
                 capture_reason=None, when=None,
                 text=None, extracted_by=None, force_new=False):
    """Capture a source from its **original bytes** (ADR-0010).

    The canonical source of record is `raw`, stored as `source<ext>` where `<ext>`
    comes from `filename`. If the format is text-native it is its own aid; else the
    extractor registry produces a `source-text.md` aid — or, when `text` is passed
    (e.g. adapter-side OCR), that text is used with `extracted_by` as its label.
    No extractor and no supplied text ⇒ a valid **bytes-only** source (rule 5).
    `origin.recoverable` defaults to True here (we hold the recoverable original).
    """
    if not isinstance(raw, (bytes, bytearray)):
        raise ValueError("raw must be bytes")
    raw = bytes(raw)
    when = when or util._now()
    ext = Path(filename).suffix.lower()
    canonical_name = "source" + (ext or ".bin")

    extraction_error = None
    if ext in TEXT_SUFFIXES:
        text, extracted_by = None, None          # canonical is itself the text
    elif text is None:
        ex = extractors.for_format(ext)
        if ex is not None:
            try:
                text, extracted_by = ex.extract(raw), ex.name
            except Exception as e:               # bytes-only fallback (rule 5)
                # Never swallowed silently (T-118b): a missing text aid must be
                # diagnosable. Logged + returned, NOT persisted in meta.yml —
                # the 1.0 meta surface is frozen (ADR-0037) and this is an
                # operational trace, not a property of the source.
                text, extracted_by = None, None
                extraction_error = f"{ex.name}: {type(e).__name__}: {e}"

    origin = dict(origin)
    origin.setdefault("recoverable", True)
    res = _capture(root, id, raw=raw, canonical_name=canonical_name,
                   origin=origin, tier=tier, capture_reason=capture_reason,
                   when=when, text=text, extracted_by=extracted_by,
                   force_new=force_new)
    if extraction_error and res.get("action") != "deduped":
        _append_log(Path(root), when,
                    f"capture | extraction-failed | {res['id']} ({extraction_error}) "
                    f"— captured bytes-only")
        res["extraction_error"] = extraction_error
    return res


@_locked
def _capture(root, id, *, raw, canonical_name, origin, tier, capture_reason,
             when, text, extracted_by, force_new=False):
    """Shared capture engine — hash-first dedup, immutable write, versioning.

    Contract (validated by tests/test_core_capture*.py, test_capture_lineage.py):
      - NEW content  -> writes sources/<id>/{source<ext>, [source-text.md], meta.yml},
                        v1 ledger, content_hash over the canonical BYTES; returns
                        action="created".
      - IDENTICAL bytes (any existing id) -> no new source; action="deduped".
      - CHANGED bytes of an existing id -> new version: prior canonical retained as
                        source.v<N><ext> (and its aid as source-text.v<N>.md), the
                        current names hold the new version, ledger + hash advanced;
                        action="versioned".
      - CHANGED bytes under a NEW id whose origin.ref matches an existing source
                        -> refused (a silent lineage SPLIT; the T-045 locator rung):
                        the caller either captures under the matching id (versioning
                        it) or passes force_new=True to declare a deliberate split,
                        which is recorded in log.md and returned as
                        "lineage_split_from". No silent merges or splits.
      - Always appends to log.md; never creates or edits a derived document.
      - Atomic: invalid input raises ValueError before any write; a new source is
        assembled in a temp dir and renamed into place.

    Returns: {"id", "action", "version", "path", "content_hash", "canonical"}.
    """
    root = Path(root)

    # --- validate up front, before any write (atomic on bad input) ---------- #
    _valid_id(id, what="source id")
    if tier not in ("full", "reference"):
        raise ValueError(f"tier must be 'full' or 'reference', got {tier!r}")
    if tier == "reference" and not capture_reason:
        raise ValueError("reference capture requires a capture_reason (ADR-0003)")

    # Hash via the SAME rule `lint` applies to the canonical (muninn_lint.
    # content_hash_of_canonical): text by normalized body, binary by raw bytes —
    # so capture and lint agree regardless of CRLF/LF. content_hash_of_bytes here
    # was the CRLF-vs-LF L5 bug for text-native `--source-file` captures.
    h = content_hash_of_canonical(canonical_name, raw)
    aid_name = "source-text.md" if text is not None else None
    sources = root / "sources"

    # --- hash-first dedup across ALL existing sources (by canonical bytes) --- #
    ref = (origin or {}).get("ref")
    ref_match = None  # first existing source sharing this origin.ref (locator rung)
    if sources.is_dir():
        for child in sorted(sources.iterdir()):
            meta_p = child / "meta.yml"
            if not child.is_dir() or not meta_p.exists():
                continue
            existing = _load_yaml(meta_p)
            if existing.get("content_hash") == h:
                ex_id = existing.get("id", child.name)
                _append_log(root, when,
                            f"capture | dedup | {ex_id} (also via {origin.get('system', '?')})")
                return {"id": ex_id, "action": "deduped",
                        "version": existing.get("version", 1), "path": str(child),
                        "content_hash": h, "canonical": None}
            ex_id = existing.get("id", child.name)
            if (ref_match is None and ref and ex_id != id
                    and (existing.get("origin") or {}).get("ref") == ref):
                ref_match = ex_id

    sdir = sources / id

    # --- locator rung (T-045): changed content at a KNOWN origin.ref under a
    # NEW id would silently split that source's lineage — versioning stops,
    # staleness stops propagating. Refuse (before any write) unless the caller
    # declares the split; a declared split is logged, never silent.
    if ref_match and not sdir.exists():
        if not force_new:
            raise ValueError(
                f"origin.ref '{ref}' is already captured as source '{ref_match}' — "
                f"capturing changed content under new id '{id}' would silently split "
                f"its lineage (T-045). Capture under '{ref_match}' to version it, or "
                f"pass force_new (--force-new) to deliberately start a new lineage.")
    else:
        ref_match = None  # same-id versioning / fresh locator: rung does not apply

    # --- changed bytes of an existing id -> new version --------------------- #
    if sdir.exists():
        meta_p = sdir / "meta.yml"
        meta = _load_yaml(meta_p)
        cur_n = int(meta.get("version", 1))
        new_n = cur_n + 1
        cur_canonical = current_canonical(sdir, meta)
        cur_entry = next((e for e in meta.get("history", [])
                          if isinstance(e, dict) and e.get("version") == cur_n), {})
        cur_aid = cur_entry.get("text_aid")

        # Crash-consistent versioning (T-115): preserve first, stage second,
        # commit last. The prior version's bytes are copied aside BEFORE anything
        # overwrites the current names, all new content is staged under dot-tmp
        # names, and `meta.yml`'s atomic tmp+replace() is the single commit point
        # (matching the new-source path below). A crash anywhere in the sequence
        # loses no bytes and never leaves a half-written meta.yml — worst case is
        # staged-but-uncommitted files with the OLD meta intact, which L5/L13
        # surface and a re-capture repairs.

        # 1. preserve: prior canonical (and its aid) copied aside — write-if-absent:
        # an existing v<N> copy is a crashed prior attempt's preserve step and
        # holds the TRUE old bytes (the current name may already carry the new
        # ones); overwriting it here is the one way a repair re-capture could
        # lose data.
        prior_name = f"source.v{cur_n}{cur_canonical.suffix}"
        if not (sdir / prior_name).exists():
            (sdir / prior_name).write_bytes(cur_canonical.read_bytes())
        prior_aid_name = None
        if cur_aid and (sdir / cur_aid).exists():
            prior_aid_name = f"source-text.v{cur_n}.md"
            if not (sdir / prior_aid_name).exists():
                (sdir / prior_aid_name).write_text(
                    (sdir / cur_aid).read_text(encoding="utf-8"), encoding="utf-8")
        for entry in meta.get("history", []):
            if entry.get("version") == cur_n:
                if entry.get("file"):
                    entry["file"] = prior_name
                if entry.get("text_aid"):
                    entry["text_aid"] = prior_aid_name

        # 2. stage: new canonical, new aid, and the advanced meta — all dot-tmp
        meta["content_hash"] = h
        meta["version"] = new_n
        meta["captured_at"] = when
        new_entry = {"version": new_n, "content_hash": h, "captured_at": when,
                     "file": canonical_name, "supersedes": cur_n}
        if aid_name:
            new_entry["text_aid"] = aid_name
            new_entry["extracted_by"] = extracted_by
        meta.setdefault("history", []).append(new_entry)
        tmp_canon = sdir / f".{canonical_name}.tmp"
        tmp_canon.write_bytes(raw)
        tmp_aid = None
        if aid_name:
            tmp_aid = sdir / f".{aid_name}.tmp"
            tmp_aid.write_text(text, encoding="utf-8")
        tmp_meta = sdir / ".meta.yml.tmp"
        tmp_meta.write_text(_dump_yaml(meta), encoding="utf-8")

        # 3. flip: content into place (atomic per-file), then meta commits
        if cur_canonical.name != canonical_name and cur_canonical.exists():
            cur_canonical.unlink()             # ext changed: drop the old name
        tmp_canon.replace(sdir / canonical_name)
        if tmp_aid is not None:
            tmp_aid.replace(sdir / aid_name)
        elif cur_aid and (sdir / cur_aid).exists():
            (sdir / cur_aid).unlink()          # new version is bytes-only
        tmp_meta.replace(meta_p)               # THE commit point
        _append_log(root, when, f"capture | version {new_n} | {id} supersedes v{cur_n}")
        return {"id": id, "action": "versioned", "version": new_n,
                "path": str(sdir), "content_hash": h, "canonical": canonical_name}

    # --- new source: assemble in a temp dir, then rename into place --------- #
    sources.mkdir(exist_ok=True)
    tmp = sources / f".{id}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()
    (tmp / canonical_name).write_bytes(raw)
    if aid_name:
        (tmp / aid_name).write_text(text, encoding="utf-8")
    meta = {"id": id, "type": "source", "origin": origin, "capture": tier}
    if tier == "reference":
        meta["capture_reason"] = capture_reason
    meta["captured_at"] = when
    meta["content_hash"] = h
    meta["version"] = 1
    entry = {"version": 1, "content_hash": h, "captured_at": when,
             "file": canonical_name, "supersedes": None}
    if aid_name:
        entry["text_aid"] = aid_name
        entry["extracted_by"] = extracted_by
    meta["history"] = [entry]
    (tmp / "meta.yml").write_text(_dump_yaml(meta), encoding="utf-8")
    tmp.rename(sdir)  # single atomic move into place
    note = f" | new-lineage split from {ref_match} (forced)" if ref_match else ""
    _append_log(root, when, f"capture | created | {id} ({tier}){note}")
    res = {"id": id, "action": "created", "version": 1, "path": str(sdir),
           "content_hash": h, "canonical": canonical_name}
    if ref_match:
        res["lineage_split_from"] = ref_match
    return res


def capture_repo(root, id, repo_path, *, origin_ref=None, head=None, when=None,
                 extra_surfaces=None):
    """Capture a repository as a REFERENCE-tier source grounded in its **constitution**
    (ADR-0028). The captured text is a deterministic manifest of the repo's intent-bearing
    surfaces (README, ARCHITECTURE, in-repo ADRs, public contract, identity manifests,
    top-level shape) — **not** its full tree, **not** HEAD. So the source's `content_hash`
    — and any mental model an adapter later grounds in it — changes on a *constitutional
    amendment* (re-architecture / repurpose / split-merge / ownership) and stays flat under
    implementation churn. Building the manifest is a faithful transform; the mental-model
    *inference* is the adapter's `model-read` (ADR-0028 §6), not this Core step.

    `origin_ref` is the durable locator (a remote URL); defaults to the absolute path.
    `head` is an optional human-readable commit stamp — recorded in the manifest, never the
    staleness trigger. Returns the capture result plus the enumerated `surfaces`.
    """
    manifest, surfaces = repo_constitution.build_manifest(
        repo_path, head=head, extra_surfaces=extra_surfaces)
    origin = {"system": "repo",
              "ref": origin_ref or str(Path(repo_path).resolve()),
              "recoverable": True}
    res = capture(root, id, manifest, origin=origin, tier="reference",
                  capture_reason="repo constitution — authoritative copy is the live repo",
                  when=when or util._now())
    res["surfaces"] = [{"label": s["label"], "paths": s["paths"], "hash": s["hash"]}
                       for s in surfaces]
    return res


def dedup_check(root, *, id=None, source_file=None, raw=None, filename=None,
                origin_ref=None):
    """Dry-run dedup: report a candidate's status vs memory **without writing**
    (ADR-0020, T-064).

    This is the deterministic dedup-preview `explore` runs on a candidate before
    any capture. It **never writes** — no source, no version, no `log.md` entry.
    Two modes, matching the two dedup rungs Core owns (ADR-0020 §4):

      - **Content-hash** (`source_file` or `raw`): hash the candidate's canonical
        bytes with the SAME rule `capture`/`lint` use (so text/CRLF agree), then:
          * hash matches any existing source        -> ``already-captured``
          * else `id` given and ``sources/<id>`` exists -> ``changed`` (would version)
          * else `origin_ref` given and matches an existing source's ``origin.ref``
            -> ``changed`` (method ``origin.ref``) — the same locator rung `capture`
            enforces (T-045): changed bytes at a known locator are that source's
            next version, not a new source
          * else                                    -> ``new``
        `id` is optional; with no target lineage and no locator match, a hash-miss
        is honestly ``new``.

      - **origin.ref** (`origin_ref`, no bytes): for a reference-tier candidate we
        can't hold/hash. A source whose ``origin.ref`` matches -> ``already-captured``
        (method ``origin.ref``); else ``new``. ``changed`` is undetectable with no
        bytes — reported ``new`` rather than guessed.

    The fuzzy content-similarity rung (reference near-dups) is deliberately **not**
    here: it is agentic and only *proposes* (ADR-0020 §4, the T-045 ladder). Core
    does the deterministic rungs only, and **no AI ever computes a hash**.

    Returns: ``{"status": "already-captured"|"changed"|"new",
                "method": "content-hash"|"origin.ref",
                "match_id": <id or None>, "content_hash": <hex or None>}``
    """
    root = Path(root)
    if id is not None:
        _valid_id(id, what="candidate id")
    sources = root / "sources"

    def _metas():
        if sources.is_dir():
            for child in sorted(sources.iterdir()):
                meta_p = child / "meta.yml"
                if child.is_dir() and meta_p.exists():
                    yield child, _load_yaml(meta_p)

    # --- origin.ref rung: no bytes, deterministic locator match ------------- #
    if raw is None and source_file is None:
        if not origin_ref:
            raise ValueError("dedup_check needs candidate bytes "
                             "(source_file/raw) or origin_ref")
        for child, meta in _metas():
            if (meta.get("origin") or {}).get("ref") == origin_ref:
                return {"status": "already-captured", "method": "origin.ref",
                        "match_id": meta.get("id", child.name), "content_hash": None}
        return {"status": "new", "method": "origin.ref",
                "match_id": None, "content_hash": None}

    # --- content-hash rung: hash the candidate's canonical bytes ------------ #
    if source_file is not None:
        src = Path(source_file)
        raw = src.read_bytes()
        filename = filename or src.name
    if not isinstance(raw, (bytes, bytearray)):
        raise ValueError("raw must be bytes")
    raw = bytes(raw)
    if filename:                                   # like capture_file
        ext = Path(filename).suffix.lower()
        canonical_name = "source" + (ext or ".bin")
    else:                                          # like capture (text)
        canonical_name = "source.md"
    h = content_hash_of_canonical(canonical_name, raw)

    for child, meta in _metas():
        if meta.get("content_hash") == h:
            return {"status": "already-captured", "method": "content-hash",
                    "match_id": meta.get("id", child.name), "content_hash": h}

    if id is not None and (sources / id).is_dir():
        return {"status": "changed", "method": "content-hash",
                "match_id": id, "content_hash": h}

    if origin_ref:
        for child, meta in _metas():
            if (meta.get("origin") or {}).get("ref") == origin_ref:
                return {"status": "changed", "method": "origin.ref",
                        "match_id": meta.get("id", child.name), "content_hash": h}

    return {"status": "new", "method": "content-hash",
            "match_id": None, "content_hash": h}


def source_status(root, id):
    """The deterministic source facts the adapter's fetch / self-heal decisions
    rest on — **read-only**, never writes (T-066, ADR-0013 §4 / ADR-0020 §3).

    The re-fetch limb of `regenerate` (heal a missing summary for a source whose
    bytes aren't held) is an *adapter* orchestration over Huginn's `fetch`, but the
    trigger is a deterministic fact: does the source hold its current canonical
    bytes locally? That fact (and `recoverable` / `origin.ref`, the inputs to a
    re-fetch) is Core's to report, so the adapter decides on ground truth, not a
    guess — the spine/judgment split (ADR-0008). `fetch` itself stays adapter-side
    (MCP); this only tells the adapter *whether* a fetch is needed and *where* from.

    Returns: ``{"id", "tier", "version", "has_bytes", "recoverable",
                "origin_ref", "origin_system"}``. Raises if the source is unknown.
    """
    root = Path(root)
    sdir = root / "sources" / id
    meta_p = sdir / "meta.yml"
    if not meta_p.exists():
        raise ValueError(f"no such source: {id}")
    meta = _load_yaml(meta_p)
    origin = meta.get("origin") or {}
    return {
        "id": meta.get("id", id),
        "tier": meta.get("capture", "full"),
        "version": meta.get("version", 1),
        # bytes are "absent" exactly when the current canonical file is missing —
        # the same signal lint/derivation already use (current_canonical -> None).
        "has_bytes": current_canonical(sdir, meta) is not None,
        "recoverable": origin.get("recoverable"),
        "origin_ref": origin.get("ref"),
        "origin_system": origin.get("system"),
    }
