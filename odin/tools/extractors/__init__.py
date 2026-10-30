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

from .code import CodeTextExtractor  # stdlib — plain-text source/config formats
register(CodeTextExtractor())      # .sql/.js/.py/.json/... (stdlib)

from .html import HtmlExtractor     # stdlib — always available
register(HtmlExtractor())

def register_optional(load) -> bool:
    """Run `load()` (an import + `register(...)`) for an OPTIONAL extractor and
    contain any failure, returning whether it loaded (T-269). Catches
    `BaseException`, not just `Exception`: a broken native dependency (pypdf's
    `cryptography` binding) raises pyo3's `PanicException`, which subclasses
    `BaseException` and escaped the old `except Exception` - taking `lint`,
    `status`, every CLI verb down at import. An optional accelerator must never
    take down the deterministic floor. Operator interrupts still propagate."""
    try:
        load()
        return True
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:  # noqa: BLE001 - deliberate, see docstring
        return False


def _load_pdf():  # PDFs fall back to bytes-only if pypdf isn't installed
    from .pdf import PdfExtractor
    register(PdfExtractor())


def _load_docx():  # .docx falls back to bytes-only if python-docx isn't installed
    from .docx import DocxExtractor
    register(DocxExtractor())


def _load_xlsx():  # .xlsx/.xlsm fall back to bytes-only if openpyxl isn't installed
    from .xlsx import XlsxExtractor
    register(XlsxExtractor())


register_optional(_load_pdf)
register_optional(_load_docx)
register_optional(_load_xlsx)
