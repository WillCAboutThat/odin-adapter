"""HTML file → readable text, using only the standard library (no dependency).

Drops <script>/<style>/<head> content, inserts line breaks at block boundaries,
and collapses whitespace. This is a *readability aid*, not a faithful render — the
canonical HTML bytes remain the source of record (ADR-0010). Handles local HTML
files; fetching a live URL is acquisition (Huginn/`explore`), not extraction.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

from .base import Extractor

_SKIP = {"script", "style", "head", "noscript", "template"}
_BLOCK = {"p", "div", "br", "li", "tr", "section", "article", "header", "footer",
          "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "blockquote"}


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip_depth += 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth == 0:
            self.parts.append(data)


class HtmlExtractor(Extractor):
    name = "html-parser@1"
    extensions = frozenset({".html", ".htm"})

    def extract(self, raw: bytes) -> str:
        collector = _Collector()
        collector.feed(raw.decode("utf-8", errors="replace"))
        text = "".join(collector.parts)
        text = re.sub(r"[ \t]+", " ", text)          # collapse horizontal runs
        text = re.sub(r"\n[ \t]*(?:\n[ \t]*)+", "\n\n", text)  # collapse blank lines
        return text.strip()
