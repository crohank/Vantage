"""
Macro Trends Agent

Responsibility: Analyze macroeconomic trends and sector performance.
"""

import time
from typing import Dict, Any
from schemas.state import ResearchState
from tools.macro_data import get_macro_data
from tools.sentiment import analyze_sentiment_with_llm


def macro_trends_agent(state: ResearchState) -> ResearchState:
    """
    Macro Trends Agent - Analyzes macroeconomic conditions.
    
    Args:
        state: Current research state
    
    Returns:
        Updated state with macro_data populated
    """
    agent_start = time.time()
    print("\n[Macro Trends Agent] Analyzing macroeconomic conditions...")
    
    # Get macro data
    macro_data = get_macro_data()
    
    # Get market data context for sentiment
    market_data = state.get("market_data", {})
    ticker = state.get("ticker", "")
    
    # Analyze sentiment with LLM if we have context
    sentiment_time = 0
    if market_data and ticker:
        sentiment_start = time.time()
        context = f"Ticker: {ticker}, Price trend: {market_data.get('price_trend', 'Unknown')}"
        sentiment = analyze_sentiment_with_llm(ticker, context)
        sentiment_time = time.time() - sentiment_start
        macro_data["news_sentiment"] = sentiment
        print(f"[OK] Sentiment analysis complete in {sentiment_time:.1f}s. Result: {sentiment}")
    
    # Update state
    state["macro_data"] = macro_data
    
    agent_time = time.time() - agent_start
    print(f"[Macro Trends Agent] Complete in {agent_time:.1f}s (LLM: {sentiment_time:.1f}s).")
    
    # Store timing
    state["_agent_timing"] = state.get("_agent_timing", {})
    state["_agent_timing"]["macro_trends"] = agent_time
    if sentiment_time > 0:
        state["_agent_timing"]["macro_trends_llm"] = sentiment_time
    
    return state
