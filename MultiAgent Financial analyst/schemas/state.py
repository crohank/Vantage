"""
Shared State Schema

Defines the ResearchState TypedDict that LangGraph passes between agents.
"""

from typing import TypedDict, Dict, Any


class ResearchState(TypedDict):
    """State object passed between agents in the research graph."""
    
    ticker: str
    horizon: str
    risk_profile: str

    market_data: Dict[str, Any]
    macro_data: Dict[str, Any]
    risk_analysis: Dict[str, Any]
    scenarios: Dict[str, Any]

    recommendation: str
    confidence_score: float
    memo: str

