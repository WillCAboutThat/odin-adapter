## Search (semantic retrieval — proposes candidates, never grounds)

`search` is the **AI-facing companion** to the `find` floor (ADR-0014, T-087): it
ranks derived docs by **meaning**, so a reader's word crosses to the author's — e.g.
`search <root> "illness"` surfaces the vet-exam summary that never says "illness",
where `find` returns nothing. Prefer `odin_search` (MCP) or
`python <ODIN>/tools/muninn_semantic.py search <root> "<query>"`; it returns scored
candidates, best first.

Two rules that keep it honest — it lives in the **disposable-index tier** (ADR-0027):

- **It only *proposes*.** A hit is a doc to **read**, never a citation and never
  provenance. Always ground the actual answer in the source bytes (see `ask`) — the
  embedding index can rank a doc near a query it doesn't truly support. `find` stays
  the AI-free floor; `search` never replaces it.
- **Reach for it by task.** A literal token or id → `find`. Meaning, a synonym, "the
  thing about…" → `search`. Use both and merge; they answer different questions.

**Freshness is automatic — `retrieve` self-heals.** The vector store is a git-ignored,
rebuildable `.odin/semantic.db` sidecar — **not** knowledge, safe to delete. You do
**not** need to reindex after an `ingest`: `retrieve` runs a best-effort `refresh`
before ranking, so a doc ingested since the last embed is searchable on the very next
retrieve (ADR-0027, refined — the read path may invoke the accelerator write-only). It
re-embeds only what changed, needs a reachable backend (local Ollama via
`ODIN_OLLAMA_URL`; see `docs/odin/ollama-setup.md`), and if the backend is down it
**doesn't block** — the docs behind stay `find`-reachable and `retrieve`'s result
carries a `warning` you should relay ("N docs added since the last embed aren't
semantically searchable yet"). `reindex`/`refresh` remain as an **optional proactive
warm** (e.g. right after a big ingest); bare `search` ranks the index as-is and prints
a note if it's behind — prefer `retrieve` when you want current results.

**Degrade gracefully AND transparently when Ollama is off/unreachable.** The tier is
optional; the base loses nothing without it. But *don't hide the degradation* (§I5):

- **Backend down/unreachable** → `search`/`odin_search` returns a clear error
  (`BackendUnavailable`, naming Ollama and the fallback), **not** a silent empty that
  looks like "no matches." When you see it, **say so in one line** ("semantic search
  is unavailable — Ollama isn't reachable; using `find` instead") and **run `find`**.
  Never surface the raw error and never block. Same for `reindex`: report it couldn't
  build and carry on — `find` still works.
- **No index built yet** (nothing `reindex`ed) → a plain empty result. Offer to
  `reindex` (if a backend is around) or just use `find`.
- **Backend up, genuinely nothing similar** → a real empty result; treat it as "no
  semantic match," and a literal `find` may still hit.

