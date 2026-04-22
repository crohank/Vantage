"""
SEC EDGAR API Client

Fetches 10-K/10-Q filings from SEC EDGAR, extracts key sections.
See: https://www.sec.gov/search#/dateRange=custom
"""

import re
import time
import requests
from typing import Optional, Dict, List
from bs4 import BeautifulSoup


# SEC requires a User-Agent header with company/email
DEFAULT_USER_AGENT = "FinancialAnalystBot research@example.com"

# EDGAR full-text search API
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_FILING_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
SEC_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"


def _get_user_agent() -> str:
    """Get user agent from env or use default."""
    import os
    return os.getenv("SEC_EDGAR_USER_AGENT", DEFAULT_USER_AGENT)


def _get_headers() -> Dict[str, str]:
    return {
        "User-Agent": _get_user_agent(),
        "Accept-Encoding": "gzip, deflate",
    }


def get_cik_for_ticker(ticker: str) -> Optional[str]:
    """
    Look up the CIK number for a given ticker using SEC EDGAR.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")

    Returns:
        CIK number as zero-padded string, or None
    """
    try:
        normalized = ticker.strip().upper()
        # Preferred source: SEC official ticker mapping
        resp = requests.get(SEC_TICKER_MAP_URL, headers=_get_headers(), timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for row in data.values():
                if str(row.get("ticker", "")).upper() == normalized:
                    return str(row.get("cik_str", "")).zfill(10)

        # Fallback: company browse atom feed parser (legacy behavior)
        url = "https://www.sec.gov/cgi-bin/browse-edgar"
        params = {
            "action": "getcompany",
            "company": normalized,
            "CIK": normalized,
            "type": "10-K",
            "dateb": "",
            "owner": "include",
            "count": "1",
            "search_text": "",
            "output": "atom",
        }
        resp = requests.get(url, params=params, headers=_get_headers(), timeout=15)
        if resp.status_code != 200:
            return None

        cik_match = re.search(r"CIK=(\d{10})", resp.text)
        if cik_match:
            return cik_match.group(1)

        return None
    except Exception as e:
        print(f"[SEC EDGAR] Error looking up CIK for {ticker}: {e}")
        return None


def fetch_filing_urls(ticker: str, filing_type: str = "10-K", count: int = 2) -> List[Dict[str, str]]:
    """
    Fetch recent filing URLs for a ticker from EDGAR.

    Args:
        ticker: Stock ticker
        filing_type: Filing type (10-K, 10-Q)
        count: Number of filings to fetch

    Returns:
        List of dicts with keys: url, filing_date, accession_number
    """
    try:
        # Use the EDGAR full-text search
        url = "https://efts.sec.gov/LATEST/search-index"
        params = {
            "q": f'"{ticker}"',
            "dateRange": "custom",
            "startdt": "2022-01-01",
            "enddt": "2026-12-31",
            "forms": filing_type,
        }

        resp = requests.get(url, params=params, headers=_get_headers(), timeout=15)

        # Fallback: use company search API
        if resp.status_code != 200:
            return _fetch_filings_via_company_search(ticker, filing_type, count)

        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])

        filings = []
        for hit in hits[:count]:
            source = hit.get("_source", {})
            accession = source.get("file_num", "")
            filing_date = source.get("file_date", "")
            # Construct filing URL
            filing_url = source.get("file_url", "")
            if filing_url:
                filings.append({
                    "url": f"https://www.sec.gov{filing_url}" if not filing_url.startswith("http") else filing_url,
                    "filing_date": filing_date,
                    "accession_number": accession,
                })

        if not filings:
            return _fetch_filings_via_company_search(ticker, filing_type, count)

        return filings

    except Exception as e:
        print(f"[SEC EDGAR] Error fetching filing URLs: {e}")
        return _fetch_filings_via_company_search(ticker, filing_type, count)


def _fetch_filings_via_company_search(ticker: str, filing_type: str, count: int) -> List[Dict[str, str]]:
    """Fallback: fetch filings via the company search API."""
    try:
        cik = get_cik_for_ticker(ticker)
        if not cik:
            print(f"[SEC EDGAR] Could not find CIK for {ticker}")
            return []

        # Fetch submissions
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        resp = requests.get(url, headers=_get_headers(), timeout=15)
        if resp.status_code != 200:
            return []

        data = resp.json()
        recent = data.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        filings = []
        for i, form in enumerate(forms):
            if form == filing_type and len(filings) < count:
                acc_clean = accessions[i].replace("-", "")
                doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{acc_clean}/{primary_docs[i]}"
                filings.append({
                    "url": doc_url,
                    "filing_date": dates[i],
                    "accession_number": accessions[i],
                })

        # Rate limit: SEC requires max 10 requests/second
        time.sleep(0.15)
        return filings

    except Exception as e:
        print(f"[SEC EDGAR] Fallback search error: {e}")
        return []


def download_filing(url: str) -> Optional[str]:
    """
    Download a filing and extract text content.

    Args:
        url: URL to the filing document

    Returns:
        Plain text content of the filing, or None on error
    """
    try:
        resp = requests.get(url, headers=_get_headers(), timeout=30)
        if resp.status_code != 200:
            print(f"[SEC EDGAR] Failed to download filing: HTTP {resp.status_code}")
            return None

        content_type = resp.headers.get("Content-Type", "")

        if "html" in content_type or url.endswith(".htm") or url.endswith(".html"):
            soup = BeautifulSoup(resp.text, "html.parser")
            # Remove script/style elements
            for element in soup(["script", "style", "meta", "link"]):
                element.decompose()
            text = soup.get_text(separator="\n")
        else:
            text = resp.text

        # Clean up excessive whitespace
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(line for line in lines if line)

        # Rate limit
        time.sleep(0.15)
        return text

    except Exception as e:
        print(f"[SEC EDGAR] Error downloading filing: {e}")
        return None


def extract_sections(filing_text: str) -> Dict[str, str]:
    """
    Extract key sections from a 10-K filing using regex-based section detection.

    Sections extracted:
    - risk_factors: Item 1A (Risk Factors)
    - mda: Item 7 (Management's Discussion and Analysis)
    - business: Item 1 (Business description)

    Args:
        filing_text: Full text of the filing

    Returns:
        Dict mapping section names to their text content
    """
    sections = {}

    # Section patterns for 10-K
    section_patterns = {
        "risk_factors": [
            r"(?i)item\s+1a[\.\s\-—]+risk\s+factors(.*?)(?=item\s+1b|item\s+2)",
            r"(?i)risk\s+factors\s*\n(.*?)(?=item\s+1b|item\s+2|quantitative\s+and\s+qualitative)",
        ],
        "mda": [
            r"(?i)item\s+7[\.\s\-—]+management.?s?\s+discussion\s+and\s+analysis(.*?)(?=item\s+7a|item\s+8)",
            r"(?i)management.?s?\s+discussion\s+and\s+analysis(.*?)(?=item\s+7a|item\s+8|financial\s+statements)",
        ],
        "business": [
            r"(?i)item\s+1[\.\s\-—]+business(.*?)(?=item\s+1a|item\s+2)",
            r"(?i)(?:^|\n)business\s*\n(.*?)(?=item\s+1a|risk\s+factors)",
        ],
    }

    for section_name, patterns in section_patterns.items():
        for pattern in patterns:
            match = re.search(pattern, filing_text, re.DOTALL)
            if match:
                text = match.group(1).strip()
                # Truncate to ~5000 chars to keep chunks manageable
                if len(text) > 5000:
                    text = text[:5000] + "\n...[truncated]"
                sections[section_name] = text
                break

    return sections
