"""
Risk Analyst Agent

Responsibility: Compute risk metrics and identify key risks.
"""

import time
from typing import Dict, Any, List
from schemas.state import ResearchState
from tools.risk_metrics import get_risk_metrics


def identify_key_risks(ticker: str, market_data: Dict[str, Any],
                      macro_data: Dict[str, Any],
                      risk_metrics: Dict[str, Any],
                      sec_filing_context: Dict[str, Any] = None) -> List[str]:
    """
    Use LLM to identify key risks based on data.
    Uses Gemini Flash for structured reasoning.
    
    Args:
        ticker: Stock ticker
        market_data: Market data dictionary
        macro_data: Macro data dictionary
        risk_metrics: Risk metrics dictionary
    
    Returns:
        List of key risks
    """
    try:
        from services.llm_service import get_gemini_service
        from services.prompt_manager import render_prompt, list_versions

        gemini = get_gemini_service()

        # Use v2 prompt if SEC filing context is available, otherwise v1
        sec_context = sec_filing_context or {}
        variables = {
            "ticker": ticker,
            "price_trend": market_data.get('price_trend', 'Unknown'),
            "pe_ratio": market_data.get('valuation', {}).get('pe_ratio', 'Unknown'),
            "rsi": market_data.get('technical_indicators', {}).get('rsi', 'Unknown'),
            "interest_rate_trend": macro_data.get('interest_rate_trend', 'Unknown'),
            "inflation_trend": macro_data.get('inflation_trend', 'Unknown'),
            "market_trend": macro_data.get('market_trend', 'Unknown'),
            "volatility": risk_metrics.get('volatility', 'Unknown'),
            "beta": risk_metrics.get('beta', 'Unknown'),
            "drawdown": risk_metrics.get('drawdown', 'Unknown'),
        }

        # Check if v2 prompt exists and SEC context is available
        sec_filing = sec_context if sec_context else {}
        has_sec = sec_filing.get('available', False)
        has_v2 = 2 in list_versions("risk_analysis")

        if has_sec and has_v2:
            variables["sec_risk_factors"] = sec_filing.get('risk_factors_context', 'Not available')
            variables["uploaded_context"] = sec_filing.get('uploaded_context', 'Not available')
            prompt = render_prompt("risk_analysis", variables, version=2)
        else:
            prompt = render_prompt("risk_analysis", variables, version=1)

        result = gemini.invoke_json(prompt, temperature=0.5)
        
        # Extract key risks
        key_risks = result.get("key_risks", [])
        if not key_risks:
            return ["Unable to identify risks"]
        
        return key_risks[:5]  # Limit to 5 risks
    except Exception as e:
        print(f"Error identifying risks: {e}")
        return ["Unable to identify risks"]


def risk_agent(state: ResearchState) -> ResearchState:
    """
    Risk Analyst Agent - Computes risk metrics and identifies risks.
    
    Args:
        state: Current research state
    
    Returns:
        Updated state with risk_analysis populated
    """
    agent_start = time.time()
    ticker = state.get("ticker", "")
    
    if not ticker:
        state["risk_analysis"] = {"error": "No ticker provided"}
        return state
    
    print(f"\n[Risk Analyst Agent] Computing risk metrics for {ticker}...")
    
    # Get risk metrics
    risk_metrics = get_risk_metrics(ticker)
    
    # Get market and macro data for context
    market_data = state.get("market_data", {})
    macro_data = state.get("macro_data", {})
    
    # Identify key risks using LLM
    sec_filing_context = state.get("sec_filing_context", {})
    print("[Risk Analyst Agent] Calling Gemini API...")
    llm_start = time.time()
    key_risks = identify_key_risks(ticker, market_data, macro_data, risk_metrics, sec_filing_context)
    llm_time = time.time() - llm_start
    print(f"[OK] Risk analysis complete in {llm_time:.1f}s")
    
    # Combine into risk analysis
    risk_analysis = {
        **risk_metrics,
        "key_risks": key_risks
    }
    
    # Update state
    state["risk_analysis"] = risk_analysis
    
    agent_time = time.time() - agent_start
    print(f"[Risk Analyst Agent] Complete in {agent_time:.1f}s (LLM: {llm_time:.1f}s). Volatility: {risk_metrics.get('volatility', 'Unknown')}")
    
    # Store timing
    state["_agent_timing"] = state.get("_agent_timing", {})
    state["_agent_timing"]["risk_analysis"] = agent_time
    state["_agent_timing"]["risk_analysis_llm"] = llm_time
    
    return state
