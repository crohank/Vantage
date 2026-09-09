"""Year-over-year section diffing.

This is the deterministic half of the system and the reason the whole thing
is gradeable. Location is decided here, mechanically, by aligning paragraphs
between two comparable filings. The LLM never gets to say *that* something
changed, only to explain a change this module already found and cited.

Consequence: precision and recall on `DetectedChange` can be measured against
ground truth built from EDGAR history, with no model in the loop and no judge,
which is what lets the CI gate be both cheap and meaningful.
"""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher

from vantage.domain.filing import FilingSection, SectionId, Span
from vantage.domain.finding import ChangeType, DetectedChange, Materiality

# Below this, a pair of paragraphs is treated as unrelated (one removed, one
# added) rather than as a rewrite. Filings reuse boilerplate phrasing across
# unrelated paragraphs, so a low bar produces bogus REWORDED pairs.
REWORD_SIMILARITY_FLOOR = 0.55

# Above this a rewrite is cosmetic: punctuation, a date roll, a renumbered
# cross-reference. Real disclosure changes sit below it.
COSMETIC_SIMILARITY_CEILING = 0.97

# Paragraphs shorter than this are page furniture: page numbers, running
# headers, stray table cells. Skipped as change candidates, but they still
# occupy their offsets so spans stay accurate.
MIN_PARAGRAPH_CHARS = 60

# Sections where a change is inherently more interesting. Risk factors and
# MD&A are where management describes deterioration in its own words.
_SECTION_WEIGHT: dict[SectionId, float] = {
    SectionId.RISK_FACTORS: 1.0,
    SectionId.QUARTERLY_RISK_FACTORS: 1.0,
    SectionId.MDA: 0.9,
    SectionId.QUARTERLY_MDA: 0.9,
    SectionId.LEGAL_PROCEEDINGS: 0.85,
    SectionId.QUARTERLY_LEGAL: 0.85,
    SectionId.CYBERSECURITY: 0.8,
    SectionId.CONTROLS: 0.8,
    SectionId.BUSINESS: 0.6,
    SectionId.FINANCIAL_STATEMENTS: 0.5,
    SectionId.MARKET_RISK: 0.5,
    SectionId.PROPERTIES: 0.3,
    SectionId.UNRESOLVED_STAFF_COMMENTS: 0.3,
}
_DEFAULT_SECTION_WEIGHT = 0.5

# Language that tends to accompany a materially worse disclosure. Used only
# to rank what a reader sees first, never to decide whether a change happened.
_ELEVATED_TERMS = (
    "going concern",
    "material weakness",
    "restatement",
    "substantial doubt",
    "impairment",
    "covenant",
    "default",
    "investigation",
    "subpoena",
    "delisting",
    "concentration",
    "adverse",
    "litigation",
    "cyberattack",
    "breach",
    "export control",
    "tariff",
    "sanction",
)

_WHITESPACE = re.compile(r"\s+")
# Figures and month names change every filing. Normalizing them out stops a
# pure date roll from reading as a rewrite.
_VOLATILE = re.compile(
    r"\b(?:\d[\d,.]*%?|january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\b",
    re.IGNORECASE,
)


class Paragraph:
    """A block of section text with its offsets into `FilingSection.text`."""

    __slots__ = ("end", "key", "norm", "start", "text")

    def __init__(self, text: str, start: int, end: int) -> None:
        self.text = text
        self.start = start
        self.end = end
        self.norm = _normalize_for_match(text)
        # Volatile tokens removed, so a paragraph whose only change is a date
        # or a figure still aligns with its counterpart.
        self.key = _WHITESPACE.sub(" ", _VOLATILE.sub("#", self.norm)).strip()

    @property
    def substantive(self) -> bool:
        return len(self.text) >= MIN_PARAGRAPH_CHARS

    def __repr__(self) -> str:
        return f"Paragraph([{self.start}:{self.end}] {self.text[:50]!r})"


def _normalize_for_match(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().lower()


def split_paragraphs(section: FilingSection) -> list[Paragraph]:
    """Split a section into offset-addressed paragraphs.

    Offsets are accumulated while walking, not recovered by searching for
    each paragraph afterwards, which would mis-locate repeated boilerplate.
    """
    paragraphs: list[Paragraph] = []
    cursor = 0
    for raw in section.text.split("\n"):
        start = cursor
        cursor += len(raw) + 1  # the newline consumed by split
        stripped = raw.strip()
        if not stripped:
            continue
        lead = len(raw) - len(raw.lstrip())
        paragraphs.append(Paragraph(stripped, start + lead, start + lead + len(stripped)))
    return paragraphs


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def diff_sections(
    prior: FilingSection,
    current: FilingSection,
    *,
    include_cosmetic: bool = False,
) -> list[DetectedChange]:
    """Align two versions of the same canonical section.

    Both arguments must carry the same `section_id`, from two comparable
    filings. Returns changes in document order of the current filing.
    """
    if prior.section_id is not current.section_id:
        raise ValueError(f"cannot diff {prior.section_id.value} against {current.section_id.value}")

    old = split_paragraphs(prior)
    new = split_paragraphs(current)

    # Moves are resolved first. A paragraph that moved is deleted at its old
    # position and inserted at its new one, so the opcode walk would also
    # report it as a REMOVED plus an ADDED. Reporting one edit three times
    # inflates the feed and, in evaluation, showed up as zero correctly
    # classified moves: the spurious ADDED consumed the match and the real
    # MOVED scored as a false positive.
    moves = _find_moves(prior, current, old, new)
    moved_keys = {
        p.key
        for p in old
        for m in moves
        if m.prior_span is not None and m.prior_span.start == p.start
    }

    changes: list[DetectedChange] = list(moves)
    matcher = SequenceMatcher(None, [p.key for p in old], [p.key for p in new], autojunk=False)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Aligned on the normalized key, so the pair may still differ in
            # the masked tokens: a date roll or a restated figure. That is a
            # reporting decision, not an alignment one, so it is handled here
            # rather than by widening the key.
            if include_cosmetic:
                changes.extend(_cosmetic_pairs(prior, current, old[i1:i2], new[j1:j2]))
            continue
        removed = [p for p in old[i1:i2] if p.substantive and p.key not in moved_keys]
        added = [p for p in new[j1:j2] if p.substantive and p.key not in moved_keys]
        if tag == "replace":
            changes.extend(_pair_replacements(prior, current, removed, added, include_cosmetic))
        elif tag == "delete":
            changes.extend(_as_removals(prior, removed))
        elif tag == "insert":
            changes.extend(_as_additions(current, added))

    changes.sort(key=lambda c: c.current_span.start if c.current_span else -1)
    return changes


def _cosmetic_pairs(
    prior: FilingSection,
    current: FilingSection,
    old: list[Paragraph],
    new: list[Paragraph],
) -> list[DetectedChange]:
    """Report key-identical paragraphs whose literal text still moved.

    In practice these are date rolls and restated figures. Off by default
    because otherwise every annual filing produces a feed of nothing else.
    """
    changes: list[DetectedChange] = []
    for old_p, new_p in zip(old, new, strict=False):
        if not (old_p.substantive or new_p.substantive) or old_p.norm == new_p.norm:
            continue
        changes.append(
            DetectedChange(
                change_type=ChangeType.REWORDED,
                section_id=current.section_id,
                prior_span=Span.from_section(prior, old_p.start, old_p.end),
                current_span=Span.from_section(current, new_p.start, new_p.end),
                similarity=round(_similarity(old_p.norm, new_p.norm), 4),
            )
        )
    return changes


def _pair_replacements(
    prior: FilingSection,
    current: FilingSection,
    removed: list[Paragraph],
    added: list[Paragraph],
    include_cosmetic: bool,
) -> list[DetectedChange]:
    """Greedily pair each removed paragraph with its closest replacement.

    A replace opcode spans a whole run of paragraphs, but the interesting
    case is one paragraph being rewritten inside that run. Pairing recovers
    which old paragraph became which new one. Whatever fails to pair is a
    genuine addition or removal.
    """
    changes: list[DetectedChange] = []
    unmatched_new = list(added)

    for old_p in removed:
        best: Paragraph | None = None
        best_score = 0.0
        for new_p in unmatched_new:
            score = _similarity(old_p.norm, new_p.norm)
            if score > best_score:
                best, best_score = new_p, score

        if best is None or best_score < REWORD_SIMILARITY_FLOOR:
            changes.append(
                DetectedChange(
                    change_type=ChangeType.REMOVED,
                    section_id=prior.section_id,
                    prior_span=Span.from_section(prior, old_p.start, old_p.end),
                )
            )
            continue

        unmatched_new.remove(best)
        if best_score >= COSMETIC_SIMILARITY_CEILING and not include_cosmetic:
            continue
        changes.append(
            DetectedChange(
                change_type=ChangeType.REWORDED,
                section_id=prior.section_id,
                prior_span=Span.from_section(prior, old_p.start, old_p.end),
                current_span=Span.from_section(current, best.start, best.end),
                similarity=round(best_score, 4),
            )
        )

    changes.extend(_as_additions(current, unmatched_new))
    return changes


def _as_additions(current: FilingSection, paragraphs: list[Paragraph]) -> list[DetectedChange]:
    return [
        DetectedChange(
            change_type=ChangeType.ADDED,
            section_id=current.section_id,
            current_span=Span.from_section(current, p.start, p.end),
        )
        for p in paragraphs
    ]


def _as_removals(prior: FilingSection, paragraphs: list[Paragraph]) -> list[DetectedChange]:
    return [
        DetectedChange(
            change_type=ChangeType.REMOVED,
            section_id=prior.section_id,
            prior_span=Span.from_section(prior, p.start, p.end),
        )
        for p in paragraphs
    ]


def _find_moves(
    prior: FilingSection,
    current: FilingSection,
    old: list[Paragraph],
    new: list[Paragraph],
) -> list[DetectedChange]:
    """Paragraphs whose text survived but whose position shifted materially.

    Reordering risk factors is a real editorial signal: issuers tend to move
    the risk they now consider most pressing toward the front.
    """
    old_substantive = [p for p in old if p.substantive]
    new_substantive = [p for p in new if p.substantive]

    # A move is only identifiable when the paragraph is unique on both sides.
    # Filings repeat boilerplate, and once a key appears twice there is no
    # way to say which copy moved where. Left in, ambiguous keys make every
    # later paragraph look displaced: a section of near-identical paragraphs
    # reported 36 moves where one had occurred.
    old_counts = Counter(p.key for p in old_substantive)
    new_counts = Counter(p.key for p in new_substantive)
    unique = {k for k, n in old_counts.items() if n == 1 and new_counts.get(k) == 1}

    old_rank = {p.key: i for i, p in enumerate(old_substantive)}
    old_by_key = {p.key: p for p in old_substantive}

    # A shift of a few positions is fallout from neighbouring edits. A tenth
    # of the section is an editorial decision.
    threshold = max(3, len(new_substantive) // 10)

    moves: list[DetectedChange] = []
    for new_rank, p in enumerate(new_substantive):
        if p.key not in unique:
            continue
        before = old_rank.get(p.key)
        if before is None or abs(before - new_rank) < threshold:
            continue
        source = old_by_key[p.key]
        moves.append(
            DetectedChange(
                change_type=ChangeType.MOVED,
                section_id=current.section_id,
                prior_span=Span.from_section(prior, source.start, source.end),
                current_span=Span.from_section(current, p.start, p.end),
                similarity=1.0,
            )
        )
    return moves


def score_materiality(change: DetectedChange) -> Materiality:
    """A deterministic first pass at how much a change matters.

    Ranking only. This decides what a reader sees first, never whether a
    change is reported. Kept rule-based so the ordering is reproducible and
    explainable rather than a model's opinion that drifts between runs.
    """
    reasons: list[str] = []
    weight = _SECTION_WEIGHT.get(change.section_id, _DEFAULT_SECTION_WEIGHT)
    score = weight * 0.4
    reasons.append(f"section {change.section_id.value} weighted {weight:.2f}")

    if change.change_type is ChangeType.ADDED:
        score += 0.3
        reasons.append("newly added disclosure")
    elif change.change_type is ChangeType.REMOVED:
        score += 0.25
        reasons.append("disclosure withdrawn")
    elif change.change_type is ChangeType.REWORDED:
        # The further from identical, the more was actually said.
        divergence = 1.0 - (change.similarity or 1.0)
        score += min(0.3, divergence * 0.6)
        reasons.append(f"reworded, similarity {change.similarity:.2f}")
    else:
        score += 0.05
        reasons.append("reordered within the section")

    text = " ".join(
        s.quote.lower() for s in (change.current_span, change.prior_span) if s is not None
    )
    hits = sorted({t for t in _ELEVATED_TERMS if t in text})
    if hits:
        score += min(0.25, 0.08 * len(hits))
        reasons.append("elevated language: " + ", ".join(hits[:4]))

    longest = max(
        len(change.current_span.quote) if change.current_span else 0,
        len(change.prior_span.quote) if change.prior_span else 0,
    )
    if longest > 1200:
        score += 0.05
        reasons.append("substantial passage")

    return Materiality(score=round(min(score, 1.0), 4), reasons=reasons)
