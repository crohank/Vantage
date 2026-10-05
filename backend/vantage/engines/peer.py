"""Peer adoption: is the whole industry saying this at once?

One filer adding a risk factor is a company event. Seven filers in the same
SIC adding it in one quarter is a sector event, and no free tool reports it.

On denominators. EDGAR full-text search has no server-side SIC parameter:
`sic=`, `sics=` and `SIC=` are all accepted and silently ignored, so results
cannot be restricted to an industry before counting. What is available is the
`sic_filter` aggregation, computed over the full match set, which gives a
truthful numerator ("52 filings in SIC 3674 used this phrase").

The denominator, meaning how many filers in that SIC filed at all in the
window, cannot be measured this way. Rather than invent one, the honest
numerator is reported on its own, and a true "N of M" is produced only when
the caller supplies an explicit peer set, which can be scoped with `ciks`.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from vantage.domain.filing import normalize_cik
from vantage.ingest.edgar import EdgarClient

# EFTS reports at most 30 buckets per facet, so a very common phrase produces
# a truncated entity list. Named adopters are therefore a sample, not a census.
MAX_FACET_BUCKETS = 30

# Elasticsearch caps the reported hit total. Aggregation counts can exceed it.
ES_TOTAL_CAP = 10_000

_CIK_IN_LABEL = re.compile(r"\(CIK\s+(\d{10})\)")
_NAME_IN_LABEL = re.compile(r"^(.*?)\s*\(")


class PeerAdopter(BaseModel):
    model_config = ConfigDict(frozen=True)

    cik: str
    name: str
    filings: int


class PeerAdoption(BaseModel):
    """How widely a phrase spread, over one form and one window."""

    model_config = ConfigDict(frozen=True)

    phrase: str
    sic: str | None
    start: date
    end: date
    form: str

    # Filings in the target SIC containing the phrase. Truthful, and the
    # headline number.
    sic_filings: int = 0
    # Across every industry, capped by Elasticsearch at 10,000.
    total_filings: int = 0
    total_is_capped: bool = False

    adopters: list[PeerAdopter] = Field(default_factory=list)
    adopters_truncated: bool = False

    # Populated only when the caller supplied an explicit peer set, which is
    # the one case where a denominator is real.
    peer_set_size: int | None = None
    peer_set_adopters: int | None = None

    @property
    def is_sector_wide(self) -> bool:
        """Enough independent filers for this to be an industry event.

        Three is a judgement call, not a measured threshold. It is the point
        at which coincidence stops being the simplest explanation.
        """
        if self.peer_set_size and self.peer_set_adopters is not None:
            return self.peer_set_adopters >= 3
        return self.sic_filings >= 3

    def describe(self) -> str:
        if self.peer_set_size and self.peer_set_adopters is not None:
            return (
                f"{self.peer_set_adopters} of {self.peer_set_size} named peers used this "
                f"in {self.form} filings between {self.start:%Y-%m-%d} and {self.end:%Y-%m-%d}."
            )
        if self.sic:
            return (
                f"{self.sic_filings} {self.form} filings in SIC {self.sic} used this "
                f"between {self.start:%Y-%m-%d} and {self.end:%Y-%m-%d}."
            )
        total = f"{self.total_filings}{'+' if self.total_is_capped else ''}"
        return f"{total} {self.form} filings used this in the window."


def _parse_entity_label(label: str) -> tuple[str, str] | None:
    """EFTS entity buckets are display strings, not structured records.

    Format: "APPLE INC.  (AAPL)  (CIK 0000320193)".
    """
    cik_match = _CIK_IN_LABEL.search(label)
    if not cik_match:
        return None
    name_match = _NAME_IN_LABEL.match(label)
    name = name_match.group(1).strip() if name_match else label
    return normalize_cik(cik_match.group(1)), name


async def peer_adoption(
    edgar: EdgarClient,
    phrase: str,
    *,
    start: date,
    end: date,
    sic: str | None = None,
    form: str = "10-Q",
    peer_ciks: list[str] | None = None,
) -> PeerAdoption:
    """Count filers using a phrase in one form over one window.

    With `peer_ciks` this runs a second, CIK-scoped search so the result can
    state a real "N of M". Without it, only the SIC numerator is reported.
    """
    result = await edgar.full_text_search(phrase, forms=form, start=start, end=end, limit=100)

    entity_counts = result.entity_counts()
    adopters: list[PeerAdopter] = []
    for label, count in entity_counts.items():
        parsed = _parse_entity_label(label)
        if parsed is None:
            continue
        cik, name = parsed
        adopters.append(PeerAdopter(cik=cik, name=name, filings=count))
    adopters.sort(key=lambda a: (-a.filings, a.name))

    peer_set_size: int | None = None
    peer_set_adopters: int | None = None
    if peer_ciks:
        normalized = [normalize_cik(c) for c in peer_ciks]
        peer_set_size = len(normalized)
        scoped = await edgar.full_text_search(
            phrase, forms=form, start=start, end=end, ciks=normalized, limit=100
        )
        matched = {c for hit in scoped.hits for c in hit.ciks}
        peer_set_adopters = len(matched & set(normalized))

    return PeerAdoption(
        phrase=phrase,
        sic=sic,
        start=start,
        end=end,
        form=form,
        sic_filings=result.sic_counts().get(sic, 0) if sic else 0,
        total_filings=result.total,
        total_is_capped=result.total >= ES_TOTAL_CAP,
        adopters=adopters,
        adopters_truncated=len(entity_counts) >= MAX_FACET_BUCKETS,
        peer_set_size=peer_set_size,
        peer_set_adopters=peer_set_adopters,
    )


async def sector_peers(edgar: EdgarClient, sic: str, phrase_hint: str = "the Company") -> list[str]:
    """Best-effort peer CIKs for an industry.

    There is no EDGAR endpoint that lists filers by SIC, so this samples the
    entity facet of a near-ubiquitous phrase and keeps the filers whose SIC
    matches. Capped at 30 buckets by EFTS, so it is a sample of active filers
    rather than a complete peer set. Treat the output as a seed list to be
    reviewed, not as ground truth.
    """
    today = date.today()
    result = await edgar.full_text_search(
        phrase_hint,
        forms="10-K",
        start=date(today.year - 1, 1, 1),
        end=today,
        limit=100,
    )
    return sorted({cik for hit in result.hits if sic in hit.sics for cik in hit.ciks})
