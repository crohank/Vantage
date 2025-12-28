"""
Macro Data Tools

Functions for fetching macroeconomic data:
- FRED API (rates, CPI)
- Sector ETF performance
- News sentiment
"""

import yfinance as yf
import pandas as pd
from typing import Dict, Any, Optional
from fredapi import Fred
import os
from dotenv import load_dotenv

load_dotenv()


def get_fred_data() -> Dict[str, Any]:
    """
    Fetch macroeconomic data from FRED API.
    
    Returns:
        Dictionary with macro indicators
    """
    try:
        api_key = os.getenv("FRED_API_KEY")
        if not api_key:
            return {
                "interest_rate_trend": "Unknown (FRED API key not set)",
                "inflation_trend": "Unknown (FRED API key not set)",
                "error": "FRED_API_KEY not found in environment"
            }
        
        fred = Fred(api_key=api_key)
        
        # Federal Funds Rate (FEDFUNDS)
        try:
            fed_funds = fred.get_series("FEDFUNDS", observation_start="2023-01-01")
            if fed_funds is not None and len(fed_funds) > 1:
                recent_rate = fed_funds.iloc[-1]
                older_rate = fed_funds.iloc[0] if len(fed_funds) > 6 else fed_funds.iloc[-1]
                
                if recent_rate > older_rate * 1.01:
                    interest_trend = "Rising"
                elif recent_rate < older_rate * 0.99:
                    interest_trend = "Falling"
                else:
                    interest_trend = "Stable"
            else:
                interest_trend = "Unknown"
        except Exception:
            interest_trend = "Unknown"
        
        # CPI (Consumer Price Index)
        try:
            cpi = fred.get_series("CPIAUCSL", observation_start="2023-01-01")
            if cpi is not None and len(cpi) > 1:
                # Calculate YoY inflation
                recent_cpi = cpi.iloc[-1]
                year_ago_cpi = cpi.iloc[-12] if len(cpi) >= 12 else cpi.iloc[0]
                inflation_rate = ((recent_cpi - year_ago_cpi) / year_ago_cpi) * 100
                
                if inflation_rate > 3:
                    inflation_trend = "Elevated"
                elif inflation_rate < 2:
                    inflation_trend = "Cooling"
                else:
                    inflation_trend = "Moderate"
            else:
                inflation_trend = "Unknown"
        except Exception:
            inflation_trend = "Unknown"
        
        return {
            "interest_rate_trend": interest_trend,
            "inflation_trend": inflation_trend,
        }
    except Exception as e:
        print(f"Error fetching FRED data: {e}")
        return {
            "interest_rate_trend": "Unknown",
            "inflation_trend": "Unknown",
            "error": str(e)
        }


def get_sector_performance() -> Dict[str, Any]:
    """
    Compare sector ETF performance.
    
    Returns:
        Dictionary with sector performance data
    """
    try:
        # Key sector ETFs
        sectors = {
            "XLK": "Technology",
            "XLF": "Financials",
            "XLV": "Healthcare",
            "XLE": "Energy",
            "XLI": "Industrials",
            "XLP": "Consumer Staples",
            "XLY": "Consumer Discretionary",
            "XLB": "Materials",
            "XLU": "Utilities",
            "XLRE": "Real Estate",
            "XLC": "Communication Services"
        }
        
        sector_performance = {}
        
        for etf, name in sectors.items():
            try:
                ticker = yf.Ticker(etf)
                data = ticker.history(period="6mo")
                
                if data is not None and not data.empty and len(data) > 1:
                    start_price = data["Close"].iloc[0]
                    end_price = data["Close"].iloc[-1]
                    return_pct = ((end_price - start_price) / start_price) * 100
                    sector_performance[name] = round(return_pct, 2)
            except Exception:
                continue
        
        # Determine overall market trend
        if sector_performance:
            avg_performance = sum(sector_performance.values()) / len(sector_performance)
            if avg_performance > 5:
                market_trend = "Strong"
            elif avg_performance > 0:
                market_trend = "Positive"
            elif avg_performance > -5:
                market_trend = "Weak"
            else:
                market_trend = "Negative"
        else:
            market_trend = "Unknown"
        
        return {
            "sector_performance": sector_performance,
            "market_trend": market_trend,
            "sector_performance_summary": market_trend
        }
    except Exception as e:
        print(f"Error fetching sector performance: {e}")
        return {"sector_performance": {}, "market_trend": "Unknown"}


def get_macro_data() -> Dict[str, Any]:
    """
    Get comprehensive macroeconomic data.
    
    Returns:
        Dictionary with all macro indicators
    """
    fred_data = get_fred_data()
    sector_data = get_sector_performance()
    
    macro_data = {
        **fred_data,
        **sector_data,
        "news_sentiment": "Neutral-positive"  # Placeholder - can be enhanced with actual news API
    }
    
    return macro_data
