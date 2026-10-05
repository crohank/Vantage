"""Structural section extraction from filing HTML.

The previous implementation ran two regexes per section over the whole raw
document and truncated each match to 5,000 characters. That fails on modern
inline-XBRL filings for three reasons, all visible in any recent 10-K:

1. The table of contents contains the same "Risk Factors" text as the real
   heading, so a first-match regex captures the TOC entry.
2. Prose cross-references ("those discussed in Part I, Item 1A of this Form
   10-K") look like headings to a naive pattern.
3. A real Item 1A runs 20k to 50k words. Truncating at 5,000 characters
   makes year-over-year diffing meaningless.

Approach here: flatten the document to block-level text, discard internal
anchors (which is what the TOC is built from), then treat a block as a
heading only when the entire block is short and matches an item pattern.
Sections run from one heading to the next.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from html import unescape
from typing import cast

from lxml import html as lxml_html
from lxml.etree import _Element

from vantage.domain.filing import Filing, FilingSection, Form, SectionId

log = logging.getLogger(__name__)

NEWLINE = chr(10)
ZERO_WIDTH_SPACE = chr(0x200B)
NBSP = chr(0xA0)

_DROP_XPATH = "//script | //style | //*[local-name()='ix:header']"
_ANCHOR_XPATH = "//a[starts-with(@href, '#')]"

# Block-level tags that should force a line break when flattening.
_BLOCK_TAGS = frozenset(
    {"div", "p", "tr", "td", "th", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "table"}
)

# A heading block is short. Real Item headings are a line; prose that merely
# mentions an item is not.
_MAX_HEADING_CHARS = 140

# "Item 1A." / "Item 1A" / "ITEM 1A -" and optional "Part II" prefix.
_ITEM_RE = re.compile(
    r"^(?:part\s+(?P<part>[ivx]+)\s*[.,\-\u2013]?\s*)?"
    r"item\s+(?P<num>\d{1,2})(?P<alpha>[a-z]?)\s*[.\-:\u2013]?\s*(?P<title>.{0,120})$",
    re.IGNORECASE,
)

# Canonical mapping, keyed by (part_roman_or_None, item_number, item_letter).
_TEN_K_SECTIONS: dict[tuple[str, str], SectionId] = {
    ("1", ""): SectionId.BUSINESS,
    ("1", "a"): SectionId.RISK_FACTORS,
    ("1", "b"): SectionId.UNRESOLVED_STAFF_COMMENTS,
    ("1", "c"): SectionId.CYBERSECURITY,
    ("2", ""): SectionId.PROPERTIES,
    ("3", ""): SectionId.LEGAL_PROCEEDINGS,
    ("7", ""): SectionId.MDA,
    ("7", "a"): SectionId.MARKET_RISK,
    ("8", ""): SectionId.FINANCIAL_STATEMENTS,
    ("9", "a"): SectionId.CONTROLS,
}

# 10-Q renumbers everything and splits across two parts, so the same
# "Item 1A" means different things depending on the part.
_TEN_Q_SECTIONS: dict[tuple[str, str, str], SectionId] = {
    ("i", "2", ""): SectionId.QUARTERLY_MDA,
    ("ii", "1", ""): SectionId.QUARTERLY_LEGAL,
    ("ii", "1", "a"): SectionId.QUARTERLY_RISK_FACTORS,
}

# Titles that confirm a heading is the real thing rather than a coincidence.
_EXPECTED_TITLE_WORDS: dict[SectionId, tuple[str, ...]] = {
    SectionId.BUSINESS: ("business",),
    SectionId.RISK_FACTORS: ("risk",),
    SectionId.UNRESOLVED_STAFF_COMMENTS: ("unresolved", "staff"),
    SectionId.CYBERSECURITY: ("cybersecurity", "cyber"),
    SectionId.PROPERTIES: ("propert",),
    SectionId.LEGAL_PROCEEDINGS: ("legal", "proceeding"),
    SectionId.MDA: ("management", "discussion"),
    SectionId.MARKET_RISK: ("quantitative", "market risk"),
    SectionId.FINANCIAL_STATEMENTS: ("financial statement",),
    SectionId.CONTROLS: ("controls", "procedures"),
    SectionId.QUARTERLY_MDA: ("management", "discussion"),
    SectionId.QUARTERLY_LEGAL: ("legal", "proceeding"),
    SectionId.QUARTERLY_RISK_FACTORS: ("risk",),
}


class _Heading:
    """An item heading found in the body.

    `section_id` is None for items outside the canonical map (Item 4, Item 5,
    Item 1C before it was mapped, and so on). Those are still recorded,
    because an unmapped heading has to terminate the section before it. When
    it does not, its body is absorbed into the previous section and the diff
    engine reports a spurious rewrite: Apple's FY2024 Item 1B swallowed the
    whole new Item 1C Cybersecurity disclosure that way.
    """

    __slots__ = ("has_title", "item_key", "line_index", "section_id", "text")

    def __init__(
        self,
        section_id: SectionId | None,
        item_key: str,
        text: str,
        line_index: int,
        has_title: bool = False,
    ) -> None:
        self.section_id = section_id
        self.item_key = item_key
        self.text = text
        self.line_index = line_index
        self.has_title = has_title


def _normalize(text: str) -> str:
    """Decode entities, collapse nbsp and friends.

    Filings are dense with `&#160;` runs used as heading padding, and
    `&#8217;` for apostrophes. Both have to go before any pattern matching.
    """
    text = unescape(text)
    text = unicodedata.normalize("NFKC", text)
    # Zero-width space and non-breaking space, written as escapes because
    # the literal characters are invisible in a diff.
    text = text.replace(ZERO_WIDTH_SPACE, "").replace(NBSP, chr(32))
    return re.sub(r"[ 	]+", " ", text).strip()


def html_to_lines(raw_html: str | bytes) -> list[str]:
    """Flatten filing HTML to block-level lines.

    Internal anchors are dropped: in practice every `<a href="#...">` in a
    filing is either a table-of-contents row or a cross-reference, and both
    produce false headings.
    """
    if not raw_html:
        return []

    # lxml refuses a str carrying an XML encoding declaration, which every
    # inline-XBRL filing has. Feeding bytes also lets lxml honour the meta
    # charset instead of us guessing, which is what produced mojibake in
    # apostrophes when the document was pre-decoded as utf-8.
    payload = raw_html.encode("utf-8", errors="replace") if isinstance(raw_html, str) else raw_html

    try:
        tree = lxml_html.fromstring(payload)
    except (ValueError, lxml_html.etree.ParserError, lxml_html.etree.XMLSyntaxError):
        log.warning("lxml could not parse document, falling back to tag stripping")
        text = payload.decode("utf-8", errors="replace")
        stripped = re.sub(r"<[^>]+>", NEWLINE, text)
        return [_normalize(x) for x in stripped.split(NEWLINE) if x.strip()]

    for bad in cast(list[_Element], tree.xpath(_DROP_XPATH)):
        parent = bad.getparent()
        if parent is not None:
            parent.remove(bad)

    # Drop internal-anchor text. External links keep theirs.
    for anchor in cast(list[_Element], tree.xpath(_ANCHOR_XPATH)):
        anchor.text = ""
        for child in list(anchor):
            anchor.remove(child)

    parts: list[str] = []

    def walk(node: lxml_html.HtmlElement) -> None:
        tag = node.tag if isinstance(node.tag, str) else ""
        block = tag.lower() in _BLOCK_TAGS
        if block:
            parts.append(NEWLINE)
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
            if child.tail:
                parts.append(child.tail)
        if block:
            parts.append(NEWLINE)

    walk(tree)
    flat = "".join(parts)
    return [ln for ln in (_normalize(x) for x in flat.split(NEWLINE)) if ln]


def _parse_item_line(line: str, form: Form) -> tuple[str, SectionId | None, bool] | None:
    """Identify an item heading.

    Returns (item_key, canonical_section_or_None, has_title), or None when
    the line is not a heading at all. The key identifies the item within the
    document so repeated occurrences collapse onto one entry. `has_title`
    separates a real section heading ("ITEM 1A. RISK FACTORS") from a running
    page header or a contents row, which are bare ("Item 1A").
    """
    if len(line) > _MAX_HEADING_CHARS:
        return None
    m = _ITEM_RE.match(line)
    if not m:
        return None

    num = m.group("num")
    alpha = (m.group("alpha") or "").lower()
    part = (m.group("part") or "").lower()
    title = (m.group("title") or "").lower()
    item_key = f"{part}|{num}{alpha}"

    if form is Form.TEN_Q:
        candidate = _TEN_Q_SECTIONS.get((part, num, alpha))
        if candidate is None and not part:
            # 10-Q filings often state the part once in its own heading
            # rather than repeating it on every item.
            for (_p, n, a), sid in _TEN_Q_SECTIONS.items():
                if (n, a) == (num, alpha):
                    candidate = sid
                    break
    else:
        candidate = _TEN_K_SECTIONS.get((num, alpha))

    # A titled heading has to carry an expected word, which rejects
    # coincidental matches. An untitled "Item 1A." is accepted as-is.
    if candidate is not None and title:
        expected = _EXPECTED_TITLE_WORDS.get(candidate, ())
        if expected and not any(w in title for w in expected):
            candidate = None

    return item_key, candidate, bool(title)


def _classify(line: str, form: Form) -> SectionId | None:
    """Canonical section for a heading line, or None."""
    parsed = _parse_item_line(line, form)
    return parsed[1] if parsed else None


def find_headings(lines: list[str], form: Form) -> list[_Heading]:
    """Locate the real section headings.

    Three things masquerade as headings in a filing, all present in
    Microsoft's 10-K:

    - Contents rows near the top, which are bare ("Item 1A").
    - Running page headers repeated on every page of a section, also bare.
      Microsoft's Item 1A body carries fifteen of them.
    - Divider lines covering several items at once ("Item 1B, 1C").

    Each candidate is scored on whether it carries a title and on how much
    text it owns before the next heading of a different item. The real
    heading wins on both: it is titled, and it owns the whole section, while
    a page header owns only the few lines until the next repeat. Selecting
    by document order alone picks a page header and truncates the section.
    """
    candidates: list[_Heading] = []
    for i, line in enumerate(lines):
        parsed = _parse_item_line(line, form)
        if parsed is not None:
            key, sid, has_title = parsed
            candidates.append(_Heading(sid, key, line, i, has_title))

    if not candidates:
        return []

    # A heading whose immediate neighbour is also a heading belongs to a
    # contents block or a combined divider line.
    neighbours = {c.line_index for c in candidates}
    standalone = [c for c in candidates if (c.line_index + 1) not in neighbours]
    if not standalone:
        standalone = candidates

    positions = sorted(c.line_index for c in candidates)

    def owned_lines(h: _Heading) -> int:
        for pos in positions:
            if pos > h.line_index and _key_at(candidates, pos) != h.item_key:
                return pos - h.line_index
        return len(lines) - h.line_index

    best: dict[str, _Heading] = {}
    for h in standalone:
        incumbent = best.get(h.item_key)
        if incumbent is None or (h.has_title, owned_lines(h)) > (
            incumbent.has_title,
            owned_lines(incumbent),
        ):
            best[h.item_key] = h
    return sorted(best.values(), key=lambda h: h.line_index)


def _key_at(candidates: list[_Heading], line_index: int) -> str:
    for c in candidates:
        if c.line_index == line_index:
            return c.item_key
    return ""


def extract_sections(filing: Filing, raw_html: str | bytes) -> list[FilingSection]:
    """Full, untruncated canonical sections for one filing.

    Every heading bounds a section, but only mapped ones are emitted.
    """
    lines = html_to_lines(raw_html)
    headings = find_headings(lines, filing.form)
    if not headings:
        log.warning("no sections found in %s %s", filing.ticker, filing.accession)
        return []

    sections: list[FilingSection] = []
    for idx, heading in enumerate(headings):
        if heading.section_id is None:
            continue
        start = heading.line_index + 1
        end = headings[idx + 1].line_index if idx + 1 < len(headings) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        if not body:
            continue
        sections.append(
            FilingSection(
                accession=filing.accession,
                cik=filing.cik,
                section_id=heading.section_id,
                heading=heading.text,
                order=len(sections),
                text=body,
            )
        )
    return sections
