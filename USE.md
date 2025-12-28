# How to Use the Financial Research Analyst

## What It Does

This AI-powered system analyzes stocks and generates investment research reports. It provides:

- **Market Analysis**: Price trends, valuation metrics, technical indicators
- **Macro Analysis**: Interest rates, inflation, sector performance
- **Risk Assessment**: Volatility, beta, drawdown, key risks
- **Scenarios**: Bull/Base/Bear outcomes with probabilities
- **Recommendation**: Buy, Hold, or Sell with confidence score
- **Investment Memo**: Professional research report in Markdown

## Quick Start

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# or: source venv/bin/activate  # Mac/Linux

# Install packages
pip install -r requirements.txt
```

### 2. Set Up Ollama

```bash
# Install Ollama from https://ollama.ai
# Then pull the model
ollama pull deepseek-r1:8b
```

### 3. Configure Environment

Create a `.env` file in the project root:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=deepseek-r1:8b
FRED_API_KEY=your_key_here  # Optional but recommended
```

Get a free FRED API key at: https://fred.stlouisfed.org/docs/api/api_key.html

### 4. Run Analysis

```bash
python main.py <ticker> <horizon> <risk_profile>
```

**Example:**
```bash
python main.py AAPL medium moderate
```

**Parameters:**
- `ticker`: Stock symbol (e.g., AAPL, MSFT, TSLA)
- `horizon`: `short` | `medium` | `long`
- `risk_profile`: `conservative` | `moderate` | `aggressive`

## Output

The system generates:

1. **Console Output**: Recommendation, confidence score, and scenarios
2. **Investment Memo**: Saved to `outputs/{TICKER}_memo.md`

## Example Output

```
============================================================
AI-Powered Financial Research Analyst
============================================================
Ticker: AAPL
Horizon: medium
Risk Profile: moderate
============================================================

============================================================
ANALYSIS COMPLETE
============================================================

Recommendation: Buy
Confidence Score: 0.75

Scenarios:
  Bull: +25.0% return, 30% probability
  Base: +8.0% return, 50% probability
  Bear: -15.0% return, 20% probability

Investment memo saved to: outputs/AAPL_memo.md
============================================================
```

## What Each Agent Does

| Agent | Purpose |
|-------|---------|
| **Market Data** | Fetches stock prices, P/E ratios, RSI, moving averages |
| **Macro Trends** | Analyzes interest rates, inflation, sector performance |
| **Risk Analyst** | Calculates volatility, beta, identifies key risks |
| **Scenario** | Generates Bull/Base/Bear scenarios with probabilities |
| **Memo Writer** | Creates professional investment memo |

## Tips

- **First Run**: May take 10-15 minutes as the LLM model loads into memory
- **Subsequent Runs**: Will be faster (2-5 minutes) once model is loaded
- **FRED API**: Optional but improves macroeconomic analysis
- **Ollama**: Must be running (`ollama serve` if not auto-started)
- **Network**: Requires internet for market data and FRED API
- **If Too Slow**: Consider using a smaller model like `llama3.2:3b` for faster inference

## Troubleshooting

**"Connection refused" error:**
- Make sure Ollama is running: `ollama serve`

**"FRED API key not found":**
- System will still work but with limited macro data
- Add your key to `.env` file

**"No module named 'yfinance'":**
- Activate virtual environment and run: `pip install -r requirements.txt`


