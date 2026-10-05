"""Diff engine.

These are the tests the CI gate leans on. Detection is deterministic, so a
regression here is measurable rather than a matter of judgement.
"""

import pytest

from vantage.domain.filing import FilingSection, SectionId
from vantage.domain.finding import ChangeType
from vantage.engines.diff import (
    COSMETIC_SIMILARITY_CEILING,
    MIN_PARAGRAPH_CHARS,
    diff_sections,
    score_materiality,
    split_paragraphs,
)

PRIOR_ACC = "0000320193-23-000106"
CURRENT_ACC = "0000320193-24-000123"


def section(text: str, *, accession: str, section_id: SectionId = SectionId.RISK_FACTORS):
    return FilingSection(
        accession=accession,
        cik="0000320193",
        section_id=section_id,
        heading="Item 1A. Risk Factors",
        order=0,
        text=text,
    )


def para(body: str) -> str:
    """Pad to clear the page-furniture floor without changing meaning."""
    if len(body) >= MIN_PARAGRAPH_CHARS:
        return body
    return body + " " + "x" * (MIN_PARAGRAPH_CHARS - len(body) - 1)


A = para("Demand for our products may decline due to competitive pressure worldwide.")
B = para("We depend on a limited number of suppliers for critical components today.")
C = para("Two customers accounted for thirty nine percent of net sales in the period.")


class TestSplitting:
    def test_offsets_address_the_section_text(self) -> None:
        s = section("\n".join([A, B]), accession=CURRENT_ACC)
        for p in split_paragraphs(s):
            assert s.text[p.start : p.end] == p.text

    def test_repeated_paragraphs_get_distinct_offsets(self) -> None:
        # Searching for the text rather than tracking a cursor would collapse
        # both copies onto the first offset.
        s = section("\n".join([A, B, A]), accession=CURRENT_ACC)
        paragraphs = [p for p in split_paragraphs(s) if p.text == A]
        assert len(paragraphs) == 2
        assert paragraphs[0].start != paragraphs[1].start
        for p in paragraphs:
            assert s.text[p.start : p.end] == A


class TestDetection:
    def test_added_paragraph(self) -> None:
        changes = diff_sections(
            section("\n".join([A, B]), accession=PRIOR_ACC),
            section("\n".join([A, B, C]), accession=CURRENT_ACC),
        )
        added = [c for c in changes if c.change_type is ChangeType.ADDED]
        assert len(added) == 1
        assert added[0].current_span is not None
        assert added[0].current_span.quote == C

    def test_removed_paragraph(self) -> None:
        changes = diff_sections(
            section("\n".join([A, B, C]), accession=PRIOR_ACC),
            section("\n".join([A, B]), accession=CURRENT_ACC),
        )
        removed = [c for c in changes if c.change_type is ChangeType.REMOVED]
        assert len(removed) == 1
        assert removed[0].prior_span is not None
        assert removed[0].prior_span.quote == C

    def test_reworded_paragraph_pairs_both_sides(self) -> None:
        rewritten = para("Two customers accounted for forty five percent of net sales, up sharply.")
        changes = diff_sections(
            section("\n".join([A, C]), accession=PRIOR_ACC),
            section("\n".join([A, rewritten]), accession=CURRENT_ACC),
        )
        reworded = [c for c in changes if c.change_type is ChangeType.REWORDED]
        assert len(reworded) == 1
        assert reworded[0].prior_span is not None
        assert reworded[0].current_span is not None
        assert reworded[0].similarity is not None

    def test_unrelated_replacement_is_not_a_rewrite(self) -> None:
        # Below the similarity floor these are two separate events, not one
        # paragraph becoming another.
        changes = diff_sections(
            section("\n".join([A, B]), accession=PRIOR_ACC),
            section("\n".join([A, C]), accession=CURRENT_ACC),
        )
        kinds = {c.change_type for c in changes}
        assert ChangeType.REWORDED not in kinds
        assert kinds == {ChangeType.ADDED, ChangeType.REMOVED}

    def test_date_roll_is_suppressed_as_cosmetic(self) -> None:
        # A filing that only advances its dates should produce no findings.
        # Without this the feed is nothing but date changes every year.
        prior = para("The fiscal year ended September 30, 2023 with revenue of 383,285 million.")
        current = para("The fiscal year ended September 28, 2024 with revenue of 391,035 million.")
        changes = diff_sections(
            section(prior, accession=PRIOR_ACC),
            section(current, accession=CURRENT_ACC),
        )
        assert changes == []

    def test_cosmetic_changes_surface_when_requested(self) -> None:
        prior = para("The fiscal year ended September 30, 2023 with revenue of 383,285 million.")
        current = para("The fiscal year ended September 28, 2024 with revenue of 391,035 million.")
        changes = diff_sections(
            section(prior, accession=PRIOR_ACC),
            section(current, accession=CURRENT_ACC),
            include_cosmetic=True,
        )
        # Surfaced via the masked-key path rather than the similarity
        # ceiling: the paragraphs aligned because dates and figures are
        # normalized out, which is a stronger cosmetic signal than the raw
        # ratio (0.90 here, since four tokens moved in a short paragraph).
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.REWORDED
        assert changes[0].prior_span is not None
        assert changes[0].current_span is not None

    def test_trivial_edit_in_a_long_paragraph_is_dropped_as_cosmetic(self) -> None:
        # The ceiling is a ratio, so it scales with paragraph length: a
        # one-word swap in a short paragraph is proportionally significant
        # and reported, while the same swap inside a long legal paragraph is
        # noise. That is the intended behaviour, not an artefact.
        body = (
            "We rely on a limited number of outsourcing partners for the manufacture "
            "and assembly of our products, and those partners operate facilities "
            "concentrated in a small number of locations, which exposes us to supply "
            "disruption arising from natural disasters, public health events, labour "
            "disputes, political instability and other conditions outside our control"
        )
        prior = para(body + ".")
        current = para(body + ";")
        assert (
            diff_sections(
                section(prior, accession=PRIOR_ACC),
                section(current, accession=CURRENT_ACC),
            )
            == []
        )
        surfaced = diff_sections(
            section(prior, accession=PRIOR_ACC),
            section(current, accession=CURRENT_ACC),
            include_cosmetic=True,
        )
        assert len(surfaced) == 1
        assert surfaced[0].similarity is not None
        assert surfaced[0].similarity >= COSMETIC_SIMILARITY_CEILING

    def test_one_word_swap_in_a_short_paragraph_is_reported(self) -> None:
        prior = para("We rely on a limited number of suppliers for critical display parts.")
        current = para("We rely on a limited number of vendors for critical display parts.")
        changes = diff_sections(
            section(prior, accession=PRIOR_ACC),
            section(current, accession=CURRENT_ACC),
        )
        assert len(changes) == 1
        assert changes[0].change_type is ChangeType.REWORDED

    def test_page_furniture_is_ignored(self) -> None:
        changes = diff_sections(
            section("\n".join([A, "27"]), accession=PRIOR_ACC),
            section("\n".join([A, "28"]), accession=CURRENT_ACC),
        )
        assert changes == []

    def test_reordering_is_reported_as_moved(self) -> None:
        filler = [
            para(f"Risk number {i} concerns operational matters in our business.")
            for i in range(20)
        ]
        prior = section("\n".join([*filler, C]), accession=PRIOR_ACC)
        current = section("\n".join([C, *filler]), accession=CURRENT_ACC)
        moved = [c for c in diff_sections(prior, current) if c.change_type is ChangeType.MOVED]
        assert any(c.current_span is not None and c.current_span.quote == C for c in moved)

    def test_identical_sections_produce_nothing(self) -> None:
        body = "\n".join([A, B, C])
        assert (
            diff_sections(section(body, accession=PRIOR_ACC), section(body, accession=CURRENT_ACC))
            == []
        )

    def test_refuses_to_diff_different_sections(self) -> None:
        with pytest.raises(ValueError, match="cannot diff"):
            diff_sections(
                section(A, accession=PRIOR_ACC, section_id=SectionId.MDA),
                section(A, accession=CURRENT_ACC, section_id=SectionId.RISK_FACTORS),
            )


class TestSpanIntegrity:
    def test_every_emitted_span_resolves(self) -> None:
        # The citation-validity invariant. A finding that cannot be traced
        # back to verbatim source text is a bug, not a low score.
        prior = section("\n".join([A, B, C]), accession=PRIOR_ACC)
        current = section(
            "\n".join([C, A, para("A wholly new risk about export controls and tariffs.")]),
            accession=CURRENT_ACC,
        )
        changes = diff_sections(prior, current)
        assert changes
        for change in changes:
            if change.prior_span is not None:
                assert change.prior_span.verify(prior)
            if change.current_span is not None:
                assert change.current_span.verify(current)


class TestMateriality:
    def test_risk_factor_addition_outranks_a_properties_tweak(self) -> None:
        risky = diff_sections(
            section(A, accession=PRIOR_ACC),
            section(
                "\n".join([A, para("We face a new investigation into our conduct.")]),
                accession=CURRENT_ACC,
            ),
        )
        dull = diff_sections(
            section(A, accession=PRIOR_ACC, section_id=SectionId.PROPERTIES),
            section(
                "\n".join([A, para("We lease an additional office in Austin, Texas.")]),
                accession=CURRENT_ACC,
                section_id=SectionId.PROPERTIES,
            ),
        )
        assert score_materiality(risky[0]).score > score_materiality(dull[0]).score

    def test_elevated_language_is_named_in_the_reasons(self) -> None:
        changes = diff_sections(
            section(A, accession=PRIOR_ACC),
            section(
                "\n".join([A, para("There is substantial doubt about our going concern status.")]),
                accession=CURRENT_ACC,
            ),
        )
        reasons = " ".join(score_materiality(changes[0]).reasons)
        assert "going concern" in reasons
        assert score_materiality(changes[0]).band == "high"

    def test_score_stays_in_range(self) -> None:
        changes = diff_sections(
            section(A, accession=PRIOR_ACC),
            section(
                "\n".join(
                    [
                        A,
                        para(
                            "Going concern, material weakness, restatement, impairment, covenant "
                            "default, investigation, subpoena, delisting and litigation all apply, "
                            "at considerable length, " + "and adverse concentration " * 40
                        ),
                    ]
                ),
                accession=CURRENT_ACC,
            ),
        )
        assert 0.0 <= score_materiality(changes[0]).score <= 1.0
