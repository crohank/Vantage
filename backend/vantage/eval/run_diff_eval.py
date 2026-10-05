"""The PR gate.

Runs the diff engine against synthetically mutated real filing sections and
fails the build when detection or citation validity regresses. No LLM, no
judge, no network when a cached corpus is present, so it is cheap enough to
run on every pull request.

    python -m vantage.eval.run_diff_eval --corpus eval_corpus
    python -m vantage.eval.run_diff_eval --refresh --tickers AAPL MSFT

Thresholds live in `thresholds.json` next to this module so a deliberate
change to them shows up in review as its own diff.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from vantage.domain.filing import Filing, FilingSection, Form, SectionId
from vantage.engines.diff import diff_sections
from vantage.eval.metrics import EvalReport, merge_reports, score_case
from vantage.eval.mutate import mutate_section
from vantage.ingest.edgar import EdgarClient
from vantage.ingest.parser import extract_sections

log = logging.getLogger(__name__)

DEFAULT_CORPUS = Path(__file__).resolve().parent / "corpus"
THRESHOLDS_FILE = Path(__file__).resolve().parent / "thresholds.json"

# Sections large enough to mutate meaningfully. Item 1B is one word in
# practice and Properties is a paragraph.
EVAL_SECTIONS = (
    SectionId.RISK_FACTORS,
    SectionId.MDA,
    SectionId.BUSINESS,
    SectionId.LEGAL_PROCEEDINGS,
)

DEFAULT_TICKERS = ("AAPL", "MSFT", "NVDA", "JPM", "XOM", "PFE")

# Several seeds per section, so a score is not one lucky arrangement of edits.
SEEDS = (11, 23, 37, 59)


@dataclass(frozen=True)
class Thresholds:
    min_precision: float
    min_recall: float
    min_classification_accuracy: float
    min_citation_validity: float

    @classmethod
    def load(cls) -> Thresholds:
        if not THRESHOLDS_FILE.exists():
            # Conservative defaults on first run. Tighten them once a real
            # baseline exists rather than guessing high and disabling the gate.
            return cls(0.80, 0.80, 0.85, 1.0)
        data = json.loads(THRESHOLDS_FILE.read_text(encoding="utf-8"))
        return cls(
            min_precision=float(data["min_precision"]),
            min_recall=float(data["min_recall"]),
            min_classification_accuracy=float(data["min_classification_accuracy"]),
            min_citation_validity=float(data["min_citation_validity"]),
        )


async def refresh_corpus(tickers: tuple[str, ...], corpus: Path) -> None:
    """Cache one recent 10-K per ticker.

    Committed filings would add megabytes to the repository, so CI restores
    this from cache and refreshes it on a schedule instead.
    """
    await asyncio.to_thread(corpus.mkdir, parents=True, exist_ok=True)
    async with EdgarClient() as edgar:
        for ticker in tickers:
            filings = await edgar.list_filings(ticker, Form.TEN_K, limit=1)
            if not filings:
                log.warning("no 10-K for %s", ticker)
                continue
            filing = filings[0]
            raw = await edgar.fetch_document(filing.primary_doc_url)
            await asyncio.to_thread((corpus / f"{ticker}_{filing.accession}.htm").write_bytes, raw)
            meta = {
                "ticker": ticker,
                "accession": filing.accession,
                "cik": filing.cik,
                "filing_date": filing.filing_date.isoformat(),
            }
            await asyncio.to_thread(
                (corpus / f"{ticker}_{filing.accession}.json").write_text,
                json.dumps(meta),
                encoding="utf-8",
            )
            print(f"cached {ticker} {filing.accession} ({len(raw):,} bytes)")


def load_corpus(corpus: Path) -> list[tuple[str, list[FilingSection]]]:
    cases: list[tuple[str, list[FilingSection]]] = []
    for meta_path in sorted(corpus.glob("*.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        html = meta_path.with_suffix(".htm")
        if not html.exists():
            continue
        filing = Filing(
            accession=meta["accession"],
            cik=meta["cik"],
            ticker=meta["ticker"],
            form=Form.TEN_K,
            filing_date=date.fromisoformat(meta["filing_date"]),
            primary_doc_url="cached",
        )
        cases.append((meta["ticker"], extract_sections(filing, html.read_bytes())))
    return cases


def run(corpus: Path) -> EvalReport:
    documents = load_corpus(corpus)
    if not documents:
        raise SystemExit(f"no corpus in {corpus}. Run with --refresh to download one.")

    reports: list[EvalReport] = []
    skipped = 0
    for ticker, sections in documents:
        by_id = {s.section_id: s for s in sections}
        for section_id in EVAL_SECTIONS:
            section = by_id.get(section_id)
            if section is None:
                continue
            for seed in SEEDS:
                try:
                    case = mutate_section(section, seed=seed)
                except ValueError:
                    # Too few substantial paragraphs to mutate reliably.
                    skipped += 1
                    continue
                detected = diff_sections(case.original, case.mutated)
                reports.append(score_case(case, detected))
        log.info("scored %s", ticker)

    if skipped:
        print(f"note: skipped {skipped} section/seed pairs as too small to mutate\n")
    return merge_reports(reports)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic diff-engine gate")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--refresh", action="store_true", help="download filings first")
    parser.add_argument("--tickers", nargs="*", default=list(DEFAULT_TICKERS))
    parser.add_argument("--write-baseline", action="store_true", help="record current scores")
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="also write the scores here, for the metrics dashboard",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    if args.refresh:
        asyncio.run(refresh_corpus(tuple(args.tickers), args.corpus))

    report = run(args.corpus)
    print(report.render())

    if args.write_baseline:
        # Deliberately floors the observed scores rather than recording them
        # exactly, so ordinary run-to-run variation does not fail the gate.
        payload = {
            "min_precision": round(max(0.0, report.detection.precision - 0.05), 3),
            "min_recall": round(max(0.0, report.detection.recall - 0.05), 3),
            "min_classification_accuracy": round(max(0.0, report.confusion.accuracy - 0.05), 3),
            "min_citation_validity": 1.0,
        }
        THRESHOLDS_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote thresholds to {THRESHOLDS_FILE}")
        return 0

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report.as_dict(), indent=2) + chr(10), encoding="utf-8")
        print(f"wrote scores to {args.json}")

    thresholds = Thresholds.load()
    failures: list[str] = []
    if report.detection.precision < thresholds.min_precision:
        failures.append(f"precision {report.detection.precision:.3f} < {thresholds.min_precision}")
    if report.detection.recall < thresholds.min_recall:
        failures.append(f"recall {report.detection.recall:.3f} < {thresholds.min_recall}")
    if report.confusion.accuracy < thresholds.min_classification_accuracy:
        failures.append(
            f"classification {report.confusion.accuracy:.3f} < "
            f"{thresholds.min_classification_accuracy}"
        )
    if report.citation_validity < thresholds.min_citation_validity:
        # This one is a correctness gate, not a quality score. A finding that
        # cannot cite its source verbatim is a bug.
        failures.append(
            f"citation validity {report.citation_validity:.4f} < {thresholds.min_citation_validity}"
        )

    if failures:
        print("\nFAILED")
        for failure in failures:
            print(f"  {failure}")
        if report.missed:
            print(f"\n  {len(report.missed)} missed edits, first 3:")
            for miss in report.missed[:3]:
                print(f"    [{miss.change_type.value}] {miss.text[:90]}")
        return 1

    print("\nPASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
