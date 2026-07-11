"""Muninn Core — deterministic, tool-neutral operations (ADR-0008).

The Core owns every file write and every invariant-carrying step, as **fat atomic
operations**, and runs with no AI present. The adapter supplies judgment and calls
into here for anything that touches the store. This module is the trust layer:
its output must always leave the Muninn conformant (the linter is the check).

`capture` is the first operation. `place`, `regenerate_index`, and `fingerprint`
follow.
"""
import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import muninn_lint  # noqa: E402
import extractors  # noqa: E402  (the document-processing extension point, ADR-0010)
import repo_constitution  # noqa: E402  (constitution enumerator for repo-sources, ADR-0028)
from muninn_lint import (  # noqa: E402  (shared model + hashing)
    Linter,
    TEXT_SUFFIXES,
    content_hash_of_body,
    content_hash_of_bytes,
    content_hash_of_canonical,
    current_canonical,
    source_text,
)

FORMAT_VERSION = "0.6"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_yaml(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _dump_yaml(data: dict) -> str:
    # allow_unicode keeps §/— legible in frontmatter (T-018); sort_keys=False
    # preserves the field order the spec presents.
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def _append_log(root: Path, when: str, line: str) -> None:
    logp = root / "log.md"
    prev = logp.read_text(encoding="utf-8") if logp.exists() else "# Log\n"
    if not prev.endswith("\n"):
        prev += "\n"
    logp.write_text(prev + f"## [{when}] {line}\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Usage ledger — the first deterministic tenant of the disposable-index tier
# (ADR-0027). A byte-footprint proxy for the token cost of AI-heavy operations,
# recorded in a git-ignored `.odin/usage.jsonl`. It is operational state, not
# knowledge: never a source, never fingerprinted/linted, and disposable.
# --------------------------------------------------------------------------- #
def _source_bytes(root, sid) -> int:
    """Bytes of a source's current text (its `source-text.md` aid, else the
    current canonical file) — a proxy for how much an adapter reads to derive
    from it. Missing/opaque sources count as 0. Never raises for a bad id."""
    d = Path(root) / "sources" / sid
    if not d.is_dir():
        return 0
    aid = d / "source-text.md"
    if aid.exists():
        return aid.stat().st_size
    cands = [p for p in d.glob("source.*")
             if p.is_file() and not p.name.startswith("source.v")]
    return max((p.stat().st_size for p in cands), default=0)


def log_usage(root, op, *, bytes_in=0, bytes_out=0, **extra) -> None:
    """Append one usage record to `<root>/.odin/usage.jsonl` (ADR-0027).

    Best-effort by design: usage accounting must never break the operation it
    measures, so every failure is swallowed. `.odin/` is disposable operational
    state — git-ignored, excluded from lint and the fingerprint."""
    try:
        d = Path(root) / ".odin"
        d.mkdir(exist_ok=True)
        rec = {"ts": _now(), "op": str(op),
               "bytes_in": int(bytes_in or 0), "bytes_out": int(bytes_out or 0)}
        rec.update(extra)
        with (d / "usage.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def usage_report(root) -> dict:
    """Aggregate the usage ledger by op: {total_ops, by_op: {op: {count, bytes_in,
    bytes_out, tokens, tokens_n}}}. Absent ledger → empty.

    `tokens` sums the *real* token counts when they were recorded; `tokens_n` is how
    many records carried one — so a reader can tell "0 tokens logged" (proxy-only, the
    common case) from "tokens genuinely summed to 0" (never happens for an AI verb)."""
    out = {"total_ops": 0, "by_op": {}}
    p = Path(root) / ".odin" / "usage.jsonl"
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        op = str(rec.get("op", "?"))
        agg = out["by_op"].setdefault(
            op, {"count": 0, "bytes_in": 0, "bytes_out": 0, "tokens": 0, "tokens_n": 0})
        agg["count"] += 1
        agg["bytes_in"] += int(rec.get("bytes_in", 0) or 0)
        agg["bytes_out"] += int(rec.get("bytes_out", 0) or 0)
        if rec.get("tokens") is not None:
            agg["tokens"] += int(rec.get("tokens") or 0)
            agg["tokens_n"] += 1
        out["total_ops"] += 1
    return out


def _scope_bytes(root, ids) -> int:
    """Deterministic byte-footprint of a set of doc/source ids — the readable bytes an
    AI-heavy verb (ask/review/synthesize) grounded in. A source counts its current
    text (its `source-text.md` aid or text canonical, via `_source_bytes`); any other
    doc (summary/insight/decision/…) counts its file size. Unknown ids count 0. This
    is the honest *proxy* for cost when real token counts aren't exposed (T-088)."""
    root = Path(root)
    linter = Linter(root)
    linter.load()
    total = 0
    for i in ids or []:
        d = linter.by_id.get(i)
        if d is None:
            continue
        if d.kind == "source":
            total += _source_bytes(root, i)
        else:
            try:
                total += d.path.stat().st_size
            except OSError:
                pass
    return total


def usage_log(root, op, *, scope=None, bytes_in=None, bytes_out=0, tokens=None,
              note=None):
    """Append a usage record for an **adapter verb** the Core never sees itself —
    `ask`, `review`, `synthesize` (T-088). These are the real token spenders, so
    measuring them is what answers "is routine `review` worth its cost?".

    `bytes_in` defaults to the deterministic `_scope_bytes` of `scope` (the doc/source
    ids the verb read) — a faithful, reproducible *proxy* for how much it chewed. An
    explicit `bytes_in` overrides it. `tokens` is the **real** count when the harness
    exposes it (Claude Code /cost, an API `usage` field, subagent task metadata) and
    stays null otherwise — the ledger is honest about which it has. Best-effort like
    all usage accounting: it never fails the verb it measures.

    Returns the record's computed fields (for the caller to echo)."""
    ids = list(scope or [])
    if bytes_in is None:
        bytes_in = _scope_bytes(root, ids)
    extra = {}
    if tokens is not None:
        extra["tokens"] = int(tokens)
    if ids:
        extra["scope_n"] = len(ids)
    if note:
        extra["note"] = str(note)
    log_usage(root, op, bytes_in=bytes_in, bytes_out=bytes_out, **extra)
    return {"op": op, "bytes_in": bytes_in, "bytes_out": int(bytes_out or 0),
            "tokens": tokens, "scope_n": len(ids)}


def capture(root, id, body, *, origin, tier="full", capture_reason=None,
            when="2026-07-03T00:00:00Z"):
    """Capture a **text** source (backward-compatible entry point).

    A text source's canonical bytes are the UTF-8 of `body`; the canonical file is
    `source.md` and no separate text aid is written (it *is* the text). For binary
    sources (PDF, images, …) use `capture_file`.
    """
    if not isinstance(body, str):
        raise ValueError("body must be a string")
    return _capture(root, id, raw=body.encode("utf-8"), canonical_name="source.md",
                    origin=origin, tier=tier, capture_reason=capture_reason,
                    when=when, text=None, extracted_by=None)


def capture_file(root, id, raw, filename, *, origin, tier="full",
                 capture_reason=None, when="2026-07-03T00:00:00Z",
                 text=None, extracted_by=None):
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
    ext = Path(filename).suffix.lower()
    canonical_name = "source" + (ext or ".bin")

    if ext in TEXT_SUFFIXES:
        text, extracted_by = None, None          # canonical is itself the text
    elif text is None:
        ex = extractors.for_format(ext)
        if ex is not None:
            try:
                text, extracted_by = ex.extract(raw), ex.name
            except Exception:                    # bytes-only fallback (rule 5)
                text, extracted_by = None, None

    origin = dict(origin)
    origin.setdefault("recoverable", True)
    return _capture(root, id, raw=raw, canonical_name=canonical_name,
                    origin=origin, tier=tier, capture_reason=capture_reason,
                    when=when, text=text, extracted_by=extracted_by)


def _capture(root, id, *, raw, canonical_name, origin, tier, capture_reason,
             when, text, extracted_by):
    """Shared capture engine — hash-first dedup, immutable write, versioning.

    Contract (validated by tests/test_core_capture*.py):
      - NEW content  -> writes sources/<id>/{source<ext>, [source-text.md], meta.yml},
                        v1 ledger, content_hash over the canonical BYTES; returns
                        action="created".
      - IDENTICAL bytes (any existing id) -> no new source; action="deduped".
      - CHANGED bytes of an existing id -> new version: prior canonical retained as
                        source.v<N><ext> (and its aid as source-text.v<N>.md), the
                        current names hold the new version, ledger + hash advanced;
                        action="versioned".
      - Always appends to log.md; never creates or edits a derived document.
      - Atomic: invalid input raises ValueError before any write; a new source is
        assembled in a temp dir and renamed into place.

    Returns: {"id", "action", "version", "path", "content_hash", "canonical"}.
    """
    root = Path(root)

    # --- validate up front, before any write (atomic on bad input) ---------- #
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

    sdir = sources / id

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

        # retain prior canonical (and its aid), repoint the prior ledger entry
        prior_name = f"source.v{cur_n}{cur_canonical.suffix}"
        (sdir / prior_name).write_bytes(cur_canonical.read_bytes())
        prior_aid_name = None
        if cur_aid and (sdir / cur_aid).exists():
            prior_aid_name = f"source-text.v{cur_n}.md"
            (sdir / prior_aid_name).write_text(
                (sdir / cur_aid).read_text(encoding="utf-8"), encoding="utf-8")
        for entry in meta.get("history", []):
            if entry.get("version") == cur_n:
                if entry.get("file"):
                    entry["file"] = prior_name
                if entry.get("text_aid"):
                    entry["text_aid"] = prior_aid_name

        # write the new current canonical (drop the old name if the ext changed)
        if cur_canonical.name != canonical_name and cur_canonical.exists():
            cur_canonical.unlink()
        (sdir / canonical_name).write_bytes(raw)
        # write / clear the current text aid
        if aid_name:
            (sdir / aid_name).write_text(text, encoding="utf-8")
        elif cur_aid and (sdir / cur_aid).exists():
            (sdir / cur_aid).unlink()          # new version is bytes-only

        meta["content_hash"] = h
        meta["version"] = new_n
        meta["captured_at"] = when
        new_entry = {"version": new_n, "content_hash": h, "captured_at": when,
                     "file": canonical_name, "supersedes": cur_n}
        if aid_name:
            new_entry["text_aid"] = aid_name
            new_entry["extracted_by"] = extracted_by
        meta.setdefault("history", []).append(new_entry)
        meta_p.write_text(_dump_yaml(meta), encoding="utf-8")
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
    _append_log(root, when, f"capture | created | {id} ({tier})")
    return {"id": id, "action": "created", "version": 1, "path": str(sdir),
            "content_hash": h, "canonical": canonical_name}


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
                  when=when or _now())
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
          * else                                    -> ``new``
        `id` is optional; with no target lineage to compare against, a hash-miss is
        honestly ``new`` (``changed`` needs the intended id).

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


# --------------------------------------------------------------------------- #
# place / regenerate_index — the deterministic projection (SPEC §5.3)
# --------------------------------------------------------------------------- #
_DERIVED_GROUPS = [("Summaries", "summary"), ("Entities", "entity"),
                   ("Concepts", "concept"), ("Questions", "question"),
                   ("Insights", "insight")]


def _cover_map(derived):
    """source id -> the derived doc that covers it (a `summary` preferred), for
    the source→summary blurb join shared by the index and project pages."""
    cover = {}
    for d in sorted(derived, key=lambda x: (x.type != "summary", x.id)):
        for s in d.data.get("sources") or []:
            sid = s.get("id") if isinstance(s, dict) else s
            cover.setdefault(sid, d)
    return cover


def _blurb(title, abstract):
    return f"{title} — {abstract}" if abstract else title


def _index_markers(d, current_by_source):
    """The compact coded metadata layer for a derived doc's index line — the
    card-catalogue 'call number' (T-056, ADR-0011/0014): the human title+abstract
    stays skimmable, and this legible marker set serves the AI librarian. A pure
    deterministic projection — assurance rung + corroboration breadth from
    frontmatter, staleness via the *same* recorded-vs-current source-hash check the
    linter uses for L4, `global` from scope. No authored prose.

    Order: `<rung> · <N source(s)> · [stale]`. Rung and count are always present
    (a uniform field an AI can rely on); `stale` appears only when true (surface the
    exception, stay quiet otherwise — the freshness posture). (`scope: global` lives
    on project pages, not derived docs, so it is marked in the Projects group.)"""
    parts = [d.data.get("derivation") or "extracted"]          # assurance rung
    srcs = d.data.get("sources") or []
    if srcs:
        parts.append(f"{len(srcs)} source" + ("s" if len(srcs) != 1 else ""))
    stale = d.data.get("status") == "stale"
    for s in srcs:
        recorded = s.get("hash") if isinstance(s, dict) else None
        current = current_by_source.get(s.get("id") if isinstance(s, dict) else s)
        if recorded and current and recorded != current:
            stale = True
            break
    if stale:
        parts.append("stale")
    return " · ".join(parts)


def regenerate_index(root):
    """Rebuild index.md as a pure projection of document frontmatter (SPEC §5.3).

    Sources first — each borrowing its description from the derived doc that
    covers it (a source→summary join), or its origin locator if none covers it
    yet. Then derived docs by category, each rendering `title` (+ `abstract`).
    No free text is authored; the index is *computed*, and every registered doc
    id appears (so L8 holds). Deterministic and idempotent.
    """
    root = Path(root)
    linter = Linter(root)
    linter.load()
    sources = sorted((d for d in linter.docs if d.kind == "source"), key=lambda x: x.id)
    derived = [d for d in linter.docs if d.kind == "derived"]
    projects = sorted((d for d in linter.docs if d.kind == "project"), key=lambda x: x.id)
    decisions = sorted((d for d in linter.docs if d.kind == "decision"), key=lambda x: x.id)

    # source id -> the derived doc that covers it (prefer a summary), for its blurb
    cover = _cover_map(derived)
    # source id -> its current content_hash, so the derived-doc markers can flag
    # staleness (recorded vs current) exactly as the linter's L4 does.
    current_by_source = {d.id: d.data.get("content_hash") for d in sources}

    def rel(p):
        return p.relative_to(root).as_posix()

    lines = ["# Index", ""]
    if sources:
        lines.append("## Sources")
        for d in sources:
            cov = cover.get(d.id)
            origin = d.data.get("origin") or {}
            if cov is not None:
                desc = cov.data.get("title", cov.id)
                # Surface the source's origin locator (a URL, repo, connector ref) next to its
                # summary title, so a human skimming the index sees the LINEAGE without opening
                # the source's meta.yml. Most valuable for web/reference sources.
                ref = origin.get("ref")
                if ref:
                    desc = f"{desc} — {ref}"
            else:
                desc = f"(source; {origin.get('ref') or origin.get('system') or 'not yet summarized'})"
            # Link to the actual canonical file (source.pdf, …), not a hardcoded
            # source.md that binary sources don't have (ADR-0010).
            canonical = current_canonical(d.path, d.data)
            target = f"sources/{d.id}/{canonical.name}" if canonical else f"sources/{d.id}/"
            # tier marker — a reference-tier source is authority-not-storage (can't be
            # re-verified byte-for-byte); flag it, leave full-capture (the default) bare.
            tier = " · reference" if d.data.get("capture") == "reference" else ""
            lines.append(f"- [{d.id}]({target}) — {desc}{tier}")
        lines.append("")
    for label, typ in _DERIVED_GROUPS:
        items = sorted((d for d in derived if d.type == typ), key=lambda x: x.id)
        if not items:
            continue
        lines.append(f"## {label}")
        for d in items:
            blurb = _blurb(d.data.get('title', d.id), d.data.get('abstract'))
            markers = _index_markers(d, current_by_source)
            suffix = f"  · {markers}" if markers else ""
            lines.append(f"- [{d.id}]({rel(d.path)}) — {blurb}{suffix}")
        lines.append("")
    for label, group in (("Projects", projects), ("Decisions", decisions)):
        if not group:
            continue
        lines.append(f"## {label}")
        for d in group:
            # mark the always-in-scope global hub (project pages only carry scope)
            scope_mark = "  · global" if d.data.get("scope") == "global" else ""
            lines.append(f"- [{d.id}]({rel(d.path)}) — {d.data.get('title', d.id)}{scope_mark}")
        lines.append("")

    index = root / "index.md"
    index.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    return index


# --------------------------------------------------------------------------- #
# fingerprint — the freshness hash as a Core op (ADR-0005, SPEC §4.4)
# --------------------------------------------------------------------------- #
def fingerprint(root):
    """Return the content fingerprint over all registered docs (excludes
    index.md / log.md by construction). Same value the linter computes."""
    linter = Linter(Path(root))
    linter.load()
    return linter.content_fingerprint()


# --------------------------------------------------------------------------- #
# find — deterministic retrieval (the substrate `find` presents and `ask` uses)
# --------------------------------------------------------------------------- #
def find(root, query, type=None):
    """Return docs whose id/title/abstract/tags/body contain ALL whitespace-
    separated query terms (case-insensitive). Sources first, then derived, then
    projects/decisions, each by id. Returns [{id, kind, type, title, path}].

    `type` (optional) restricts results to docs of that frontmatter type — e.g.
    `type="decision"` is the retrieval half of the `why` verb (SPEC §5.5). An empty
    query with a type lists every doc of that type.
    """
    root = Path(root)
    terms = [t for t in query.lower().split() if t]
    linter = Linter(root)
    linter.load()
    order = {"source": 0, "derived": 1, "project": 2, "decision": 3}
    results = []
    for d in linter.docs:
        if d.kind == "manifest":
            continue
        if type is not None and d.type != type:
            continue
        parts = [d.id]
        for k in ("title", "abstract"):
            if d.data.get(k):
                parts.append(str(d.data[k]))
        parts += [str(t) for t in (d.data.get("tags") or [])]
        try:
            # A source's searchable text is its aid/canonical text (ADR-0010) —
            # NOT a hardcoded source.md, which binary sources don't have.
            parts.append(source_text(d.path, d.data)
                         if d.kind == "source" else d.path.read_text(encoding="utf-8"))
        except OSError:
            pass
        hay = "\n".join(parts).lower()
        if all(t in hay for t in terms):
            results.append({"id": d.id, "kind": d.kind, "type": d.type,
                            "title": d.data.get("title", d.id), "path": str(d.path)})
    results.sort(key=lambda r: (order.get(r["kind"], 9), r["id"]))
    return results


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


def write_derived(root, id, *, body, sources, type="summary", title,
                  abstract=None, status="current", see_also=None,
                  derivation=None, derived_at="2026-07-03T00:10:00Z", connectors=None):
    """Write a derived document with provenance — the write half of derivation.

    The adapter supplies judgment (title/abstract/body, and *which* sources);
    Core writes the file, copying each source's CURRENT `content_hash` into the
    provenance list (so the doc is born fresh, L4-clean), and enforces
    grounding-in-sources-only at the boundary: a provenance id that is not a real
    source raises ValueError (I3 — no chaining). Atomic single-file write.

    Returns {"id", "type", "path", "sources"}.
    """
    root = Path(root)
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


# --------------------------------------------------------------------------- #
# write_project — create/update a project page (a curated VIEW; ADR-0002/0017)
# --------------------------------------------------------------------------- #
def _render_project_body(root, members, description=None, this_id=None, scope="project"):
    """Project each member's own title/abstract onto the page — the deterministic
    skim surface (ADR-0017). A source borrows its covering summary's title (the
    source→summary join the index uses); a derived doc renders its own
    title/abstract. Links are relative to the `projects/` dir. No prose is
    authored — the body is *computed* from member frontmatter, like the index.

    A non-global page also carries a computed **Always in scope** pointer to every
    `scope: global` view (SPEC §5.6): the global layer is unioned into every
    scope at query time (`resolve_scope`), so the human skimming this page must
    see it applies here too. It is a *reference*, not the members — single source
    of truth stays the global page; the pointer only changes when the *set* of
    global views does (not when their members do).
    """
    root = Path(root)
    linter = Linter(root)
    linter.load()
    by_id = {d.id: d for d in linter.docs}
    cover = _cover_map([d for d in linter.docs if d.kind == "derived"])
    global_views = sorted(
        (d for d in linter.docs
         if d.kind == "project" and d.data.get("scope") == "global" and d.id != this_id),
        key=lambda d: d.id)

    def target_and_blurb(mid):
        d = by_id.get(mid)
        if d is None:
            return f"../{mid}", None  # dangling link — L11 flags it
        if d.kind == "source":
            cov = cover.get(mid)
            canonical = current_canonical(d.path, d.data)
            tgt = f"../sources/{mid}/{canonical.name}" if canonical else f"../sources/{mid}/"
            if cov is None:
                return tgt, "(not yet summarized)"
            return tgt, _blurb(cov.data.get("title", cov.id), cov.data.get("abstract"))
        tgt = "../" + d.path.relative_to(root).as_posix()
        return tgt, _blurb(d.data.get("title", mid), d.data.get("abstract"))

    lines = []
    if description:
        lines += [description.rstrip(), ""]
    lines.append("## Members")
    if not members:
        lines.append("_No members yet._")
    for mid in members:
        tgt, blurb = target_and_blurb(mid)
        lines.append(f"- [{mid}]({tgt})" + (f" — {blurb}" if blurb else ""))

    if scope != "global" and global_views:
        lines += ["", "## Always in scope",
                  "_Global views apply to every project (SPEC §5.6); unioned into "
                  "this scope automatically._"]
        for gv in global_views:
            title = gv.data.get("title", gv.id)
            lines.append(f"- [{gv.id}]({gv.id}.md) — {title}")
    return "\n".join(lines).rstrip("\n") + "\n"


def write_project(root, id, *, title=None, add_members=None, scope=None,
                  description=None, maintained_by=None, tags=None, when=None):
    """Create or update a project page — a curated VIEW (ADR-0002, ADR-0017).

    Members are *links, not provenance*: this cannot reuse `write_derived` (that
    path demands ≥1 source + hashes). `add_members` are unioned into any existing
    members (order-stable); `title`/`scope`/`description`/`maintained_by`/`tags`
    update in place, falling back to the existing page's values. The body is a
    deterministic projection of each member's own title/abstract (the skim
    surface) — no authored prose. Atomic single-file write, idempotent.

    Returns {"id", "type", "path", "members", "scope"}.
    """
    root = Path(root)
    when = when or _now()
    ppath = root / "projects" / f"{id}.md"

    existing = {}
    if ppath.exists():
        fm, _ = muninn_lint.split_frontmatter(ppath.read_text(encoding="utf-8"))
        existing = fm or {}

    title = title or existing.get("title")
    if not title:
        raise ValueError("a project needs a title")

    members = list(existing.get("members") or [])
    for m in (add_members or []):
        if m not in members:
            members.append(m)

    scope = scope or existing.get("scope") or "project"
    if scope not in muninn_lint.SCOPE_VALUES:
        raise ValueError(f"scope {scope!r} not one of "
                         f"{' | '.join(sorted(muninn_lint.SCOPE_VALUES))} (L16)")

    description = description if description is not None else existing.get("description")
    maintained_by = maintained_by if maintained_by is not None else existing.get("maintained_by")
    tags = tags if tags is not None else existing.get("tags")

    fm = {"id": id, "type": "project", "title": title}
    if description:
        fm["description"] = description
    fm["members"] = members
    if scope != "project":            # 'project' is the default (SPEC §5.6) — keep clean pages clean
        fm["scope"] = scope
    if maintained_by:
        fm["maintained_by"] = maintained_by
    if tags:
        fm["tags"] = tags

    body = _render_project_body(root, members, description, this_id=id, scope=scope)
    doc_text = "---\n" + _dump_yaml(fm) + "---\n" + body

    ppath.parent.mkdir(exist_ok=True)
    tmp = ppath.parent / f".{id}.md.tmp"
    tmp.write_text(doc_text, encoding="utf-8")
    tmp.replace(ppath)  # atomic replace into place
    _append_log(root, when, f"project | {id} <- {', '.join(members) or '(empty)'}")
    return {"id": id, "type": "project", "path": str(ppath),
            "members": members, "scope": scope}


def reproject(root, when=None):
    """Re-render every project page from current state — the ADR-0018 follow-ons (T-057).

    A regenerate-class maintenance pass (like `stamp`), CLI/operational, idempotent:

    - **Migrate a pre-hub base:** if no `scope: global` view exists (a Muninn created
      before ADR-0018), seed the canonical `global` hub — exactly what `init` seeds now
      — so the always-in-scope layer is present. `resolve_scope` was always correct
      without it; this makes the *page* layer consistent too.
    - **Reproject on global-set change:** each non-global page's **Always in scope**
      pointer is a *write-time* projection (SPEC §5.6), so a hand-authored *second*
      `scope: global` view leaves older pages stale until re-rendered. Re-running
      `write_project` on every page recomputes the pointer (and refreshes each member's
      projected blurb — the sibling ADR-0017 'refresh blurbs when a member changes'
      case) from current frontmatter. No authored content is touched; the body is a
      pure projection.

    Returns {seeded_global, reprojected: [ids]}."""
    root = Path(root)
    when = when or _now()
    linter = Linter(root)
    linter.load()
    projects = [d for d in linter.docs if d.kind == "project"]

    seeded = False
    if not any(d.data.get("scope") == "global" for d in projects):
        write_project(root, "global", title="Global context",
                      description="Standing context that applies to every project — "
                                  "always in scope.",
                      scope="global", when=when)
        seeded = True
        linter = Linter(root)
        linter.load()
        projects = [d for d in linter.docs if d.kind == "project"]

    reprojected = []
    for d in sorted(projects, key=lambda x: x.id):
        write_project(root, d.id, when=when)   # re-render in place; recomputes the pointer + blurbs
        reprojected.append(d.id)
    regenerate_index(root)
    return {"seeded_global": seeded, "reprojected": reprojected}


# --------------------------------------------------------------------------- #
# record_decision — the owner records a decision (AUTHORED, not derived; ADR-0019)
# --------------------------------------------------------------------------- #
def _source_version(root, sid):
    """Current version of a source id, or None if it does not resolve."""
    meta_p = Path(root) / "sources" / sid / "meta.yml"
    if not meta_p.exists():
        return None
    return int(_load_yaml(meta_p).get("version", 1))


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
    when = when or _now()
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


# --------------------------------------------------------------------------- #
# resolve_scope — a scope -> its working-set member ids (SPEC §5.6, ADR-0009 §2)
# --------------------------------------------------------------------------- #
def resolve_scope(root, project=None):
    """Resolve a scope to the set of member ids it covers — deterministic set
    math, no judgment (SPEC §5.6, ADR-0009 §2, ADR-0017). The read-side companion
    to `write_project`: `synthesize` calls this to learn its working set instead
    of re-deriving it per adapter.

    Every `scope: global` view is ALWAYS unioned in — the cross-cutting layer
    (org constraints, business model) the user never has to remember to include.

    - `project` given: working set = that project page's members ∪ every global
      view's members. An unknown project id raises ValueError (the user named a
      scope that isn't there — surface it, don't silently fall back to the base).
    - `project` None (whole base): working set = the whole base (every source +
      derived doc id); each global view is already a subset, so the union is
      implicit — `global_views` is still reported for transparency.

    Returns {"scope": project|None, "whole_base": bool,
             "global_views": [project ids, sorted],
             "members": [resolved member ids, sorted]}.
    """
    root = Path(root)
    linter = Linter(root)
    linter.load()
    projects = [d for d in linter.docs if d.kind == "project"]

    global_views, global_members = [], []
    for d in projects:
        if d.data.get("scope") == "global":
            global_views.append(d.id)
            for m in (d.data.get("members") or []):
                if m not in global_members:
                    global_members.append(m)

    if project is None:
        members = sorted(d.id for d in linter.docs if d.kind in ("source", "derived"))
        return {"scope": None, "whole_base": True,
                "global_views": sorted(global_views), "members": members}

    named = next((d for d in projects if d.id == project), None)
    if named is None:
        raise ValueError(
            f"project {project!r} not found — no projects/{project}.md to scope to")
    resolved = set(named.data.get("members") or []) | set(global_members)
    return {"scope": project, "whole_base": False,
            "global_views": sorted(global_views), "members": sorted(resolved)}


#: origin systems that are LOCAL, not reachable connectors — skipped in the projection.
_LOCAL_ORIGINS = {"file", "chat"}


def connector_projection(root):
    """Project the distinct connectors the **resource-landscape layer** references
    (ADR-0021 §2, ADR-0028) — a deterministic, faithful view (no inference, no registry):
    the computed *skeleton* to the landscape docs' authored *flesh*. Over every
    `scope: global` view's members it unions two grounded inputs:

      (a) the `origin.{system, ref}` of **source** members — the connectors your durable
          knowledge came *from* (a repo mental model's source contributes `repo:<url>` for
          free); local origins (`file`, `chat`) are not connectors and are skipped.
      (b) an explicit `connectors: [{system, ref}]` field on **derived** members — for a
          connector a landscape doc *asserts* but hasn't ingested from ("contracts in Drive").

    Returns `[{system, ref, referenced_by: [ids]}]`, sorted. Like `index.md`, it is a pure
    projection of frontmatter — it goes stale like any projection, never a durable registry."""
    from collections import defaultdict
    root = Path(root)
    linter = Linter(root)
    linter.load()
    by_id = {d.id: d for d in linter.docs}

    members: list[str] = []
    for d in linter.docs:
        if d.kind == "project" and d.data.get("scope") == "global":
            for m in (d.data.get("members") or []):
                if m not in members:
                    members.append(m)

    conns: dict = defaultdict(set)
    for mid in members:
        d = by_id.get(mid)
        if d is None:
            continue
        if d.kind == "source":                                   # (a) origin-union
            origin = d.data.get("origin") or {}
            system = origin.get("system")
            if system and system not in _LOCAL_ORIGINS:
                conns[(system, origin.get("ref"))].add(mid)
        for c in (d.data.get("connectors") or []):               # (b) explicit assertions
            if isinstance(c, dict) and c.get("system"):
                conns[(c["system"], c.get("ref"))].add(mid)

    out = [{"system": s, "ref": r, "referenced_by": sorted(ids)}
           for (s, r), ids in conns.items()]
    out.sort(key=lambda c: (c["system"], c["ref"] or ""))
    return out


# --------------------------------------------------------------------------- #
# init — scaffold a new Muninn (operational verb; deterministic, SPEC §3, §5.8)
# --------------------------------------------------------------------------- #
_LAYOUT = ("sources", "summaries", "entities", "concepts", "questions",
           "insights", "projects", "decisions")


_TOOL_ROOT_SENTINEL = ".odin-tool-root"


def _tool_root_above(target) -> Path | None:
    """The nearest dir at/above `target` carrying the ODIN tool-root sentinel, else
    None. The deterministic half of the T-032 guard (ADR-0032): a Muninn must live
    separately from ODIN-the-tool (ADR-0002). The sentinel is committed to ODIN's dev
    repo root and is NOT copied into the shipped plugin bundle, so a real user running
    from their own folder never trips it; only a dev checkout does. `target` need not
    exist yet — we walk its resolved path's parents."""
    p = Path(target).resolve()
    for cand in (p, *p.parents):
        if (cand / _TOOL_ROOT_SENTINEL).exists():
            return cand
    return None


def init(root, name=None, when=None, allow_tool_root=False):
    """Scaffold a Muninn: manifest, MUNINN.md (from the template), the standard
    layout, index.md, log.md. No-op with a report if already a Muninn.

    **Soft-warn tool-repo guard (T-032/ADR-0032):** if the target sits inside ODIN's
    own checkout (sentinel found) and `allow_tool_root` is not set, return an
    `action: "warn"` result and write **nothing** — the adapter surfaces it and, on the
    user's consent, re-calls with `allow_tool_root=True`. Surface-don't-block
    (principle 5): the consented op still proceeds."""
    root = Path(root)
    when = when or _now()
    manifest = root / "muninn.yml"
    if manifest.exists():
        return {"action": "noop", "path": str(root), "reason": "already a Muninn"}
    if not allow_tool_root:
        tr = _tool_root_above(root)
        if tr is not None:
            return {"action": "warn", "path": str(root), "tool_root": str(tr),
                    "warning": f"target is inside the ODIN tool checkout ({tr}/"
                               f"{_TOOL_ROOT_SENTINEL}); a Muninn should live separately "
                               f"(ADR-0002). Re-run elsewhere, or pass --allow-tool-root "
                               f"to scaffold here anyway."}
    root.mkdir(parents=True, exist_ok=True)
    for d in _LAYOUT:
        (root / d).mkdir(exist_ok=True)
    name = name or root.name
    # The integrity knob is written present-but-off, so it is discoverable in the file
    # (self-documenting) rather than an invisible absent key (ADR-0029). Off by default;
    # flip to true — or ask the adapter to — to enforce L19 (out-of-band derived-doc edits).
    manifest.write_text(
        f"muninn: {FORMAT_VERSION}\nname: {name}\ncreated_at: {when}\n"
        f"integrity:\n  derived_self_hash: false  # opt-in: enforce L19 (out-of-band edits)\n",
        encoding="utf-8")

    # MUNINN.md from the scaffold template: drop the leading comment, fill tokens.
    tmpl = (Path(__file__).resolve().parent / "templates" / "MUNINN.md").read_text(encoding="utf-8")
    if tmpl.startswith("<!--"):
        end = tmpl.find("-->")
        if end != -1:
            tmpl = tmpl[end + 3:].lstrip("\n")
    tmpl = (tmpl.replace("{{NAME}}", name)
                .replace("{{FORMAT_VERSION}}", FORMAT_VERSION)
                .replace("{{CREATED}}", when))
    (root / "MUNINN.md").write_text(tmpl, encoding="utf-8")

    (root / "index.md").write_text("# Index\n", encoding="utf-8")
    (root / "log.md").write_text("# Log\n", encoding="utf-8")
    # The disposable-index tier is operational, never knowledge — keep it out of
    # git (ADR-0027). Written only if the Muninn has no .gitignore of its own.
    gi = root / ".gitignore"
    if not gi.exists():
        gi.write_text(".odin/\n", encoding="utf-8")
    _append_log(root, when, f"init | created Muninn '{name}' (format {FORMAT_VERSION})")

    # Seed the one canonical global view (ADR-0018): the always-in-scope home for
    # cross-cutting context, discoverable from the moment you init. An empty
    # placeholder — projected into the index so the fresh base is lint-clean out of
    # the box (L8 index-complete, L16 scope-enum).
    write_project(root, "global", title="Global context",
                  description="Standing context that applies to every project — "
                              "always in scope.",
                  scope="global", when=when)
    regenerate_index(root)
    return {"action": "created", "path": str(root), "name": name}


# --------------------------------------------------------------------------- #
# CLI — the command surface the adapter Skill (and a human) invoke
# --------------------------------------------------------------------------- #
def _read_body(args) -> str:
    if getattr(args, "file", None) and args.file != "-":
        return Path(args.file).read_text(encoding="utf-8")
    return sys.stdin.read()


def main(argv=None):
    # Help text and `find`/`resolve` output carry non-ASCII (—, ·, ∪). On a
    # Windows console defaulted to cp1252, argparse/print raise UnicodeEncodeError
    # mid-write; force UTF-8 so the CLI is codepage-independent (no-op where the
    # stream is already UTF-8 or can't be reconfigured, e.g. a captured buffer).
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    p = argparse.ArgumentParser(prog="muninn_core",
                                description="Muninn Core — deterministic operations (ADR-0008).")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="scaffold a new Muninn")
    pi.add_argument("root")
    pi.add_argument("--name")
    pi.add_argument("--allow-tool-root", action="store_true",
                    help="scaffold even if the target is inside ODIN's own checkout "
                         "(overrides the soft-warn tool-repo guard; e.g. dogfooding)")

    pc = sub.add_parser("capture", help="capture a source (text via --file/stdin, "
                                        "or original bytes via --source-file)")
    pc.add_argument("root")
    pc.add_argument("id")
    pc.add_argument("--file")
    pc.add_argument("--source-file", help="capture this file's ORIGINAL BYTES as the "
                                          "source (binary-safe; extracts a text aid, ADR-0010)")
    pc.add_argument("--filename", help="canonical filename hint (defaults to --source-file's name)")
    pc.add_argument("--origin-system", required=True)
    pc.add_argument("--origin-ref", required=True)
    pc.add_argument("--tier", default="full", choices=["full", "reference"])
    pc.add_argument("--reason")
    pc.add_argument("--recoverable", dest="recoverable",
                    action=argparse.BooleanOptionalAction, default=None,
                    help="declare whether the original is re-fetchable via origin.ref "
                         "(sets origin.recoverable; needed for the regenerate self-heal "
                         "re-fetch on a URL/connector source, T-066). Text-path default "
                         "is unset; --source-file still defaults True.")

    pdd = sub.add_parser("dedup-check",
                         help="dry-run dedup: report already-captured/changed/new for a "
                              "candidate WITHOUT writing (explore preview; ADR-0020)")
    pdd.add_argument("root")
    pdd.add_argument("--id", help="candidate's intended source id (enables changed vs new)")
    pdd.add_argument("--source-file", help="candidate file whose bytes to hash (content-hash rung)")
    pdd.add_argument("--filename", help="canonical filename hint (defaults to --source-file's name)")
    pdd.add_argument("--origin-ref", help="reference-tier locator: match by origin.ref when "
                                          "no bytes are held (no hash)")

    pss = sub.add_parser("source-status",
                         help="report a source's deterministic facts (tier, bytes-present, "
                              "recoverable, origin.ref) for fetch/self-heal decisions (T-066)")
    pss.add_argument("root")
    pss.add_argument("id")

    pd = sub.add_parser("derive", help="write a derived doc (body from --file or stdin)")
    pd.add_argument("root")
    pd.add_argument("id")
    pd.add_argument("--title", required=True)
    pd.add_argument("--abstract")
    pd.add_argument("--type", default="summary")
    pd.add_argument("--source", action="append", required=True, dest="sources")
    pd.add_argument("--derivation", choices=sorted(muninn_lint.DERIVATION_VALUES))
    pd.add_argument("--connector", action="append", default=[], metavar="system[=ref]",
                    help="assert a connector this landscape doc references (repeatable; T-070)")
    pd.add_argument("--file")

    for name in ("index", "fingerprint", "lint"):
        sp = sub.add_parser(name, help=f"{name} the Muninn")
        sp.add_argument("root")

    pst = sub.add_parser("stamp", help="backfill derived-doc self_hashes (self-heal a base "
                                       "whose docs predate self-hashing; ADR-0029)")
    pst.add_argument("root")

    prp = sub.add_parser("reproject", help="re-render every project page: seed the global hub "
                                           "if missing + refresh the Always-in-scope pointer "
                                           "(ADR-0018 follow-ons; T-057)")
    prp.add_argument("root")

    pcr = sub.add_parser("capture-repo",
                         help="capture a repo as a constitution-grounded reference source "
                              "(README/ARCHITECTURE/ADRs/contract/manifests/topology; ADR-0028)")
    pcr.add_argument("root")
    pcr.add_argument("id")
    pcr.add_argument("repo", help="path to the repository")
    pcr.add_argument("--origin-ref", help="durable locator (remote URL); defaults to abs path")
    pcr.add_argument("--head", help="optional commit stamp (recorded, never the staleness trigger)")
    pcr.add_argument("--surface", action="append", default=[], metavar="LABEL=glob[,glob...]",
                     help="adapter-chosen surface (repeatable) — AUGMENTS the default floor; "
                          "e.g. --surface deploy=Dockerfile,netlify.toml (ADR-0028 §6)")

    pconn = sub.add_parser("connectors",
                           help="project the distinct connectors the scope:global landscape "
                                "references (origin-union + explicit fields; ADR-0021 §2 / T-070)")
    pconn.add_argument("root")

    pu = sub.add_parser("usage", help="report the disposable usage ledger (ADR-0027)")
    pu.add_argument("root")

    pul = sub.add_parser("usage-log",
                         help="append a usage record for an adapter verb — ask/review/"
                              "synthesize (T-088). Core computes the scope byte-footprint.")
    pul.add_argument("root")
    pul.add_argument("op", help="the verb being measured, e.g. review | ask | synthesize")
    pul.add_argument("--scope", action="append", dest="scope",
                     help="a doc/source id the verb read (repeatable); Core sums their "
                          "readable bytes as the deterministic cost proxy")
    pul.add_argument("--bytes-in", type=int, dest="bytes_in",
                     help="override the computed scope byte-footprint")
    pul.add_argument("--bytes-out", type=int, dest="bytes_out", default=0,
                     help="bytes the verb produced (e.g. the answer/insight length)")
    pul.add_argument("--tokens", type=int,
                     help="REAL token count when the harness exposes it (else omit)")
    pul.add_argument("--note")

    pfind = sub.add_parser("find", help="retrieve docs matching a query")
    pfind.add_argument("root")
    pfind.add_argument("query", nargs="*", help="query terms (omit to list all of --type)")
    pfind.add_argument("--type", dest="type",
                       help="restrict to a doc type, e.g. 'decision' (the `why` verb)")

    pp = sub.add_parser("project", help="create/update a project page (a curated view; ADR-0002/0017)")
    pp.add_argument("root")
    pp.add_argument("id")
    pp.add_argument("--title", help="required when creating; kept on update if omitted")
    pp.add_argument("--member", action="append", dest="add_members",
                    help="member id to add (repeatable; unioned into existing members)")
    pp.add_argument("--scope", choices=sorted(muninn_lint.SCOPE_VALUES))
    pp.add_argument("--description", help="a plain maintainer label (not a sourced claim)")
    pp.add_argument("--maintained-by", dest="maintained_by")
    pp.add_argument("--tag", action="append", dest="tags")

    pr = sub.add_parser("resolve", help="resolve a scope to its working-set member ids "
                                        "(a project ∪ every global view; SPEC §5.6)")
    pr.add_argument("root")
    pr.add_argument("project", nargs="?", help="a project id; omit for the whole base")

    pdec = sub.add_parser("record-decision",
                          help="record the owner's decision — AUTHORED, not derived "
                               "(only on explicit request; body from --file/stdin)")
    pdec.add_argument("root")
    pdec.add_argument("id", help="stable slug id (dec-…)")
    pdec.add_argument("--title", help="required when recording; kept on --amend if omitted")
    pdec.add_argument("--status", choices=sorted(muninn_lint.DECISION_STATUS_VALUES),
                      help="proposed | accepted (default: accepted)")
    pdec.add_argument("--evidence", action="append", dest="evidence",
                      help="an informing source id (repeatable; a LINK, not provenance)")
    pdec.add_argument("--amend", action="store_true",
                      help="prepend a dated AMENDED banner to an existing decision "
                           "(append-only; never deletes prior text)")
    pdec.add_argument("--file")

    args = p.parse_args(argv)
    if args.cmd == "init":
        print(init(args.root, name=args.name, allow_tool_root=args.allow_tool_root))
    elif args.cmd == "capture":
        origin = {"system": args.origin_system, "ref": args.origin_ref}
        if args.recoverable is not None:            # explicit override, both paths (T-068)
            origin["recoverable"] = args.recoverable
        if args.source_file:
            src = Path(args.source_file)
            raw = src.read_bytes()
            res = capture_file(args.root, args.id, raw, args.filename or src.name,
                               origin=origin, tier=args.tier,
                               capture_reason=args.reason, when=_now())
            log_usage(args.root, "capture", bytes_out=len(raw),
                      id=args.id, action=res.get("action"))
            print(res)
        else:
            body = _read_body(args)
            res = capture(args.root, args.id, body, origin=origin,
                          tier=args.tier, capture_reason=args.reason, when=_now())
            log_usage(args.root, "capture", bytes_out=len(body.encode("utf-8")),
                      id=args.id, action=res.get("action"))
            print(res)
    elif args.cmd == "dedup-check":
        print(dedup_check(args.root, id=args.id, source_file=args.source_file,
                          filename=args.filename, origin_ref=args.origin_ref))
    elif args.cmd == "source-status":
        print(source_status(args.root, args.id))
    elif args.cmd == "derive":
        body = _read_body(args)
        connectors = []
        for spec in args.connector:                    # system[=ref] -> {system, ref}
            system, _, ref = spec.partition("=")
            connectors.append({"system": system.strip(), "ref": ref.strip() or None})
        res = write_derived(args.root, args.id, body=body, sources=args.sources,
                            type=args.type, title=args.title, abstract=args.abstract,
                            derivation=args.derivation, derived_at=_now(),
                            connectors=connectors or None)
        log_usage(args.root, "derive",
                  bytes_in=sum(_source_bytes(args.root, s) for s in args.sources),
                  bytes_out=len(body.encode("utf-8")), id=args.id, type=args.type)
        print(res)
    elif args.cmd == "project":
        print(write_project(args.root, args.id, title=args.title,
                            add_members=args.add_members, scope=args.scope,
                            description=args.description, maintained_by=args.maintained_by,
                            tags=args.tags, when=_now()))
    elif args.cmd == "record-decision":
        print(record_decision(args.root, args.id, body=_read_body(args),
                              title=args.title, status=args.status,
                              evidence=args.evidence, amend=args.amend, when=_now()))
    elif args.cmd == "index":
        print(regenerate_index(args.root))
    elif args.cmd == "stamp":
        print(stamp_derived(args.root))
    elif args.cmd == "reproject":
        print(reproject(args.root))
    elif args.cmd == "capture-repo":
        extra = []
        for spec in args.surface:                      # LABEL=glob[,glob...] -> (label, [globs])
            label, _, globs = spec.partition("=")
            extra.append((label.strip(), [g.strip() for g in globs.split(",") if g.strip()]))
        print(capture_repo(args.root, args.id, args.repo, origin_ref=args.origin_ref,
                           head=args.head, extra_surfaces=extra or None))
    elif args.cmd == "connectors":
        conns = connector_projection(args.root)
        for c in conns:
            ref = f" {c['ref']}" if c["ref"] else ""
            print(f"{c['system']}{ref}  <- {', '.join(c['referenced_by'])}")
        print(f"({len(conns)} connector(s) across the scope:global landscape)")
    elif args.cmd == "usage":
        rep = usage_report(args.root)
        for op, agg in sorted(rep["by_op"].items()):
            tok = str(agg.get("tokens", 0)) if agg.get("tokens_n") else "n/a"
            print(f"{op:16} {agg['count']:>5}x  in={agg['bytes_in']:>10}  "
                  f"out={agg['bytes_out']:>10}  tok={tok:>8}")
        print(f"({rep['total_ops']} op(s) logged)")
    elif args.cmd == "usage-log":
        print(usage_log(args.root, args.op, scope=args.scope, bytes_in=args.bytes_in,
                        bytes_out=args.bytes_out, tokens=args.tokens, note=args.note))
    elif args.cmd == "fingerprint":
        print(fingerprint(args.root))
    elif args.cmd == "find":
        hits = find(args.root, " ".join(args.query), type=args.type)
        for r in hits:
            print(f"{r['kind']:8} {r['id']}  —  {r['title']}")
        scope = f" of type '{args.type}'" if args.type else ""
        print(f"({len(hits)} match(es){scope})")
    elif args.cmd == "resolve":
        r = resolve_scope(args.root, args.project)
        for mid in r["members"]:
            print(mid)
        scope_label = r["scope"] if r["scope"] else "(whole base)"
        gv = ", ".join(r["global_views"]) or "(none)"
        print(f"({len(r['members'])} member(s); scope {scope_label}; "
              f"global views unioned: {gv})")
    elif args.cmd == "lint":
        return muninn_lint.Linter(Path(args.root)).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

