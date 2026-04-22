"""
Query Resolver Service

Resolves natural language queries to stock ticker symbols using Gemini LLM.
Supports direct ticker input (passthrough) and free-text queries.
"""

import re
import json
from typing import Optional, Dict, Any
from services.llm_service import get_gemini_service


# Common company name → ticker mappings for fast resolution without LLM
KNOWN_COMPANIES = {
    "apple": "AAPL",
    "microsoft": "MSFT",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "tesla": "TSLA",
    "meta": "META",
    "facebook": "META",
    "nvidia": "NVDA",
    "netflix": "NFLX",
    "amd": "AMD",
    "intel": "INTC",
    "disney": "DIS",
    "walmart": "WMT",
    "jpmorgan": "JPM",
    "goldman sachs": "GS",
    "bank of america": "BAC",
    "coca cola": "KO",
    "coca-cola": "KO",
    "pepsi": "PEP",
    "pepsico": "PEP",
    "boeing": "BA",
    "palantir": "PLTR",
    "uber": "UBER",
    "airbnb": "ABNB",
    "spotify": "SPOT",
    "snowflake": "SNOW",
    "salesforce": "CRM",
    "oracle": "ORCL",
    "ibm": "IBM",
    "adobe": "ADBE",
    "paypal": "PYPL",
    "shopify": "SHOP",
    "coinbase": "COIN",
    "robinhood": "HOOD",
    "berkshire hathaway": "BRK-B",
    "johnson & johnson": "JNJ",
    "procter & gamble": "PG",
    "exxon": "XOM",
    "chevron": "CVX",
}


def is_likely_ticker(input_text: str) -> bool:
    """
    Check if the input looks like a direct stock ticker symbol.
    Tickers are 1-5 uppercase alphanumeric characters, optionally with a hyphen (e.g., BRK-B).
    """
    return bool(re.match(r'^[A-Z]{1,5}(-[A-Z]{1,2})?$', input_text.strip()))


def try_known_company(query: str) -> Optional[str]:
    """
    Try to resolve a company name from the known mappings without calling LLM.
    """
    query_lower = query.lower().strip()

    # Direct lookup
    if query_lower in KNOWN_COMPANIES:
        return KNOWN_COMPANIES[query_lower]

    # Check if any known company name appears in the query
    for company, ticker in KNOWN_COMPANIES.items():
        if company in query_lower:
            return ticker

    return None


def resolve_query(query: str) -> Dict[str, Any]:
    """
    Resolve a natural language query to a stock ticker and optional parameters.

    Args:
        query: User input — either a ticker symbol or natural language query.

    Returns:
        Dict with keys:
        - ticker: Resolved stock ticker (str or None)
        - horizon: Inferred time horizon (str or None)
        - risk_profile: Inferred risk profile (str or None)
        - original_query: The original query text
        - resolved: Whether LLM resolution was used
        - confidence: Confidence score (0.0-1.0)
        - error: Error message if resolution failed
    """
    query = query.strip()

    if not query:
        return {
            "ticker": None,
            "original_query": query,
            "resolved": False,
            "confidence": 0.0,
            "error": "Empty query"
        }

    # If it already looks like a ticker, pass through directly
    upper_query = query.upper()
    if is_likely_ticker(upper_query):
        return {
            "ticker": upper_query,
            "original_query": query,
            "resolved": False,
            "confidence": 1.0,
        }

    # Try known company mappings first (no LLM call needed)
    known_ticker = try_known_company(query)
    if known_ticker:
        return {
            "ticker": known_ticker,
            "original_query": query,
            "resolved": True,
            "confidence": 0.95,
        }

    # Use Gemini to resolve the query
    return _resolve_with_llm(query)


def _resolve_with_llm(query: str) -> Dict[str, Any]:
    """
    Use Gemini LLM to extract ticker and parameters from a natural language query.
    """
    prompt = f"""You are a financial query parser. Extract the stock ticker symbol and optional parameters from the user's query.

User query: "{query}"

Return ONLY valid JSON with this exact structure:
{{
    "ticker": "AAPL",
    "horizon": null,
    "risk_profile": null,
    "confidence": 0.9
}}

Rules:
- "ticker": The US stock ticker symbol (uppercase, 1-5 chars). Return null if you cannot determine a specific stock.
- "horizon": If the user mentions a time frame, map it: "short" (days-weeks), "medium" (months), "long" (years). Otherwise null.
- "risk_profile": If the user mentions risk preference, map it: "conservative", "moderate", "aggressive". Otherwise null.
- "confidence": How confident you are in the ticker resolution (0.0-1.0).

If the query mentions a well-known company, resolve it to its ticker (e.g., "Apple" → "AAPL", "Tesla" → "TSLA").
If the query is ambiguous or doesn't reference a specific stock, set ticker to null.

Return ONLY the JSON, no explanation."""

    try:
        gemini = get_gemini_service()
        result = gemini.invoke_json(prompt, temperature=0.1)

        ticker = result.get("ticker")
        if ticker:
            ticker = ticker.upper().strip()
            # Validate ticker format
            if not re.match(r'^[A-Z]{1,5}(-[A-Z]{1,2})?$', ticker):
                ticker = None

        return {
            "ticker": ticker,
            "horizon": result.get("horizon"),
            "risk_profile": result.get("risk_profile"),
            "original_query": query,
            "resolved": True,
            "confidence": result.get("confidence", 0.5),
            "error": None if ticker else "Could not determine a stock ticker from the query"
        }

    except Exception as e:
        print(f"[Query Resolver] LLM resolution failed: {e}")
        return {
            "ticker": None,
            "original_query": query,
            "resolved": False,
            "confidence": 0.0,
            "error": f"Query resolution failed: {str(e)}"
        }
