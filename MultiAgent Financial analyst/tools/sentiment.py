"""
Sentiment Analysis Tools

Functions for analyzing market sentiment.
Uses Hugging Face Mistral for lightweight sentiment analysis.
"""

from typing import Dict, Any
from services.llm_service import get_hf_service


def analyze_sentiment_with_llm(ticker: str, context: str = "") -> str:
    """
    Use LLM to analyze sentiment for a given ticker.
    Uses Hugging Face Mistral (lightweight, no reasoning chains).
    
    Args:
        ticker: Stock ticker symbol
        context: Additional context about the stock
    
    Returns:
        Sentiment description
    """
    try:
        hf_service = get_hf_service()
        
        print(f"[Macro Sentiment Agent] Calling Hugging Face API...")
        
        # Simple, direct prompt (no reasoning chains)
        prompt = f"""Analyze sentiment for {ticker}:
{context}

Return JSON: {{"sentiment": "positive|neutral|negative", "score": 0.0-1.0}}"""

        response_text = hf_service.invoke(prompt, temperature=0.3)
        
        # Try to parse JSON, fallback to simple text parsing
        try:
            import json
            # Remove markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            result = json.loads(response_text)
            sentiment_val = result.get("sentiment", "neutral")
            
            # Map to expected categories
            if sentiment_val == "positive":
                return "Neutral-positive"
            elif sentiment_val == "negative":
                return "Neutral-negative"
            else:
                return "Neutral"
        except:
            # Fallback: try to extract sentiment from text
            response_lower = response_text.lower()
            if "positive" in response_lower or "bullish" in response_lower:
                return "Neutral-positive"
            elif "negative" in response_lower or "bearish" in response_lower:
                return "Neutral-negative"
            else:
                return "Neutral"
        
    except Exception as e:
        print(f"Error analyzing sentiment: {e}")
        return "Neutral"
