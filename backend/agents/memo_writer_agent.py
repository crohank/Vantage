"""
Investment Memo Writer Agent

Responsibility: Generate professional investment memo in Markdown format.
"""

import time
from typing import Dict, Any
from schemas.state import ResearchState
from datetime import datetime


def calculate_confidence_score(state: ResearchState) -> float:
    """
    Calculate confidence score based on data completeness and quality.
    
    Args:
        state: Current research state
    
    Returns:
        Confidence score between 0 and 1
    """
    # Data completeness (0.3 weight)
    completeness = 1.0
    if not state.get("market_data") or state.get("market_data", {}).get("error"):
        completeness -= 0.3
    if not state.get("macro_data") or state.get("macro_data", {}).get("error"):
        completeness -= 0.2
    if not state.get("risk_analysis") or state.get("risk_analysis", {}).get("error"):
        completeness -= 0.2
    if not state.get("scenarios"):
        completeness -= 0.3
    
    completeness = max(0.0, completeness)
    
    # Volatility penalty (0.3 weight)
    volatility = state.get("risk_analysis", {}).get("volatility", 0.3)
    volatility_score = max(0.0, 1.0 - volatility)  # Lower volatility = higher score
    
    # Agent agreement (0.4 weight) - simplified for now
    agreement = 0.7  # Placeholder - can be enhanced with actual agreement metrics
    
    # Calculate final confidence
    confidence = (
        completeness * 0.3 +
        agreement * 0.4 +
        volatility_score * 0.3
    )
    
    return round(max(0.0, min(1.0, confidence)), 2)


def determine_recommendation(state: ResearchState) -> str:
    """
    Determine Buy/Hold/Sell recommendation based on scenarios and data.
    
    Args:
        state: Current research state
    
    Returns:
        Recommendation: "Buy", "Hold", or "Sell"
    """
    scenarios = state.get("scenarios", {})
    
    if not scenarios:
        return "Hold"
    
    # Calculate expected return
    expected_return = (
        scenarios.get("bull", {}).get("return", 0) * scenarios.get("bull", {}).get("prob", 0) +
        scenarios.get("base", {}).get("return", 0) * scenarios.get("base", {}).get("prob", 0) +
        scenarios.get("bear", {}).get("return", 0) * scenarios.get("bear", {}).get("prob", 0)
    )
    
    # Get risk metrics
    risk_analysis = state.get("risk_analysis", {})
    volatility = risk_analysis.get("volatility", 0.3)
    
    # Determine recommendation
    if expected_return > 0.10 and volatility < 0.4:
        return "Buy"
    elif expected_return < -0.05 or volatility > 0.5:
        return "Sell"
    else:
        return "Hold"


def memo_writer_agent(state: ResearchState) -> ResearchState:
    """
    Investment Memo Writer Agent - Generates professional investment memo.
    
    Args:
        state: Current research state
    
    Returns:
        Updated state with memo and recommendation populated
    """
    ticker = state.get("ticker", "")
    horizon = state.get("horizon", "medium")
    risk_profile = state.get("risk_profile", "moderate")
    
    agent_start = time.time()
    print(f"\n[Memo Writer Agent] Generating investment memo...")
    
    # Calculate confidence and recommendation
    confidence = calculate_confidence_score(state)
    recommendation = determine_recommendation(state)
    
    state["confidence_score"] = confidence
    state["recommendation"] = recommendation
    
    print(f"[Memo Writer Agent] Recommendation: {recommendation}, Confidence: {confidence}")
    
    # Generate memo
    try:
        from services.llm_service import get_gemini_service, get_hf_service

        from services.prompt_manager import render_prompt

        # Shared prompt construction
        market_data = state.get("market_data", {})
        macro_data = state.get("macro_data", {})
        risk_analysis = state.get("risk_analysis", {})
        scenarios = state.get("scenarios", {})
        sec_context = state.get("sec_filing_context", {})

        prompt = render_prompt("memo_writer", {
            "ticker": ticker,
            "horizon": horizon,
            "risk_profile": risk_profile,
            "recommendation": recommendation,
            "confidence": f"{confidence:.0%}",
            "price_trend": market_data.get('price_trend', 'N/A'),
            "pe_ratio": market_data.get('valuation', {}).get('pe_ratio', 'N/A'),
            "interest_rate_trend": macro_data.get('interest_rate_trend', 'N/A'),
            "market_trend": macro_data.get('market_trend', 'N/A'),
            "volatility": risk_analysis.get('volatility', 'N/A'),
            "beta": risk_analysis.get('beta', 'N/A'),
            "bull_return": f"{scenarios.get('bull', {}).get('return', 0)*100:+.0f}%",
            "bull_prob": f"{scenarios.get('bull', {}).get('prob', 0)*100:.0f}%",
            "base_return": f"{scenarios.get('base', {}).get('return', 0)*100:+.0f}%",
            "base_prob": f"{scenarios.get('base', {}).get('prob', 0)*100:.0f}%",
            "bear_return": f"{scenarios.get('bear', {}).get('return', 0)*100:+.0f}%",
            "bear_prob": f"{scenarios.get('bear', {}).get('prob', 0)*100:.0f}%",
            "sec_risk_factors": sec_context.get("risk_factors_context", "Not available"),
            "sec_mda": sec_context.get("mda_context", "Not available"),
            "uploaded_context": sec_context.get("uploaded_context", "Not available"),
        })

        memo = None
        llm_time = 0.0

        # First try Gemini
        try:
            gemini = get_gemini_service()
            print("[Memo Writer Agent] Calling Gemini API...")
            llm_start = time.time()
            memo = gemini.invoke(prompt, temperature=0.3)
            llm_time = time.time() - llm_start
            print(f"[OK] Memo generation complete with Gemini in {llm_time:.1f}s")
        except Exception as gemini_error:
            error_str = str(gemini_error)
            print(f"[Memo Writer Agent] Gemini error: {error_str}")

            # Known geo/location restriction from Gemini: fall back to Hugging Face
            if "User location is not supported for the API use" in error_str:
                try:
                    print("[Memo Writer Agent] Falling back to Hugging Face LLM due to Gemini location restriction...")
                    hf = get_hf_service()
                    llm_start = time.time()
                    memo = hf.invoke(prompt, temperature=0.3)
                    llm_time = time.time() - llm_start
                    print(f"[OK] Memo generation complete with Hugging Face in {llm_time:.1f}s")
                except Exception as hf_error:
                    raise Exception(
                        f"Gemini blocked by location and Hugging Face fallback failed: {hf_error}"
                    ) from hf_error
            else:
                # Re-raise other Gemini errors so they surface as before
                raise

        if memo is None:
            raise Exception("No memo text generated by any LLM.")

        state["memo"] = memo

        from services.mongo_client import get_db

        analysis_id = state.get("_analysis_id", "")
        get_db()["analyses"].replace_one(
            {"_id": analysis_id},
            {
                "_id": analysis_id,
                "ticker": state.get("ticker"),
                "horizon": state.get("horizon"),
                "riskProfile": state.get("risk_profile"),
                "recommendation": state.get("recommendation"),
                "confidenceScore": state.get("confidence_score"),
                "scenarios": state.get("scenarios"),
                "marketData": state.get("market_data"),
                "macroData": state.get("macro_data"),
                "riskAnalysis": state.get("risk_analysis"),
                "memoMarkdown": state.get("memo"),
                "documentsUsed": state.get("document_sources", []),
                "createdAt": datetime.utcnow(),
            },
            upsert=True,
        )

        agent_time = time.time() - agent_start
        print(f"Memo persisted to MongoDB (took {agent_time:.1f}s, LLM: {llm_time:.1f}s)")

        # Store timing
        state["_agent_timing"] = state.get("_agent_timing", {})
        state["_agent_timing"]["memo_writer"] = agent_time
        state["_agent_timing"]["memo_writer_llm"] = llm_time

    except Exception as e:
        agent_time = time.time() - agent_start
        print(f"Error generating memo after {agent_time:.1f}s: {e}")
        state["memo"] = f"Error generating memo: {str(e)}"
    
    return state
