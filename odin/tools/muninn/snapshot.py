"""Disposable read-path accelerators (T-116) — the loaded-base snapshot cache and
the capture hash-index.

Everything here lives in the ADR-0027 disposable tier: rebuildable operational
state that **no Core guarantee rests on**. The discipline that keeps the Core
boundary honest:

  - **Never authoritative.** `lint` never touches this module — it always builds
    fresh and re-hashes real bytes. A hash-index *hit* is verified against the one
    `meta.yml` it names before it is believed; a wrong or corrupt index can cost a
    rebuild, never a wrong answer.
  - **Self-healing, not trusted.** Validity is a stat-only sweep (path, mtime_ns,
    size — no reads, no parses). Any change, from any writer, invalidates on the
    next access; a missing/corrupt index or cache entry is rebuilt from the base.
  - **Read-only contract.** `load_snapshot` hands out a LOADED (never `check()`ed)
    Linter shared across calls — callers must not mutate it or run rules on it.

Why this exists: nearly every read op built a fresh Linter and re-read every file
— `status` on the 130-source Yosemite base cost ~950ms *per session load*, and
capture's hash-first dedup parsed every `meta.yml` per capture (an N-doc ingest
was O(N²)). The MCP server is long-lived; it should pay the load once per change,
not once per tool call.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import muninn_lint  # noqa: E402
from .util import _load_yaml  # noqa: E402

# Doc-bearing places a loaded Linter reflects (candidates/inbox/.odin are outside
# the knowledge layer by construction and are read directly by their consumers).
_WATCHED_DIRS = ("summaries", "entities", "concepts", "questions", "insights",
                 "projects", "decisions")


# --------------------------------------------------------------------------- #
# The stat sweep — the one change detector both accelerators key on
# --------------------------------------------------------------------------- #
def _stat_part(rel, p):
    st = p.stat()
    return f"{rel}:{st.st_mtime_ns}:{st.st_size}"


def base_sweep(root) -> str:
    """Fingerprint of the base's doc-bearing files by (path, mtime_ns, size) —
    stat-only, no file is opened. Cheap enough to run on every access."""
    root = Path(root)
    parts = []
    m = root / "muninn.yml"
    if m.exists():
        parts.append(_stat_part("muninn.yml", m))
    parts.extend(sources_sweep_parts(root))
    for dn in _WATCHED_DIRS:
        d = root / dn
        if d.is_dir():
            for md in sorted(d.glob("*.md")):
                parts.append(_stat_part(f"{dn}/{md.name}", md))
    return "sha256:" + hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def sources_sweep_parts(root):
    sdir = Path(root) / "sources"
    parts = []
    if sdir.is_dir():
        for child in sorted(sdir.iterdir()):
            mp = child / "meta.yml"
            if child.is_dir() and mp.exists():
                parts.append(_stat_part(f"sources/{child.name}", mp))
    return parts


def sources_sweep(root) -> str:
    """The sources-only sweep the hash-index keys on."""
    return ("sha256:" + hashlib.sha256(
        "\n".join(sources_sweep_parts(root)).encode("utf-8")).hexdigest())


# --------------------------------------------------------------------------- #
# Snapshot cache — one loaded Linter per base, reused until anything changes
# --------------------------------------------------------------------------- #
_SNAPSHOTS: dict = {}   # resolved root -> (sweep, linter)


def load_snapshot(root):
    """A LOADED (never checked) Linter for read-only consumers (`find`, `status`,
    scope-byte accounting). Revalidated by `base_sweep` on every call: any change
    to any doc-bearing file — by this process or another — forces a fresh load.
    In the long-lived MCP server this turns per-call full loads into one load per
    change. Callers MUST NOT mutate the returned Linter or run `check()` on it."""
    key = str(Path(root).resolve())
    sweep = base_sweep(root)
    hit = _SNAPSHOTS.get(key)
    if hit is not None and hit[0] == sweep:
        return hit[1]
    linter = muninn_lint.Linter(Path(root))
    linter.load()
    _SNAPSHOTS[key] = (sweep, linter)
    return linter


# --------------------------------------------------------------------------- #
# Capture hash-index — O(1) dedup instead of parsing every meta.yml per capture
# --------------------------------------------------------------------------- #
def _index_path(root) -> Path:
    return Path(root) / ".odin" / "hash-index.json"


def current_hash_index(root) -> dict:
    """The hash-index, current as of THIS call: `{by_hash: {content_hash: id},
    by_ref: {origin_ref: id}}`. If the stored index's recorded sweep doesn't match
    the sources dir right now (or the file is absent/corrupt), it is rebuilt from
    the base — one O(N) parse, after which lookups are honest misses. Callers must
    still VERIFY any hit against the meta.yml it names (never authoritative)."""
    root = Path(root)
    sweep = sources_sweep(root)
    try:
        data = json.loads(_index_path(root).read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("sweep") == sweep:
            return data
    except Exception:
        pass
    return _rebuild(root, sweep)


def _rebuild(root, sweep) -> dict:
    idx = {"sweep": sweep, "by_hash": {}, "by_ref": {}}
    sdir = Path(root) / "sources"
    if sdir.is_dir():
        for child in sorted(sdir.iterdir()):
            mp = child / "meta.yml"
            if not (child.is_dir() and mp.exists()):
                continue
            try:
                meta = _load_yaml(mp)
            except Exception:
                continue
            sid = meta.get("id", child.name)
            if meta.get("content_hash"):
                idx["by_hash"][meta["content_hash"]] = sid
            ref = (meta.get("origin") or {}).get("ref")
            if ref:
                idx["by_ref"].setdefault(str(ref), sid)
    _write_index(root, idx)
    return idx


def note_capture(root, idx, *, content_hash, ref, id) -> None:
    """Incremental write-through after a capture wrote sources/: record the one
    new/updated source in the index `capture` already validated this call, and
    re-stamp the sweep. O(stat) — never a re-parse, so an N-doc ingest stays
    linear (the whole point). Safe to trust `idx` here: capture holds the base
    write lock between validating it and this update, so only our own write
    moved sources/ in between. Best-effort — never fails the op."""
    try:
        # a source has exactly ONE current hash — versioning replaces its entry
        idx["by_hash"] = {k: v for k, v in idx["by_hash"].items() if v != id}
        idx["by_hash"][content_hash] = id
        if ref:
            idx["by_ref"].setdefault(str(ref), id)
        idx["sweep"] = sources_sweep(root)
        _write_index(Path(root), idx)
    except Exception:
        pass


def _write_index(root, idx) -> None:
    try:
        d = Path(root) / ".odin"
        d.mkdir(exist_ok=True)
        tmp = d / ".hash-index.json.tmp"
        tmp.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_index_path(root))
    except Exception:
        pass
