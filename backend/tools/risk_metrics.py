"""
Risk Metrics Tools

Functions for computing risk metrics:
- Volatility
- Beta vs S&P 500
- Max drawdown
"""

import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional


def calculate_volatility(ticker: str, period: str = "1y") -> Optional[float]:
    """
    Calculate annualized volatility.
    
    Args:
        ticker: Stock ticker symbol
        period: Time period for calculation
    
    Returns:
        Annualized volatility (as decimal) or None if error
    """
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period=period)
        
        if data is None or data.empty or len(data) < 2:
            return None
        
        # Calculate daily returns
        returns = data["Close"].pct_change().dropna()
        
        # Annualized volatility (assuming 252 trading days)
        volatility = returns.std() * np.sqrt(252)
        
        return float(volatility)
    except Exception as e:
        print(f"Error calculating volatility for {ticker}: {e}")
        return None


def calculate_beta(ticker: str, benchmark: str = "SPY", period: str = "1y") -> Optional[float]:
    """
    Calculate beta vs benchmark (default: S&P 500).
    
    Args:
        ticker: Stock ticker symbol
        benchmark: Benchmark ticker (default: SPY for S&P 500)
        period: Time period for calculation
    
    Returns:
        Beta value or None if error
    """
    try:
        stock = yf.Ticker(ticker)
        benchmark_stock = yf.Ticker(benchmark)
        
        stock_data = stock.history(period=period)
        benchmark_data = benchmark_stock.history(period=period)
        
        if stock_data is None or stock_data.empty or benchmark_data is None or benchmark_data.empty:
            return None
        
        # Align data by date
        aligned = pd.merge(
            stock_data[["Close"]],
            benchmark_data[["Close"]],
            left_index=True,
            right_index=True,
            suffixes=("_stock", "_benchmark")
        )
        
        if len(aligned) < 2:
            return None
        
        # Calculate returns
        stock_returns = aligned["Close_stock"].pct_change().dropna()
        benchmark_returns = aligned["Close_benchmark"].pct_change().dropna()
        
        # Align returns
        aligned_returns = pd.merge(
            stock_returns.to_frame("stock"),
            benchmark_returns.to_frame("benchmark"),
            left_index=True,
            right_index=True
        )
        
        if len(aligned_returns) < 2:
            return None
        
        # Calculate covariance and variance
        covariance = np.cov(aligned_returns["stock"], aligned_returns["benchmark"])[0][1]
        benchmark_variance = np.var(aligned_returns["benchmark"])
        
        if benchmark_variance == 0:
            return None
        
        beta = covariance / benchmark_variance
        
        return float(beta)
    except Exception as e:
        print(f"Error calculating beta for {ticker}: {e}")
        return None


def calculate_max_drawdown(ticker: str, period: str = "1y") -> Dict[str, Any]:
    """
    Calculate maximum drawdown.
    
    Args:
        ticker: Stock ticker symbol
        period: Time period for calculation
    
    Returns:
        Dictionary with max drawdown info
    """
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period=period)
        
        if data is None or data.empty:
            return {"max_drawdown": None, "drawdown_pct": None, "severity": "Unknown"}
        
        # Calculate running maximum
        running_max = data["Close"].expanding().max()
        
        # Calculate drawdown
        drawdown = (data["Close"] - running_max) / running_max
        
        max_drawdown = drawdown.min()
        max_drawdown_pct = abs(max_drawdown) * 100
        
        # Categorize severity
        if max_drawdown_pct < 10:
            severity = "Low"
        elif max_drawdown_pct < 20:
            severity = "Medium"
        elif max_drawdown_pct < 30:
            severity = "High"
        else:
            severity = "Very High"
        
        return {
            "max_drawdown": float(max_drawdown),
            "drawdown_pct": round(max_drawdown_pct, 2),
            "severity": severity
        }
    except Exception as e:
        print(f"Error calculating max drawdown for {ticker}: {e}")
        return {"max_drawdown": None, "drawdown_pct": None, "severity": "Unknown"}


def get_risk_metrics(ticker: str) -> Dict[str, Any]:
    """
    Get comprehensive risk metrics for a ticker.
    
    Args:
        ticker: Stock ticker symbol
    
    Returns:
        Dictionary with all risk metrics
    """
    volatility = calculate_volatility(ticker)
    beta = calculate_beta(ticker)
    drawdown_info = calculate_max_drawdown(ticker)
    
    risk_metrics = {
        "volatility": round(volatility, 4) if volatility is not None else None,
        "beta": round(beta, 2) if beta is not None else None,
        "drawdown": drawdown_info.get("severity", "Unknown"),
        "max_drawdown_pct": drawdown_info.get("drawdown_pct", None),
    }
    
    return risk_metrics
