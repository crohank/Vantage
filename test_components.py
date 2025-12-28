"""
Quick test script to identify which component is hanging
"""

import time
from tools.market_data import fetch_stock_data, get_valuation_metrics
from config import get_llm

print("=" * 60)
print("Testing Individual Components")
print("=" * 60)

# Test 1: Market Data
print("\n[TEST 1] Testing Market Data Fetch (should take 15-30 seconds)...")
start = time.time()
try:
    data = fetch_stock_data("AAPL", period="3mo")  # Even shorter for testing
    elapsed = time.time() - start
    if data is not None:
        print(f"[PASS] Market data test PASSED in {elapsed:.1f}s")
    else:
        print(f"[FAIL] Market data test FAILED - no data returned after {elapsed:.1f}s")
except Exception as e:
    elapsed = time.time() - start
    print(f"[FAIL] Market data test FAILED after {elapsed:.1f}s: {e}")

# Test 2: Valuation Metrics
print("\n[TEST 2] Testing Valuation Metrics (should take 15-30 seconds)...")
start = time.time()
try:
    metrics = get_valuation_metrics("AAPL")
    elapsed = time.time() - start
    if metrics:
        print(f"[PASS] Valuation metrics test PASSED in {elapsed:.1f}s")
        print(f"  P/E Ratio: {metrics.get('pe_ratio', 'N/A')}")
    else:
        print(f"[FAIL] Valuation metrics test FAILED - no data returned after {elapsed:.1f}s")
except Exception as e:
    elapsed = time.time() - start
    print(f"[FAIL] Valuation metrics test FAILED after {elapsed:.1f}s: {e}")

# Test 3: Ollama Connection
print("\n[TEST 3] Testing Ollama Connection (should take 10-30 seconds)...")
start = time.time()
try:
    llm = get_llm(timeout=30)
    response = llm.invoke("Say 'hello' in one word only.")
    elapsed = time.time() - start
    content = response.content if hasattr(response, 'content') else str(response)
    print(f"[PASS] Ollama test PASSED in {elapsed:.1f}s")
    print(f"  Response: {content}")
except Exception as e:
    elapsed = time.time() - start
    print(f"[FAIL] Ollama test FAILED after {elapsed:.1f}s: {e}")
    print(f"  Make sure Ollama is running: ollama serve")
    print(f"  Or test manually: ollama run deepseek-r1:8b 'test'")

print("\n" + "=" * 60)
print("Testing Complete")
print("=" * 60)

