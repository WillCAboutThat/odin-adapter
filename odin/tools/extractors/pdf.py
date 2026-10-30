"""PDF text extractor (pypdf). Deterministic for a fixed pypdf version.

This module imports `pypdf` at import time; the registry (`__init__`) only
registers it when the import succeeds, so a box without pypdf simply captures
PDFs bytes-only (ADR-0010 rule 5) instead of crashing.
"""
from __future__ import annotations

import io

import pypdf

from .base import Extractor

_VERSION = getattr(pypdf, "__version__", "?")


class PdfExtractor(Extractor):
    name = f"pypdf@{_VERSION}"
    extensions = frozenset({".pdf"})

    def extract(self, raw: bytes) -> str:
        reader = pypdf.PdfReader(io.BytesIO(raw))
        # Join per-page text with blank lines; a page with no extractable text
        # (e.g. a scanned image) contributes an empty string, not a crash.
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
