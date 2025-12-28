# Quick Test Guide

If the full analysis is taking too long, here's a quick test to verify each component:

## Test Individual Components

### 1. Test Market Data Only
```python
from tools.market_data import get_market_data
data = get_market_data("AAPL")
print(data)
```

### 2. Test Ollama Connection
```python
from config import get_llm
llm = get_llm()
response = llm.invoke("Say hello in one word")
print(response.content)
```

### 3. Test with Shorter Period
The code now uses 6 months instead of 1 year for faster fetching.

## If It's Still Hanging

1. **Check Ollama is running**: `ollama ps`
2. **Test Ollama directly**: `ollama run deepseek-r1:8b "test"`
3. **Check network**: Try accessing yahoo finance in browser
4. **Use shorter time periods**: Already set to 6mo instead of 1y

## Expected Times

- Market data fetch: 15-30 seconds
- Valuation metrics: 15-30 seconds  
- Risk calculations: 10-20 seconds
- LLM sentiment: 30-60 seconds (first call)
- LLM scenarios: 30-60 seconds
- LLM memo: 60-120 seconds

**Total: 3-5 minutes is normal, 15+ minutes indicates a problem.**

