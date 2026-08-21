## Find (the AI-free floor)

Run `python <ODIN>/tools/muninn_core.py find <root> <query terms>`. It returns
matching docs, **sources first**, then derived. Present them with links — no
synthesis, no reasoning layer between the user and the record. It matches a doc's
id, title, abstract, tags, and body text — and, for sources, the **origin
locator** (`origin.ref` / `origin.upstream_ref`, T-141), so *"what did we capture
from `<filename/URL>`?"* hits on the locator alone.

**A miss is not absence (T-142).** Zero hits means *these literal terms don't
appear* — never "the base doesn't have it." Before reporting anything as not
present:

1. **Degrade the query:** strip extensions, split path/word separators
   (`ARCHITECTURE.md` → `architecture`), drop the rarest term; retry.
2. **Prefer `retrieve`** for the question itself when the semantic tier is
   present (synonyms reach what literal terms miss).
3. **Skim `index.md`** — every doc is listed there with its title. An existence
   question ("did we ingest X?") is answered by the index, never by one grep.
4. **Voice the miss honestly:** *"no literal match for '<query>' — I also checked
   the index"* — then offer `explore` if the base genuinely lacks it. Never
   invent a result; never report a literal miss as "not in the base."

`find` is deterministic substring — *grep that knows the doc structure*. It is the
**AI-free floor** (ADR-0014): the guarantee the base is retrievable with no AI and
no vendor, forever — **not** how *you* should search. When **you** reason over the
base, read the index + summaries, then the sources (see `ask`); `find` is a cheap
pre-filter for that, and the way a human or a later tool gets in with no model at
all. Its quality rides on summaries authored in the reader's vocabulary (Ingest
step 3, ADR-0012) — improve the **summary**, never this matcher.

