"""The extractor contract — Odin's document-processing extension point (ADR-0010).

Adding a new source format is a *local* change: write one `Extractor`, register
it (see `text.py` / `pdf.py` for the pattern), add one test. The invariant-carrying
Core (`muninn_core.capture`) never changes.

An extractor turns a source's **canonical bytes** into a plain-text *aid* — the
text that `find`/`ask`/`synthesize` and derivations actually read. The bytes stay
the source of record; the text is non-authoritative (ADR-0010 rule 3).

Rules for a Core extractor:
- **Deterministic and dependency-light.** It runs inside the no-AI Core; the same
  bytes must always yield the same text (its output is retained as provenance).
- **Judgment-free.** AI/vision/OCR extraction belongs adapter-side (ADR-0008);
  the adapter passes that text into `capture` directly instead of registering here.
- **Never trusted to succeed.** If `extract` raises, `capture` falls back to a
  bytes-only source (ADR-0010 rule 5) — a faithful, lint-clean source with no aid.
"""
from __future__ import annotations


class Extractor:
    """Base class. Subclass, set `name` + `extensions`, implement `extract`."""

    #: Provenance label recorded in the ledger, e.g. "pypdf@6.14.2".
    name: str = "extractor"
    #: Lowercased, dot-prefixed suffixes this handles, e.g. frozenset({".pdf"}).
    extensions: frozenset = frozenset()

    def handles(self, ext: str, mimetype: str | None = None) -> bool:
        """True if this extractor claims the given file extension / mimetype."""
        return ext.lower() in self.extensions

    def extract(self, raw: bytes) -> str:
        """Return plain text for `raw`. Must be deterministic. May raise."""
        raise NotImplementedError
