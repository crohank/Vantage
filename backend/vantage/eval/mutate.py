"""Synthetic mutation: ground truth for the diff engine, at scale, for free.

The problem with evaluating a diff engine on real year-over-year filings is
that nobody has labelled what changed. Hand-labelling a 70,000 character Item
1A is a day of work per pair.

So this inverts it. Take one real filing section, apply a known set of edits,
and the edits *are* the ground truth. Recall becomes "of the edits we made,
how many were recovered", and precision becomes "of the changes reported, how
many were edits we made". Both are exact, need no judge, and scale to as many
cases as there are filings.

The obvious objection is that synthetic edits are not real edits, and it is a
fair one. Two things address it. The source text is real filing prose, not
generated, so the alignment problem has genuine boilerplate and repetition in
it. And the harness reports synthetic and real-sample scores separately rather
than blending them, because synthetic alone would overstate.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from vantage.domain.filing import FilingSection, SectionId
from vantage.domain.finding import ChangeType

# Edits are applied to paragraphs at least this long, so a mutation is never
# hidden inside page furniture the engine deliberately ignores.
MIN_TARGET_CHARS = 200

# Reworded paragraphs get this share of their words replaced. Enough to fall
# below the cosmetic ceiling, little enough to stay above the similarity floor
# so the pair is still recognisably the same paragraph.
REWORD_FRACTION = 0.25

_WORD_BOUNDARY = re.compile(r"\S+")

# Substitutions that read like real filing language, so a reworded paragraph
# is not obviously synthetic to the aligner.
_SUBSTITUTIONS = {
    "may": "could",
    "could": "may",
    "significant": "substantial",
    "substantial": "significant",
    "adversely": "negatively",
    "negatively": "adversely",
    "business": "operations",
    "operations": "business",
    "increase": "rise",
    "decrease": "decline",
    "customers": "clients",
    "products": "offerings",
    "risks": "exposures",
    "results": "outcomes",
    "future": "subsequent",
    "material": "meaningful",
}

_INSERTED_PARAGRAPHS = [
    (
        "The Company has become subject to new export control restrictions that limit "
        "the sale of certain products into specified jurisdictions. These restrictions "
        "could reduce addressable demand and require redesign of affected offerings."
    ),
    (
        "A single customer accounted for a substantial portion of net sales during the "
        "period. The loss of, or a significant reduction in purchases by, this customer "
        "would have a material adverse effect on results of operations."
    ),
    (
        "The Company identified a material weakness in internal control over financial "
        "reporting relating to the review of manual journal entries. Remediation is "
        "ongoing and may require additional resources."
    ),
    (
        "Ongoing litigation in several jurisdictions alleges anticompetitive conduct in "
        "the distribution of third-party applications. An adverse outcome could require "
        "changes to established business practices."
    ),
    (
        "Climate-related regulation in certain markets now imposes reporting obligations "
        "on the Company's supply chain. Compliance costs are expected to increase and "
        "may not be recoverable through pricing."
    ),
]


@dataclass(frozen=True)
class ExpectedChange:
    """One edit that was applied, and therefore must be recovered."""

    change_type: ChangeType
    # Offsets into the mutated text for ADDED, REWORDED and MOVED, and into
    # the original text for REMOVED.
    start: int
    end: int
    text: str

    def overlaps(self, start: int, end: int, *, min_iou: float = 0.5) -> bool:
        """Intersection over union, so near-miss boundaries still match.

        Paragraph boundaries are not always identical between what was edited
        and what the aligner reports, and demanding exact offsets would
        measure boundary conventions rather than detection.
        """
        inter = max(0, min(self.end, end) - max(self.start, start))
        if inter == 0:
            return False
        union = max(self.end, end) - min(self.start, start)
        return union > 0 and inter / union >= min_iou


@dataclass(frozen=True)
class MutationCase:
    """A section, a mutated copy of it, and the edits between them."""

    section_id: SectionId
    original: FilingSection
    mutated: FilingSection
    expected: list[ExpectedChange]
    seed: int

    @property
    def counts(self) -> dict[ChangeType, int]:
        out: dict[ChangeType, int] = {}
        for change in self.expected:
            out[change.change_type] = out.get(change.change_type, 0) + 1
        return out


def _reword(text: str, rng: random.Random) -> str:
    """Substitute a fraction of words, preferring known filing synonyms."""
    tokens = text.split(" ")
    indices = [i for i, t in enumerate(tokens) if len(t) > 3]
    if not indices:
        return text + " This paragraph has been revised."
    rng.shuffle(indices)
    budget = max(1, int(len(indices) * REWORD_FRACTION))

    changed = 0
    for i in indices:
        if changed >= budget:
            break
        bare = re.sub(r"\W", "", tokens[i]).lower()
        if bare in _SUBSTITUTIONS:
            tokens[i] = tokens[i].lower().replace(bare, _SUBSTITUTIONS[bare])
            changed += 1
    if changed == 0:
        # No known synonym present, so append a clause instead. Still a
        # genuine rewrite, and still recoverable.
        return text + " The Company continues to evaluate this exposure."
    return " ".join(tokens)


def mutate_section(
    section: FilingSection,
    *,
    seed: int,
    additions: int = 2,
    removals: int = 2,
    rewordings: int = 2,
    moves: int = 1,
) -> MutationCase:
    """Apply a known set of edits and return them alongside the result.

    The mutated copy is presented as the *current* filing and the original as
    the *prior* one, which is the direction the diff engine expects.
    """
    rng = random.Random(seed)
    paragraphs = [p for p in section.text.split("\n")]
    eligible = [i for i, p in enumerate(paragraphs) if len(p.strip()) >= MIN_TARGET_CHARS]

    if len(eligible) < additions + removals + rewordings + moves + 1:
        raise ValueError(
            f"section {section.section_id.value} has {len(eligible)} paragraphs over "
            f"{MIN_TARGET_CHARS} chars, too few to mutate reliably"
        )

    rng.shuffle(eligible)
    cursor = 0
    to_remove = set(eligible[cursor : cursor + removals])
    cursor += removals
    to_reword = set(eligible[cursor : cursor + rewordings])
    cursor += rewordings
    to_move = set(eligible[cursor : cursor + moves])
    cursor += moves

    removed_texts = [paragraphs[i].strip() for i in sorted(to_remove)]
    moved_texts = [paragraphs[i].strip() for i in sorted(to_move)]

    # Build the mutated paragraph list first, then compute offsets from the
    # finished text. Deriving offsets while building would drift as later
    # edits change earlier lengths.
    rebuilt: list[str] = []
    reworded_pairs: list[str] = []
    for i, paragraph in enumerate(paragraphs):
        if i in to_remove or i in to_move:
            continue
        if i in to_reword:
            new_text = _reword(paragraph.strip(), rng)
            reworded_pairs.append(new_text)
            rebuilt.append(new_text)
        else:
            rebuilt.append(paragraph)

    # Moved paragraphs reappear at the front, which is what an issuer does
    # when it decides a risk has become more pressing.
    rebuilt = moved_texts + rebuilt

    inserted = [
        _INSERTED_PARAGRAPHS[(seed + n) % len(_INSERTED_PARAGRAPHS)] for n in range(additions)
    ]
    for n, text in enumerate(inserted):
        position = min(len(rebuilt), (n + 1) * max(1, len(rebuilt) // (additions + 1)))
        rebuilt.insert(position, text)

    mutated_text = "\n".join(rebuilt)
    mutated = FilingSection(
        accession=_bump_accession(section.accession),
        cik=section.cik,
        section_id=section.section_id,
        heading=section.heading,
        order=section.order,
        text=mutated_text,
    )

    expected: list[ExpectedChange] = []
    for text in inserted:
        expected.append(_locate(ChangeType.ADDED, text, mutated_text))
    for text in reworded_pairs:
        expected.append(_locate(ChangeType.REWORDED, text, mutated_text))
    for text in moved_texts:
        expected.append(_locate(ChangeType.MOVED, text, mutated_text))
    for text in removed_texts:
        expected.append(_locate(ChangeType.REMOVED, text, section.text))

    return MutationCase(
        section_id=section.section_id,
        original=section,
        mutated=mutated,
        expected=expected,
        seed=seed,
    )


def _locate(change_type: ChangeType, needle: str, haystack: str) -> ExpectedChange:
    index = haystack.find(needle)
    if index < 0:
        raise ValueError(f"mutation bookkeeping error: {change_type} text not found in output")
    return ExpectedChange(
        change_type=change_type, start=index, end=index + len(needle), text=needle
    )


def _bump_accession(accession: str) -> str:
    """Give the mutated copy a distinct accession.

    Span verification checks the accession, so reusing the original's would
    let a span verify against the wrong document.
    """
    prefix, year, serial = accession.split("-")
    return f"{prefix}-{int(year) + 1:02d}-{serial}"
