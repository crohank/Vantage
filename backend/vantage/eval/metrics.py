"""Scoring for the deterministic tier.

Three numbers, none of which need a model:

- Detection precision, recall and F1 against known edits.
- Classification accuracy, as a confusion matrix over change types. A single
  accuracy figure hides that the engine is, say, fine on additions and poor on
  rewrites, which is the thing worth knowing.
- Citation validity, the share of emitted spans that resolve to their quoted
  text. This is a correctness gate rather than a score: anything below 1.0 is
  a bug.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from vantage.domain.filing import FilingSection
from vantage.domain.finding import ChangeType, DetectedChange
from vantage.eval.mutate import ExpectedChange, MutationCase

# Overlap required before a detected change counts as the same event as an
# expected one. Paragraph boundary conventions differ slightly between the
# mutator and the aligner, and demanding exact offsets would measure that
# rather than detection quality.
MATCH_MIN_IOU = 0.5


@dataclass
class ConfusionMatrix:
    """Expected change type against reported change type."""

    counts: Counter[tuple[ChangeType, ChangeType]] = field(default_factory=Counter)

    def record(self, expected: ChangeType, actual: ChangeType) -> None:
        self.counts[(expected, actual)] += 1

    @property
    def accuracy(self) -> float:
        total = sum(self.counts.values())
        if total == 0:
            return 0.0
        correct = sum(n for (exp, act), n in self.counts.items() if exp is act)
        return correct / total

    def per_type(self) -> dict[ChangeType, tuple[int, int]]:
        """Correct and total, per expected type."""
        out: dict[ChangeType, tuple[int, int]] = {}
        for (exp, act), n in self.counts.items():
            correct, total = out.get(exp, (0, 0))
            out[exp] = (correct + (n if exp is act else 0), total + n)
        return out

    def render(self) -> str:
        types = sorted({t for pair in self.counts for t in pair}, key=lambda t: t.value)
        if not types:
            return "  (no classified changes)"
        width = max(len(t.value) for t in types) + 2
        header = " " * width + "".join(f"{t.value:>12}" for t in types)
        rows = [header]
        for exp in types:
            cells = "".join(f"{self.counts.get((exp, act), 0):>12}" for act in types)
            rows.append(f"{exp.value:<{width}}{cells}")
        return "\n".join(rows)


@dataclass
class DetectionScore:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def merge(self, other: DetectionScore) -> None:
        self.true_positives += other.true_positives
        self.false_positives += other.false_positives
        self.false_negatives += other.false_negatives


@dataclass
class EvalReport:
    cases: int = 0
    detection: DetectionScore = field(default_factory=DetectionScore)
    confusion: ConfusionMatrix = field(default_factory=ConfusionMatrix)
    spans_checked: int = 0
    spans_valid: int = 0
    missed: list[ExpectedChange] = field(default_factory=list)
    spurious: list[DetectedChange] = field(default_factory=list)

    @property
    def citation_validity(self) -> float:
        return self.spans_valid / self.spans_checked if self.spans_checked else 1.0

    def as_dict(self) -> dict[str, Any]:
        """Machine-readable scores, for the metrics dashboard.

        Rendered text is for a human reading CI output; this is the same
        numbers in a shape the frontend can chart without parsing a table.
        """
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "cases": self.cases,
            "detection": {
                "precision": round(self.detection.precision, 4),
                "recall": round(self.detection.recall, 4),
                "f1": round(self.detection.f1, 4),
                "true_positives": self.detection.true_positives,
                "false_positives": self.detection.false_positives,
                "false_negatives": self.detection.false_negatives,
            },
            "classification": {
                "accuracy": round(self.confusion.accuracy, 4),
                "per_type": {
                    expected.value: {"correct": correct, "total": total}
                    for expected, (correct, total) in sorted(
                        self.confusion.per_type().items(), key=lambda kv: kv[0].value
                    )
                },
                "matrix": [
                    {"expected": exp.value, "reported": act.value, "count": n}
                    for (exp, act), n in sorted(
                        self.confusion.counts.items(),
                        key=lambda kv: (kv[0][0].value, kv[0][1].value),
                    )
                ],
            },
            "citations": {
                "checked": self.spans_checked,
                "valid": self.spans_valid,
                "validity": round(self.citation_validity, 6),
            },
        }

    def render(self) -> str:
        d = self.detection
        lines = [
            f"cases                {self.cases}",
            f"detection precision  {d.precision:.3f}  "
            f"({d.true_positives} tp, {d.false_positives} fp)",
            f"detection recall     {d.recall:.3f}  ({d.false_negatives} fn)",
            f"detection F1         {d.f1:.3f}",
            f"classification acc   {self.confusion.accuracy:.3f}",
            f"citation validity    {self.citation_validity:.4f}  "
            f"({self.spans_valid}/{self.spans_checked} spans resolve)",
            "",
            "confusion (rows expected, columns reported):",
            self.confusion.render(),
        ]
        per_type = self.confusion.per_type()
        if per_type:
            lines.append("")
            lines.append("per change type:")
            for change_type, (correct, total) in sorted(
                per_type.items(), key=lambda kv: kv[0].value
            ):
                lines.append(f"  {change_type.value:<10} {correct}/{total}")
        return "\n".join(lines)


def _expected_span(change: DetectedChange) -> tuple[int, int] | None:
    """Which side of a detected change to compare against.

    REMOVED is located in the prior document, everything else in the current
    one, matching how the mutator records its edits.
    """
    if change.change_type is ChangeType.REMOVED:
        return (change.prior_span.start, change.prior_span.end) if change.prior_span else None
    return (change.current_span.start, change.current_span.end) if change.current_span else None


def score_case(case: MutationCase, detected: list[DetectedChange]) -> EvalReport:
    """Match reported changes to known edits and tally the result.

    Matching is greedy on overlap and ignores change type, so a recovered edit
    reported under the wrong type counts as detected but is recorded as a
    classification error. Conflating the two would make a type mistake look
    like a miss.
    """
    report = EvalReport(cases=1)
    unmatched = list(case.expected)
    sections = {
        case.original.key: case.original,
        case.mutated.key: case.mutated,
    }

    for change in detected:
        for span in (change.prior_span, change.current_span):
            if span is None:
                continue
            report.spans_checked += 1
            section = sections.get(f"{span.accession}:{span.section_id.value}")
            if section is not None and span.verify(section):
                report.spans_valid += 1

        bounds = _expected_span(change)
        if bounds is None:
            report.detection.false_positives += 1
            report.spurious.append(change)
            continue

        match = next(
            (e for e in unmatched if e.overlaps(*bounds, min_iou=MATCH_MIN_IOU)),
            None,
        )
        if match is None:
            report.detection.false_positives += 1
            report.spurious.append(change)
            continue

        unmatched.remove(match)
        report.detection.true_positives += 1
        report.confusion.record(match.change_type, change.change_type)

    report.detection.false_negatives += len(unmatched)
    report.missed.extend(unmatched)
    return report


def merge_reports(reports: list[EvalReport]) -> EvalReport:
    total = EvalReport()
    for r in reports:
        total.cases += r.cases
        total.detection.merge(r.detection)
        total.confusion.counts.update(r.confusion.counts)
        total.spans_checked += r.spans_checked
        total.spans_valid += r.spans_valid
        total.missed.extend(r.missed)
        total.spurious.extend(r.spurious)
    return total


def verify_all_spans(
    changes: list[DetectedChange], sections: dict[str, FilingSection]
) -> list[str]:
    """Every span that fails to resolve. Empty means the gate passes."""
    problems: list[str] = []
    for change in changes:
        for label, span in (("prior", change.prior_span), ("current", change.current_span)):
            if span is None:
                continue
            section = sections.get(f"{span.accession}:{span.section_id.value}")
            if section is None:
                problems.append(f"{label} span references unknown section {span.accession}")
            elif not span.verify(section):
                problems.append(
                    f"{label} span [{span.start},{span.end}) in {span.accession} "
                    f"does not match its quote"
                )
    return problems
