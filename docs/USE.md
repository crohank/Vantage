# How to Use the Financial Research Analyst

## What It Does

This AI-powered system analyzes stocks and generates investment research reports. It provides:

- **Market Analysis**: Price trends, valuation metrics, technical indicators
- **Macro Analysis**: Interest rates, inflation, sector performance
- **Risk Assessment**: Volatility, beta, drawdown, key risks
- **Scenarios**: Bull/Base/Bear outcomes with probabilities
- **Recommendation**: Buy, Hold, or Sell with confidence score
- **Investment Memo**: Professional research report in Markdown

---

## Option A: Web Application (Recommended)

The full-stack app gives you a browser UI with real-time progress tracking.

### 1. Install Dependencies

```bash
# Python dependencies (from project root)
python -m venv venv
venv\Scripts\activate        # Windows
# or: source venv/bin/activate  # Mac/Linux
pip install -r backend/requirements.txt

# Node.js dependencies
cd backend && npm install
cd ../frontend && npm install
cd ..
```

### 2. Configure Environment

Copy `.env.example` to `.env` in the project root and fill in your keys:

```env
GEMINI_API_KEY=your_gemini_api_key_here
HUGGINGFACE_API_KEY=your_huggingface_api_key_here
FRED_API_KEY=your_fred_api_key_here   # Optional but recommended
```

- **Gemini API key**: [aistudio.google.com](https://aistudio.google.com) (free tier available)
- **HuggingFace API key**: [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) (free)
- **FRED API key**: [fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html) (free)

### 3. Start the Backend

```bash
cd backend
npm run dev
# API server runs on http://localhost:3001
```

### 4. Start the Frontend

In a second terminal:

```bash
cd frontend
npm run dev
# UI runs on http://localhost:5173
```

### 5. Run an Analysis

Open [http://localhost:5173](http://localhost:5173), enter a ticker (e.g. `AAPL`), select a horizon and risk profile, and click **Run Analysis**. Progress streams in real time.

---

## Option B: Command Line

Run the Python pipeline directly without the web app.

### 1. Install Python Dependencies

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# or: source venv/bin/activate  # Mac/Linux
pip install -r backend/requirements.txt
```

### 2. Configure Environment

Same `.env` setup as above (at project root).

### 3. Run Analysis

```bash
cd backend
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

---

## Option C: Docker (Production)

Runs both services in containers — no local Python or Node.js setup needed.

```bash
# From the project root
docker-compose up --build
```

- Frontend: [http://localhost](http://localhost)
- API: [http://localhost:3001](http://localhost:3001)

Memos are saved to `backend/outputs/`.

---

## Output

| Output | Location |
|--------|----------|
| Console summary (recommendation, scenarios) | Terminal / browser UI |
| Investment memo (Markdown) | `backend/outputs/{TICKER}_memo.md` |

**Example console output:**
```
Recommendation: Buy
Confidence Score: 0.75

Scenarios:
  Bull: +25.0% return, 30% probability
  Base: +8.0% return, 50% probability
  Bear: -15.0% return, 20% probability

Investment memo saved to: outputs/AAPL_memo.md
```

---

## What Each Agent Does

| Agent | Purpose | Uses LLM |
|-------|---------|----------|
| **Market Data** | Fetches stock prices, P/E ratios, RSI, moving averages | No |
| **Macro Trends** | Analyzes interest rates, inflation, sector performance | Yes (HuggingFace) |
| **Risk Analyst** | Calculates volatility, beta, identifies key risks | Yes (Gemini) |
| **Scenario** | Generates Bull/Base/Bear scenarios with probabilities | Yes (Gemini) |
| **Memo Writer** | Creates professional investment memo | Yes (Gemini) |

---

## Tips

- **Runtime**: Analysis typically takes 5–10 minutes (LLM API calls are the bottleneck)
- **FRED API**: Optional but improves macroeconomic analysis quality
- **Network**: Requires internet for market data, FRED API, Gemini, and HuggingFace

---

## Troubleshooting

**"GEMINI_API_KEY not set" or API errors:**
- Check your `.env` file is in the project root (not inside `backend/`)
- Verify the key is valid at [aistudio.google.com](https://aistudio.google.com)

**"FRED API key not found":**
- System still works but with limited macro data
- Add `FRED_API_KEY` to your `.env` file

**"No module named 'yfinance'" or similar:**
- Activate the virtual environment, then: `pip install -r backend/requirements.txt`

**Frontend can't reach backend:**
- Make sure the backend is running on port 3001 before starting the frontend
- Check there are no firewall rules blocking localhost:3001
