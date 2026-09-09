"""Novelty and peer engines, offline.

Network behaviour is covered by the live suite. These pin the pure logic:
phrase extraction, and how EFTS facet output is interpreted.
"""

import datetime as dt

from vantage.engines.novelty import (
    COMMON_PHRASE_CEILING,
    NoveltyResult,
    _sentences,
    _tokens,
    extract_novel_phrases,
)
from vantage.engines.peer import PeerAdopter, PeerAdoption, _parse_entity_label

AS_OF = dt.date(2024, 11, 1)


class TestTokenizing:
    def test_dotted_acronyms_survive_as_one_token(self) -> None:
        assert _tokens("lawsuits in the U.S. alleging") == [
            "lawsuits",
            "in",
            "the",
            "u.s.",
            "alleging",
        ]

    def test_acronym_does_not_end_a_sentence(self) -> None:
        text = "We face suits in the U.S. alleging monopolization. A second sentence."
        assert len(_sentences(text)) == 2


class TestPhraseExtraction:
    def test_returns_only_phrases_absent_from_the_prior_filing(self) -> None:
        prior = "We face competition in every market we serve."
        added = "We are subject to antitrust investigations in several jurisdictions."
        phrases = extract_novel_phrases(added, prior)
        assert phrases
        assert all("competition" not in p for p in phrases)
        assert any("antitrust" in p for p in phrases)

    def test_phrases_never_span_a_sentence_boundary(self) -> None:
        # Crossing the boundary invents collocations that were never written.
        added = "Demand may fall. Export controls may tighten."
        assert all("fall export" not in p for p in extract_novel_phrases(added, ""))

    def test_phrases_do_not_start_or_end_on_a_stopword(self) -> None:
        phrases = extract_novel_phrases(
            "The company is subject to significant regulatory scrutiny worldwide.", ""
        )
        assert phrases
        for p in phrases:
            assert p.split()[0] not in {"the", "is", "to", "of", "and"}
            assert p.split()[-1] not in {"the", "is", "to", "of", "and"}

    def test_shorter_phrases_inside_accepted_ones_are_dropped(self) -> None:
        phrases = extract_novel_phrases("Export control restrictions tightened sharply.", "")
        # No accepted phrase may be a substring of another.
        for i, a in enumerate(phrases):
            for j, b in enumerate(phrases):
                if i != j:
                    assert a not in b

    def test_identical_text_yields_nothing(self) -> None:
        body = "We are subject to antitrust investigations in several jurisdictions."
        assert extract_novel_phrases(body, body) == []

    def test_respects_the_limit(self) -> None:
        added = " ".join(f"Distinct clause number {i} about regulatory matters." for i in range(30))
        assert len(extract_novel_phrases(added, "", limit=3)) == 3


class TestNoveltyInterpretation:
    def _result(self, **kw: object) -> NoveltyResult:
        base = dict(phrase="export control restrictions", cik="0000320193", as_of=AS_OF)
        return NoveltyResult(**{**base, **kw})  # type: ignore[arg-type]

    def test_first_use_by_filer_when_no_prior_hits(self) -> None:
        r = self._result(filer_prior_uses=0, corpus_uses=42)
        assert r.is_first_for_filer
        assert r.is_notable

    def test_boilerplate_is_not_notable_even_when_new_to_the_filer(self) -> None:
        # A phrase in tens of thousands of filings says nothing about
        # this one, however new it is here.
        r = self._result(filer_prior_uses=0, corpus_uses=COMMON_PHRASE_CEILING + 1)
        assert r.is_first_for_filer
        assert not r.is_notable

    def test_prior_use_disqualifies(self) -> None:
        r = self._result(filer_prior_uses=3, filer_first_used=dt.date(2019, 10, 1), corpus_uses=10)
        assert not r.is_first_for_filer
        assert not r.is_notable
        assert "2019-10-01" in r.describe()

    def test_never_seen_anywhere_is_reported_as_such(self) -> None:
        assert "any filer" in self._result(filer_prior_uses=0, corpus_uses=0).describe()


class TestEntityLabelParsing:
    def test_extracts_cik_and_name(self) -> None:
        parsed = _parse_entity_label("APPLE INC.  (AAPL)  (CIK 0000320193)")
        assert parsed == ("0000320193", "APPLE INC.")

    def test_handles_multiple_tickers(self) -> None:
        parsed = _parse_entity_label(
            "ALLURION TECHNOLOGIES, INC.  (ALUR, ALUR-WT)  (CIK 0001964979)"
        )
        assert parsed is not None
        assert parsed[0] == "0001964979"

    def test_returns_none_without_a_cik(self) -> None:
        assert _parse_entity_label("SOME FUND WITH NO CIK") is None


class TestPeerAdoptionReporting:
    def _adoption(self, **kw: object) -> PeerAdoption:
        base = dict(
            phrase="export control",
            sic="3674",
            start=dt.date(2025, 1, 1),
            end=dt.date(2025, 12, 31),
            form="10-K",
        )
        return PeerAdoption(**{**base, **kw})  # type: ignore[arg-type]

    def test_reports_the_sic_numerator_without_inventing_a_denominator(self) -> None:
        # EFTS has no server-side SIC filter, so the population of filers in
        # an industry is not measurable here. The description must not imply
        # a fraction.
        text = self._adoption(sic_filings=52).describe()
        assert "52" in text
        assert " of " not in text

    def test_states_a_real_fraction_when_a_peer_set_was_supplied(self) -> None:
        text = self._adoption(peer_set_size=12, peer_set_adopters=7).describe()
        assert "7 of 12" in text

    def test_three_adopters_counts_as_sector_wide(self) -> None:
        assert self._adoption(sic_filings=3).is_sector_wide
        assert not self._adoption(sic_filings=2).is_sector_wide

    def test_capped_total_is_marked(self) -> None:
        text = self._adoption(sic=None, total_filings=10_000, total_is_capped=True).describe()
        assert "10000+" in text

    def test_adopter_list_is_flagged_when_truncated(self) -> None:
        adoption = self._adoption(
            adopters=[PeerAdopter(cik="0000320193", name="APPLE INC.", filings=2)],
            adopters_truncated=True,
        )
        assert adoption.adopters_truncated
