"""
Market Data Tools

Functions for fetching and processing market data:
- Price history
- Valuation metrics
- Technical indicators (RSI, moving averages)
"""

import yfinance as yf
import pandas as pd
from typing import Dict, Any, Optional
import signal
import time
from functools import wraps

# Try to import pandas_ta, but make it optional
try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False
    ta = None


def timeout_handler(signum, frame):
    raise TimeoutError("Operation timed out")


def with_timeout(seconds=30):
    """Decorator to add timeout to functions (Unix only)"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if hasattr(signal, 'SIGALRM'):  # Unix only
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(seconds)
                try:
                    result = func(*args, **kwargs)
                finally:
                    signal.alarm(0)
                return result
            else:
                # Windows - just run without timeout
                return func(*args, **kwargs)
        return wrapper
    return decorator


def fetch_stock_data(ticker: str, period: str = "6mo") -> Optional[pd.DataFrame]:
    """
    Fetch historical stock data using yfinance.
    Using shorter period (6mo) to speed up.
    
    Args:
        ticker: Stock ticker symbol
        period: Time period (default: 6mo for faster fetching)
    
    Returns:
        DataFrame with OHLCV data or None if error
    """
    start_time = time.time()
    try:
        print(f"  Fetching price data for {ticker} (period: {period})...")
        print(f"  [Note: This may take 15-30 seconds. If it hangs, press Ctrl+C]")
        
        stock = yf.Ticker(ticker)
        # Use shorter period and add progress indication
        data = stock.history(period=period)
        
        elapsed = time.time() - start_time
        if data is not None and not data.empty:
            print(f"  [OK] Fetched {len(data)} days of data in {elapsed:.1f}s")
        else:
            print(f"  [WARNING] No data returned after {elapsed:.1f}s")
        return data
    except KeyboardInterrupt:
        print(f"  [CANCELLED] User interrupted after {time.time() - start_time:.1f}s")
        return None
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"  [ERROR] Error fetching data for {ticker} after {elapsed:.1f}s: {e}")
        return None


def get_valuation_metrics(ticker: str) -> Dict[str, Any]:
    """
    Get valuation metrics for a stock.
    
    Args:
        ticker: Stock ticker symbol
    
    Returns:
        Dictionary with valuation metrics
    """
    start_time = time.time()
    try:
        print(f"  Fetching valuation metrics for {ticker}...")
        print(f"  [Note: This may take 15-30 seconds. If it hangs, press Ctrl+C]")
        
        stock = yf.Ticker(ticker)
        info = stock.info
        
        metrics = {
            "pe_ratio": info.get("trailingPE", None),
            "forward_pe": info.get("forwardPE", None),
            "pb_ratio": info.get("priceToBook", None),
            "ps_ratio": info.get("priceToSalesTrailing12Months", None),
            "peg_ratio": info.get("pegRatio", None),
            "dividend_yield": info.get("dividendYield", None),
            "market_cap": info.get("marketCap", None),
            "enterprise_value": info.get("enterpriseValue", None),
            "current_price": info.get("currentPrice", None),
            "52_week_high": info.get("fiftyTwoWeekHigh", None),
            "52_week_low": info.get("fiftyTwoWeekLow", None),
        }
        
        elapsed = time.time() - start_time
        print(f"  [OK] Valuation metrics retrieved in {elapsed:.1f}s")
        return metrics
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"  [ERROR] Error fetching valuation metrics for {ticker} after {elapsed:.1f}s: {e}")
        return {}


def calculate_technical_indicators(data: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate technical indicators from price data.
    
    Args:
        data: DataFrame with OHLCV data
    
    Returns:
        Dictionary with technical indicators
    """
    if data is None or data.empty:
        return {}
    
    try:
        current_price = data["Close"].iloc[-1]
        
        if PANDAS_TA_AVAILABLE and ta is not None:
            # Calculate RSI
            rsi = ta.rsi(data["Close"], length=14)
            current_rsi = rsi.iloc[-1] if not rsi.empty else None
            
            # Calculate moving averages
            sma_50 = ta.sma(data["Close"], length=50)
            sma_200 = ta.sma(data["Close"], length=200)
            
            sma_50_current = sma_50.iloc[-1] if not sma_50.empty else None
            sma_200_current = sma_200.iloc[-1] if not sma_200.empty else None
            
            # Calculate MACD
            macd = ta.macd(data["Close"])
            macd_signal = None
            if macd is not None and not macd.empty:
                macd_line = macd.iloc[:, 0] if len(macd.columns) > 0 else None
                signal_line = macd.iloc[:, 2] if len(macd.columns) > 2 else None
                if macd_line is not None and signal_line is not None:
                    if macd_line.iloc[-1] > signal_line.iloc[-1]:
                        macd_signal = "Bullish"
                    else:
                        macd_signal = "Bearish"
            
            # Calculate Bollinger Bands
            bbands = ta.bbands(data["Close"], length=20)
            bbands_signal = None
            if bbands is not None and not bbands.empty:
                upper = bbands.iloc[:, 0] if len(bbands.columns) > 0 else None
                lower = bbands.iloc[:, 2] if len(bbands.columns) > 2 else None
                if upper is not None and lower is not None:
                    if current_price > upper.iloc[-1]:
                        bbands_signal = "Overbought"
                    elif current_price < lower.iloc[-1]:
                        bbands_signal = "Oversold"
        else:
            # Fallback: Use pandas for simple calculations
            current_rsi = None
            sma_50_current = data["Close"].rolling(window=50).mean().iloc[-1] if len(data) >= 50 else None
            sma_200_current = data["Close"].rolling(window=200).mean().iloc[-1] if len(data) >= 200 else None
            macd_signal = None
            bbands_signal = None
        
        # Determine MA signal
        ma_signal = "Neutral"
        if sma_50_current and sma_200_current:
            if current_price > sma_50_current > sma_200_current:
                ma_signal = "Bullish"
            elif current_price < sma_50_current < sma_200_current:
                ma_signal = "Bearish"
        
        indicators = {
            "rsi": round(current_rsi, 2) if current_rsi is not None else None,
            "sma_50": round(sma_50_current, 2) if sma_50_current is not None else None,
            "sma_200": round(sma_200_current, 2) if sma_200_current is not None else None,
            "ma_signal": ma_signal,
            "macd_signal": macd_signal,
            "bbands_signal": bbands_signal,
            "current_price": round(current_price, 2),
        }
        
        return indicators
    except Exception as e:
        print(f"Error calculating technical indicators: {e}")
        return {}


def get_price_trend(data: pd.DataFrame, months: int = 6) -> str:
    """
    Determine price trend over specified period.
    
    Args:
        data: DataFrame with price data
        months: Number of months to analyze
    
    Returns:
        Trend description (e.g., "Upward (6M)", "Downward (6M)")
    """
    if data is None or data.empty:
        return "Unknown"
    
    try:
        # Get data for specified months
        period_data = data.tail(months * 21)  # Approximate trading days per month
        
        if len(period_data) < 2:
            return "Insufficient data"
        
        start_price = period_data["Close"].iloc[0]
        end_price = period_data["Close"].iloc[-1]
        change_pct = ((end_price - start_price) / start_price) * 100
        
        if change_pct > 5:
            return f"Upward ({months}M)"
        elif change_pct < -5:
            return f"Downward ({months}M)"
        else:
            return f"Sideways ({months}M)"
    except Exception as e:
        print(f"Error determining price trend: {e}")
        return "Unknown"


def get_market_data(ticker: str) -> Dict[str, Any]:
    """
    Get comprehensive market data for a ticker.
    
    Args:
        ticker: Stock ticker symbol
    
    Returns:
        Dictionary with all market data metrics
    """
    # Fetch price data
    price_data = fetch_stock_data(ticker, period="1y")
    
    # Get valuation metrics
    valuation = get_valuation_metrics(ticker)
    
    # Calculate technical indicators
    indicators = calculate_technical_indicators(price_data) if price_data is not None else {}
    
    # Get price trend
    price_trend = get_price_trend(price_data, months=6)
    
    # Combine all data
    market_data = {
        "ticker": ticker,
        "price_trend": price_trend,
        "valuation": valuation,
        "technical_indicators": indicators,
        "data_available": price_data is not None and not price_data.empty,
    }
    
    return market_data
