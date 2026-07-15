#!/usr/bin/env python3
"""Muninn linter — enforces the invariants of the Muninn knowledge format.

Implements the lint rules L1–L15 defined in docs/muninn/SPEC.md §7. The linter
is the guardian of the invariants: it is what makes summary chaining (and the
other failure modes) representable as an error rather than an accidental drift.

Usage:
    python3 tools/muninn_lint.py [MUNINN_DIR]

Exit code 0 if no errors (warnings are allowed), 1 if any error is found.

Tool-neutral by design: this reads only the on-disk format, no LLM required.
"""
from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("error: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

DERIVED_TYPES = {"summary", "entity", "concept", "question", "insight"}
DERIVED_DIRS = {"summaries", "entities", "concepts", "questions", "insights"}
DERIVATION_VALUES = {"extracted", "model-read", "synthesis"}  # §5.2 / ADR-0011 (L14)
SCOPE_VALUES = {"project", "global"}  # §5.6 / ADR-0002 (L16); absent defaults to 'project'
DECISION_STATUS_VALUES = {"proposed", "accepted"}  # §5.5 / ADR-0019 (L17)
# L18 summary-compression: a summary shorter than this many chars of source text is
# exempt — a small table or short note is *already* summary-length, so its derived doc
# is mostly findability facets, not restated content, and may legitimately run longer.
SUMMARY_COMPRESS_FLOOR = 500

# Upstream-anchor identity forms (ADR-0039, L20-opt-in). A partial capture's
# per-version `upstream_identity` names the WHOLE it was excerpted from, as a
# form-tagged content identity: git's own blob hash (comparable against a
# remote with no content fetch) or a plain SHA-256 of the fetched whole. The
# single authority shared by `capture`/`anchor` (write boundary) and the
# linter, so the two can never disagree about what a well-formed anchor is.
UPSTREAM_IDENTITY_RE = re.compile(r"^(git-blob:[0-9a-f]{40}|sha256:[0-9a-f]{64})$")

# Assurance ranking of a derivation, strongest (closest to deterministic ground)
# first. `ask` rolls the *weakest* rung among the docs it cites into one
# user-facing integrity line (ADR-0011 weakest-link; SKILLS §5 `ask`). Absent =
# `extracted` (the §5.2 default). This is the deterministic oracle the adapter
# mirrors — kept here beside DERIVATION_VALUES so the enum and its ordering can't
# drift apart.
_DERIVATION_RANK = {"extracted": 0, "model-read": 1, "synthesis": 2}


def weakest_derivation(derivations):
    """The weakest (least deterministic) derivation among `derivations`.

    Each entry is a derivation value or None (None ⇒ `extracted`, the default).
    Returns `extracted` for an empty set — nothing cited yet is not a weak link.
    Raises ValueError on an unknown value (mirrors L14 at the boundary).
    """
    weakest = "extracted"
    for d in derivations:
        d = d or "extracted"
        if d not in _DERIVATION_RANK:
            raise ValueError(f"unknown derivation {d!r} (L14)")
        if _DERIVATION_RANK[d] > _DERIVATION_RANK[weakest]:
            weakest = d
    return weakest


# --------------------------------------------------------------------------- #
# Shared helpers (also used by the ingest reference flow)
# --------------------------------------------------------------------------- #
def split_frontmatter(text: str):
    """Return (frontmatter_dict_or_None, body_str).

    Frontmatter is a leading `---` ... `---` YAML block. The body is everything
    after it; if there is no frontmatter, the whole text is the body.
    """
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            fm_text = text[4:end]
            body = text[end + 5 :]
            return yaml.safe_load(fm_text) or {}, body
        # A frontmatter open with no close is malformed; treat all as body.
    return None, text


# Text canonicals hash their (frontmatter-stripped) body; binary canonicals hash
# raw bytes (ADR-0010). Everything ultimately routes through content_hash_of_bytes.
TEXT_SUFFIXES = {".md", ".txt"}


def content_hash_of_bytes(raw: bytes) -> str:
    """The canonical Muninn content hash: SHA-256 over raw bytes (ADR-0010).

    NOTE: text normalization (whitespace/encoding) is still an open question
    (SPEC §9); binary is unambiguous — the bytes are the bytes.
    """
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def content_hash_of_body(body: str) -> str:
    """Hash for a TEXT source: SHA-256 over the UTF-8 bytes of the body.

    A text source's canonical bytes ARE the UTF-8 of its body, so this is just
    content_hash_of_bytes over that encoding — existing text hashes are unchanged.
    """
    return content_hash_of_bytes(body.encode("utf-8"))


def derived_content_hash(title, abstract, body) -> str:
    """Content self-hash of a derived doc's AUTHORED fields (title + abstract + body),
    deliberately excluding machine/provenance frontmatter (id, sources, derived_at,
    status, self_hash, …). The Core stamps it at write and the linter recomputes it
    (L18-opt-in / ADR-0029), so they must agree: an out-of-band edit to the authored
    content is detectable (L19), while a `regenerate` that reproduces the same content
    (only `derived_at` moves) is not a false positive. Body is stripped so the trailing
    newline the writer appends doesn't shift the hash."""
    canonical = f"{title or ''}\n\n{abstract or ''}\n\n{(body or '').strip()}\n"
    return content_hash_of_body(canonical)


def source_content_hash(source_md: Path) -> str:
    """Text-source hash: frontmatter stripped, body hashed (SPEC §4.2)."""
    _, body = split_frontmatter(source_md.read_text(encoding="utf-8"))
    return content_hash_of_body(body)


def content_hash_of_canonical(canonical_name: str, raw: bytes) -> str:
    """Content-identity hash of a captured canonical, from its bytes + filename.

    The **single source of truth** shared by `capture` (which has the bytes) and
    `lint` (which has the file on disk), so the two agree *by construction*
    regardless of platform line endings:

      - a **text** canonical (`.md`/`.txt`) hashes its newline-normalized,
        frontmatter-stripped body — CRLF and LF of the same text hash identically;
      - a **binary** canonical (`.pdf`/`.docx`/`.png`/…) hashes its raw bytes
        (ADR-0010; the bytes are unambiguous).

    This closes the CRLF-vs-LF L5 seam: previously `capture` hashed raw CRLF file
    bytes while `lint` hashed the LF-normalized body, so every text source
    captured from a `--source-file` on Windows failed L5. Normalizing text here
    also means trivial line-ending changes no longer count as a new version
    (SPEC §9 / T-013).
    """
    if Path(canonical_name).suffix.lower() in TEXT_SUFFIXES:
        # Match text-mode universal-newline reads (CRLF/CR -> LF), then strip
        # frontmatter, exactly as `source_content_hash` does off a file.
        text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        _, body = split_frontmatter(text)
        return content_hash_of_body(body)
    return content_hash_of_bytes(raw)


def canonical_content_hash(canonical: Path) -> str:
    """Hash over a source's canonical captured content (ADR-0010).

    Delegates to `content_hash_of_canonical` so a file on disk hashes the same as
    the bytes `capture` held: text by normalized body, binary by raw bytes.
    """
    return content_hash_of_canonical(canonical.name, canonical.read_bytes())


def partition_source_files(source_dir: Path):
    """Split a source dir's files into (canonical, text-aid) name→Path maps.

    Canonical = `source.<ext>` / `source.v<N>.<ext>`; aid = `source-text*.md`
    (ADR-0010). `meta.yml` and anything else is ignored.
    """
    canon, aids = {}, {}
    for p in sorted(source_dir.iterdir()):
        if not p.is_file():
            continue
        if p.name.startswith("source-text"):
            aids[p.name] = p
        elif p.name.startswith("source."):
            canon[p.name] = p
    return canon, aids


def current_canonical(source_dir: Path, meta: dict):
    """The current version's canonical file (ADR-0010), or None if absent.

    Reads the ledger entry whose `version` == meta['version']; falls back to a
    legacy `source.md` so pre-0.5 Muninns still resolve.
    """
    version = meta.get("version")
    for h in meta.get("history") or []:
        if isinstance(h, dict) and h.get("version") == version and h.get("file"):
            p = source_dir / h["file"]
            return p if p.exists() else None
    legacy = source_dir / "source.md"
    return legacy if legacy.exists() else None


def source_text(source_dir: Path, meta: dict) -> str:
    """The readable text of a source for retrieval / derivation (ADR-0010).

    Returns the current extracted-text aid if present (binary sources), else the
    canonical file if it is itself text (text-native sources), else '' — a
    bytes-only source has no readable text to search or derive from. This is the
    one place `find`, `index`, and `ask` should look for "what does this source
    say," so binary and text sources are handled uniformly.
    """
    aid = source_dir / "source-text.md"
    if aid.exists():
        return aid.read_text(encoding="utf-8", errors="replace")
    canonical = current_canonical(source_dir, meta)
    if canonical is not None and canonical.suffix.lower() in TEXT_SUFFIXES:
        return canonical.read_text(encoding="utf-8", errors="replace")
    return ""


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #
@dataclass
class Finding:
    rule: str
    severity: str  # "error" | "warn"
    message: str
    path: str


@dataclass
class Doc:
    id: str
    type: str
    kind: str  # "source" | "derived" | "project" | "decision" | "manifest"
    path: Path
    data: dict = field(default_factory=dict)


class Linter:
    def __init__(self, root: Path):
        self.root = root
        self.findings: list[Finding] = []
        self.docs: list[Doc] = []
        self.by_id: dict[str, Doc] = {}
        # L19 opt-in: derived-doc self-hash integrity, enabled per-Muninn in muninn.yml
        # (`integrity.derived_self_hash: true`). Default off so it never churns a base
        # that didn't ask for it (ADR-0029 §4). Set in _load_manifest.
        self._self_hash_enabled = False
        # L20 opt-in: upstream-anchor coherence for partial captures
        # (`integrity.upstream_anchors: true`, ADR-0039). Same posture as L19.
        self._anchors_enabled = False

    # -- reporting ---------------------------------------------------------- #
    def error(self, rule, msg, path):
        self.findings.append(Finding(rule, "error", msg, str(path)))

    def warn(self, rule, msg, path):
        self.findings.append(Finding(rule, "warn", msg, str(path)))

    # -- loading ------------------------------------------------------------ #
    def load(self):
        self._load_manifest()
        self._load_sources()
        self._load_dir(DERIVED_DIRS, "derived")
        self._load_dir({"projects"}, "project")
        self._load_dir({"decisions"}, "decision")
        # index id uniqueness now that everything is registered
        for doc in self.docs:
            if doc.id in self.by_id and self.by_id[doc.id] is not doc:
                self.error("L6", f"duplicate id '{doc.id}'", doc.path)
            self.by_id.setdefault(doc.id, doc)

    def _rel(self, p: Path) -> str:
        try:
            return str(p.relative_to(self.root))
        except ValueError:
            return str(p)

    def _load_manifest(self):
        mpath = self.root / "muninn.yml"
        if not mpath.exists():
            self.error("L12", "no muninn.yml manifest at Muninn root", mpath)
            return
        data = yaml.safe_load(mpath.read_text(encoding="utf-8")) or {}
        if "muninn" not in data:
            self.error("L12", "muninn.yml missing required 'muninn:' format version", mpath)
        integrity = data.get("integrity") or {}
        self._self_hash_enabled = bool(integrity.get("derived_self_hash"))
        self._anchors_enabled = bool(integrity.get("upstream_anchors"))
        self.docs.append(Doc(id="__manifest__", type="manifest", kind="manifest", path=mpath, data=data))

    def _load_sources(self):
        sdir = self.root / "sources"
        if not sdir.is_dir():
            return
        for child in sorted(sdir.iterdir()):
            if not child.is_dir():
                continue
            meta_path = child / "meta.yml"
            if not meta_path.exists():
                self.error("L9", f"source '{child.name}' has no meta.yml", child)
                continue
            data = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            doc = Doc(id=data.get("id", f"?{child.name}"), type="source",
                      kind="source", path=child, data=data)
            self.docs.append(doc)

    def _load_dir(self, dirnames: set[str], kind: str):
        for dirname in dirnames:
            d = self.root / dirname
            if not d.is_dir():
                continue
            for md in sorted(d.glob("*.md")):
                fm, _ = split_frontmatter(md.read_text(encoding="utf-8"))
                if fm is None:
                    self.error("L9", f"{self._rel(md)} has no YAML frontmatter", md)
                    continue
                doc = Doc(id=fm.get("id", f"?{md.stem}"), type=fm.get("type", "?"),
                          kind=kind, path=md, data=fm)
                self.docs.append(doc)

    # -- checks ------------------------------------------------------------- #
    def check(self):
        for d in self.docs:
            if d.kind == "source":
                self._check_source(d)
            elif d.kind == "derived":
                self._check_derived(d)
            elif d.kind == "project":
                self._check_project(d)
            elif d.kind == "decision":
                self._check_decision(d)
        self._check_index()
        self._check_source_summaries()

    def _require(self, doc, fields):
        for f in fields:
            if doc.data.get(f) in (None, "", []):
                self.error("L9", f"missing required field '{f}'", doc.path)

    def _check_source(self, d: Doc):
        self._require(d, ["id", "type", "origin", "capture", "captured_at",
                          "content_hash", "version", "history"])
        capture = d.data.get("capture")
        if capture == "reference" and not d.data.get("capture_reason"):
            self.error("L9", "reference capture requires 'capture_reason'", d.path)
        if capture not in ("full", "reference", None):
            self.error("L9", f"capture must be full|reference, got '{capture}'", d.path)

        # L5 immutable-source: recorded hash must match the current canonical
        # content — text body or binary bytes (ADR-0010).
        canonical = current_canonical(d.path, d.data)
        if canonical is not None:
            actual = canonical_content_hash(canonical)
            recorded = d.data.get("content_hash")
            if recorded and actual != recorded:
                self.error("L5", f"content_hash {recorded} != actual {actual} "
                                 f"(source edited in place?)", canonical)
        else:
            self.error("L9", "source directory has no canonical source file", d.path)

        # L13 version-ledger: history <-> on-disk source + text-aid files agree.
        history = [h for h in (d.data.get("history") or []) if isinstance(h, dict)]
        canon_disk, aid_disk = partition_source_files(d.path)
        ledger_canon = {h.get("file") for h in history if h.get("file")}
        ledger_aids = {h.get("text_aid") for h in history if h.get("text_aid")}
        for f in ledger_canon - set(canon_disk):
            self.error("L13", f"history references missing source file '{f}'", d.path)
        for f in set(canon_disk) - ledger_canon:
            self.error("L13", f"source file '{f}' not covered by history ledger", d.path)
        for f in ledger_aids - set(aid_disk):
            self.error("L13", f"history references missing text aid '{f}'", d.path)
        for f in set(aid_disk) - ledger_aids:
            self.error("L13", f"text aid '{f}' not covered by history ledger", d.path)

        # L20 anchor-coherence (opt-in, ADR-0039). A partial capture declares
        # the whole it excerpts via `origin.upstream_ref`; each version may
        # carry `upstream_identity` (the whole's content identity as of that
        # read) + `anchored_at` (only when attached later, by the `anchor`
        # backfill). Off by default: absence of every anchor field is always
        # legal (pre-ADR-0039 bases are simply "undeclared", never wrong).
        if self._anchors_enabled:
            origin = d.data.get("origin") or {}
            uref = origin.get("upstream_ref")
            cur_n = d.data.get("version")
            for e in history:
                ui = e.get("upstream_identity")
                if ui is not None and not UPSTREAM_IDENTITY_RE.match(str(ui)):
                    self.error("L20", f"v{e.get('version')} upstream_identity "
                                      f"'{ui}' has no known form "
                                      f"(git-blob:<sha1> | sha256:<hex64>)", d.path)
                if ui is not None and not uref:
                    self.error("L20", f"v{e.get('version')} has upstream_identity "
                                      f"but origin.upstream_ref is missing "
                                      f"(an anchor names WHAT changed of WHERE)", d.path)
                if e.get("anchored_at") and ui is None:
                    self.error("L20", f"v{e.get('version')} has anchored_at but "
                                      f"no upstream_identity", d.path)
            if uref:
                cur_e = next((e for e in history if e.get("version") == cur_n), None)
                if cur_e is None or cur_e.get("upstream_identity") is None:
                    self.error("L20", "declared partial capture (origin."
                                      "upstream_ref) is unanchored at its current "
                                      "version — run `anchor` to attach the "
                                      "upstream identity", d.path)

    def _check_derived(self, d: Doc):
        self._require(d, ["id", "type", "title", "sources", "derived_at", "status"])
        if d.type not in DERIVED_TYPES:
            self.warn("L9", f"unexpected derived type '{d.type}'", d.path)
        # L14 derivation-enum: absent is fine (defaults to 'extracted'); a present
        # value must be one of the known kinds (ADR-0011, §5.2).
        deriv = d.data.get("derivation")
        if deriv is not None and deriv not in DERIVATION_VALUES:
            self.error("L14", f"derivation '{deriv}' not one of "
                              f"{' | '.join(sorted(DERIVATION_VALUES))}", d.path)
        sources = d.data.get("sources") or []
        # L1 orphan
        if not sources:
            self.error("L1", "derived doc has no provenance (orphan)", d.path)
        all_reference = bool(sources)
        for s in sources:
            sid = s.get("id") if isinstance(s, dict) else s
            ref = self.by_id.get(sid)
            # L3 source-exists
            if ref is None:
                self.error("L3", f"provenance id '{sid}' resolves to nothing", d.path)
                all_reference = False
                continue
            # L2 no-chaining — the heart of the spec
            if ref.kind != "source":
                self.error("L2", f"provenance id '{sid}' is a {ref.kind}, not a source "
                                 f"(summary chaining)", d.path)
                all_reference = False
                continue
            # L4 hash-current / staleness. `superseded` is exempt like `stale`:
            # a CLOSED record (ADR-0041) is no longer obligated to track its
            # sources — its provenance still verifies against the versions it names.
            recorded = s.get("hash") if isinstance(s, dict) else None
            current = ref.data.get("content_hash")
            if (recorded and current and recorded != current
                    and d.data.get("status") not in ("stale", "superseded")):
                self.error("L4", f"source '{sid}' changed but this doc is not "
                                 f"flagged stale", d.path)
            if ref.data.get("capture") != "reference":
                all_reference = False
        # L10 reference-assurance
        if sources and all_reference:
            self.warn("L10", "grounded only in reference captures (not held in full)", d.path)
        # L7 link-resolves (see_also)
        for link in d.data.get("see_also") or []:
            if link not in self.by_id:
                self.error("L7", f"see_also link '{link}' resolves to nothing", d.path)
        # L19 derived-content integrity (opt-in, ADR-0029). When a Muninn enables
        # `integrity.derived_self_hash`, a derived doc carries a `self_hash` over its
        # authored content, stamped by the Core at write. A mismatch means the doc was
        # edited **out of band** (not through the Core) — the one in-format signal that
        # catches a hand-edit to a derived doc (sources are already covered by L5). It
        # is honesty tooling, not tamper-proofing: an adversary who edits the doc can
        # also rewrite the hash. A doc with no `self_hash` (captured before the flag was
        # enabled) is skipped, so turning the flag on never forces a mass regenerate.
        if self._self_hash_enabled and (stamped := d.data.get("self_hash")):
            _, body = split_frontmatter(d.path.read_text(encoding="utf-8"))
            actual = derived_content_hash(d.data.get("title"), d.data.get("abstract"), body or "")
            if stamped != actual:
                self.error("L19", "derived doc edited out-of-band — self_hash does not "
                           "match its authored content; regenerate it or revert the edit",
                           d.path)
        # L18 summary-compression: a summary must be shorter than its source(s). A
        # summary *compresses* — restating a source at length is paraphrase-bloat, not a
        # summary; enrich for findability (reader-vocabulary facets), not length. Advisory
        # (warn): the fix is a judgment call (regenerate tighter), never a silent edit (I5).
        # Exempt: sources with no text layer (a model-read of an image — nothing to be
        # shorter than) and already-terse sources below SUMMARY_COMPRESS_FLOOR.
        if d.type == "summary":
            src_len = sum(
                len(source_text(ref.path, ref.data))
                for s in sources
                if (ref := self.by_id.get(s.get("id") if isinstance(s, dict) else s))
                is not None and ref.kind == "source")
            if src_len >= SUMMARY_COMPRESS_FLOOR:
                _, body = split_frontmatter(d.path.read_text(encoding="utf-8"))
                summary_len = len(d.data.get("abstract") or "") + len(body or "")
                if summary_len > src_len:
                    self.warn("L18", f"summary ({summary_len} chars) is longer than its "
                              f"source ({src_len} chars) — summaries compress; enrich for "
                              f"findability, not length", d.path)

        # L21 supersession-coherence (ADR-0041; always-on: no pre-existing base
        # carries these fields, so none can fail it). A closed record's ending
        # must cohere: the pointer resolves and is not the doc itself; the
        # supersession fields appear only on a superseded doc; a superseded doc
        # carries its stamp and a successor or a reason.
        status = d.data.get("status")
        sup_by = d.data.get("superseded_by")
        if status == "superseded":
            if not d.data.get("superseded_at"):
                self.error("L21", "superseded doc has no superseded_at", d.path)
            if sup_by is None and not d.data.get("supersede_reason"):
                self.error("L21", "superseded doc names neither a successor "
                                  "(superseded_by) nor a supersede_reason", d.path)
            if sup_by is not None:
                if sup_by == d.id:
                    self.error("L21", "doc supersedes itself", d.path)
                elif sup_by not in self.by_id:
                    self.error("L21", f"superseded_by '{sup_by}' resolves to "
                                      f"nothing", d.path)
        else:
            for f in ("superseded_by", "superseded_at", "supersede_reason"):
                if d.data.get(f) is not None:
                    self.error("L21", f"'{f}' present but status is "
                                      f"'{status}', not 'superseded'", d.path)

    def _check_source_summaries(self):
        """L15 source-has-summary (ADR-0013): every source is grounded by >=1
        derived `summary`. Detection only — the linter never creates the summary;
        the gap is healed by the deliberate `regenerate` operation (I5)."""
        summarized = set()
        for d in self.docs:
            if d.kind == "derived" and d.type == "summary":
                for s in (d.data.get("sources") or []):
                    sid = s.get("id") if isinstance(s, dict) else s
                    if sid:
                        summarized.add(sid)
        for d in self.docs:
            if d.kind == "source" and d.id not in summarized:
                self.error("L15", "source has no summary — captured but unfindable; "
                                  "heal with `regenerate`", d.path)

    def _check_project(self, d: Doc):
        self._require(d, ["id", "type", "title"])
        # `members` must be *present* (a view declares its membership) but may be
        # empty — an empty view is valid, e.g. the seeded global hub (ADR-0018).
        if "members" not in d.data:
            self.error("L9", "missing required field 'members'", d.path)
        for m in d.data.get("members") or []:
            if m not in self.by_id:
                self.error("L11", f"project member '{m}' resolves to nothing", d.path)
        # L16 scope-enum: absent is fine (defaults to 'project'); a present scope
        # must be one of the allowed values (mirrors L14 for `derivation`).
        scope = d.data.get("scope")
        if scope is not None and scope not in SCOPE_VALUES:
            self.error("L16", f"scope '{scope}' not one of "
                              f"{' | '.join(sorted(SCOPE_VALUES))}", d.path)

    def _check_decision(self, d: Doc):
        # Decisions are AUTHORED, not derived (SPEC §5.5, ADR-0019): required
        # id/type/title/status/date and an enum status. A decision has NO
        # `sources` provenance — so L2 (chaining) and L4 (staleness) never apply.
        # It may carry `evidence` LINKS (source id + the version seen at record
        # time). Those must resolve to real sources (L17 error); when a cited
        # source's version has since advanced, that is a SOFT informational note
        # (L17 warn), never a stale flag — a decision is a judgment fixed in time.
        self._require(d, ["id", "type", "title", "status", "date"])
        status = d.data.get("status")
        if status is not None and status not in DECISION_STATUS_VALUES:
            self.error("L17", f"decision status '{status}' not one of "
                              f"{' | '.join(sorted(DECISION_STATUS_VALUES))}", d.path)
        for ev in d.data.get("evidence") or []:
            eid = ev.get("id") if isinstance(ev, dict) else ev
            ref = self.by_id.get(eid)
            if ref is None:
                self.error("L17", f"evidence '{eid}' resolves to nothing", d.path)
                continue
            if ref.kind != "source":
                self.error("L17", f"evidence '{eid}' is a {ref.kind}, not a source "
                                  f"(a decision links informing sources)", d.path)
                continue
            seen = ev.get("version") if isinstance(ev, dict) else None
            current = ref.data.get("version")
            if seen is not None and current is not None and current > seen:
                self.warn("L17", f"evidence '{eid}' advanced to v{current} since this "
                                 f"decision recorded v{seen} — revisit if the change "
                                 f"bears on it", d.path)

    # -- freshness (ADR-0005) ---------------------------------------------- #
    def content_fingerprint(self) -> str:
        """Hash over every registered doc's (id, hash), sorted.

        Sources contribute their body content_hash; other docs contribute a hash
        of their bytes. index.md and log.md are not registered docs and so are
        excluded by construction (SPEC §4.4).
        """
        entries = []
        for d in self.docs:
            if d.kind == "source":
                h = d.data.get("content_hash", "")
            else:
                h = "sha256:" + hashlib.sha256(d.path.read_bytes()).hexdigest()
            entries.append(f"{d.id}\t{h}")
        entries.sort()
        return "sha256:" + hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()

    def _check_index(self):
        index = self.root / "index.md"
        if not index.exists():
            self.error("L8", "no index.md at Muninn root", index)
            return
        text = index.read_text(encoding="utf-8")
        # Structural, not substring (T-026): a doc "appears in the index" when it
        # is an actual entry — a Markdown link whose label is the id (exactly what
        # the §5.3 projection emits). The old substring check false-passed an id
        # that merely occurred inside a longer id or in prose, and that is not
        # "index-complete" under any honest reading of the (unchanged) SPEC rule.
        linked = set(re.findall(r"\[([^\]\n]+)\]\([^)\n]*\)", text))
        listed = {d.id for d in self.docs if d.kind != "manifest"}
        for doc_id in sorted(listed):
            if doc_id not in linked:
                self.error("L8", f"'{doc_id}' has no index.md entry (a link labelled "
                                 f"with the id)", index)

    # -- run ---------------------------------------------------------------- #
    def run(self) -> int:
        self.load()
        self.check()
        errors = [f for f in self.findings if f.severity == "error"]
        warns = [f for f in self.findings if f.severity == "warn"]
        for f in sorted(self.findings, key=lambda x: (x.severity != "error", x.rule)):
            marker = "ERROR" if f.severity == "error" else "warn "
            print(f"  [{marker}] {f.rule}: {f.message}  ({f.path})")
        n_docs = len([d for d in self.docs if d.kind != "manifest"])
        print(f"\nMuninn: {self.root}")
        print(f"  {n_docs} documents · {len(errors)} error(s) · {len(warns)} warning(s)")
        print(f"  fingerprint: {self.content_fingerprint()}")
        if not errors:
            print("  OK — invariants hold." + (" (with warnings)" if warns else ""))
        return 1 if errors else 0


def last_lint_fingerprint(root: Path):
    """Read the fingerprint from the most recent standardized lint entry."""
    log = root / "log.md"
    if not log.exists():
        return None
    found = None
    for line in log.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("## [") or "]" not in s or "fingerprint=" not in s:
            continue
        # operation is the first `|`-delimited field after the `[date]`
        op = s.split("]", 1)[1].split("|", 1)[0].strip()
        if op == "lint":
            found = s.split("fingerprint=", 1)[1].strip().split()[0]
    return found


def check_freshness(root: Path) -> int:
    """Read-only: is the last lint current with the KB's content? (ADR-0005)"""
    linter = Linter(root)
    linter.load()
    current = linter.content_fingerprint()
    recorded = last_lint_fingerprint(root)
    if recorded is None:
        print(f"lint freshness: UNKNOWN — no prior lint recorded in log.md\n"
              f"  current fingerprint: {current}\n  suggest: run `odin lint`")
    elif recorded == current:
        print(f"lint freshness: FRESH — last lint matches current content\n"
              f"  fingerprint: {current}")
    else:
        print(f"lint freshness: STALE — the base changed since the last lint\n"
              f"  recorded: {recorded}\n  current:  {current}\n  suggest: run `odin lint`")
    return 0


def main(argv):
    args = argv[1:]
    freshness = "--freshness" in args
    args = [a for a in args if a != "--freshness"]
    root = Path(args[0]).resolve() if args else Path.cwd()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    if freshness:
        return check_freshness(root)
    return Linter(root).run()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
