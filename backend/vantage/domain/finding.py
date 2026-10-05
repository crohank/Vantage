"""Findings: what the engines emit.

Design rule the whole eval story rests on: **location is deterministic,
explanation is generative.** A mechanical aligner decides that a paragraph
changed and produces the spans. The LLM only classifies and explains a change
that has already been located. It is never asked to find one.

That split is why `change_type` and the spans can be scored against
ground truth with no model in the loop, while `summary` and `rationale` need
a judge.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from vantage.domain.filing import FilingSection, SectionId, Span


class FindingKind(StrEnum):
    DIFF = "diff"
    NOVELTY = "novelty"
    PEER = "peer"


class ChangeType(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    REWORDED = "reworded"
    MOVED = "moved"


class Provenance(BaseModel):
    """Stamped on every finding so eval results join back to the code and
    prompt that produced them. None of this was linked in the old system, so
    "did prompt v3 cost less than v2" was unanswerable from stored data.
    """

    model_config = ConfigDict(frozen=True)

    git_sha: str
    prompt_name: str | None = None
    prompt_version: int | None = None
    model: str | None = None
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Materiality(BaseModel):
    """Why a change is worth surfacing, not just that it is."""

    model_config = ConfigDict(frozen=True)

    score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def band(self) -> str:
        if self.score >= 0.7:
            return "high"
        if self.score >= 0.4:
            return "medium"
        return "low"


class Finding(BaseModel):
    """One surfaced observation about a filing.

    Invariant enforced by `verify_spans`: every span must resolve to its exact
    quoted text in the stored section. CI treats a violation as a failure.
    """

    id: str
    kind: FindingKind
    cik: str
    ticker: str
    section_id: SectionId

    # DIFF carries both sides. ADDED has no prior_span, REMOVED has no
    # current_span. NOVELTY and PEER carry only current_span.
    change_type: ChangeType | None = None
    current_span: Span | None = None
    prior_span: Span | None = None
    current_accession: str | None = None
    prior_accession: str | None = None

    # Generative layer. Empty until the explain node runs, which keeps
    # detection independently gradeable.
    summary: str = ""
    rationale: str = ""

    materiality: Materiality
    provenance: Provenance

    # NOVELTY: the phrase and how far back the search looked.
    novelty_phrase: str | None = None
    novelty_first_seen: str | None = None
    novelty_searched_since: int | None = None

    # PEER: which other filers made the same change.
    peer_ciks: list[str] = Field(default_factory=list)
    peer_total: int | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> Finding:
        if self.kind is FindingKind.DIFF:
            if self.change_type is None:
                raise ValueError("diff findings require a change_type")
            if self.change_type is ChangeType.ADDED and self.current_span is None:
                raise ValueError("ADDED requires current_span")
            if self.change_type is ChangeType.REMOVED and self.prior_span is None:
                raise ValueError("REMOVED requires prior_span")
            if self.change_type in (ChangeType.REWORDED, ChangeType.MOVED) and (
                self.current_span is None or self.prior_span is None
            ):
                raise ValueError(f"{self.change_type} requires both spans")
        return self

    @staticmethod
    def make_id(
        kind: FindingKind,
        accession: str,
        section_id: SectionId,
        start: int,
        end: int,
        discriminator: str = "",
    ) -> str:
        raw = f"{kind.value}:{accession}:{section_id.value}:{start}:{end}:{discriminator}"
        return hashlib.sha1(raw.encode()).hexdigest()[:20]

    def verify_spans(self, sections: dict[str, FilingSection]) -> list[str]:
        """Return one message per span that fails to resolve. Empty means valid.

        `sections` is keyed by `FilingSection.key`.
        """
        errors: list[str] = []
        for label, span in (("current", self.current_span), ("prior", self.prior_span)):
            if span is None:
                continue
            section = sections.get(f"{span.accession}:{span.section_id.value}")
            if section is None:
                errors.append(
                    f"{label}_span: section {span.accession}:{span.section_id} not stored"
                )
            elif not span.verify(section):
                errors.append(
                    f"{label}_span: offsets [{span.start},{span.end}) in "
                    f"{span.accession}:{span.section_id.value} do not match the stored quote"
                )
        return errors


class DetectedChange(BaseModel):
    """Output of the mechanical aligner, before any LLM sees it.

    Kept as its own type so the deterministic stage can be tested and scored
    on its own. Findings are built from these.
    """

    model_config = ConfigDict(frozen=True)

    change_type: ChangeType
    section_id: SectionId
    current_span: Span | None = None
    prior_span: Span | None = None
    # Character-level similarity between the two sides, 0.0 to 1.0. Only
    # meaningful for REWORDED and MOVED.
    similarity: float | None = None
