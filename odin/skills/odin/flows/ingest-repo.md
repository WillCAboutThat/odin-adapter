## Ingest a repository (its *mental model*, not its files)

To remember a **codebase**, capture its **constitution** and author a **mental model** —
what the repo is *for*, its role in the system, its major boundaries, its public contract,
and ownership. **Never a file-by-file census** (ADR-0028): you capture a repo's *identity*,
not its implementation.

1. **Capture the constitution.**
   `… capture-repo <root> src-<slug> <repo-path> [--origin-ref <remote-url>] [--head <commit>]`.
   The Core builds a deterministic **constitution manifest** from the repo's intent-bearing
   surfaces — README, agent contract (`CLAUDE.md`/`AGENTS.md`), ARCHITECTURE / in-repo ADRs,
   public contract, identity manifests, orchestration (`docker-compose`), and the top-level
   **shape** — captured **reference-tier** (`origin.system: repo`; the live repo is the
   authoritative copy).
   - **Augment the floor when this repo's identity lives elsewhere.** The default surfaces
     are the AI-free floor; **you judge what matters *here*** and add it with
     `--surface LABEL=glob[,glob…]` (repeatable) — e.g. a deploy descriptor
     (`--surface deploy=Dockerfile,netlify.toml,fly.toml`), IaC
     (`--surface iac=*.tf,terraform/*.tf`), a build (`--surface build=Makefile`), a data
     pipeline (`--surface pipeline=dvc.yaml`). **Choosing the surfaces is your judgment;
     hashing them is the Core's faithful transform** (ADR-0028 §6), and your choice is
     recorded in the manifest (legible, re-checkable).
2. **Read the manifest and author the mental model** — a summary stamped
   **`--derivation model-read`** (you *read* the constitution with judgment; it is **not** a
   deterministic extraction of the whole tree). Ground **only** in the surfaces present: the
   repo's **purpose and role**, its **major modules/boundaries** (from topology +
   architecture), its **public contract**, and **ownership**. **Never claim knowledge of code
   you did not read** — the mental model is the repo's identity, not its internals. If the
   constitution is **thin** (say, only a README + topology), the mental model is thin — **say
   so, don't invent purpose**. Author findability facets in a reader's vocabulary
   (`Covers`: "what is `<repo>` for", "who owns it", "what does it expose", "where does it
   deploy").
3. **Staleness is automatic and correct.** The mental model grounds in the repo-source, whose
   `content_hash` is over the constitution — so it goes stale on a **constitutional amendment**
   (re-architecture, repurpose, split/merge, ownership) and **stays fresh under implementation
   churn**. On amendment, re-`capture-repo` (a new version) → the mental model is flagged stale
   (L4) → heal it with `regenerate`.
4. **Know your footprint before you answer — `repo-coverage` (T-196).** Before answering a
   **code question** ("how does `<repo>` do X?"), run `… repo-coverage <root> <repo-locator>`
   — the honest footprint of what the base *holds* about that repo: the constitution + the
   surfaces it captured, the **evidence** captures (specific files/excerpts you kept while
   answering earlier questions), the **concepts** already synthesized, and
   **`references_not_captured`** (constitution-named surfaces with no dedicated capture). Use it
   to classify the question, T-142's "a miss is not absence" applied to code, so *some*
   knowledge never masquerades as knowledge of the whole repo:
   - **known** — an evidence capture or concept already grounds it → answer from the base, cite it.
   - **partial** — the mental model *locates* the subsystem (it's a constitution surface or a
     `references_not_captured` entry) but no current source is held → say where it lives, then
     **fetch the live file and capture it** (`--origin-system repo`, locator `<repo>#<path>`,
     the T-196 convention) before grounding — never guess the implementation from the identity.
   - **unknown** — the repo is absent from coverage entirely (an all-empty scoped result) → say
     so plainly and offer to `capture-repo` it. A base that knows a repo's *identity* does not
     know its *internals*; keep that line honest.
   The scoped result is **always one entry** (all-empty = unknown, not an error); omit the
   locator for the roster of every repo the base knows. Read-only — it never fetches, walks, or
   infers; it reports only what is held.

**Generated agent-wiki layers (`openwiki/` and kin, T-133).** A repo's machine-generated
wiki is fair **transient routing input** — a free map of a big repo the survey may read
before you capture the constitution properly. But it is **never a constitution surface**
(generated text churns; the constitution's value is staying flat under churn) and **never
grounds the mental model**: it is ungrounded generated prose, and grounding in it is
summarizing summaries one level removed. Capture wiki pages as sources only when the wiki
itself is the object of memory, framed honestly as machine-generated secondary material
(low assurance; L10 territory) — there the base's staleness flags give the
silently-regenerated wiki the audit trail it lacks. Some generators write a pointer into
`AGENTS.md`, which *is* a constitution surface: a one-time pointer is a legitimate
amendment and its stale flag is **correct** — voice it, never suppress it.

