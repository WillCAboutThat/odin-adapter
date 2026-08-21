"""Plain-text / delimited passthrough extractor — the simplest Extractor, and the
copy-me example.

Two roles:
- **Delimited data** (`.csv`/`.tsv`/`.tab`): capture keeps the original bytes as
  the canonical record and this produces a decoded `source-text.md` aid so
  `find`/`ask` can read it. (Byte-hashing the canonical + a decoded aid avoids the
  CRLF/read-normalization mismatch that treating them as native text would cause.)
- **Native text** (`.txt`/`.md`): capture already treats these as their own text
  (no separate aid, ADR-0010 rule 7), so this extractor serves them only when a
  caller asks the registry for the text of such a blob directly.
"""
from __future__ import annotations

from .base import Extractor


class TextExtractor(Extractor):
    name = "text-passthrough@1"
    extensions = frozenset({".txt", ".md", ".markdown", ".csv", ".tsv", ".tab"})

    def extract(self, raw: bytes) -> str:
        # Decode as UTF-8; replace undecodable bytes rather than fail — the bytes
        # remain the authoritative source of record regardless (ADR-0010 rule 1).
        return raw.decode("utf-8", errors="replace")
