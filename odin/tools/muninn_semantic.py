"""Semantic retrieval tier (T-087) — the flagship tenant of the disposable-index
tier (ADR-0027).

This closes the reader-vocabulary gap that deterministic `find` cannot (T-044):
`find('personality')` returns nothing when the doc says "temperament", because
substring matching has no notion of meaning. Here we embed the **legible layer**
(a derived doc's title + abstract + Covers/Answers facets + body) and rank
candidates by cosine similarity, implementing the AI-facing retrieval tier that
ADR-0014 already blessed.

Two bright lines this module lives inside:

  1. **It is not the Core.** Embedding is *inference*, not a faithful transform
     (the Core boundary, ADR-0008): a model reads text and emits a vector — it can
     drift, it is model-specific, it is not correct-by-construction. So this lives
     OUTSIDE `muninn_core.py`, which stays inference-free. `find` remains the
     AI-free floor; this is a separate, optional tier on top.

  2. **The index only PROPOSES (ADR-0027 §2).** A search result is a *candidate to
     read*, never a citation, never provenance, never written into the knowledge
     layer. `ask`/`review` still ground in the actual source bytes. The vector
     store is a git-ignored, rebuildable `.odin/semantic.db` sidecar — disposable
     operational state, like the usage ledger. Delete it and nothing is lost;
     `reindex` rebuilds it from the durable base.

Backend: a local Ollama embedding model (e.g. `nomic-embed-text`), reached over
HTTP with the Python stdlib — **zero new Python dependencies**. Cosine top-k is
brute force in pure Python (personal scale is hundreds–thousands of docs, not
millions; no vector DB needed). The embedder is injectable so tests run hermetically
with no Ollama.

The embedding model+version is config-provenance: **changing the model = a rebuild**
(vectors from different models are not comparable), which `reindex` does automatically
when it sees the model has changed.
"""
import argparse
import array
import hashlib
import json
import math
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import muninn_core as core  # noqa: E402  (for `retrieve`'s deterministic find floor)
from muninn_lint import Linter, split_frontmatter  # noqa: E402

# Backend config — env-driven so nothing is hardcoded (see docs/odin/ollama-setup.md).
DEFAULT_URL = os.environ.get("ODIN_OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("ODIN_EMBED_MODEL", "nomic-embed-text")
# Optional: how long Ollama keeps the embed model resident after a call (env
# `ODIN_OLLAMA_KEEP_ALIVE`, e.g. "30m", "24h", "-1" for forever). Unset → Ollama's
# default (~5m). Longer keeps the first-of-session retrieve warm (T-092).
KEEP_ALIVE = os.environ.get("ODIN_OLLAMA_KEEP_ALIVE")


class BackendUnavailable(RuntimeError):
    """The embedding backend could not be reached or is misconfigured (Ollama down,
    wrong URL, model not pulled). A *transparent, recoverable* signal — the whole
    point of the disposable tier (ADR-0027): callers catch this and **degrade to the
    AI-free `find` floor**, they do not crash and do not treat it as "no matches".
    Distinct from a genuine empty result (which is a real, backend-up []).
    """

# The sidecar lives under the disposable `.odin/` tier (git-ignored by init).
_DB_REL = (".odin", "semantic.db")


# --------------------------------------------------------------------------- #
# Embedding backend — Ollama over HTTP, stdlib only. Injectable for tests.
# --------------------------------------------------------------------------- #
def ollama_embed(texts, *, model=DEFAULT_MODEL, url=DEFAULT_URL, timeout=120):
    """Embed a list of strings via a local Ollama `/api/embed`. Returns a list of
    float vectors, one per input, in order.

    Stdlib only (no `requests`, no `ollama` client). Raises on transport failure or
    a malformed response — an empty index is better than a silently partial one, so
    the caller sees the backend is down rather than getting zero results that look
    like "nothing matched". The first call after idle can take ~30s while the model
    pages into VRAM (that is `load_duration`, not a hang), hence the generous
    default timeout.
    """
    if not texts:
        return []
    body = {"model": model, "input": list(texts)}
    if KEEP_ALIVE:                                       # keep the model resident longer (T-092)
        body["keep_alive"] = KEEP_ALIVE
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url.rstrip("/") + "/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # A down/unreachable/misconfigured backend must surface as BackendUnavailable —
    # a transparent, recoverable signal the caller degrades to `find` on — NOT a raw
    # URLError that reads like a crash and hides the "just use find" recovery.
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:                 # reachable but errored
        hint = (f" — is the model pulled?  `ollama pull {model}`"
                if e.code == 404 else "")
        raise BackendUnavailable(
            f"embedding backend at {url} returned HTTP {e.code} (model {model!r}){hint}"
        ) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:  # unreachable/timeout
        reason = getattr(e, "reason", e)
        raise BackendUnavailable(
            f"embedding backend not reachable at {url} ({reason}) — use deterministic "
            f"`find` instead, or start Ollama / set ODIN_OLLAMA_URL "
            f"(see docs/odin/ollama-setup.md)") from e
    embs = data.get("embeddings")
    if not embs or len(embs) != len(texts):
        raise BackendUnavailable(
            f"embedding backend at {url} returned {len(embs) if embs else 0} vectors "
            f"for {len(texts)} inputs (model={model!r} — pulled and an *embedding* "
            f"model, not a chat model?); falling back to `find` is safe")
    return [[float(x) for x in v] for v in embs]


# --------------------------------------------------------------------------- #
# The legible layer — what we embed for a derived doc.
# --------------------------------------------------------------------------- #
def legible_text(doc) -> str:
    """The retrieval-legible text of a derived doc: title + abstract + body (the
    Covers/Answers facets live inside the body, so the body carries them). This is
    the same enriched summary layer `find` searches and ADR-0012 invests in — we
    embed exactly what a human skim or a reader-vocabulary query would land on.
    """
    parts = []
    for key in ("title", "abstract"):
        val = doc.data.get(key)
        if val:
            parts.append(str(val))
    try:
        _, body = split_frontmatter(doc.path.read_text(encoding="utf-8"))
        if body.strip():
            parts.append(body.strip())
    except OSError:
        pass
    return "\n\n".join(parts)


def _content_hash(text: str) -> str:
    """A stable content hash of the legible text, so `reindex` re-embeds a doc only
    when its legible layer actually changed (the vectors are keyed by it)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _derived_docs(root: Path):
    """The derived (summary-layer) docs we embed, in id order. Sources are the
    ground truth `ask` reads; the *legible* layer ADR-0012 enriches for findability
    is the derived layer, so that is what the semantic tier ranks over."""
    linter = Linter(root)
    linter.load()
    return sorted((d for d in linter.docs if d.kind == "derived"),
                  key=lambda d: d.id)


# --------------------------------------------------------------------------- #
# The disposable sidecar store — a git-ignored SQLite `.odin/semantic.db`.
# --------------------------------------------------------------------------- #
def _vec_to_blob(vec) -> bytes:
    return array.array("f", vec).tobytes()


def _blob_to_vec(blob) -> array.array:
    a = array.array("f")
    a.frombytes(blob)
    return a


def _connect(root: Path) -> sqlite3.Connection:
    d = root / _DB_REL[0]
    d.mkdir(exist_ok=True)
    con = sqlite3.connect(str(root.joinpath(*_DB_REL)))
    con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute(
        "CREATE TABLE IF NOT EXISTS vectors ("
        " doc_id TEXT PRIMARY KEY,"
        " content_hash TEXT NOT NULL,"
        " type TEXT,"
        " title TEXT,"
        " path TEXT,"
        " norm REAL NOT NULL,"
        " vec BLOB NOT NULL)")
    return con


def _get_meta(con, key, default=None):
    row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def _set_meta(con, key, value):
    con.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


# --------------------------------------------------------------------------- #
# reindex — (re)build the vector store from the durable base.
# --------------------------------------------------------------------------- #
def _diff_index(docs, existing):
    """Deterministic index diff — **NO backend, NO embedding**. Given the current
    derived docs and the stored `{doc_id: content_hash}`, return
    `(to_embed, to_prune, fresh)`: `to_embed` = `[(doc, text, hash)]` for new/changed
    docs, `to_prune` = stored ids whose doc is gone, `fresh` = the up-to-date count.
    Detection is a faithful, model-free comparison; only *healing* (embedding
    `to_embed`) needs the accelerator — which is what lets a caller honestly report
    "N docs aren't searchable yet" even with the backend down."""
    present = {d.id for d in docs}
    to_prune = [did for did in existing if did not in present]
    to_embed, fresh = [], 0
    for d in docs:
        text = legible_text(d)
        h = _content_hash(text)
        if existing.get(d.id) == h:
            fresh += 1
        else:
            to_embed.append((d, text, h))
    return to_embed, to_prune, fresh


def reindex(root, *, model=DEFAULT_MODEL, url=DEFAULT_URL, embed=None):
    """(Re)embed the legible layer of every derived doc into the sidecar.

    Incremental: a doc whose legible content hash is unchanged is skipped (no
    re-embed). A doc that changed is re-embedded. A doc that no longer exists is
    pruned. If the embedding `model` differs from the one the store was built with,
    the whole store is rebuilt (vectors across models are not comparable) — this is
    the config-provenance rule of ADR-0027.

    `embed` is an injectable `fn(texts) -> [vectors]` (defaults to Ollama over HTTP)
    so tests run with no backend. Returns a summary dict.
    """
    root = Path(root)
    embed = embed or (lambda texts: ollama_embed(texts, model=model, url=url))
    con = _connect(root)
    try:
        stored_model = _get_meta(con, "model")
        rebuilt = False
        if stored_model is not None and stored_model != model:
            con.execute("DELETE FROM vectors")          # model changed → rebuild
            rebuilt = True

        existing = {r[0]: r[1] for r in
                    con.execute("SELECT doc_id, content_hash FROM vectors")}
        # Deterministic diff: what to (re)embed, what to prune, what's fresh.
        todo, pruned, skipped = _diff_index(_derived_docs(root), existing)
        for did in pruned:                      # prune needs no backend
            con.execute("DELETE FROM vectors WHERE doc_id=?", (did,))

        embedded = 0
        dim = int(_get_meta(con, "dim", 0) or 0)
        if todo:
            vectors = embed([t for (_, t, _) in todo])
            if len(vectors) != len(todo):
                raise RuntimeError("embedder returned the wrong number of vectors")
            for (d, _text, h), vec in zip(todo, vectors):
                norm = math.sqrt(sum(x * x for x in vec))
                con.execute(
                    "INSERT INTO vectors(doc_id,content_hash,type,title,path,norm,vec) "
                    "VALUES(?,?,?,?,?,?,?) "
                    "ON CONFLICT(doc_id) DO UPDATE SET "
                    "content_hash=excluded.content_hash, type=excluded.type, "
                    "title=excluded.title, path=excluded.path, norm=excluded.norm, "
                    "vec=excluded.vec",
                    (d.id, h, d.type, d.data.get("title", d.id),
                     str(d.path), norm, _vec_to_blob(vec)))
                embedded += 1
                dim = len(vec)

        _set_meta(con, "model", model)
        _set_meta(con, "dim", dim)
        con.commit()
        total = con.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]
        return {"model": model, "dim": dim, "embedded": embedded,
                "skipped": skipped, "pruned": len(pruned),
                "rebuilt": rebuilt, "total": total}
    finally:
        con.close()


# --------------------------------------------------------------------------- #
# search — embed the query, cosine top-k over the stored vectors.
# --------------------------------------------------------------------------- #
def search(root, query, *, k=10, model=None, url=DEFAULT_URL, embed=None):
    """Return the top-`k` derived docs by cosine similarity to `query`:
    [{id, score, type, title, path}], best first.

    The query is embedded with the SAME model the store was built with (recorded in
    the sidecar), because cross-model vectors are meaningless — if the caller passes
    a different `model`, the stored one still wins for the query so results stay
    coherent (rebuild the store to switch models). An empty store returns []. This
    only *proposes* candidates (ADR-0027 §2) — the caller reads the real docs.
    """
    root = Path(root)
    con = _connect(root)
    try:
        index_model = _get_meta(con, "model")
        rows = con.execute(
            "SELECT doc_id, type, title, path, norm, vec FROM vectors").fetchall()
        if not rows or index_model is None:
            return []
        use_model = index_model                     # query must match the index
        embed = embed or (lambda texts: ollama_embed(texts, model=use_model, url=url))
        qvec = embed([query])[0]
        # math.sumprod (3.12+) is a C-level dot product — ~10× on this hot loop,
        # zero deps (T-118d); the zip-sum fallback keeps the 3.9 floor working.
        sumprod = getattr(math, "sumprod",
                          lambda a, b: sum(x * y for x, y in zip(a, b)))
        qnorm = math.sqrt(sumprod(qvec, qvec))
        if qnorm == 0:
            return []
        scored = []
        for doc_id, dtype, title, path, norm, blob in rows:
            vec = _blob_to_vec(blob)
            if not norm:
                continue
            dot = sumprod(qvec, vec)
            scored.append({"id": doc_id, "score": dot / (qnorm * norm),
                           "type": dtype, "title": title, "path": path})
        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:k]
    finally:
        con.close()


def retrieve(root, query, *, k=10, model=None, url=DEFAULT_URL, embed=None):
    """Unified retrieval that ALWAYS answers and never crashes — the *mechanical*
    form of "prefer semantic search, fall back to `find`." The fallback can't be
    forgotten because it lives inside one call, not in an adapter's prose.

    It unions the two retrievers, which answer different questions (ADR-0014): the
    embedding tier proposes by **meaning**, deterministic `find` matches **literally**
    — so a semantic result never drops an exact-token hit, and a literal result never
    misses a synonym. Semantic candidates rank first (they carry a score), then any
    `find` hit not already present, deduped by id.

    **Self-healing (ADR-0027, refined 2026-07-09):** before ranking, `retrieve` runs a
    best-effort `refresh` so a doc ingested since the last embed is searchable *now* —
    no manual reindex, no adapter step to remember. The refresh is write-only and never
    raises; if the backend is down, any docs behind stay `find`-reachable and the result
    carries a `warning` saying so.

    Transparent about degradation (§I5): the result carries `via` (which retrievers
    ran), `backend` (`up` | `unavailable` | `no-index`), and `warning` (a staleness note
    or None). If the embedding backend is down or no index exists, `via` is `"find"` and
    the AI-free floor answers alone — same trustworthy result, just without the semantic
    lift. Still *proposes only* (ADR-0027 §2): every hit is a doc to read, never a citation.

    Returns {via, backend, warning, hits: [{id, type, title, path, source, score?}]}.
    """
    root = Path(root)
    find_hits = core.find(root, query)          # the floor — always available, no AI

    def _find_rows():
        return [{"id": h["id"], "type": h["type"],
                 "title": h.get("title", h["id"]), "path": h["path"],
                 "source": "find"} for h in find_hits]

    warn = refresh(root, model=model, url=url, embed=embed)["warning"]  # self-heal; never raises

    if index_info(root)["count"] == 0:          # still nothing embedded → floor only
        return {"via": "find", "backend": "no-index", "hits": _find_rows(), "warning": warn}
    try:
        sem_hits = search(root, query, k=k, model=model, url=url, embed=embed)
    except BackendUnavailable:                  # Ollama down → floor only, transparently
        return {"via": "find", "backend": "unavailable", "hits": _find_rows(), "warning": warn}

    seen, merged = set(), []
    for h in sem_hits:                          # meaning first (ranked)
        merged.append({"id": h["id"], "type": h["type"], "title": h["title"],
                       "path": h["path"], "source": "semantic", "score": h["score"]})
        seen.add(h["id"])
    for h in _find_rows():                       # then literal-only matches
        if h["id"] not in seen:
            merged.append(h)
            seen.add(h["id"])
    return {"via": "semantic+find", "backend": "up", "hits": merged, "warning": warn}


def index_info(root) -> dict:
    """Cheap, backend-free facts about the sidecar: {exists, count, model, dim}.
    Lets a caller tell "no semantic index yet" (→ reindex, or use find) apart from
    "search ran and found nothing" — both otherwise look like an empty result. No
    embedding backend is contacted."""
    p = Path(root).joinpath(*_DB_REL)
    if not p.exists():
        return {"exists": False, "count": 0, "model": None, "dim": 0}
    con = _connect(Path(root))
    try:
        return {"exists": True,
                "count": con.execute("SELECT COUNT(*) FROM vectors").fetchone()[0],
                "model": _get_meta(con, "model"),
                "dim": int(_get_meta(con, "dim", 0) or 0)}
    finally:
        con.close()


def index_staleness(root) -> dict:
    """How far the sidecar is behind the base — **deterministic, no backend**.
    `{stale, prune, fresh, indexed}`: `stale` = derived docs new/changed since their
    last embed, `prune` = stored vectors whose doc is gone, `fresh` = up-to-date,
    `indexed` = stored total. Detection needs no model (only healing does), so a
    caller can honestly say "N docs aren't searchable yet" even with Ollama down."""
    root = Path(root)
    docs = _derived_docs(root)
    if not index_info(root)["exists"]:
        return {"stale": len(docs), "prune": 0, "fresh": 0, "indexed": 0}
    con = _connect(root)
    try:
        existing = {r[0]: r[1] for r in
                    con.execute("SELECT doc_id, content_hash FROM vectors")}
    finally:
        con.close()
    to_embed, to_prune, fresh = _diff_index(docs, existing)
    return {"stale": len(to_embed), "prune": len(to_prune),
            "fresh": fresh, "indexed": len(existing)}


def refresh(root, *, model=None, url=DEFAULT_URL, embed=None):
    """Best-effort, **write-only, never-raising** bring-the-index-current — the
    Core-invokable refresh sanctioned by ADR-0027 (as refined 2026-07-09): the Core
    may *invoke* the accelerator and *store* its output in the disposable tier, but
    the durable base loses nothing if the backend is absent.

    Detection is deterministic (`index_staleness`); only healing calls the backend, so
    this returns a **structured status** instead of raising:
      - `clean`   — nothing behind (no backend contact).
      - `current` — embedded the stale docs / pruned the gone ones (backend up).
      - `stale`   — backend down and docs are behind; index left as-is and `warning`
                    set (search still ranks what's there; `find` covers the rest).
    """
    rmodel = index_info(root)["model"] or model or DEFAULT_MODEL
    st = index_staleness(root)
    if st["stale"] == 0 and st["prune"] == 0:
        return {"status": "clean", "embedded": 0, "pruned": 0, "stale": 0, "warning": None}
    try:
        rep = reindex(root, model=rmodel, url=url, embed=embed)
        return {"status": "current", "embedded": rep["embedded"],
                "pruned": rep["pruned"], "stale": 0, "warning": None}
    except BackendUnavailable as e:
        return {"status": "stale", "embedded": 0, "pruned": 0, "stale": st["stale"],
                "warning": (f"{st['stale']} doc(s) added/changed since the last embed "
                            f"aren't semantically searchable yet — `find` covers them; "
                            f"reindex when the backend is up ({e})")}


# --------------------------------------------------------------------------- #
# The semantic tier's op registry (T-113) — same declarative shape as
# muninn_core.OPS; odin_mcp unions the two into ONE MCP surface. Declared here
# (not in the Core registry) because this module imports muninn_core, and
# because the tier is inference, not Core (ADR-0027): the Core CLI stays
# inference-free by design — these four ops' CLI is *this* module's (below).
# --------------------------------------------------------------------------- #
_ROOT_P = {"type": "string", "description": "Path to the Muninn root directory.",
           "required": True, "cli": {"positional": True}}
_MODEL_P = {"type": "string",
            "description": "Override the query model; the index's own model still "
                           "wins for coherence."}
_URL_P = {"type": "string",
          "description": "Ollama base URL (default ODIN_OLLAMA_URL or "
                         "http://localhost:11434)."}

OPS = {
    "reindex": {
        "description": "(Re)build the DISPOSABLE semantic vector sidecar "
                       "(.odin/semantic.db) from the derived layer via a local "
                       "embedding model (T-087, ADR-0027). Inference, NOT a Core "
                       "transform — it only accelerates retrieval, never grounds "
                       "(ADR-0008 boundary). Incremental (re-embeds only changed "
                       "docs), prunes deleted docs, and rebuilds on a model "
                       "change. Run after ingest to keep `odin_search` fresh; "
                       "safe to delete the sidecar anytime — this rebuilds it. "
                       "Needs a reachable Ollama (ODIN_OLLAMA_URL); returns "
                       "counts, never touches the base.",
        "params": {
            "root": _ROOT_P,
            "model": {"type": "string",
                      "description": "Embedding model (default nomic-embed-text / "
                                     "ODIN_EMBED_MODEL)."},
            "url": _URL_P,
        },
        "handler": lambda root, p: reindex(
            root, model=p.get("model") or DEFAULT_MODEL,
            url=p.get("url") or DEFAULT_URL),
    },
    "search": {
        "description": "Semantic retrieval: top-k derived docs by cosine "
                       "similarity to the query, over the disposable embedding "
                       "sidecar (T-087). The AI-facing companion to the AI-free "
                       "`odin_find` floor — it crosses the reader-vocabulary gap "
                       "find cannot (e.g. 'illness'->the vet exam; ADR-0014, "
                       "T-044). It only PROPOSES candidates (ADR-0027 §2): each "
                       "hit is a doc to READ, never a citation, never provenance "
                       "— ground answers in the actual sources. Empty until "
                       "`odin_reindex` has run. Prefer `odin_find` when the query "
                       "is a literal token; reach here for meaning/synonyms.",
        "params": {
            "root": _ROOT_P,
            "query": {"type": "string", "required": True,
                      "description": "A natural-language / concept query (meaning, "
                                     "not just tokens)."},
            "k": {"type": "integer",
                  "description": "How many candidates to propose (default 10)."},
            "model": _MODEL_P,
            "url": _URL_P,
        },
        "handler": lambda root, p: search(
            root, p["query"], k=p.get("k", 10), model=p.get("model"),
            url=p.get("url") or DEFAULT_URL),
    },
    "retrieve": {
        "description": "Unified retrieval — the DEFAULT way to find things: "
                       "unions semantic candidates (meaning) with `find` hits "
                       "(literal), deduped, so you never miss a synonym OR an "
                       "exact token. It ALWAYS answers and never errors on a down "
                       "backend: the fallback to the AI-free `find` floor is "
                       "MECHANICAL (inside the call), so it can't be forgotten. "
                       "Transparent about it — the result's `via`/`backend` say "
                       "whether semantics ran or it degraded to find (Ollama down "
                       "/ no index). Still proposes only (ADR-0027 §2); read the "
                       "sources to ground. Prefer this over "
                       "`odin_search`/`odin_find` unless you specifically want "
                       "just one.",
        "params": {
            "root": _ROOT_P,
            "query": {"type": "string", "required": True,
                      "description": "A natural-language or literal query — both "
                                     "retrievers run."},
            "k": {"type": "integer",
                  "description": "Semantic candidates to union in (default 10); "
                                 "find hits are added whole."},
            "model": _MODEL_P,
            "url": _URL_P,
        },
        "handler": lambda root, p: retrieve(
            root, p["query"], k=p.get("k", 10), model=p.get("model"),
            url=p.get("url") or DEFAULT_URL),
    },
    "refresh": {
        "description": "Best-effort **warm** of the disposable semantic index "
                       "(T-091): embed any doc changed since the last embed, "
                       "prune the gone ones. Call it at the END of an `ingest` so "
                       "what you just added is searchable *now* — the next "
                       "`odin_retrieve` is instant instead of paying a cold-load. "
                       "WRITE-ONLY and NEVER errors: no backend → a clean no-op "
                       "with a status, so no try/except needed (unlike "
                       "`odin_reindex`, which raises). It is a pure optimization "
                       "— safe to skip, because `odin_retrieve` self-heals "
                       "(T-090); this only moves the embed cost off the first "
                       "query. Returns {status: clean|current|stale, embedded, "
                       "pruned, warning}. Relay `warning` if present.",
        "params": {
            "root": _ROOT_P,
            "model": {"type": "string",
                      "description": "Embedding model (default nomic-embed-text / "
                                     "the index's own)."},
            "url": _URL_P,
        },
        "handler": lambda root, p: refresh(
            root, model=p.get("model"), url=p.get("url") or DEFAULT_URL),
    },
}


# --------------------------------------------------------------------------- #
# CLI — its own front door; the Core CLI stays inference-free by design.
# --------------------------------------------------------------------------- #
def main(argv=None):
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    p = argparse.ArgumentParser(
        prog="muninn_semantic",
        description="Semantic retrieval tier (T-087, ADR-0027) — embeds the legible "
                    "layer; the disposable, AI-facing companion to deterministic find.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("reindex", help="(re)build the disposable vector sidecar from the base")
    pr.add_argument("root")
    pr.add_argument("--model", default=DEFAULT_MODEL, help=f"embedding model (default {DEFAULT_MODEL})")
    pr.add_argument("--url", default=DEFAULT_URL, help=f"Ollama base URL (default {DEFAULT_URL})")

    ps = sub.add_parser("search", help="semantic top-k over the sidecar (proposes candidates only)")
    ps.add_argument("root")
    ps.add_argument("query", nargs="+", help="the query")
    ps.add_argument("-k", type=int, default=10, help="how many candidates (default 10)")
    ps.add_argument("--model", default=DEFAULT_MODEL)
    ps.add_argument("--url", default=DEFAULT_URL)

    pt = sub.add_parser("retrieve", help="unified retrieval: semantic + find, always "
                                         "answers, self-heals, degrades to find with no backend")
    pt.add_argument("root")
    pt.add_argument("query", nargs="+", help="the query")
    pt.add_argument("-k", type=int, default=10, help="semantic candidates to union (default 10)")
    pt.add_argument("--model", default=DEFAULT_MODEL)
    pt.add_argument("--url", default=DEFAULT_URL)

    pf = sub.add_parser("refresh", help="best-effort bring-the-index-current (write-only, "
                                        "never errors; warns if the backend is down)")
    pf.add_argument("root")
    pf.add_argument("--model", default=DEFAULT_MODEL)
    pf.add_argument("--url", default=DEFAULT_URL)

    args = p.parse_args(argv)
    # Exit 3 == "backend unavailable" — a distinct, scriptable code so a caller (or a
    # human) knows the tier degraded, not that the base is broken. `find` still works.
    if args.cmd == "reindex":
        try:
            rep = reindex(args.root, model=args.model, url=args.url)
        except BackendUnavailable as e:
            print(f"reindex skipped — {e}", file=sys.stderr)
            return 3
        print(f"reindexed {args.root}: {rep['total']} vector(s) "
              f"(embedded {rep['embedded']}, skipped {rep['skipped']}, "
              f"pruned {rep['pruned']}{', REBUILT' if rep['rebuilt'] else ''}) "
              f"model={rep['model']} dim={rep['dim']}")
    elif args.cmd == "search":
        try:
            hits = search(args.root, " ".join(args.query), k=args.k,
                          model=args.model, url=args.url)
        except BackendUnavailable as e:
            print(f"semantic search unavailable — {e}", file=sys.stderr)
            print(f"fall back to the AI-free floor:  {Path(__file__).with_name('muninn_core.py')} "
                  f"find {args.root} {' '.join(args.query)}", file=sys.stderr)
            return 3
        for r in hits:
            print(f"{r['score']:.3f}  {r['type']:9} {r['id']}  —  {r['title']}")
        if not hits:
            info = index_info(args.root)
            if info["count"] == 0:                      # transparent: not "no match"
                print("(no semantic index yet — run `reindex`/`refresh`, or use `find`)")
            else:
                print("(0 candidates — nothing scored; try `find` for a literal match)")
        else:
            print(f"({len(hits)} candidate(s) — propose only; read the sources to ground)")
        # `search` ranks the index as-is; surface if it's behind (deterministic, no backend).
        st = index_staleness(args.root)
        if st["stale"] or st["prune"]:
            print(f"(note: index is behind — {st['stale']} doc(s) unindexed, "
                  f"{st['prune']} to prune; `refresh`/`reindex`, or use `retrieve` which self-heals)")
    elif args.cmd == "retrieve":
        # retrieve never raises for a down backend — it self-heals + degrades to find.
        res = retrieve(args.root, " ".join(args.query), k=args.k,
                       model=args.model, url=args.url)
        for h in res["hits"]:
            tag = h["source"][0].upper()                # S(emantic) / F(ind)
            score = f"{h['score']:.3f}" if "score" in h else "  ·  "
            print(f"[{tag}] {score}  {h['type']:9} {h['id']}  —  {h['title']}")
        print(f"({len(res['hits'])} result(s) via {res['via']}; backend {res['backend']} "
              f"— propose only; read the sources to ground)")
        if res.get("warning"):
            print(f"(note: {res['warning']})")
    elif args.cmd == "refresh":
        rep = refresh(args.root, model=args.model, url=args.url)
        if rep["status"] == "current":
            print(f"refreshed {args.root}: embedded {rep['embedded']}, pruned {rep['pruned']}")
        elif rep["status"] == "clean":
            print(f"refreshed {args.root}: already current")
        else:                                           # stale — backend down
            print(f"refresh incomplete — {rep['warning']}", file=sys.stderr)
            return 3


if __name__ == "__main__":
    sys.exit(main())
