"""Async SEC EDGAR client.

Everything here is free and needs no API key. SEC asks for two things in
return: a User-Agent carrying a real contact address, and no more than 10
requests per second. Both are enforced here rather than left to callers,
because exceeding the rate limit gets the IP blocked for ~10 minutes.

Replaces the previous sync client, which re-downloaded the entire
company_tickers.json (about 1 MB) on every CIK lookup and slept 0.15s *after*
each request instead of pacing before it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from vantage.config import get_settings
from vantage.domain.filing import Company, Filing, Form, normalize_accession, normalize_cik

log = logging.getLogger(__name__)

EFTS_SEARCH = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
TICKER_MAP = "https://www.sec.gov/files/company_tickers.json"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{adsh_nodash}/{filename}"
BROWSE_RSS = "https://www.sec.gov/cgi-bin/browse-edgar"

# SEC publishes 10 req/sec. Staying meaningfully under it costs little and
# a block costs ten minutes.
_MAX_REQUESTS_PER_SECOND = 8


class RateLimiter:
    """Token bucket shared by every EdgarClient in the process.

    Paces *before* the request. The old code slept afterwards, which does not
    bound the rate when calls are concurrent.
    """

    def __init__(self, rate_per_second: int = _MAX_REQUESTS_PER_SECOND) -> None:
        self._min_interval = 1.0 / rate_per_second
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._next_allowed - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            self._next_allowed = now + self._min_interval


_limiter = RateLimiter()


class EdgarError(RuntimeError):
    pass


class EdgarRateLimited(EdgarError):
    """SEC returned 429 or 403. Both mean back off."""


class EdgarClient:
    """Async EDGAR access. Use as a context manager."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        settings = get_settings()
        self._headers = {
            "User-Agent": settings.sec_user_agent,
            "Accept-Encoding": "gzip, deflate",
        }
        self._client: httpx.AsyncClient | None = None
        self._cache_dir = cache_dir or (Path(settings.fastembed_cache_path or ".cache") / "edgar")
        self._ticker_map: dict[str, Company] | None = None

    async def __aenter__(self) -> EdgarClient:
        self._client = httpx.AsyncClient(
            headers=self._headers,
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("EdgarClient must be used as an async context manager")
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, EdgarRateLimited)),
        wait=wait_exponential_jitter(initial=1, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def _get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        await _limiter.acquire()
        resp = await self._http.get(url, params=params)
        if resp.status_code in (403, 429):
            raise EdgarRateLimited(f"{resp.status_code} from {url}. Check the User-Agent contact.")
        return resp

    # ---------------------------------------------------------------- tickers

    async def _load_ticker_map(self) -> dict[str, Company]:
        """Ticker to Company, cached in memory and on disk for a day."""
        if self._ticker_map is not None:
            return self._ticker_map

        cache_file = self._cache_dir / "company_tickers.json"
        raw: dict[str, Any] | None = None
        if cache_file.exists() and (time.time() - cache_file.stat().st_mtime) < 86_400:
            try:
                raw = json.loads(cache_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = None

        if raw is None:
            resp = await self._get(TICKER_MAP)
            resp.raise_for_status()
            raw = resp.json()
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(raw), encoding="utf-8")

        mapping: dict[str, Company] = {}
        for row in raw.values():
            ticker = str(row.get("ticker", "")).upper()
            if not ticker:
                continue
            mapping[ticker] = Company(
                cik=normalize_cik(row.get("cik_str", "")),
                ticker=ticker,
                name=str(row.get("title", "")),
            )
        self._ticker_map = mapping
        return mapping

    async def get_company(self, ticker: str) -> Company | None:
        return (await self._load_ticker_map()).get(ticker.strip().upper())

    async def get_cik(self, ticker: str) -> str | None:
        company = await self.get_company(ticker)
        return company.cik if company else None

    # ------------------------------------------------------------- submissions

    async def get_company_profile(self, cik: str) -> Company | None:
        """Company detail including SIC, which the peer engine needs."""
        resp = await self._get(SUBMISSIONS.format(cik=normalize_cik(cik)))
        if resp.status_code != 200:
            return None
        d = resp.json()
        tickers = d.get("tickers") or [""]
        return Company(
            cik=normalize_cik(d.get("cik", cik)),
            ticker=str(tickers[0] or "").upper() or "UNKNOWN",
            name=str(d.get("name", "")),
            sic=str(d.get("sic")) if d.get("sic") else None,
            sic_description=d.get("sicDescription"),
        )

    async def list_filings(
        self,
        ticker: str,
        form: Form = Form.TEN_K,
        limit: int = 6,
    ) -> list[Filing]:
        """Recent filings of one form, newest first.

        Reads the submissions API, which is the authoritative per-filer index.
        `recent` covers roughly the last 1,000 filings; older ones live in the
        paginated `files` shards, which are followed when `recent` runs out.
        """
        company = await self.get_company(ticker)
        if company is None:
            log.warning("no CIK for ticker %s", ticker)
            return []

        resp = await self._get(SUBMISSIONS.format(cik=company.cik))
        if resp.status_code != 200:
            raise EdgarError(f"submissions returned {resp.status_code} for {ticker}")
        payload = resp.json()

        filings = self._filings_from_block(
            payload.get("filings", {}).get("recent", {}), company, form, limit
        )
        if len(filings) >= limit:
            return filings[:limit]

        # Older filings live in separate shards.
        for shard in payload.get("filings", {}).get("files", []):
            name = shard.get("name")
            if not name:
                continue
            shard_resp = await self._get(f"https://data.sec.gov/submissions/{name}")
            if shard_resp.status_code != 200:
                continue
            filings.extend(
                self._filings_from_block(shard_resp.json(), company, form, limit - len(filings))
            )
            if len(filings) >= limit:
                break

        return filings[:limit]

    @staticmethod
    def _filings_from_block(
        block: dict[str, Any], company: Company, form: Form, limit: int
    ) -> list[Filing]:
        forms = block.get("form", [])
        dates = block.get("filingDate", [])
        accessions = block.get("accessionNumber", [])
        primaries = block.get("primaryDocument", [])
        periods = block.get("reportDate", [])

        out: list[Filing] = []
        for i, f in enumerate(forms):
            if len(out) >= limit:
                break
            # Exact match only. "10-K/A" is an amendment and diffing an
            # amendment against an original produces noise.
            if f != form.value:
                continue
            try:
                accession = normalize_accession(accessions[i])
            except (ValueError, IndexError):
                continue
            period_raw = periods[i] if i < len(periods) else ""
            out.append(
                Filing(
                    accession=accession,
                    cik=company.cik,
                    ticker=company.ticker,
                    form=form,
                    filing_date=date.fromisoformat(dates[i]),
                    period_of_report=date.fromisoformat(period_raw) if period_raw else None,
                    primary_doc_url=ARCHIVES.format(
                        cik_int=int(company.cik),
                        adsh_nodash=accession.replace("-", ""),
                        filename=primaries[i],
                    ),
                )
            )
        return out

    # ---------------------------------------------------------------- document

    async def fetch_document(self, url: str) -> bytes:
        """Raw document bytes. Parsing happens in ingest.parser.

        Deliberately bytes, not `.text`. Filings declare their charset in a
        meta tag and httpx's guess is sometimes wrong, which shows up as
        mojibake in apostrophes. lxml reads the declaration itself.
        """
        resp = await self._get(url)
        if resp.status_code != 200:
            raise EdgarError(f"document fetch returned {resp.status_code} for {url}")
        return resp.content

    # ------------------------------------------------------------ full text

    async def full_text_search(
        self,
        phrase: str,
        forms: str | None = None,
        start: date | None = None,
        end: date | None = None,
        ciks: list[str] | None = None,
        limit: int = 10,
    ) -> FullTextResult:
        """Exact-phrase search across all filings, 2001 to present.

        This powers the novelty and peer engines. It is also the endpoint the
        old code called with response field names that do not exist: it read
        `_source.file_num` as the accession (it is a list of SEC file numbers)
        and `_source.file_url` (absent entirely), so every call silently fell
        through to the per-company path.
        """
        params: dict[str, Any] = {"q": f'"{phrase}"'}
        if forms:
            params["forms"] = forms
        if start and end:
            params["dateRange"] = "custom"
            params["startdt"] = start.isoformat()
            params["enddt"] = end.isoformat()
        if ciks:
            params["ciks"] = ",".join(normalize_cik(c) for c in ciks)

        resp = await self._get(EFTS_SEARCH, params=params)
        if resp.status_code != 200:
            raise EdgarError(f"full-text search returned {resp.status_code}")
        payload = resp.json()

        hits_block = payload.get("hits", {})
        total = hits_block.get("total", {}).get("value", 0)
        hits: list[FullTextHit] = []
        for raw in hits_block.get("hits", [])[:limit]:
            hit = FullTextHit.from_efts(raw)
            if hit is not None:
                hits.append(hit)
        return FullTextResult(phrase=phrase, total=total, hits=hits)

    # ----------------------------------------------------------------- XBRL

    async def company_facts(self, cik: str) -> dict[str, Any]:
        """Structured XBRL facts, used to check narrative claims against
        reported numbers instead of trusting an LLM's paraphrase."""
        resp = await self._get(COMPANY_FACTS.format(cik=normalize_cik(cik)))
        if resp.status_code == 404:
            return {}
        if resp.status_code != 200:
            raise EdgarError(f"company facts returned {resp.status_code} for {cik}")
        return dict(resp.json())

    # ------------------------------------------------------------------ RSS

    async def recent_filings_feed(
        self,
        form: str = "10-Q",
        cik: str | None = None,
        count: int = 40,
    ) -> str:
        """Atom feed of recently accepted filings. The watchlist trigger.

        Returned as raw XML so the caller can parse with feedparser without
        this module taking that dependency.
        """
        params: dict[str, Any] = {
            "action": "getcurrent" if cik is None else "getcompany",
            "type": form,
            "count": count,
            "output": "atom",
        }
        if cik is not None:
            params["CIK"] = normalize_cik(cik)
            params["dateb"] = ""
            params["owner"] = "include"
        resp = await self._get(BROWSE_RSS, params=params)
        if resp.status_code != 200:
            raise EdgarError(f"RSS feed returned {resp.status_code}")
        return resp.text


class FullTextHit:
    """One EFTS hit, decoded from the response shape SEC actually returns."""

    __slots__ = ("accession", "ciks", "display_name", "filename", "filing_date", "form", "sics")

    def __init__(
        self,
        accession: str,
        ciks: list[str],
        filename: str,
        filing_date: date,
        form: str,
        display_name: str,
        sics: list[str],
    ) -> None:
        self.accession = accession
        self.ciks = ciks
        self.filename = filename
        self.filing_date = filing_date
        self.form = form
        self.display_name = display_name
        self.sics = sics

    @classmethod
    def from_efts(cls, raw: dict[str, Any]) -> FullTextHit | None:
        source = raw.get("_source", {})
        # _id is "{accession}:{primary filename}". There is no URL field, so
        # the document location has to be rebuilt from these two parts.
        raw_id = str(raw.get("_id", ""))
        if ":" not in raw_id:
            return None
        adsh_part, filename = raw_id.split(":", 1)
        try:
            accession = normalize_accession(source.get("adsh") or adsh_part)
            filing_date = date.fromisoformat(source["file_date"])
        except (ValueError, KeyError, TypeError):
            return None
        return cls(
            accession=accession,
            ciks=[normalize_cik(c) for c in source.get("ciks", [])],
            filename=filename,
            filing_date=filing_date,
            form=str(source.get("form", "")),
            display_name=(source.get("display_names") or [""])[0],
            sics=[str(s) for s in source.get("sics", [])],
        )

    @property
    def document_url(self) -> str:
        cik_int = int(self.ciks[0]) if self.ciks else 0
        return ARCHIVES.format(
            cik_int=cik_int,
            adsh_nodash=self.accession.replace("-", ""),
            filename=self.filename,
        )

    def __repr__(self) -> str:
        return f"FullTextHit({self.accession} {self.form} {self.filing_date} {self.display_name!r})"


class FullTextResult:
    __slots__ = ("hits", "phrase", "total")

    def __init__(self, phrase: str, total: int, hits: list[FullTextHit]) -> None:
        self.phrase = phrase
        # Corpus-wide match count, independent of how many hits were returned.
        # The novelty engine reads this, not len(hits).
        self.total = total
        self.hits = hits

    @property
    def earliest(self) -> FullTextHit | None:
        return min(self.hits, key=lambda h: h.filing_date) if self.hits else None

    def __repr__(self) -> str:
        return f"FullTextResult({self.phrase!r}, total={self.total}, returned={len(self.hits)})"
