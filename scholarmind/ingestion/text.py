"""Readable-text extraction from HTML.

The corpus is built from page text, so the quality of that text decides what
retrieval can find. A plain tag strip keeps the navigation, cookie banners and
footers, which then fill the evidence chunks with sentences like "Skip to
content Resource Hub Application guidance" instead of scholarship facts.

This module extracts the main content with the standard library only, which
keeps the core package dependency-free. The rules are deliberately
conservative: when no main/article region is found the whole body is used, so a
page is never silently reduced to nothing.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# Elements whose text is never part of the page's information.
SKIP_TAGS = frozenset(
    {
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "iframe",
        "object",
        "embed",
        "head",
        "nav",
        "footer",
        "form",
        "button",
        "select",
        "option",
        "label",
        "dialog",
    }
)

# Elements that start a new block of text.
BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "blockquote",
        "br",
        "div",
        "dl",
        "fieldset",
        "figcaption",
        "figure",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "tfoot",
        "thead",
        "tr",
        "ul",
    }
)

# Cells of a table row and the terms/definitions of a description list are
# joined on one line: "Deadline - 13 October 2026" is a fact, while
# "Deadline" and "13 October 2026" on separate lines is not.
CELL_TAGS = frozenset({"td", "th", "dt", "dd"})
CELL_SEPARATOR = " - "


# A region smaller than this is treated as a fragment (a card, a teaser) rather
# than the page's content, and the next candidate is considered instead.
MIN_REGION_CHARS = 300

_WHITESPACE = re.compile(r"[ \t\r\f\v\u00a0]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")
_MANY_SEPARATORS = re.compile(r"(?:\s*-\s*){2,}")

# Timelines are usually marked up as a block holding only the date followed by
# a block holding what happens on it. Joined back together, "13 October 2026 -
# applications close" keeps the date attached to its event.
_DATE_LINE = re.compile(r"^(?:\d{1,2}\s+[A-Z][A-Za-z]+\s+\d{4}|\d{4}-\d{2}-\d{2})$")


class _ContentExtractor(HTMLParser):
    """Collects body, main and article text in a single pass."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_stack: list[str] = []
        self._main_depth = 0
        self._article_depth = 0
        self.body: list[str] = []
        self.main: list[str] = []
        self.article: list[str] = []

    def _should_skip(self, tag: str) -> bool:
        if tag in SKIP_TAGS:
            return True
        # A page-level header is site chrome, but the header of an article
        # carries its title and summary, so it is kept.
        return tag == "header" and not (self._main_depth or self._article_depth)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._should_skip(tag):
            self._skip_stack.append(tag)
            return
        if tag == "main":
            self._main_depth += 1
        elif tag == "article":
            self._article_depth += 1
        if tag in BLOCK_TAGS:
            self._emit("\n")
        elif tag in CELL_TAGS:
            self._emit(CELL_SEPARATOR)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in BLOCK_TAGS:
            self._emit("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_stack and self._skip_stack[-1] == tag:
            self._skip_stack.pop()
            return
        if tag == "main":
            if self._main_depth:
                self._main_depth -= 1
        elif tag == "article":
            if self._article_depth:
                self._article_depth -= 1
        if tag in BLOCK_TAGS:
            self._emit("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_stack:
            return
        self._emit(data)

    def _emit(self, piece: str) -> None:
        self.body.append(piece)
        if self._main_depth:
            self.main.append(piece)
        if self._article_depth:
            self.article.append(piece)


def _tidy(parts: list[str]) -> str:
    """Collapse whitespace while keeping paragraph breaks meaningful."""
    text = "".join(parts)
    text = _WHITESPACE.sub(" ", text)
    text = _MANY_SEPARATORS.sub(CELL_SEPARATOR, text)
    lines = [line.strip().strip(CELL_SEPARATOR).strip() for line in text.split("\n")]

    merged: list[str] = []
    for line in lines:
        if (
            merged
            and merged[-1]
            and _DATE_LINE.match(merged[-1])
            and line
            and not _DATE_LINE.match(line)
        ):
            merged[-1] = f"{merged[-1]}{CELL_SEPARATOR}{line}"
            continue
        merged.append(line)

    kept: list[str] = []
    for line in merged:
        if line:
            kept.append(line)
        elif kept and kept[-1] != "":
            kept.append("")
    return _MANY_NEWLINES.sub("\n\n", "\n".join(kept)).strip()


def html_to_text(html: str) -> str:
    """Extract the readable text of an HTML document.

    ``main`` is preferred, then ``article``, then the whole body. Each region is
    only used if it carries at least :data:`MIN_REGION_CHARS` characters, which
    avoids treating a page's single card as its entire content.
    """
    parser = _ContentExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # pragma: no cover - HTMLParser is tolerant in practice
        pass

    for parts in (parser.main, parser.article, parser.body):
        candidate = _tidy(parts)
        if len(candidate) >= MIN_REGION_CHARS:
            return candidate

    # Everything is short: the body is still the most complete answer.
    return _tidy(parser.body)
