"""Excel .xlsx text extractor (openpyxl). Deterministic for a fixed lib version.

A spreadsheet is not an opaque source — it is a zip of XML with a fully
specified data layer, and parsing it is a faithful transform (the Core-boundary
test). Before this extractor existed, an .xlsx fell to the bytes-only path and
adapters reached for `model-read`: inference standing in for data that was
sitting right there (T-234, filed from a live failure).

The aid is **per-sheet markdown tables** — sheet titles as headings, the first
row rendered as the table header (the common case; when row 1 is data it is
still shown, nothing is lost). Cached values, not formulas (`data_only=True`):
what the sheet last displayed is what the aid records, and the choice is
stamped in the aid's footer. Big sheets truncate at a fixed row cap with an
in-band marker — surface, never silently — and the canonical bytes always hold
the rest (ADR-0010 rule 1).

Registered by the registry only when `openpyxl` imports, so a box without it
captures .xlsx bytes-only (ADR-0010 rule 5) rather than crashing. The old
binary `.xls` format is a different beast and is intentionally not handled
here, same as `.doc` in the docx extractor.
"""
from __future__ import annotations

import io

import openpyxl as _openpyxl

from .base import Extractor

try:
    from importlib.metadata import version as _pkg_version
    _VERSION = _pkg_version("openpyxl")
except Exception:  # pragma: no cover
    _VERSION = "?"

#: Per-sheet row cap. Past this the aid records that it truncated, in-band.
MAX_ROWS_PER_SHEET = 500


def _cell(value) -> str:
    if value is None:
        return ""
    # Pipes would break the table row; newlines would break the table line.
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


class XlsxExtractor(Extractor):
    name = f"openpyxl@{_VERSION}"
    extensions = frozenset({".xlsx", ".xlsm"})

    def extract(self, raw: bytes) -> str:
        wb = _openpyxl.load_workbook(
            io.BytesIO(raw), read_only=True, data_only=True
        )
        parts: list[str] = []
        for ws in wb.worksheets:
            parts.append(f"## {ws.title}")
            parts.append("")
            rows = ws.iter_rows(values_only=True)
            header = next(rows, None)
            if header is None:
                parts.append("*(empty sheet)*")
                parts.append("")
                continue
            cells = [_cell(v) for v in header]
            parts.append("| " + " | ".join(cells) + " |")
            parts.append("|" + "---|" * len(cells))
            emitted = 1
            truncated = False
            for row in rows:
                if emitted >= MAX_ROWS_PER_SHEET:
                    truncated = True
                    break
                parts.append("| " + " | ".join(_cell(v) for v in row) + " |")
                emitted += 1
            if truncated:
                # max_row comes from the sheet's declared dimensions; read-only
                # mode reports it without walking the remaining rows.
                total = ws.max_row if isinstance(ws.max_row, int) else None
                of = f" of {total}" if total else ""
                parts.append("")
                parts.append(
                    f"*(first {emitted}{of} rows — the canonical .xlsx holds "
                    "the rest)*"
                )
            parts.append("")
        wb.close()
        parts.append(
            "*(values as last calculated, not formulas — openpyxl data_only)*"
        )
        return "\n".join(parts)
