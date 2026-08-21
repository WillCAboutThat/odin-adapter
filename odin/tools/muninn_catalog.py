# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Catalog accelerator (ADR-0047, T-205) — SQLite + FTS5 in the disposable tier.

Structured + full-text queries over the base ("every insight citing src-X",
"all question docs still OPEN", tokens the embedding tier blurred) at O(log n)
and near-zero context cost — you query it instead of reading a projection.

Two properties, in load-bearing order:

  1. **Faithful transform, Core-computable.** Tokenization and inverted-index
     construction fabricate nothing — same input, same output, no model
     anywhere. Unlike the embedding sidecar (inference, adapter-tier by the
     Core boundary), this index sits on the safe side of that line. It still
     lives OUTSIDE the durable base, because acceleration is not knowledge.

  2. **Disposable, never load-bearing (ADR-0027).** A git-ignored, rebuildable
     `.odin/catalog.db` sidecar, exactly like `semantic.db` and the usage
     ledger. Delete it and nothing is lost; the next query rebuilds it. No
     Core guarantee rests on it, no durable doc may cite it, and `find`'s
     file walk remains the AI-free floor and the arbiter of truth.

Degrade is mechanical, inside the call (the T-090 pattern): any catalog
failure — sqlite missing FTS5, a corrupt db, an unreadable sidecar — falls
back to the deterministic `find` walk and says so in the result's `via`.
Zero new Python dependencies: `sqlite3` is stdlib.
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from muninn_lint import DERIVED_DIRS, Linter, source_text  # noqa: E402

SCHEMA_VERSION = "1"
_KIND_RANK = {"source": 0, "derived": 1, "project": 2, "decision": 3}
# The Linter's doc-carrying directories (imported, so the universe can't drift):
# a stat of every carrier file is the T-207 fast path's whole cost.
_DOC_DIRS = tuple(sorted(DERIVED_DIRS)) + ("decisions", "projects")


def catalog_path(root) -> Path:
    return Path(root) / ".odin" / "catalog.db"


def _connect(root) -> sqlite3.Connection:
    p = catalog_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")
    return con


def _init(con) -> bool:
    """Create tables; returns whether FTS5 is available in this sqlite build."""
    con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute(
        "CREATE TABLE IF NOT EXISTS docs ("
        " id TEXT PRIMARY KEY, kind TEXT, type TEXT, title TEXT, abstract TEXT,"
        " status TEXT, derivation TEXT, tier TEXT, origin_system TEXT,"
        " origin_ref TEXT, path TEXT, ident TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS prov (doc_id TEXT, source_id TEXT, hash TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS tags (doc_id TEXT, tag TEXT)")
    con.execute("CREATE INDEX IF NOT EXISTS prov_by_source ON prov(source_id)")
    try:
        con.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5("
            " id UNINDEXED, title, abstract, tags, body)")
        fts_ok = True
    except sqlite3.OperationalError:  # pragma: no cover — FTS5-less builds
        fts_ok = False
    con.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)",
                (SCHEMA_VERSION,))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('fts', ?)",
                ("1" if fts_ok else "0",))
    return fts_ok


def _identity(d) -> str:
    """Cheap per-doc change stamp: mtime+size of the file that carries the
    doc's frontmatter (meta.yml for a source, the doc file otherwise). A
    version bump, edit, or re-derive rewrites that file, so the stamp moves
    exactly when re-indexing is due. Same bookkeeping *discipline* as the
    semantic sidecar's hash-index, with its own storage (the sidecars stay
    independently rebuildable)."""
    p = (d.path / "meta.yml") if d.kind == "source" else d.path
    try:
        st = p.stat()
        return f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:  # pragma: no cover — racing a delete
        return "gone"


def _body(d) -> str:
    if d.kind == "source":
        return source_text(d.path, d.data or {})
    try:
        return d.path.read_text(encoding="utf-8", errors="replace")
    except OSError:  # pragma: no cover
        return ""


def _disk_idents(root: Path):
    """Stat-only snapshot of every doc's carrier file — the same file
    `_identity` stamps: sources/*/meta.yml + *.md in the derived/project/
    decision dirs, mirroring Linter.load()'s universe without parsing a byte.
    None on any OS error (the caller then takes the full path)."""
    out = {}
    try:
        sdir = root / "sources"
        if sdir.is_dir():
            for child in sdir.iterdir():
                m = child / "meta.yml"
                if child.is_dir() and m.is_file():
                    st = m.stat()
                    out[m.relative_to(root).as_posix()] = f"{st.st_mtime_ns}:{st.st_size}"
        for name in _DOC_DIRS:
            d = root / name
            if d.is_dir():
                for p in d.glob("*.md"):
                    st = p.stat()
                    out[p.relative_to(root).as_posix()] = f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:  # pragma: no cover — racing a delete
        return None
    return out


def _stored_idents(con):
    """(carrier→ident map, fts flag) from the catalog, or None when it isn't
    initialized yet. A source row's carrier is its dir's meta.yml (what
    `_identity` stats); a derived/project/decision row's is the doc file."""
    try:
        rows = con.execute("SELECT path, kind, ident FROM docs").fetchall()
        fts = con.execute("SELECT value FROM meta WHERE key='fts'").fetchone()
    except sqlite3.OperationalError:
        return None
    if fts is None:
        return None
    stored = {(p + "/meta.yml" if k == "source" else p): i for p, k, i in rows}
    return stored, fts[0] == "1"


def refresh(root):
    """Best-effort incremental (re)build: index changed docs, prune gone ones.

    Write-only and cheap — safe to call before every query (the self-heal),
    after every ingest (the warm). Never blocks the base: any failure is the
    caller's signal to degrade, not an error a user must see.

    The no-change case is a stat-only fast path (T-207): a disk snapshot of
    every carrier file compared against the stored idents, skipping the full
    Linter parse — which is O(base) per call and measured ~5× the `find` walk
    when paid every query. Any difference at all (new, gone, moved, touched)
    falls through to the full load; the walk stays the arbiter.
    """
    root = Path(root)
    con = _connect(root)
    try:
        stored = _stored_idents(con)
        if stored is not None:
            disk = _disk_idents(root)
            if disk is not None and disk == stored[0]:
                return {"status": "current", "indexed": 0, "pruned": 0,
                        "docs": len(stored[0]), "fts": stored[1]}
        linter = Linter(root)
        linter.load()
        docs = {d.id: d for d in linter.docs if d.kind in _KIND_RANK}
        fts_ok = _init(con)
        have = dict(con.execute("SELECT id, ident FROM docs"))
        gone = [i for i in have if i not in docs]
        changed = [d for i, d in docs.items() if have.get(i) != _identity(d)]
        for batch in (gone, [d.id for d in changed]):
            for doc_id in batch:
                con.execute("DELETE FROM docs WHERE id=?", (doc_id,))
                con.execute("DELETE FROM prov WHERE doc_id=?", (doc_id,))
                con.execute("DELETE FROM tags WHERE doc_id=?", (doc_id,))
                if fts_ok:
                    con.execute("DELETE FROM fts WHERE id=?", (doc_id,))
        for d in changed:
            data = d.data or {}
            origin = data.get("origin") or {}
            try:
                rel = d.path.relative_to(root).as_posix()
            except ValueError:  # pragma: no cover
                rel = d.path.as_posix()
            tags = [str(t) for t in (data.get("tags") or [])]
            con.execute(
                "INSERT INTO docs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (d.id, d.kind, d.type if d.kind != "source" else None,
                 data.get("title"), data.get("abstract"), data.get("status"),
                 data.get("derivation"), data.get("capture"),
                 origin.get("system"), str(origin.get("ref") or "") or None,
                 rel, _identity(d)))
            for s in (data.get("sources") or []):
                if isinstance(s, dict):
                    con.execute("INSERT INTO prov VALUES (?,?,?)",
                                (d.id, s.get("id"),
                                 s.get("hash") or s.get("content_hash")))
            for t in tags:
                con.execute("INSERT INTO tags VALUES (?,?)", (d.id, t))
            if fts_ok:
                con.execute("INSERT INTO fts VALUES (?,?,?,?,?)",
                            (d.id, data.get("title") or "",
                             data.get("abstract") or "", " ".join(tags),
                             _body(d)))
        con.commit()
        return {"status": "current", "indexed": len(changed),
                "pruned": len(gone), "docs": len(docs), "fts": fts_ok}
    finally:
        con.close()


def _fts_match_expr(terms: str) -> str:
    """Each whitespace token becomes a quoted FTS5 phrase, AND-joined —
    user text is data, never FTS5 query syntax."""
    toks = [t.replace('"', '""') for t in terms.split()]
    return " ".join(f'"{t}"' for t in toks)


def query(root, *, fts=None, type=None, kind=None, cites=None,
          origin_system=None, status=None, limit=50):
    """Structured + full-text query over the catalog; degrades to `find`.

    Filters AND together. Result carries `via` ("catalog" | "find") so the
    caller always knows which surface answered — the degrade is mechanical
    and inside the call, never the caller's job to remember (T-090).
    """
    root = Path(root)
    limit = max(1, min(int(limit or 50), 500))
    try:
        res = refresh(root)
        con = _connect(root)
        try:
            where, args = [], []
            base = "SELECT d.id, d.kind, d.type, d.title, d.path FROM docs d"
            if fts:
                if not res.get("fts"):
                    raise sqlite3.OperationalError("FTS5 unavailable")
                base += " JOIN fts ON fts.id = d.id"
                where.append("fts MATCH ?")
                args.append(_fts_match_expr(fts))
            if type:
                where.append("d.type = ?")
                args.append(type)
            if kind:
                where.append("d.kind = ?")
                args.append(kind)
            if cites:
                where.append("d.id IN (SELECT doc_id FROM prov WHERE source_id = ?)")
                args.append(cites)
            if origin_system:
                where.append("d.origin_system = ?")
                args.append(origin_system)
            if status:
                where.append("d.status = ?")
                args.append(status)
            if where:
                base += " WHERE " + " AND ".join(where)
            base += " ORDER BY " + ("rank" if fts else
                                    "CASE d.kind WHEN 'source' THEN 0 "
                                    "WHEN 'derived' THEN 1 WHEN 'project' THEN 2 "
                                    "ELSE 3 END, d.id")
            base += " LIMIT ?"
            args.append(limit)
            rows = con.execute(base, args).fetchall()
            hits = [{"id": r[0], "kind": r[1], "type": r[2], "title": r[3],
                     "path": r[4]} for r in rows]
            return {"via": "catalog", "hits": hits, "count": len(hits)}
        finally:
            con.close()
    except Exception:
        # Mechanical degrade: the AI-free walk answers what it can. Literal
        # terms + type map onto `find`; catalog-only filters are reported
        # dropped rather than silently unapplied.
        from muninn.projections import find
        hits = find(root, fts or "", type=type)[:limit]
        dropped = [k for k, v in (("kind", kind), ("cites", cites),
                                  ("origin_system", origin_system),
                                  ("status", status)) if v]
        out = {"via": "find", "hits": hits, "count": len(hits)}
        if dropped:
            out["dropped_filters"] = dropped
        return out


def main(argv=None):  # pragma: no cover — thin CLI for standalone use
    import argparse
    ap = argparse.ArgumentParser(prog="muninn_catalog")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refresh")
    r.add_argument("root")
    q = sub.add_parser("query")
    q.add_argument("root")
    for flag in ("--fts", "--type", "--kind", "--cites", "--origin-system", "--status"):
        q.add_argument(flag)
    q.add_argument("--limit", type=int, default=50)
    a = ap.parse_args(argv)
    if a.cmd == "refresh":
        print(json.dumps(refresh(a.root)))
    else:
        print(json.dumps(query(a.root, fts=a.fts, type=a.type, kind=a.kind,
                               cites=a.cites, origin_system=a.origin_system,
                               status=a.status, limit=a.limit)))


if __name__ == "__main__":  # pragma: no cover
    main()
