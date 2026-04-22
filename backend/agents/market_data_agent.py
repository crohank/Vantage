"""
Market Data Agent

Responsibility: Populate market_data in state only.
No opinions, no recommendations.
"""

import time
from typing import Dict, Any
from schemas.state import ResearchState
from tools.market_data import get_market_data


def market_data_agent(state: ResearchState) -> ResearchState:
    """
    Market Data Agent - Fetches and processes market data.
    
    Args:
        state: Current research state
    
    Returns:
        Updated state with market_data populated
    """
    agent_start = time.time()
    ticker = state.get("ticker", "")
    
    if not ticker:
        state["market_data"] = {"error": "No ticker provided"}
        return state
    
    print(f"\n[Market Data Agent] Fetching data for {ticker}...")
    
    # Fetch market data
    market_data = get_market_data(ticker)
    
    # Update state
    state["market_data"] = market_data
    
    agent_time = time.time() - agent_start
    print(f"[Market Data Agent] Complete in {agent_time:.1f}s. Price trend: {market_data.get('price_trend', 'Unknown')}")
    
    # Store timing
    state["_agent_timing"] = state.get("_agent_timing", {})
    state["_agent_timing"]["market_data"] = agent_time
    
    return state
