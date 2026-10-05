"""EDGAR filing poller.

The trigger that makes this a product rather than a query tool: a filing
lands, the pipeline runs against it, and the result is a digest of what
changed. EDGAR publishes an Atom feed per company and form, updated as
filings are accepted, which costs nothing and needs no key.

Polling rather than webhooks because EDGAR offers no push.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, date, datetime

from vantage.domain.filing import normalize_cik
from vantage.ingest.edgar import EdgarClient, EdgarError
from vantage.watchlist.store import WatchedCompany, get_store

log = logging.getLogger(__name__)

ATOM = "{http://www.w3.org/2005/Atom}"

# EDGAR asks for no more than 10 requests/second overall. The client's rate
# limiter enforces that; this is the gap between full sweeps. Filings are
# accepted during business hours and a digest is not a trading signal, so
# fifteen minutes is ample and keeps the free tier comfortable.
DEFAULT_INTERVAL_SECONDS = 900


@dataclass(frozen=True)
class FeedEntry:
    """One filing from the Atom feed."""

    accession: str
    form: str
    filed: date
    title: str
    link: str


def parse_feed(xml: str) -> list[FeedEntry]:
    """Pull filings out of an EDGAR Atom feed.

    Tolerant by design: a single malformed entry is skipped rather than
    failing the sweep, because one bad row must not stop every other watched
    company from being checked.
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise EdgarError(f"malformed Atom feed: {exc}") from exc

    entries: list[FeedEntry] = []
    for node in root.findall(f"{ATOM}entry"):
        try:
            title = (node.findtext(f"{ATOM}title") or "").strip()
            link_node = node.find(f"{ATOM}link")
            link = link_node.get("href", "") if link_node is not None else ""
            updated = (node.findtext(f"{ATOM}updated") or "").strip()

            accession = _accession_from(link) or _accession_from(node.findtext(f"{ATOM}id") or "")
            if not accession:
                continue

            # Title is "FORM - Company (CIK) (Filer)".
            form = title.split(" - ", 1)[0].strip() if " - " in title else ""
            filed = (
                datetime.fromisoformat(updated.replace("Z", "+00:00")).date()
                if updated
                else datetime.now(UTC).date()
            )
            entries.append(
                FeedEntry(accession=accession, form=form, filed=filed, title=title, link=link)
            )
        except (ValueError, AttributeError) as exc:
            log.debug("skipping malformed feed entry: %s", exc)
            continue
    return entries


def _accession_from(text: str) -> str:
    """Accession numbers appear undashed in EDGAR paths and ids."""
    import re

    match = re.search(r"(\d{10})-?(\d{2})-?(\d{6})", text)
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else ""


@dataclass(frozen=True)
class NewFiling:
    """A filing worth acting on, for one watched company."""

    ticker: str
    cik: str
    entry: FeedEntry


async def check_company(
    client: EdgarClient, entry: WatchedCompany
) -> tuple[list[NewFiling], dict[str, str]]:
    """Filings accepted for this company since it was last checked.

    Returns the new filings and the updated per-form cursor.

    A form with no cursor yet is being seen for the first time, so its newest
    filing becomes the baseline and nothing is emitted. Alerting on a whole
    filing history the moment a ticker is added is noise.
    """
    cik = entry.cik
    if cik is None:
        resolved = await client.get_cik(entry.ticker)
        if resolved is None:
            log.warning("cannot resolve a CIK for %s, skipping", entry.ticker)
            return [], entry.last_seen
        cik = resolved

    normalized = normalize_cik(cik)
    new: list[NewFiling] = []
    cursors = dict(entry.last_seen)

    for form in entry.forms:
        try:
            xml = await client.recent_filings_feed(form=form, cik=normalized, count=20)
        except EdgarError as exc:
            # One form failing must not stop the others, and must not advance
            # a cursor past filings that were never examined.
            log.warning("feed for %s %s failed: %s", entry.ticker, form, exc)
            continue

        found = parse_feed(xml)
        if not found:
            continue
        found.sort(key=lambda e: e.filed, reverse=True)

        seen = cursors.get(form)
        if seen is not None:
            for item in found:
                if item.accession == seen:
                    break
                new.append(NewFiling(ticker=entry.ticker, cik=normalized, entry=item))

        cursors[form] = found[0].accession

    return new, cursors


async def sweep(client: EdgarClient) -> list[NewFiling]:
    """Check every watched company once and advance each cursor."""
    store = await get_store()
    watched = await store.list()
    if not watched:
        return []

    new: list[NewFiling] = []
    for entry in watched:
        try:
            found, cursors = await check_company(client, entry)
        except Exception as exc:
            # One company's failure must not end the sweep for the rest.
            log.warning("sweep failed for %s: %s", entry.ticker, exc)
            continue

        new.extend(found)

        cik = entry.cik or await client.get_cik(entry.ticker)
        await store.put(
            entry.model_copy(
                update={
                    "cik": normalize_cik(cik) if cik else None,
                    "last_seen": cursors,
                    "last_checked_at": datetime.now(UTC),
                }
            )
        )

    return new


class Poller:
    """Background sweep loop."""

    def __init__(self, interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> None:
        self.interval = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self.last_sweep_at: datetime | None = None
        self.last_error: str | None = None
        # Newest first, capped. This is a notification buffer, not a record;
        # the analyses themselves are the durable artefact.
        self.pending: list[NewFiling] = []

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.running:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def run_once(self) -> list[NewFiling]:
        async with EdgarClient() as client:
            found = await sweep(client)
        self.last_sweep_at = datetime.now(UTC)
        self.pending = (found + self.pending)[:100]
        return found

    async def _loop(self) -> None:
        while True:
            try:
                found = await self.run_once()
                self.last_error = None
                if found:
                    log.info("sweep found %d new filing(s)", len(found))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                log.exception("sweep failed")
            await asyncio.sleep(self.interval)


_poller: Poller | None = None


def get_poller() -> Poller:
    global _poller
    if _poller is None:
        _poller = Poller()
    return _poller


def reset_poller() -> None:
    global _poller
    _poller = None
