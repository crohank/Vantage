"""
Shared State Schema

Defines the ResearchState TypedDict that LangGraph passes between agents.
"""

from typing import TypedDict, Dict, Any, List


class ResearchState(TypedDict):
    """State object passed between agents in the research graph."""

    ticker: str
    horizon: str
    risk_profile: str
    original_query: str

    market_data: Dict[str, Any]
    macro_data: Dict[str, Any]
    risk_analysis: Dict[str, Any]
    scenarios: Dict[str, Any]

    # RAG context
    sec_filing_context: Dict[str, Any]
    uploaded_document: Dict[str, Any]
    document_sources: List[Dict[str, Any]]

    recommendation: str
    confidence_score: float
    memo: str

    # Telemetry
    _analysis_id: str
    _telemetry: Dict[str, Any]

