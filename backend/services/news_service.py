"""News provider integration for company-related articles."""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

GNEWS_API_KEY = os.getenv("GNEWS_API_KEY", "").strip()
GNEWS_BASE_URL = "https://gnews.io/api/v4/search"


def is_configured() -> bool:
    return bool(GNEWS_API_KEY)


def _to_iso8601(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return value


def fetch_company_news(
    ticker: str,
    company_name: Optional[str] = None,
    max_articles: int = 10,
    lookback_days: int = 7,
) -> Dict[str, Any]:
    """Fetch recent company news from GNews."""
    if not is_configured():
        return {
            "provider": "gnews",
            "available": False,
            "error": "GNEWS_API_KEY not configured",
            "articles": [],
            "query": "",
        }

    query_terms = [ticker.upper()]
    if company_name:
        query_terms.insert(0, f'"{company_name}"')
    query = " OR ".join(query_terms)
    from_date = (datetime.now(timezone.utc) - timedelta(days=max(1, lookback_days))).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        response = requests.get(
            GNEWS_BASE_URL,
            params={
                "q": query,
                "lang": "en",
                "max": max(1, min(max_articles, 10)),
                "from": from_date,
                "apikey": GNEWS_API_KEY,
                "expand": "content",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        return {
            "provider": "gnews",
            "available": False,
            "error": str(exc),
            "articles": [],
            "query": query,
        }

    normalized_articles: List[Dict[str, Any]] = []
    for idx, article in enumerate(payload.get("articles", []), start=1):
        normalized_articles.append({
            "id": f"{ticker.upper()}-gnews-{idx}",
            "title": article.get("title", "").strip(),
            "description": article.get("description", "").strip(),
            "content": article.get("content", "").strip(),
            "url": article.get("url", "").strip(),
            "image": article.get("image", "").strip(),
            "published_at": _to_iso8601(article.get("publishedAt", "")),
            "source_name": ((article.get("source") or {}).get("name") or "").strip(),
            "source_url": ((article.get("source") or {}).get("url") or "").strip(),
        })

    return {
        "provider": "gnews",
        "available": True,
        "error": None,
        "articles": normalized_articles,
        "query": query,
        "total_articles": payload.get("totalArticles", len(normalized_articles)),
    }
