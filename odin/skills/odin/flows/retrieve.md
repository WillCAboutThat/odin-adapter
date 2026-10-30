## Retrieve (the default — semantic ∪ find, with a mechanical fallback)

**Prefer `retrieve` / `odin_retrieve` as your default retrieval move**; reach for bare
`find` or `search` only when you specifically want just one. It unions the two —
semantic candidates (meaning) **and** `find` hits (literal), deduped and each tagged
with its `source` — so you never miss a synonym *or* an exact token in one call.
**This is the general rule for *routing* too** — locate where an answer lives (over the
resource landscape or anywhere) with `retrieve`, not bare `find`. `find` is substring-only
and brittle (a query's words must appear literally; it false-positives on stray tokens);
`retrieve` adds the semantic hit and still degrades to `find` for free, so it's the safe
default everywhere.

**Availability — retrieve/search need the semantic tier; the bare CLI is `find`-only.**
`retrieve`/`search` live in the **semantic tier**: the MCP tools `odin_retrieve` /
`odin_search` (a plugin install ships them), or `muninn_semantic.py`. The **bare Core
CLI** (`muninn_core.py`) exposes **only `find`** — the AI-free floor (ADR-0014). So
"prefer `retrieve`" holds **when the semantic tier is present** (the MCP path, the norm);
driving the raw CLI **without** MCP, `find` *is* your retrieval, and the degrade-to-find
is by hand, not by the op. Don't reach for a `retrieve`/`search` CLI subcommand — there
isn't one.

**Availability is observed, never assumed (T-198).** The paragraph above says which
transports carry the semantic tier - it is not a license to tell the user the tier is
absent. Before saying so, look: are the `odin_search`/`odin_retrieve` tools bound in
this session? Is `muninn_semantic.py` on the checkout you're driving? If you haven't
looked, don't characterize the user's environment (a probe run once asserted "semantic
search isn't available on this transport" while the tier sat installed and the backend
up). A degraded result already discloses itself via `via`/`backend` - make the call and
let it speak.

Its value over "call `search`, and if it errors call `find`" is that the fallback is
**mechanical, not yours to remember**: `retrieve` never raises on a down backend and
never returns a misleading empty — it degrades to `find` *inside the call*. It stays
transparent: the result's **`via`** (`semantic+find` | `find`) and **`backend`**
(`up` | `unavailable` | `no-index`) tell you whether semantics ran. When `via` is
`find`, say so briefly ("semantic search is off — used `find`") and present the hits;
they're the same trustworthy floor, just without the semantic lift. Still *proposes
only* (ADR-0027 §2) — read the sources to ground.

