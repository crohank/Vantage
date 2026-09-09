"""Novelty: has this filer, or its industry, ever said this before?

Runs on top of EDGAR full-text search, which covers 2001 to present and is
free. Two questions, both cheap:

- First use by this filer. Scope the phrase to one CIK and look for anything
  earlier than the filing under examination.
- First use in the industry. Same phrase, no CIK scope, read the SIC facet.

Candidate phrases are not guessed at. They come from the diff: an n-gram is a
candidate only when it appears in an added or reworded passage and appears
nowhere in the prior filing. That is a precise local definition using
information already computed, rather than a generic "distinctiveness"
heuristic that would need a corpus frequency table to justify.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, ConfigDict

from vantage.ingest.edgar import EdgarClient

# Long enough to be a real collocation, short enough that EDGAR's exact-phrase
# search still matches across issuers who word things slightly differently.
MIN_PHRASE_WORDS = 3
MAX_PHRASE_WORDS = 6

# Corpus-wide match counts above this mean the phrase is boilerplate, so its
# appearance in one filing says nothing.
COMMON_PHRASE_CEILING = 2_000

# Matches word-ish tokens including numerals, one-letter words, and dotted
# acronyms. A narrower pattern silently drops tokens, which splices
# non-adjacent words into phrases nobody wrote ("lawsuits in the alleging").
_WORD = re.compile(r"(?:[A-Za-z]\.){2,}|[A-Za-z0-9][A-Za-z0-9'-]*")

# Sentence boundary. The character before the stop must be lowercase, a digit
# or a closing bracket, so "U.S." and other acronyms do not split a sentence
# and get torn into separate tokens.
_SENTENCE_SPLIT = re.compile(r"(?<=[a-z0-9)\]\"'])[.;:!?]\s+")

# Function words. An n-gram made only of these carries no signal, and one
# starting or ending on one reads as a fragment.
_STOPWORDS = frozenset(
    """a an and are as at be been but by can could do does for from had has
    have if in into is it its may might must no nor not of on or our ours
    shall she he should so such than that the their them there these they
    this those to under until up upon was we were what when where which
    while who will with within would you your also other otherwise all""".split()  # noqa: SIM905
)


class NoveltyResult(BaseModel):
    """What full-text search says about one phrase."""

    model_config = ConfigDict(frozen=True)

    phrase: str
    cik: str
    # None when the filer has never used the phrase before `as_of`.
    filer_first_used: date | None = None
    filer_prior_uses: int = 0
    # Corpus-wide count, all filers, all time. Distinguishes a phrase that is
    # new to this filer from one that is new to everybody.
    corpus_uses: int = 0
    sector_uses: int = 0
    sector_sic: str | None = None
    as_of: date

    @property
    def is_first_for_filer(self) -> bool:
        return self.filer_prior_uses == 0

    @property
    def is_rare_in_corpus(self) -> bool:
        return 0 < self.corpus_uses <= COMMON_PHRASE_CEILING

    @property
    def is_notable(self) -> bool:
        """New to this filer and not industry boilerplate.

        A phrase the filer has never used before is only interesting if it is
        not something every filing contains.
        """
        return self.is_first_for_filer and self.is_rare_in_corpus

    def describe(self) -> str:
        if not self.is_first_for_filer:
            return (
                f"Used {self.filer_prior_uses} time(s) before, first in "
                f"{self.filer_first_used:%Y-%m-%d}."
                if self.filer_first_used
                else f"Used {self.filer_prior_uses} time(s) before."
            )
        if self.corpus_uses == 0:
            return "First recorded use in EDGAR by any filer."
        return f"First use by this filer. {self.corpus_uses} other filings contain it."


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _WORD.findall(text)]


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _ngrams(words: list[str], low: int, high: int) -> set[str]:
    out: set[str] = set()
    for size in range(low, high + 1):
        for i in range(len(words) - size + 1):
            window = words[i : i + size]
            # Anchoring on content words at both ends keeps phrases that read
            # as units ("export control restrictions") and drops fragments
            # ("of our export control").
            if window[0] in _STOPWORDS or window[-1] in _STOPWORDS:
                continue
            if all(w in _STOPWORDS for w in window):
                continue
            out.add(" ".join(window))
    return out


def _phrase_candidates(text: str, low: int, high: int) -> set[str]:
    out: set[str] = set()
    for sentence in _sentences(text):
        out |= _ngrams(_tokens(sentence), low, high)
    return out


def extract_novel_phrases(
    added_text: str,
    prior_text: str,
    *,
    limit: int = 8,
) -> list[str]:
    """N-grams present in the new passage and absent from the prior filing.

    Longer phrases are preferred: they are more specific, and EDGAR's
    exact-phrase search rewards specificity. Any candidate contained inside a
    longer accepted candidate is dropped, so the caller does not spend
    requests confirming the same finding at several lengths.
    """
    prior_words = " ".join(_tokens(prior_text))
    candidates = _phrase_candidates(added_text, MIN_PHRASE_WORDS, MAX_PHRASE_WORDS)
    fresh = [c for c in candidates if c not in prior_words]

    chosen: list[str] = []
    for phrase in sorted(fresh, key=lambda p: (-len(p.split()), p)):
        if any(phrase in longer for longer in chosen):
            continue
        chosen.append(phrase)
        if len(chosen) >= limit:
            break
    return chosen


async def assess_phrase_novelty(
    edgar: EdgarClient,
    phrase: str,
    cik: str,
    as_of: date,
    *,
    sic: str | None = None,
) -> NoveltyResult:
    """Two searches: this filer's history, then the whole corpus.

    `as_of` is the filing date under examination. The filer search ends the
    day before, so the filing being analysed cannot count as its own
    precedent.
    """
    day_before = date.fromordinal(as_of.toordinal() - 1)

    own = await edgar.full_text_search(
        phrase,
        ciks=[cik],
        start=date(2001, 1, 1),
        end=day_before,
        limit=100,
    )
    corpus = await edgar.full_text_search(phrase, limit=1)

    sector_uses = 0
    if sic:
        sector_uses = corpus.sic_counts().get(sic, 0)

    return NoveltyResult(
        phrase=phrase,
        cik=cik,
        filer_first_used=own.earliest.filing_date if own.earliest else None,
        filer_prior_uses=own.total,
        corpus_uses=corpus.total,
        sector_uses=sector_uses,
        sector_sic=sic,
        as_of=as_of,
    )


async def find_novel_phrases(
    edgar: EdgarClient,
    added_text: str,
    prior_text: str,
    cik: str,
    as_of: date,
    *,
    sic: str | None = None,
    max_checks: int = 4,
) -> list[NoveltyResult]:
    """Extract candidates, then confirm the most specific few against EDGAR.

    Capped deliberately: each check costs two rate-limited requests, and a
    single added paragraph can yield dozens of candidate n-grams.
    """
    results: list[NoveltyResult] = []
    for phrase in extract_novel_phrases(added_text, prior_text, limit=max_checks):
        results.append(await assess_phrase_novelty(edgar, phrase, cik, as_of, sic=sic))
    return sorted(results, key=lambda r: (not r.is_notable, r.corpus_uses))
