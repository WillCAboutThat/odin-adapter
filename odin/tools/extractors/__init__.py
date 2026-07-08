"""Extractor registry — resolve a source format to a text extractor (ADR-0010).

Built-ins register on import. `for_format(ext)` / `for_filename(name)` return an
`Extractor` or **None**; None means capture stores the bytes with no text aid
(still a valid, lint-clean source). A contributor extends Odin's document
processing by writing an `Extractor` (see `base.py`) and calling `register(...)`.
"""
from __future__ import annotations

from pathlib import Path

from .base import Extractor
from .text import TextExtractor

_REGISTRY: list = []


def register(extractor: Extractor) -> None:
    """Add an extractor. Most-recently-registered wins ties, so a contributor
    can override a built-in for a given extension."""
    _REGISTRY.insert(0, extractor)


def for_format(ext: str, mimetype: str | None = None):
    """Return the first registered extractor that handles `ext`, or None."""
    for e in _REGISTRY:
        if e.handles(ext, mimetype):
            return e
    return None


def for_filename(filename: str, mimetype: str | None = None):
    """Resolve by a filename's suffix."""
    return for_format(Path(filename).suffix, mimetype)


def registered() -> list:
    """The current registry, most-recent first (introspection / tests)."""
    return list(_REGISTRY)


# --- built-ins ------------------------------------------------------------- #
# Each optional-dependency extractor registers only if its lib imports; otherwise
# that format falls back to bytes-only capture (ADR-0010 rule 5) instead of erroring.
register(TextExtractor())          # .txt/.md + delimited .csv/.tsv/.tab (stdlib)

from .html import HtmlExtractor     # stdlib — always available
register(HtmlExtractor())

try:  # PDFs fall back to bytes-only if pypdf isn't installed
    from .pdf import PdfExtractor
    register(PdfExtractor())
except Exception:  # pragma: no cover
    pass

try:  # .docx falls back to bytes-only if python-docx isn't installed
    from .docx import DocxExtractor
    register(DocxExtractor())
except Exception:  # pragma: no cover
    pass
