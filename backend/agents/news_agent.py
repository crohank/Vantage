"""News agent for price-impacting company article analysis."""

import time
from typing import Any, Dict, List

from schemas.state import ResearchState


def _build_article_prompt_context(articles: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for idx, article in enumerate(articles, start=1):
        lines.append(
            f"{idx}. Title: {article.get('title', '')}\n"
            f"   Source: {article.get('source_name', '')}\n"
            f"   Published: {article.get('published_at', '')}\n"
            f"   Description: {article.get('description', '')}\n"
            f"   Content: {article.get('content', '')}"
        )
    return "\n\n".join(lines)


def _empty_news_result(provider: str = "gnews", error: str = "") -> Dict[str, Any]:
    return {
        "provider": provider,
        "available": False,
        "error": error,
        "company_name": "",
        "query": "",
        "fetched_articles": [],
        "article_summaries": [],
        "overall_summary": "No material recent company news was incorporated into this analysis.",
        "material_article_count": 0,
    }


def news_agent(state: ResearchState) -> ResearchState:
    agent_start = time.time()
    ticker = state.get("ticker", "")
    market_data = state.get("market_data", {}) or {}

    if not ticker:
        state["news_analysis"] = _empty_news_result(error="No ticker provided")
        return state

    print(f"\n[News Agent] Fetching recent company news for {ticker}...")

    try:
        from services.news_service import fetch_company_news
        from services.document_registry import register_document
        from services.llm_service import get_gemini_service
        from services.prompt_manager import render_prompt

        valuation = market_data.get("valuation", {}) or {}
        company_name = (
            valuation.get("company_name")
            or valuation.get("long_name")
            or valuation.get("short_name")
            or ticker
        )

        news_result = fetch_company_news(ticker=ticker, company_name=company_name)
        fetched_articles = news_result.get("articles", [])

        if not news_result.get("available") or not fetched_articles:
            state["news_analysis"] = {
                **_empty_news_result(error=news_result.get("error", "")),
                "provider": news_result.get("provider", "gnews"),
                "company_name": company_name,
                "query": news_result.get("query", ""),
                "fetched_articles": fetched_articles,
            }
            print("[News Agent] No news articles available or provider not configured.")
            return state

        prompt = render_prompt("news_impact", {
            "ticker": ticker,
            "company_name": company_name,
            "article_count": len(fetched_articles[:10]),
            "articles": _build_article_prompt_context(fetched_articles[:10]),
        })

        gemini = get_gemini_service()
        llm_start = time.time()
        summary_payload = gemini.invoke_json(
            prompt,
            temperature=0.3,
            agent_name="news_agent",
            analysis_id=state.get("_analysis_id"),
        )
        llm_time = time.time() - llm_start

        article_summaries: List[Dict[str, Any]] = []
        indexed_articles = {str(idx): article for idx, article in enumerate(fetched_articles[:10], start=1)}
        for item in summary_payload.get("articles", []):
            source_article = indexed_articles.get(str(item.get("article_number", "")))
            if not source_article:
                continue
            try:
                impact_score = int(item.get("impact_score", 0))
            except (TypeError, ValueError):
                impact_score = 0
            summary_entry = {
                "title": source_article.get("title", ""),
                "summary": str(item.get("summary", "")).strip(),
                "impact_direction": str(item.get("impact_direction", "neutral")).lower(),
                "impact_score": max(0, min(5, impact_score)),
                "reasoning": str(item.get("reasoning", "")).strip(),
                "source_name": source_article.get("source_name", ""),
                "source_url": source_article.get("url") or source_article.get("source_url", ""),
                "published_at": source_article.get("published_at", ""),
                "description": source_article.get("description", ""),
            }
            if summary_entry["summary"]:
                article_summaries.append(summary_entry)

        document_sources = state.get("document_sources", []) or []
        for article in article_summaries:
            document_sources.append(register_document({
                "source_type": "news_article",
                "ticker": ticker,
                "analysis_id": state.get("_analysis_id", ""),
                "title": article.get("title", ""),
                "source_url": article.get("source_url", ""),
                "source_name": article.get("source_name", ""),
                "published_at": article.get("published_at", ""),
                "summary_text": article.get("summary", ""),
                "impact_direction": article.get("impact_direction", "neutral"),
                "impact_score": article.get("impact_score", 0),
                "impact_reasoning": article.get("reasoning", ""),
                "status": "ready",
            }))

        state["document_sources"] = document_sources
        state["news_analysis"] = {
            "provider": news_result.get("provider", "gnews"),
            "available": True,
            "error": None,
            "company_name": company_name,
            "query": news_result.get("query", ""),
            "fetched_articles": fetched_articles,
            "article_summaries": article_summaries,
            "overall_summary": str(
                summary_payload.get(
                    "overall_summary",
                    "Recent company news did not produce a decisive stock-impact view.",
                )
            ).strip(),
            "material_article_count": len(article_summaries),
            "total_articles": news_result.get("total_articles", len(fetched_articles)),
        }

        agent_time = time.time() - agent_start
        print(f"[News Agent] Complete in {agent_time:.1f}s (LLM: {llm_time:.1f}s). Material articles: {len(article_summaries)}")
        state["_agent_timing"] = state.get("_agent_timing", {})
        state["_agent_timing"]["news_analysis"] = agent_time
        state["_agent_timing"]["news_analysis_llm"] = llm_time
        return state
    except Exception as exc:
        agent_time = time.time() - agent_start
        print(f"[News Agent] Error after {agent_time:.1f}s: {exc}")
        state["news_analysis"] = _empty_news_result(error=str(exc))
        return state
