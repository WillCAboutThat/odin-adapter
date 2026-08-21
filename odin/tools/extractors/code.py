"""Source-code passthrough extractor — plain-text files the registry was missing.

A `.sql`, `.js`, or `.py` file *is* plain text. Decoding it is the same faithful
transform `text.py` performs for `.txt`, and it carries the same guarantee: same
bytes, same text, no inference, nothing a model could get wrong. The registry
simply never claimed these suffixes, so they fell to the bytes-only path.

That gap had real consequences on a live base (found 2026-08-02):

- A `.js` test file was captured bytes-only and its summary stamped `model-read`,
  because there was no text layer to read. **T-180 says exactly the opposite** --
  `extracted` outranks `model-read`, and a format that is one extractor away from
  faithful should not be model-read at all.
- Quoted spans citing `.sql` and `.js` sources could not be verified at the write
  seam: with no text layer, `source_text()` returns empty and the T-153 gate has
  nothing to check against, so it skips them (T-224). Held bytes nobody can
  mechanically check are weaker evidence than held bytes anybody can.

Deliberately **text-only and conservative**. Every suffix here names a format that
is plain text by definition. A binary that borrows one of these suffixes decodes
with replacement characters rather than raising, exactly as `text.py` does -- the
bytes remain the source of record either way (ADR-0010 rule 1), and a garbled aid
is visible to a reader in a way a missing one is not.

Not registered here, on purpose: anything whose bytes are *not* text. A format
needing layout reconstruction, decompression, or any reading decision is a
different kind of transform and belongs in its own extractor with its own tests.
"""
from __future__ import annotations

from .base import Extractor


class CodeTextExtractor(Extractor):
    name = "code-passthrough@1"
    #: Plain-text source and config formats. Kept explicit rather than
    #: open-ended: an extractor that claims every unknown suffix would turn a
    #: mis-suffixed binary into a confident-looking aid.
    extensions = frozenset({
        # data definition and query
        ".sql",
        # scripting and application code
        ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
        ".py", ".rb", ".go", ".rs", ".java", ".kt", ".swift",
        ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".pl", ".lua", ".r",
        ".sh", ".bash", ".zsh", ".ps1",
        # structured text and config
        ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
        ".xml", ".css", ".scss", ".less",
        # plain-text conventions with no suffix meaning of their own
        ".log", ".rst", ".tex", ".env", ".properties",
    })

    def extract(self, raw: bytes) -> str:
        # Same posture as text.py: decode as UTF-8 and replace what will not
        # decode, rather than raising. The bytes stay authoritative regardless
        # (ADR-0010 rule 1), and a bytes-only fallback would lose the aid
        # entirely for one bad byte.
        return raw.decode("utf-8", errors="replace")
