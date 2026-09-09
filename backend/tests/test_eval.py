"""The evaluation harness itself.

If the scorer is wrong the gate is worthless, so the scorer needs its own
tests. These use hand-built cases where the right answer is obvious.
"""

import pytest

from vantage.domain.filing import FilingSection, SectionId, Span
from vantage.domain.finding import ChangeType, DetectedChange
from vantage.engines.diff import diff_sections
from vantage.eval.metrics import ConfusionMatrix, DetectionScore, merge_reports, score_case
from vantage.eval.mutate import ExpectedChange, mutate_section

ACC = "0000320193-24-000123"


def make_section(paragraphs: list[str], accession: str = ACC) -> FilingSection:
    return FilingSection(
        accession=accession,
        cik="0000320193",
        section_id=SectionId.RISK_FACTORS,
        heading="Item 1A. Risk Factors",
        order=0,
        text="\n".join(paragraphs),
    )


_TOPICS = [
    "supply chain disruption",
    "foreign currency exposure",
    "cybersecurity incidents",
    "regulatory investigations",
    "customer concentration",
    "intellectual property disputes",
    "talent retention",
    "climate related regulation",
    "interest rate movements",
    "third party manufacturing",
    "data privacy obligations",
    "tax law changes",
    "competitive pricing pressure",
    "product defects and recalls",
    "export restrictions",
    "channel partner reliance",
    "goodwill impairment",
    "pension obligations",
    "credit availability",
    "geopolitical instability",
]


def body(n: int) -> str:
    """A provably unique paragraph per index.

    Two constraints. Paragraphs differing only by a number are identical to
    the aligner, which masks digits so a date roll does not read as a
    rewrite, so the marker is alphabetic. And a move is only identifiable
    when the paragraph is unique, so every index must produce distinct text.
    """
    marker = "".join(chr(ord("a") + int(d)) for d in str(n).zfill(3))
    topic = _TOPICS[n % len(_TOPICS)]
    return (
        f"Exposure {marker} concerns {topic} and may adversely affect operating "
        f"results. Management monitors {topic} through the {marker} control programme "
        f"and has adopted measures intended to mitigate the consequences, though those "
        f"measures may prove insufficient during periods of rapid change."
    )


class TestDetectionScore:
    def test_precision_and_recall(self) -> None:
        score = DetectionScore(true_positives=8, false_positives=2, false_negatives=4)
        assert score.precision == pytest.approx(0.8)
        assert score.recall == pytest.approx(8 / 12)

    def test_empty_is_zero_not_a_crash(self) -> None:
        score = DetectionScore()
        assert (score.precision, score.recall, score.f1) == (0.0, 0.0, 0.0)


class TestConfusionMatrix:
    def test_accuracy_counts_only_the_diagonal(self) -> None:
        cm = ConfusionMatrix()
        cm.record(ChangeType.ADDED, ChangeType.ADDED)
        cm.record(ChangeType.MOVED, ChangeType.ADDED)
        assert cm.accuracy == pytest.approx(0.5)

    def test_per_type_separates_the_classes(self) -> None:
        # A blended accuracy hides that one class is broken, which is exactly
        # the thing worth knowing. Here overall accuracy is a healthy 0.9
        # while MOVED is completely broken.
        cm = ConfusionMatrix()
        for _ in range(9):
            cm.record(ChangeType.ADDED, ChangeType.ADDED)
        cm.record(ChangeType.MOVED, ChangeType.ADDED)
        per_type = cm.per_type()
        assert per_type[ChangeType.ADDED] == (9, 9)
        assert per_type[ChangeType.MOVED] == (0, 1)
        assert cm.accuracy == pytest.approx(0.9)


class TestOverlapMatching:
    def test_exact_overlap_matches(self) -> None:
        assert ExpectedChange(ChangeType.ADDED, 100, 200, "x" * 100).overlaps(100, 200)

    def test_near_miss_boundaries_still_match(self) -> None:
        # Boundary conventions differ slightly between the mutator and the
        # aligner. Demanding exact offsets would measure that, not detection.
        assert ExpectedChange(ChangeType.ADDED, 100, 200, "x" * 100).overlaps(98, 203)

    def test_small_overlap_does_not_match(self) -> None:
        assert not ExpectedChange(ChangeType.ADDED, 100, 200, "x" * 100).overlaps(190, 400)

    def test_disjoint_does_not_match(self) -> None:
        assert not ExpectedChange(ChangeType.ADDED, 100, 200, "x" * 100).overlaps(300, 400)


class TestMutation:
    def test_applies_the_requested_edit_counts(self) -> None:
        section = make_section([body(i) for i in range(30)])
        case = mutate_section(section, seed=7, additions=2, removals=2, rewordings=2, moves=1)
        assert case.counts[ChangeType.ADDED] == 2
        assert case.counts[ChangeType.REMOVED] == 2
        assert case.counts[ChangeType.REWORDED] == 2
        assert case.counts[ChangeType.MOVED] == 1

    def test_is_deterministic_for_a_seed(self) -> None:
        section = make_section([body(i) for i in range(30)])
        assert mutate_section(section, seed=7).mutated.text == (
            mutate_section(section, seed=7).mutated.text
        )

    def test_different_seeds_differ(self) -> None:
        section = make_section([body(i) for i in range(30)])
        assert (
            mutate_section(section, seed=1).mutated.text
            != mutate_section(section, seed=2).mutated.text
        )

    def test_mutated_copy_gets_its_own_accession(self) -> None:
        # Span verification checks the accession, so sharing one would let a
        # span validate against the wrong document.
        case = mutate_section(make_section([body(i) for i in range(30)]), seed=7)
        assert case.mutated.accession != case.original.accession

    def test_expected_offsets_address_the_right_document(self) -> None:
        case = mutate_section(make_section([body(i) for i in range(30)]), seed=7)
        for expected in case.expected:
            source = case.original if expected.change_type is ChangeType.REMOVED else case.mutated
            assert source.text[expected.start : expected.end] == expected.text

    def test_refuses_a_section_too_small_to_mutate(self) -> None:
        with pytest.raises(ValueError, match="too few to mutate"):
            mutate_section(make_section([body(0), body(1)]), seed=1)


class TestScoring:
    def test_perfect_recovery_scores_one(self) -> None:
        case = mutate_section(make_section([body(i) for i in range(40)]), seed=3)
        report = score_case(case, diff_sections(case.original, case.mutated))
        assert report.detection.recall == 1.0
        assert report.citation_validity == 1.0

    def test_a_move_is_reported_once_not_three_times(self) -> None:
        # Regression. A moved paragraph is deleted at its old position and
        # inserted at its new one, so the opcode walk also emitted an ADDED
        # and a REMOVED for it. That scored zero correctly classified moves
        # and held corpus precision at 0.76.
        case = mutate_section(
            make_section([body(i) for i in range(40)]),
            seed=5,
            additions=0,
            removals=0,
            rewordings=0,
            moves=1,
        )
        changes = diff_sections(case.original, case.mutated)
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.MOVED

    def test_spurious_detections_count_against_precision(self) -> None:
        case = mutate_section(make_section([body(i) for i in range(30)]), seed=3)
        detected = diff_sections(case.original, case.mutated)
        invented = DetectedChange(
            change_type=ChangeType.ADDED,
            section_id=SectionId.RISK_FACTORS,
            current_span=Span.from_section(case.mutated, 0, 40),
        )
        clean = score_case(case, detected)
        dirty = score_case(case, [*detected, invented])
        assert dirty.detection.precision < clean.detection.precision

    def test_unverifiable_span_lowers_citation_validity(self) -> None:
        case = mutate_section(make_section([body(i) for i in range(30)]), seed=3)
        tampered = DetectedChange(
            change_type=ChangeType.ADDED,
            section_id=SectionId.RISK_FACTORS,
            current_span=Span(
                accession=case.mutated.accession,
                section_id=SectionId.RISK_FACTORS,
                start=0,
                end=10,
                quote="WRONGWRONG",
            ),
        )
        assert score_case(case, [tampered]).citation_validity < 1.0

    def test_merging_sums_the_parts(self) -> None:
        section = make_section([body(i) for i in range(30)])
        reports = [
            score_case(c, diff_sections(c.original, c.mutated))
            for c in (mutate_section(section, seed=s) for s in (1, 2, 3))
        ]
        merged = merge_reports(reports)
        assert merged.cases == 3
        assert merged.detection.true_positives == sum(r.detection.true_positives for r in reports)
        assert merged.spans_checked == sum(r.spans_checked for r in reports)
