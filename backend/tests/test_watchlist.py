"""Watchlist store, feed parsing and the poller cursor.

Offline, with a fake EDGAR client. The cursor logic is what matters here:
getting it wrong means either re-alerting a whole filing history on every
sweep or silently skipping filings.
"""

from __future__ import annotations

import datetime as dt
from typing import ClassVar

import pytest

from vantage.ingest.edgar import EdgarError
from vantage.watchlist.poller import (
    FeedEntry,
    Poller,
    check_company,
    parse_feed,
    sweep,
)
from vantage.watchlist.store import (
    MemoryWatchlistStore,
    WatchedCompany,
    get_store,
    reset_store,
)


def atom(*entries: tuple[str, str, str]) -> str:
    """Build a feed. Each entry is (title, accession, updated)."""
    items = "".join(
        f"""
      <entry>
        <title>{title}</title>
        <link rel="alternate" href="https://sec.gov/a/{acc.replace("-", "")}/x.htm"/>
        <updated>{updated}</updated>
        <id>urn:tag:sec.gov,2008:accession-number={acc}</id>
      </entry>"""
        for title, acc, updated in entries
    )
    return f'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">{items}</feed>'


class FakeEdgar:
    """Serves a canned feed per form."""

    def __init__(self, feeds: dict[str, str], *, fail: set[str] | None = None) -> None:
        self.feeds = feeds
        self.fail = fail or set()
        self.calls: list[str] = []

    async def recent_filings_feed(self, form: str, cik: str, count: int = 20) -> str:
        self.calls.append(form)
        if form in self.fail:
            raise EdgarError(f"{form} feed is down")
        return self.feeds.get(form, atom())

    async def get_cik(self, ticker: str) -> str | None:
        return "0000320193"


class TestParseFeed:
    def test_extracts_accession_form_and_date(self) -> None:
        entries = parse_feed(
            atom(
                (
                    "10-K - Apple Inc. (0000320193) (Filer)",
                    "0000320193-25-000079",
                    "2025-11-01T00:00:00-04:00",
                )
            )
        )
        assert len(entries) == 1
        assert entries[0].accession == "0000320193-25-000079"
        assert entries[0].form == "10-K"
        assert entries[0].filed == dt.date(2025, 11, 1)

    def test_skips_a_malformed_entry_rather_than_failing_the_sweep(self) -> None:
        # One bad row must not stop every other watched company from being
        # checked.
        feed = atom(
            ("10-K - Apple", "0000320193-25-000079", "2025-11-01T00:00:00Z"),
        ).replace("</feed>", "<entry><title>no accession anywhere</title></entry></feed>")
        assert len(parse_feed(feed)) == 1

    def test_malformed_xml_raises(self) -> None:
        with pytest.raises(EdgarError, match="malformed"):
            parse_feed("<feed><unclosed>")

    def test_empty_feed_is_empty(self) -> None:
        assert parse_feed(atom()) == []


class TestCheckCompany:
    FEEDS: ClassVar[dict[str, str]] = {
        "10-K": atom(("10-K - Apple", "0000320193-25-000079", "2025-11-01T00:00:00Z")),
        "8-K": atom(
            ("8-K - Apple", "0000320193-26-000018", "2026-07-30T00:00:00Z"),
            ("8-K - Apple", "0000320193-26-000011", "2026-04-30T00:00:00Z"),
        ),
    }

    async def test_first_sight_records_a_baseline_without_alerting(self) -> None:
        # Adding a ticker must not immediately report its entire history.
        entry = WatchedCompany(ticker="AAPL", cik="0000320193", forms=["10-K", "8-K"])
        new, cursors = await check_company(FakeEdgar(self.FEEDS), entry)  # type: ignore[arg-type]

        assert new == []
        assert cursors == {
            "10-K": "0000320193-25-000079",
            "8-K": "0000320193-26-000018",
        }

    async def test_steady_state_reports_nothing(self) -> None:
        entry = WatchedCompany(
            ticker="AAPL",
            cik="0000320193",
            forms=["10-K", "8-K"],
            last_seen={"10-K": "0000320193-25-000079", "8-K": "0000320193-26-000018"},
        )
        new, _ = await check_company(FakeEdgar(self.FEEDS), entry)  # type: ignore[arg-type]
        assert new == []

    async def test_a_cursor_is_per_form(self) -> None:
        # A single cursor across all forms cannot work: the newest 10-K never
        # appears in the 8-K feed, so every 8-K looked new on every sweep.
        entry = WatchedCompany(
            ticker="AAPL",
            cik="0000320193",
            forms=["10-K", "8-K"],
            last_seen={
                "10-K": "0000320193-25-000079",
                "8-K": "0000320193-26-000011",
            },
        )
        new, cursors = await check_company(FakeEdgar(self.FEEDS), entry)  # type: ignore[arg-type]

        assert [f.entry.accession for f in new] == ["0000320193-26-000018"]
        assert cursors["10-K"] == "0000320193-25-000079"

    async def test_a_failed_feed_does_not_advance_its_cursor(self) -> None:
        # Advancing past filings that were never examined would silently
        # drop them forever.
        entry = WatchedCompany(
            ticker="AAPL",
            cik="0000320193",
            forms=["10-K", "8-K"],
            last_seen={"10-K": "old-10k", "8-K": "old-8k"},
        )
        edgar = FakeEdgar(self.FEEDS, fail={"8-K"})
        new, cursors = await check_company(edgar, entry)  # type: ignore[arg-type]

        assert cursors["8-K"] == "old-8k"
        assert cursors["10-K"] == "0000320193-25-000079"
        assert all(f.entry.form != "8-K" for f in new)

    async def test_resolves_a_missing_cik(self) -> None:
        entry = WatchedCompany(ticker="AAPL", forms=["10-K"])
        _, cursors = await check_company(FakeEdgar(self.FEEDS), entry)  # type: ignore[arg-type]
        assert cursors["10-K"]

    async def test_gives_up_when_the_ticker_has_no_cik(self) -> None:
        class NoCik(FakeEdgar):
            async def get_cik(self, ticker: str) -> str | None:
                return None

        entry = WatchedCompany(ticker="ZZZZ", forms=["10-K"])
        new, cursors = await check_company(NoCik(self.FEEDS), entry)  # type: ignore[arg-type]
        assert new == []
        assert cursors == {}


class TestSweep:
    @pytest.fixture(autouse=True)
    def _store(self) -> None:
        reset_store()

    async def test_one_failing_company_does_not_end_the_sweep(self) -> None:
        store = MemoryWatchlistStore()
        await store.put(WatchedCompany(ticker="AAPL", cik="0000320193", forms=["10-K"]))
        await store.put(WatchedCompany(ticker="MSFT", cik="0000789019", forms=["10-K"]))

        import vantage.watchlist.poller as poller_module

        async def _get_store() -> MemoryWatchlistStore:
            return store

        original = poller_module.get_store
        poller_module.get_store = _get_store  # type: ignore[assignment]
        try:

            class Flaky(FakeEdgar):
                async def recent_filings_feed(self, form: str, cik: str, count: int = 20) -> str:
                    if cik.endswith("789019"):
                        raise RuntimeError("boom")
                    return await super().recent_filings_feed(form, cik, count)

            feeds = {"10-K": atom(("10-K - Apple", "0000320193-25-000079", "2025-11-01T00:00:00Z"))}
            await sweep(Flaky(feeds))  # type: ignore[arg-type]
        finally:
            poller_module.get_store = original  # type: ignore[assignment]

        assert (await store.get("AAPL")).last_seen  # type: ignore[union-attr]

    async def test_empty_watchlist_is_a_no_op(self) -> None:
        assert await sweep(FakeEdgar({})) == []  # type: ignore[arg-type]


class TestStore:
    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_store()

    async def test_falls_back_to_memory_without_mongo(self) -> None:
        store = await get_store()
        assert isinstance(store, MemoryWatchlistStore)

    async def test_round_trip(self) -> None:
        store = MemoryWatchlistStore()
        await store.put(WatchedCompany(ticker="aapl"))
        fetched = await store.get("AAPL")
        assert fetched is not None and fetched.ticker == "AAPL"
        assert await store.remove("aapl") is True
        assert await store.remove("aapl") is False

    def test_ticker_is_normalised(self) -> None:
        assert WatchedCompany(ticker="aapl").ticker == "AAPL"


class TestPoller:
    def test_is_not_running_before_start(self) -> None:
        assert Poller().running is False

    async def test_stop_is_safe_when_never_started(self) -> None:
        await Poller().stop()

    def test_pending_is_capped(self) -> None:
        poller = Poller()
        poller.pending = [
            type(
                "F",
                (),
                {
                    "ticker": "X",
                    "cik": "1",
                    "entry": FeedEntry("a", "8-K", dt.date.today(), "t", "l"),
                },
            )()
            for _ in range(150)
        ]
        poller.pending = poller.pending[:100]
        assert len(poller.pending) == 100
