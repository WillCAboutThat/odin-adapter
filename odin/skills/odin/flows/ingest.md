## Ingest (the flagship): remember a document

1. **Acquire** the source. **Have the original file? Hand the Core the file
   itself** — do *not* pre-extract text. The Core stores the original bytes as the
   canonical record and extracts a text aid via its own extractor registry
   (ADR-0010). Only paste/chat text (no file behind it) goes in as text.
2. **Capture** via the Core — pick a stable slug id (`src-…`):
   - **A file (PDF, image, .docx, .txt, …):** capture the original bytes —
     `… capture <root> src-<slug> --source-file <path> --origin-system file --origin-ref <name>`
     The Core writes `source.<ext>` + (when it can) a `source-text.md` aid; a
     format with no extractor is captured bytes-only (still valid). To add a
     format, register an extractor in `tools/extractors/` — you don't touch capture.
   - **Pasted/chat text (no original file):** `… capture <root> src-<slug> --file <bodyfile>
     --origin-system chat --origin-ref <where>` (canonical `source.md`).
   *(MCP transport - the norm for plugin installs: a `--file`/stdin body becomes the **`body` param carrying the literal text, never a file path**; `--source-file` becomes the **`source_file`** path param. Same op, same other args - the kernel's Setup section has the full mapping.)*
   - **A URL / connector source** (e.g. an `explore` finding, a live web page):
     always add `--origin-system url --origin-ref <URL>` + **`--recoverable`** so
     `regenerate` can re-`fetch` it later (T-066 self-heal). **The tier describes
     what the base HOLDS (ADR-0003), never who owns the truth (T-134):** complete
     artifact bytes held verbatim (a file, a raw payload, a full export) =
     **`full`**, even when the upstream record is live and evolving; liveness is
     already carried by `origin.ref` + `--recoverable`, and upstream change makes
     a new *version*, never a tier downgrade (the README's updated-lease case).
     **`--tier reference` (+ `--reason`)** only when the bytes are NOT held or the
     held text is a lossy stand-in: the model-rendering fallback below, an
     excerpt, a licensed/too-large/private artifact. (The gloss *"reference is
     about authority, not storage"* is scoped to **stand-ins**: a rendering whose
     authoritative copy is the live URL. It is never a reason to mark a held raw
     payload `reference`; under that reading every connector source would be
     reference and the L10 assurance signal would drown.) A misjudged tier is
     corrected with the deliberate **`retier`** op, never a hand-edit of
     `meta.yml`. **Large binaries (T-233):** a full-tier capture of ≥25 MB is
     refused unless you pass `--allow-large` — sources are immutable, so held
     bytes live in the base's git history forever, and hosts refuse pushes
     near 100 MB. The posture is plain git, no LFS (an LFS-backed base isn't
     readable with bare git — the no-vendor durability rule, ADR-0008):
     small originals ride full-tier as ever; the genuinely big get
     `--tier reference --reason <why>`, and holding big bytes anyway is a
     deliberate, flagged act, voiced to the user before you pass the flag. **For an HTML page, prefer the raw bytes:**
     fetch the page **decompressed** (e.g. `curl -L --compressed`, or your fetch tool's
     raw-HTML mode — a gzip'd body decoded as text is garbage) and capture it with
     **`--source-file page.html`**, so the Core's html extractor writes a faithful
     **`extracted`** `source-text.md`. This grounds the summary in the *full* page text
     (typically many times richer than a model rendering) — an **ordinary summary, no
     `model-read` stamp**; nav/footer chrome in the extract is fine, you ignore it when
     you read. **Fall back to the model-driven fetch rendering** — store *that* text as
     the source body and stamp its summary **`--derivation model-read`** — only when raw
     HTML is unusable: a bot-blocked page, a JS-rendered SPA whose static HTML is mostly
     chrome, or a non-HTML endpoint. The rendering is a re-fetchable snapshot, never the
     durable original; `model-read` is its honest assurance (mirrors the opaque-source
     rule under Derive). **The same raw-first rule holds for ANY connector item**
     (a work item, a ticket, a thread, a cloud doc): the **raw tool response is the
     capturable artifact**; persist it verbatim (`--source-file item.json`, or the
     body as the unmodified payload text), never your own prose retelling of it.
     **Never truncate, abbreviate, or placeholder a field value** — a `[…]`, a
     "see original", or a half-copied long field is a *silent lossy capture* the
     linter cannot see (a truncated body hashes and lints as cleanly as the full
     one). The mechanical guard is the raw-first rule itself: **hand the Core the
     payload file and `--source-file` it — do not retype field values into the
     body by hand.** You cannot truncate what you do not retype; truncation creeps
     in only on the hand-authored path, under context pressure, on the longest
     fields (observed three times on real ADR work items — T-192). If the full
     bytes genuinely cannot be held, that is the voiced **reference**-tier fallback
     below — never a quiet truncation dressed as `capture: full`.
     A rendering may stand in as the source body **only when no raw representation
     is available**, and then it is **voiced and carries all four honesty stamps,
     never silent**: say in chat that a rendering (not the source data) is being
     captured, then stamp (1) `--tier reference --reason <why>` (the live item stays
     authoritative; a rendering is never `capture: full`), (2) `--recoverable` with
     the real locator, (3) `--captured-by huginn/<model>@<version>` (ADR-0001:
     disclose the producer of the bytes), and (4) `--derivation model-read` on every
     doc derived from it. Artifacts the item links (an attachment, a supporting
     document) are **their own capture candidates: surface them, never silently
     drop them** (T-131). **Capturing an EXCERPT of a larger whole (ADR-0039):**
     when the evidence is a targeted region — one clause of a contract, a section
     of a wiki page, the relevant method of a repo file — a partial capture is
     the right middle path (evidence held, no bloat), and it must be **anchored**:
     (1) put the verbatim excerpted content in **fenced blocks**, disclosure
     prose outside them (fences are what the containment check verifies — prose
     inside upstream text is not); (2) give the excerpt a **distinct, qualified
     `--origin-ref`** (`<whole's locator>#<excerpt-slug>` — two excerpts of one
     file must never share a ref, T-045); (3) pass **`--upstream-ref <whole's
     clean locator>`** and, when you can identify the whole as of this read,
     **`--upstream-identity git-blob:<sha1>`** (git-backed: `git rev-parse
     HEAD:<path>` or the API's blob sha, free) **or `sha256:<hex>`** of the
     fetched whole. An anchored excerpt drift-checks *exactly*; an unanchored
     one is honestly hedged forever. Pre-existing excerpts are anchored later
     with the consented **`anchor`** op (below), never a hand-edit.
   - **A capture sourced from a REPO carries the repo pointer (T-196).** When the
     file (or the excerpt's whole) is a repo file, stamp **`--origin-system repo`**
     and make the locator **repo-scoped**: `<repo-locator>#<path-in-repo>` for a
     whole file, `<repo-locator>#<path>#<excerpt-slug>` for an excerpt (with
     `--upstream-ref <repo-locator>#<path>`). This is the **same `origin.system:
     repo`** a `capture-repo` constitution uses, so every code file or excerpt you
     keep while answering a question is *groupable back to its repo* — the durable
     pointer to the system of record, and what makes Odin's demand-driven evidence
     map a coherent, projectable footprint (the `repo-coverage` read). The
     constitution's own capture keeps the **bare** `<repo-locator>` as its ref;
     evidence captures qualify it with `#<path>`, so the two never collide.
   - **The inbox (batch mode):** the user drops files into the Muninn's `inbox/`
     (or you parked explore findings there on their opt-in) and says "ingest the
     inbox." Process **each pending file through this same pipeline** (capture →
     derive → index), `--origin-system inbox` (a parked preview note keeps the
     origin it carries), and report a **digest** rather than gating per item —
     bulk is the lower-supervision path, and capture is never gated (ADR-0007).
     **Then clear each processed file (ADR-0006 / T-135):** once its source is
     durably written — a dedup hit counts, the content is already held — remove
     the pending file from `inbox/` and say so in the digest; its immutable copy now lives in `sources/`,
     so nothing is lost and a re-dropped file is recognized, not duplicated. A
     file that **fails** to process stays in the inbox and is named in the
     digest — the inbox's meaning is exactly "still pending." A parked explore
     finding the user **declines** is removed too (declined findings leave no trace).
   Report the dedup/version outcome the Core returns. If capture is **refused**
   because the `origin.ref` already belongs to another source (changed content at
   a known locator under a new id — a lineage split), re-capture under the id the
   error names so the source **versions**; pass `force_new` only when the user
   confirms it is genuinely a different source sharing the locator. Capture needs
   no approval — the user asked you to remember it (ADR-0007) — but confirm before
   storing anything that looks like secrets or personal data.
3. **Derive** (your judgment). Read the source and write its grounded summary.
   Every source gets one; the rules for writing it are below. That one summary
   per source is ingest's whole derive scope. The enrichment layer of entities,
   concepts, and open questions is authored by the deliberate `map` verb, whose
   section sits beside *Synthesize*. Insights are authored by `synthesize`.
   Neither is ever a per-source side judgment here. ADR-0043 made this
   unconditional because the old optional "where warranted" gate systematically
   under-fired. Batch ingest is predictable now: one summary each, nothing to
   weigh.

   For each doc you derive, write a short `title`, a one-line `abstract`, and a
   body that cites the source inline as a linked citation (ADR-0038). The id is
   the label and the source's readable file is the target:
   `… [src-<slug>](../sources/src-<slug>/source-text.md)`. For a text-native
   capture, target the canonical `source.md` instead.

   **Author in the plain register.** The shared rules under *Plain-English
   authoring rules* (T-221) govern every word you write into the base and every
   word you say about it. Rules 1, 4, and 6 bite hardest in a summary: give a
   fact carried in an aside its own sentence, put each citation at the end of
   the sentence it supports, and take the longer plain sentence over the
   compressed one. The `abstract` earns the register before anything else does,
   because it is the most-skimmed span in the base.

   **Two mechanical style rules ride alongside**, binding everything written
   into the base — titles, abstracts, and bodies, from every verb and not only
   ingest. Write plain portable Markdown. Use no em-dashes; commas, colons, or
   parentheses instead. The base is read in ordinary editors such as VS Code and
   Obsidian, whose Markdown views render em-dashes poorly, and it must read
   cleanly everywhere.

   **Quoted spans use logical quotation** (T-153). End the span at a word and
   keep your own sentence punctuation outside the closing quote. The quote marks
   delimit the exact verbatim source substring. A period or comma pulled inside
   to smooth your sentence is the commonest way a span silently stops matching
   its source. Ending at a word costs you at worst a slightly tighter span than
   you could have taken, and it never fails the gate.

   How you *read* the source, and how you stamp the summary's `derivation`,
   depends on what the Core could extract (ADR-0011):
   - **Text-native or extractable.** This covers `.md`, `.txt`, and any PDF or
     .docx the extractor registry read. Read the `source-text.md` aid. The bytes
     stay authoritative. The summary's derivation is `extracted`, which is the
     default, so you needn't pass the flag.
   - **Opaque.** This covers an image, a scan, or any format captured bytes-only,
     with no `source-text.md`. There is no deterministic text, so model-read the
     bytes yourself: open the source, describe what it actually shows, and author
     the summary from that. Stamp it `--derivation model-read`. **Opaque means
     no extractor exists — not that one wasn't installed (T-234).** A format the
     registry covers (.pdf, .docx, .xlsx) that captured bytes-only means the
     optional dependency was missing at capture time; the honest move is to
     install it and let capture aid the source deterministically, never to
     model-read data a parser can read exactly. Genuine model-read is
     understanding, not OCR. Capture stays deterministic and AI-free, the reading
     is a *derive*-step act, and the model-read summary is now the only way that
     source is findable at all.
     - **Quarantine origin-carried attribution (T-178).** In the doc itself,
       separate what the reading grounds from what rides on origin metadata. What
       the reading grounds is what the bytes or pixels actually show. What rides
       on the metadata is a filename's author or date, and the ref. Name the
       latter as origin-carried, in the form *"attribution carried by the file's
       origin, not read from the image content: …"*. Never state it as something
       the reading found. The reading warrants the content; only the origin
       warrants the label. A mislabeled file is exactly where the difference
       bites.
   - **Prefer the deterministic text layer, and obtain it when obtainable
     (T-180).** Model-read is for the *genuinely* opaque, meaning images and
     scans. Sometimes a format the extractor registry supports arrives bytes-only
     merely because a dependency was missing. Then obtaining the dependency beats
     model-reading a document that was one install away from faithful, because
     `extracted` outranks `model-read` on the assurance ladder. Say so in the
     digest, disclosing that you changed the environment. If the attempt breaks
     something, restore the working state and say that too. Never leave the
     environment silently altered. **For sources already captured bytes-only
     before the extractor existed, the repair is `reextract` (T-226)** — it
     backfills the aid from held bytes, no new version, no re-capture (which
     would only dedup). It never re-stamps a doc's derivation; if a summary was
     model-read for want of an aid, `regenerate` is the consented path to
     re-derive it from the now-present text.
   - **Scale by delegation, but never delegate grounding (T-179).** In a bulk
     ingest you may fan authoring out to subagents. Grounding is per-doc and
     non-delegable: whatever context authors a summary must itself read that
     source's actual bytes or text aid. Orchestrator-side checks are validation,
     and they are voiced as validation, because "validated" is not "re-read
     against the source." The digest discloses that authoring was delegated.
   - **Every source gets a summary (L15, an error).** A captured source with no
     summary is an unfindable gap, and the linter flags it. Never leave one
     un-summarised. If you meet an old one, heal it per *Regenerate*.
   - **Ground only in sources**, never in other derived docs. The Core rejects
     chaining, so don't try it.
   - **Never fabricate.** If a fact isn't in the source, don't state it. A
     missing defining input is a question to the user, not a guess.
   - **Intent stays out of the abstract (T-181).** What a document *is* may be
     stated when the bytes ground it, as in *"contains no mention of X"* or
     *"actually Pinchot's text under a Muir header"*. *Why* it exists in the
     collection is a different thing: calling it a "distractor", a plant, or a
     test is your inference about someone's intent. Voice that inference to the
     user in the digest, or label it in the body as your own observation. Never
     state it as fact in the abstract, which is the most-skimmed span. This is
     the ADR-0015 abstract rule, applied to summaries.
   - **Author for findability (ADR-0012).** `find` is literal substring, so write
     the summary in the reader's vocabulary and not only the source's. Add
     `Covers` and `Answers` facets that phrase the questions someone would
     actually ask, in their words. A "from the shelter" record should also say
     adopted. A "Birthday" should also answer age. Carry the inflected form the
     reader types, too: `find` is literal substring and not stemmed, so "rescue"
     will not match a `find("rescued")`, and you author rescued alongside the
     stem. Use only words grounded in *this* source, because the no-fabrication
     rule still binds and an image-only fact stays out. Sanity-check by running
     `find` on a few likely queries. Nothing back means an under-worded digest,
     not broken retrieval.
     - A facet is a keyword run, not prose, and the plain-register rules (T-221)
       do not govern it. Commas are the whole point there.
   - **A structured source's summary states the schema reading and coverage
     (T-048).** For a spreadsheet, a large CSV, an export - any source whose
     meaning lives in structure - the summary is where the schema is READ:
     say what the thing tracks, at what grain, over what span, and where
     ("weekly MAU and churn, one row per week, header on row 3 of sheet
     Metrics, covering January through December 2026"). Deciding which row is
     the header and which columns matter is *judgment*, so it belongs here
     and never in the deterministic text aid - the aid's mechanical facts
     line (sheet names, dimensions, typed date/numeric ranges) is the
     evidence you read to write it. This is the model-read pattern applied to
     structure: where the deterministic layer cannot reach the meaning, the
     summary carries the findable reading, in the reader's vocabulary - a
     locator question like "which doc talks about MAU in July 2026?" is
     answered by a summary written to be found by exactly those words.
   - **Compress; a summary is shorter than its source (L18).** A summary must not
     run longer than its source. Enrich for findability rather than restating the
     content at length. A source that is already terse, such as a small table or
     a short note, is basically a summary already: give it a tight abstract plus
     a reader-vocabulary facet and stop, rather than stretching it. The linter
     warns via L18 on a bloated summary. A `model-read` of a textless image is
     exempt, having no source text to be shorter than.
4. **Write** each derived doc via the Core (it copies the current source hash and
   refuses chaining):
   `… derive <root> <id> --type summary --title "<t>" --abstract "<a>" --source src-<slug> [--derivation model-read] --file <bodyfile>`
   *(MCP: `body` takes the summary's literal text itself - passing a
   scratchpad file PATH as `body` stores the path string as the whole body,
   the L24 path-as-body class. Write the prose, not the pointer.)*
   Pass `--derivation model-read` for a summary you authored by reading an opaque
   source's bytes (step 3); omit it for extracted text (defaults to `extracted`).
5. **Place:** `… index <root>` (regenerates the catalog projection). **Only if the
   user named a project** ("…for the Q3 project"), also add the source *and* its
   summary to that view:
   `… project <root> prj-<slug> --title "<Project name>" --member src-<slug> --member sum-<slug>`
   The Core unions members (re-running is safe) and edits only the *view*, never
   the source (membership lives on the page, ADR-0002). **Un-grouping is the same
   op:** `--remove-member <id>` takes a doc out of the view (T-148) — a link
   change only, the doc stays findable; **never hand-edit a members list**, and
   removal is the user's curation call exactly like adding. **Never invent a
   project the user didn't ask for** — grouping is the user's curation, not yours;
   with no project named, just index. Cross-cutting *standing* context (an org
   constraint, a business model, a personal commitment) goes in the seeded
   `global` hub (`… project <root> global --member …`), which every scope already
   unions in (ADR-0018) — and **only** standing context: the membership test is
   "should this be in scope for *every* question?"; when unsure, default to a
   project view, not global.
6. **Verify:** `… lint <root>` — it **must** report 0 errors. If not, fix and
   re-lint. "The Muninn lints clean" is the definition of done **for an ingest**. A
   common finding is **L15** (a source with no summary) — heal it per **Regenerate**,
   don't ship past it.
   - **Scoped write onto an already-dirty base is different.** When you `derive` /
     `regenerate` / `fold` **one** doc into a base that already carried *unrelated*
     lint errors, you are done when **your own** output lints clean; **surface** the
     pre-existing errors for the user's consented healing — do **not** silently fix
     them (that is unconsented repair — *surface, never silently repair*, §I5). Fix
     what your write caused; flag the rest.
7. **Warm the semantic index (optional, best-effort — T-091).** After a clean lint,
   fire `odin_refresh` (or `muninn_semantic.py refresh <root>`) so the docs you just
   added are embedded **now** — while the user is already here — and the next
   `retrieve`/`search` is instant instead of paying a cold model-load. It is
   **write-only and never blocks**: no backend → a clean no-op. You may **skip it**
   entirely — `retrieve` self-heals (T-090), so this only *moves* the embed cost off
   the first query; it never affects correctness. Say nothing about it unless it
   returns a `warning` worth relaying.
8. **Report** plainly. Say what you captured, giving its id and where it lives.
   Say what you derived. Then say anything notable, such as a dedup hit, a new
   version, or staleness you surfaced. The digest is spoken prose, so the plain
   register (T-221) governs it: rules 2, 3, and 5 are the ones a digest breaks
   most often, so write arrows as words, expand each term the first time it
   appears, and bold at most one thing per section.

