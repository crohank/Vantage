# AI-Powered Financial Research Analyst Team

## Complete Step-by-Step Build Plan

---

## PHASE 0 — Project Definition (1–2 hours)

### 0.1 Define scope (lock this early)

#### Input

- Stock ticker (e.g., AAPL)
- Time horizon: `short` | `medium` | `long`
- Risk profile: `conservative` | `moderate` | `aggressive`

#### Output

- Buy / Hold / Sell
- Confidence score (0–1)
- Bull / Base / Bear scenarios
- Investment memo (Markdown)

> 📌 **Important**: You are building a decision-support research system, NOT a trading bot.

### 0.2 Tech stack (lock this)

- **Language**: Python 3.10+
- **Multi-agent framework**: LangGraph
- **LLM**: Ollama (local models)
- **Data**:
  - yfinance
  - FRED API
- **Quant**: pandas, numpy, scipy, pandas-ta
- **Output**: Markdown → PDF (optional)
- **UI** (optional later): Streamlit

### 0.3 Repository structure (create now)

```
financial-research-agent/
│
├── agents/
│   ├── market_data_agent.py
│   ├── macro_trends_agent.py
│   ├── risk_agent.py
│   ├── scenario_agent.py
│   └── memo_writer_agent.py
│
├── graph/
│   └── research_graph.py
│
├── tools/
│   ├── market_data.py
│   ├── macro_data.py
│   ├── risk_metrics.py
│   └── sentiment.py
│
├── schemas/
│   └── state.py
│
├── outputs/
│
├── config.py
├── main.py
├── requirements.txt
└── README.md
```

---

## PHASE 1 — Environment & Data Foundations (1 day)

### 1.1 Set up environment

```bash
python -m venv venv
source venv/bin/activate
pip install langgraph langchain langchain-ollama yfinance pandas numpy scipy pandas-ta fredapi
```

**Install Ollama** (if not already installed):

- Download from https://ollama.ai
- Pull model: `ollama pull deepseek-r1:8b`

**Add `.env`:**

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=deepseek-r1:8b
FRED_API_KEY=xxx
```

### 1.2 Market data tooling

**Create `tools/market_data.py`**

**Implement:**

- Price history
- Valuation metrics
- Technical indicators (RSI, moving averages)

**Output example:**

```json
{
  "price_trend": "Upward (6M)",
  "pe_ratio": 28.4,
  "rsi": 62,
  "ma_signal": "Bullish"
}
```

✅ **Checkpoint**: Can you fetch and print clean metrics for a ticker?

---

## PHASE 2 — Define Shared State (CRITICAL) (2–3 hours)

**Create `schemas/state.py`**

```python
from typing import TypedDict, Dict, Any

class ResearchState(TypedDict):
    ticker: str
    horizon: str
    risk_profile: str

    market_data: Dict[str, Any]
    macro_data: Dict[str, Any]
    risk_analysis: Dict[str, Any]
    scenarios: Dict[str, Any]

    recommendation: str
    confidence_score: float
    memo: str
```

> 📌 This is what LangGraph passes between agents.

---

## PHASE 3 — Market Data Agent (Day 1)

### 3.1 Agent responsibility

- Populate `market_data` only
- No opinions
- No recommendation

### 3.2 Implementation

**Create `agents/market_data_agent.py`**

**Steps:**

1. Fetch data via yfinance
2. Compute indicators
3. Return structured dictionary
4. Update state

✅ **Checkpoint**: `state["market_data"]` is complete and JSON-serializable.

---

## PHASE 4 — Macro Trends Agent (Day 2)

### 4.1 Data sources

- FRED (rates, CPI)
- Sector ETF performance (XLK, XLF)
- News sentiment (simple LLM summary or FinBERT)

### 4.2 Output schema

```json
{
  "interest_rate_trend": "Rising",
  "inflation_trend": "Cooling",
  "sector_performance": "Outperforming",
  "news_sentiment": "Neutral-positive"
}
```

### 4.3 Implementation

**Create `agents/macro_trends_agent.py`**

✅ **Checkpoint**: Macro agent runs independently.

---

## PHASE 5 — Risk Analyst Agent (Day 3)

### 5.1 Metrics to compute

- Volatility
- Beta vs S&P 500
- Max drawdown
- Event risk list (LLM assisted)

### 5.2 Tools

- numpy, scipy
- Market returns via yfinance

### 5.3 Output

```json
{
  "volatility": 0.32,
  "beta": 1.18,
  "drawdown": "Medium",
  "key_risks": ["Rate hikes", "Earnings miss"]
}
```

✅ **Checkpoint**: Risk metrics numerically correct.

---

## PHASE 6 — Scenario Analysis Agent (Day 4)

### 6.1 Scenarios

- Bull
- Base
- Bear

### 6.2 Logic

- Combine market + macro + risk
- Estimate expected returns
- Assign probabilities

### 6.3 Output

```json
{
  "bull": {"return": 0.25, "prob": 0.25},
  "base": {"return": 0.08, "prob": 0.50},
  "bear": {"return": -0.18, "prob": 0.25}
}
```

> 📌 This is where your quant + LLM hybrid reasoning shines.

---

## PHASE 7 — Confidence Scoring (Day 4)

### 7.1 Inputs

- Data completeness
- Agent agreement
- Volatility penalty

### 7.2 Formula

```python
confidence = (
    completeness * 0.3 +
    agreement * 0.4 +
    (1 - volatility) * 0.3
)
```

> 📌 Store this in `state["confidence_score"]`

---

## PHASE 8 — Investment Memo Writer (Day 5)

### 8.1 Prompt structure

1. Executive summary
2. Thesis
3. Supporting data
4. Risks
5. Scenarios
6. Recommendation
7. Disclaimer

### 8.2 Output

- Clean Markdown
- Professional tone
- No hype language

### 8.3 Save output

`outputs/{ticker}_memo.md`

---

## PHASE 9 — LangGraph Orchestration (Day 5)

**Create `graph/research_graph.py`**

**Graph flow:**

```
Start
 → MarketDataAgent
 → MacroTrendsAgent
 → RiskAgent
 → ScenarioAgent
 → MemoWriterAgent
 → End
```

**Add:**

- Typed state
- Deterministic edges
- Error handling

✅ **Checkpoint**: `main.py` runs end-to-end.

---

## PHASE 10 — README & Resume Polish (Day 6)

**README must include:**

- Architecture diagram
- Agent responsibilities
- Sample output
- Disclaimer
- How to run

**Resume bullet:**

> Built a multi-agent AI financial research system using LangGraph to generate structured investment theses with risk modeling and scenario analysis

---

## PHASE 11 — Optional Enhancements (Only if time allows)

- Streamlit UI
- PDF export
- Multi-ticker comparison
- Human-in-the-loop overrides

---

## Final Advice (Important)

If you build 80% of this cleanly, it beats:

- 10 Kaggle notebooks
- 5 fine-tuning demos
- 20 prompt engineering repos

**This is industry-grade AI engineering.**

---

# VERSION 2 — Web Interface (React + TypeScript + Node.js)

## Overview

Build a modern web interface **alongside** the existing CLI, allowing users to interact with the financial research analyst through a browser. Both CLI and web interface will use the same Python backend analysis engine.

## Tech Stack

### Frontend
- **Framework**: React 18+ with TypeScript
- **Language**: TypeScript (.tsx for components, .ts for utilities)
- **Styling**: Bootstrap 5 (with react-bootstrap components)
- **State Management**: React Hooks (useState, useEffect)
- **HTTP Client**: Fetch API (native, no axios needed)
- **Build Tool**: Vite with TypeScript support

### Backend
- **Runtime**: Node.js 18+
- **Framework**: Express.js
- **API**: RESTful API endpoints
- **Python Integration**: Child process execution or Python HTTP server
- **CORS**: Enable CORS for frontend-backend communication

### Architecture
- **Frontend**: React SPA (Single Page Application)
- **Backend**: Express.js API server
- **Python Service**: Existing Python analysis engine (unchanged, shared by both CLI and web)
- **CLI**: Existing `main.py` continues to work independently
- **Communication**: 
  - CLI: Direct Python execution (unchanged)
  - Web: HTTP REST API → Express → Python subprocess/HTTP
  - Both use the same Python analysis codebase

---

## PHASE 0 — Web Project Setup (2–3 hours)

### 0.1 Repository Structure

```
analyst/
├── backend/              # Node.js Express API (TypeScript)
│   ├── src/
│   │   ├── routes/
│   │   │   └── analysis.ts
│   │   ├── services/
│   │   │   └── pythonService.ts
│   │   ├── middleware/
│   │   │   └── cors.ts
│   │   └── server.ts
│   ├── package.json
│   ├── tsconfig.json
│   └── .env
│
├── frontend/             # React application (TypeScript)
│   ├── src/
│   │   ├── components/
│   │   │   ├── TickerInput.tsx
│   │   │   ├── HorizonSelect.tsx
│   │   │   ├── RiskProfileSelect.tsx
│   │   │   ├── AnalysisButton.tsx
│   │   │   ├── ResultsDisplay.tsx
│   │   │   ├── ScenarioCard.tsx
│   │   │   └── MemoViewer.tsx
│   │   ├── services/
│   │   │   └── api.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
├── [existing Python code remains unchanged]
└── README.md
```

### 0.2 API Design

**Endpoint**: `POST /api/analyze`

**Request Body**:
```json
{
  "ticker": "AAPL",
  "horizon": "medium",
  "risk_profile": "moderate"
}
```

**Response Options**:

**Option A: Standard Response** (Simple, but no real-time progress)
```json
{
  "status": "success",
  "data": {
    "recommendation": "Buy",
    "confidence_score": 0.72,
    "scenarios": {...},
    "memo": "...",
    "market_data": {...},
    "macro_data": {...},
    "risk_analysis": {...}
  },
  "timing": {
    "total_time": 245.3,
    "llm_warmup": 120.5,
    "analysis_pipeline": 124.8
  }
}
```

**Option B: Server-Sent Events (SSE)** (Recommended for progress)
- Endpoint: `POST /api/analyze` with `Accept: text/event-stream` header
- Streams progress events in real-time:
```
event: progress
data: {"step": "market_data", "message": "Fetching data for AAPL...", "timestamp": 1234567890}

event: progress
data: {"step": "market_data", "message": "[OK] Fetched 250 days of data in 0.8s", "timestamp": 1234567891}

event: progress
data: {"step": "macro_trends", "message": "Analyzing macroeconomic conditions...", "timestamp": 1234567892}

event: complete
data: {"status": "success", "data": {...}, "timing": {...}}
```

**Option C: WebSocket** (Most flexible, but more complex)
- Connection: `ws://localhost:3001/ws`
- Messages: Bidirectional communication for progress updates

**Recommendation**: Start with **Option B (SSE)** for real-time progress updates without the complexity of WebSockets.

**Error Response**:
```json
{
  "status": "error",
  "message": "Invalid ticker symbol",
  "error": "..."
}
```

---

## PHASE 1 — Backend API (1 day)

### 1.1 Express.js Server Setup

**Create `backend/src/server.ts`**

- Initialize Express app with TypeScript
- Configure CORS middleware
- Set up body parser (JSON)
- Define port (default: 3001)
- Health check endpoint: `GET /api/health`
- Add TypeScript types for Express

### 1.2 Python Service Integration

**Create `backend/src/services/pythonService.ts`**

**Options**:

**Option A: Child Process** (Simpler)
```typescript
import { spawn } from 'child_process';
import path from 'path';

interface AnalysisResult {
  recommendation: string;
  confidence_score: number;
  scenarios: Record<string, { return: number; prob: number }>;
  memo: string;
  timing?: Record<string, number>;
}

function runAnalysis(
  ticker: string, 
  horizon: string, 
  riskProfile: string
): Promise<AnalysisResult> {
  return new Promise((resolve, reject) => {
    const pythonProcess = spawn('python', [
      path.join(__dirname, '../../main.py'),
      ticker,
      horizon,
      riskProfile
    ]);
    
    // Capture stdout/stderr and parse JSON
    // Handle errors and timeouts
  });
}
```

**Option B: Python HTTP Server** (More scalable)
- Create `api_server.py` using Flask/FastAPI
- Expose REST endpoint that wraps existing analysis
- Backend (TypeScript) calls Python service via HTTP

**Recommendation**: Start with Option A, migrate to Option B if needed.

**TypeScript Setup for Backend**:
- Install TypeScript: `npm install -D typescript @types/node @types/express`
- Create `tsconfig.json` with Node.js and Express types
- Use ES modules (`"type": "module"` in package.json)
- Compile TypeScript or use `ts-node` for development

### 1.3 Analysis Route

**Create `backend/src/routes/analysis.ts`**

**Standard Endpoint**: `POST /api/analyze`
- Validate input (ticker, horizon, risk_profile)
- Call Python service (same `main.py` that CLI uses)
- Parse Python output (JSON or stdout)
- Return formatted response
- Error handling and timeout (15 minutes max)

**Progress Streaming Endpoint**: `POST /api/analyze/stream` or `GET /api/analyze/stream`
- Same validation and Python execution
- **Capture stdout/stderr in real-time** from Python process (line by line)
- Stream progress events to client via Server-Sent Events (SSE)
- Parse progress messages (e.g., "[Market Data Agent] Fetching data...")
- Send progress events: `event: progress`, `data: {step, message, timestamp}`
- Send completion event with final results
- Handle errors and stream error events

**Implementation Approach**:
```typescript
// Capture Python stdout line by line
pythonProcess.stdout.on('data', (data: Buffer) => {
  const message = data.toString();
  // Parse progress messages from CLI output
  // Send SSE event to client
  res.write(`event: progress\n`);
  res.write(`data: ${JSON.stringify({step, message, timestamp: Date.now()})}\n\n`);
});
```

**Note**: The backend calls the exact same `main.py` that the CLI uses, ensuring identical results and progress messages.

### 1.4 Testing

- Test with Postman/curl
- Verify Python integration works
- Test error cases (invalid ticker, timeout, etc.)
- **Verify CLI still works independently**: `python main.py AAPL medium moderate`

✅ **Checkpoint**: Backend API accepts requests and returns analysis results. CLI continues to work unchanged.

---

## PHASE 2 — Frontend UI (2 days)

### 2.1 React Setup with TypeScript

**Create React app with TypeScript**:
```bash
cd frontend
npm create vite@latest . -- --template react-ts
```

**Install dependencies**:
- `bootstrap` and `react-bootstrap` for styling
- `react-markdown` for memo rendering
- TypeScript types: `@types/react`, `@types/react-dom`
- No axios needed (use native Fetch API)

### 2.2 Input Components (TypeScript + Bootstrap)

**Create `frontend/src/components/TickerInput.tsx`**
- Text input for stock ticker using Bootstrap `Form.Control`
- TypeScript props interface
- Validation (uppercase, alphanumeric)
- Auto-format to uppercase
- Error messages with Bootstrap `Alert`

**Create `frontend/src/components/HorizonSelect.tsx`**
- Dropdown using Bootstrap `Form.Select`
- TypeScript props with union types: `'short' | 'medium' | 'long'`
- Options: Short, Medium, Long
- Default: Medium

**Create `frontend/src/components/RiskProfileSelect.tsx`**
- Dropdown using Bootstrap `Form.Select`
- TypeScript props with union types: `'conservative' | 'moderate' | 'aggressive'`
- Options: Conservative, Moderate, Aggressive
- Default: Moderate

### 2.3 API Service (TypeScript)

**Create `frontend/src/services/api.ts`**

**TypeScript Interfaces**:
```typescript
interface ProgressData {
  step: string;
  message: string;
  timestamp: number;
}

interface AnalysisResults {
  recommendation: string;
  confidence_score: number;
  scenarios: Record<string, { return: number; prob: number }>;
  memo: string;
  timing?: Record<string, number>;
}
```

**Standard API Call** (for simple requests):
```typescript
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:3001/api';

export const analyzeStock = async (
  ticker: string, 
  horizon: string, 
  riskProfile: string
): Promise<AnalysisResults> => {
  const response = await fetch(`${API_BASE_URL}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticker, horizon, risk_profile: riskProfile })
  });
  
  if (!response.ok) {
    throw new Error('Analysis failed');
  }
  
  return response.json();
};
```

**SSE Progress Stream** (for real-time progress updates):
```typescript
export const analyzeStockWithProgress = (
  ticker: string,
  horizon: string,
  riskProfile: string,
  onProgress: (data: ProgressData) => void,
  onComplete: (data: AnalysisResults) => void,
  onError: (error: Error) => void
) => {
  // Use fetch with ReadableStream for POST + SSE
  // (EventSource only supports GET)
  // Implementation uses fetch streaming for POST requests
};
```

**Note**: For POST with SSE, use `fetch` with ReadableStream since EventSource only supports GET requests.

### 2.4 Main App Component (TypeScript + Bootstrap)

**Update `frontend/src/App.tsx`**
- TypeScript component with typed state
- Combine input components using Bootstrap `Form` components
- Submit button using Bootstrap `Button`
- **Progress display** (show real-time updates during analysis)
- Loading state (show Bootstrap spinner during analysis)
- Error handling with Bootstrap `Alert`
- Results display using Bootstrap `Card` components
- State management for progress updates with TypeScript types

### 2.5 Progress Display Component (TypeScript + Bootstrap)

**Create `frontend/src/components/ProgressDisplay.tsx`**
- TypeScript component with typed props
- Real-time progress updates (using SSE streaming)
- Show current step (e.g., "Market Data Agent", "Macro Trends Agent")
- Display progress messages using Bootstrap `ListGroup` or `Card`
- Progress bar using Bootstrap `Progress` component
- Timing information for each step
- Auto-scroll progress log
- Example messages to display:
  - "Warming up LLM (preloading model)..."
  - "[Market Data Agent] Fetching data for AAPL..."
  - "[OK] Fetched 250 days of data in 0.8s"
  - "[Macro Trends Agent] Analyzing sentiment with LLM..."
  - "[Risk Analyst Agent] Computing risk metrics..."
  - "[Scenario Agent] Generating Bull/Base/Bear scenarios..."
  - "[Memo Writer Agent] Writing memo with LLM..."
  - etc.

### 2.6 Results Display Components (TypeScript + Bootstrap)

**Create `frontend/src/components/ResultsDisplay.tsx`**
- TypeScript component with typed props for results
- Display recommendation (Buy/Hold/Sell) using Bootstrap badges/colors
- Show confidence score using Bootstrap `Progress` component
- Display scenarios in Bootstrap `Card` components
- Link to memo viewer using Bootstrap `Button`
- Show timing breakdown in Bootstrap `ListGroup`

**Create `frontend/src/components/ScenarioCard.tsx`**
- TypeScript component with typed props
- Individual scenario card using Bootstrap `Card`
- Show return percentage and probability
- Visual indicators using Bootstrap colors and badges

**Create `frontend/src/components/MemoViewer.tsx`**
- TypeScript component with typed props
- Display investment memo in Bootstrap `Card`
- Markdown rendering using `react-markdown`
- Expandable/collapsible sections using Bootstrap `Accordion` (optional)
- Download as PDF option (optional)

### 2.7 Styling with Bootstrap

- Use Bootstrap 5 utility classes and components
- Responsive design (Bootstrap's grid system)
- Loading animations (Bootstrap spinners)
- Error states (Bootstrap `Alert` components)
- Success states (Bootstrap badges and colors)
- Custom theme colors can be added via Bootstrap CSS variables
- No custom CSS files needed (all styling via Bootstrap classes)

✅ **Checkpoint**: Frontend can submit analysis requests and display results.

---

## PHASE 3 — Integration & Polish (1 day)

### 3.1 Real-time Updates (Optional)

- WebSocket or Server-Sent Events for progress updates
- Show which agent is currently running
- Display timing information in real-time

### 3.2 Error Handling

- Network errors
- Timeout handling (show user-friendly message)
- Invalid input validation
- Python service errors

### 3.3 Performance

- Request cancellation if user navigates away
- Caching recent analyses (optional)
- Optimize bundle size

### 3.4 Testing

- Test full flow: input → API → Python → results
- Test error scenarios
- Test on different browsers
- Mobile responsiveness

---

## PHASE 4 — Deployment Preparation (Optional, 1 day)

### 4.1 Environment Configuration

- Environment variables for API URLs
- Production build configuration
- Docker setup (optional)

### 4.2 Documentation

- Update README with web interface instructions
- API documentation
- Frontend component documentation

### 4.3 Deployment Options

- **Local**: Run both servers locally
- **Cloud**: Deploy backend to Heroku/Railway, frontend to Vercel/Netlify
- **Docker**: Containerize both services

---

## Key Features

### User Experience
- ✅ Simple, intuitive interface
- ✅ Real-time feedback (loading states)
- ✅ Clear error messages
- ✅ Professional results display
- ✅ Responsive design

### Technical
- ✅ RESTful API architecture
- ✅ Separation of concerns (frontend/backend/Python)
- ✅ Error handling and validation
- ✅ Scalable structure (can migrate to microservices later)

---

# VERSION 3 — Hybrid LLM Layer (Gemini + Hugging Face)

## Overview

Replace Ollama with a hybrid LLM layer using cloud-based APIs:
- **Gemini (free tier)** → reasoning-critical agents
- **Hugging Face (free model)** → lightweight generation agents

This eliminates the need for:
- Local Ollama installation
- GPU requirements
- Local model warmup
- Long startup times

Both CLI and web interface will use the same hybrid LLM layer without breaking:
- LangGraph orchestration
- Agent boundaries
- Web UI functionality
- Streaming updates

---

## Agent → LLM Mapping

| Agent | Role | Model | Rationale |
|-------|------|-------|-----------|
| **Macro Sentiment** | LIGHT | **HF Mistral** | Simple sentiment analysis, no complex reasoning needed |
| **Risk Agent** | REASONING | **Gemini Flash** | Requires structured risk analysis and constraint enforcement |
| **Scenario Agent** | REASONING | **Gemini Flash** | Complex scenario generation with probability assignments |
| **Memo Writer** | WRITING | **Gemini Flash** | Professional writing with structured format requirements |

---

## Prompt Rules

### Hugging Face (Mistral) Prompt Rules

**Use for**: Macro Sentiment Agent only

**Guidelines**:
- ✅ One task only (single, focused objective)
- ✅ Short prompts (concise, no unnecessary context)
- ✅ No reasoning chains (direct output, no step-by-step thinking)
- ✅ Simple JSON output format

**Example Structure**:
```
Analyze the sentiment of the following news headlines for {ticker}:
{headlines}

Return JSON: {"sentiment": "positive|neutral|negative", "score": 0.0-1.0}
```

### Gemini (Flash) Prompt Rules

**Use for**: Risk Agent, Scenario Agent, Memo Writer

**Guidelines**:
- ✅ Explicit schema (define exact output structure)
- ✅ Enforce constraints (validation rules, format requirements)
- ✅ Structured reasoning (when needed for complex tasks)
- ✅ JSON mode when possible (for structured outputs)

**Example Structure**:
```
You are a financial risk analyst. Analyze the following data:
{market_data}
{macro_data}

Return JSON with this exact schema:
{
  "volatility": float,
  "beta": float,
  "drawdown": "Low|Medium|High",
  "key_risks": [string],
  "reasoning": string
}

Constraints:
- volatility must be between 0.0 and 1.0
- beta must be a positive number
- key_risks must contain 2-5 items
```

---

## What's No Longer Needed

### Removed Dependencies
- ❌ Ollama (local installation)
- ❌ `langchain-ollama` package
- ❌ GPU requirements
- ❌ Local model warmup time
- ❌ Long startup delays

### Updated Dependencies
- ✅ `google-generativeai` (Gemini API)
- ✅ `huggingface_hub` or `transformers` (Hugging Face API)
- ✅ API keys in `.env` (no local model management)

---

## PHASE 0 — API Setup & Configuration (2–3 hours)

### 0.1 API Keys & Environment

**Update `.env`**:
```env
# Remove Ollama
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_MODEL=deepseek-r1:8b

# Add Gemini
GEMINI_API_KEY=xxx

# Add Hugging Face (optional, if using Inference API)
HUGGINGFACE_API_KEY=xxx

# Keep existing
FRED_API_KEY=xxx
```

### 0.2 Install Dependencies

**Update `requirements.txt`**:
```txt
# Remove
# langchain-ollama

# Add
google-generativeai>=0.3.0
huggingface_hub>=0.20.0
# OR transformers>=4.35.0 (if using local HF models)

# Keep existing
langgraph
langchain
yfinance
pandas
numpy
scipy
pandas-ta
fredapi
```

### 0.3 LLM Service Layer

**Create `services/llm_service.py`**:
- Abstract LLM interface
- Gemini client wrapper
- Hugging Face client wrapper
- Agent-to-model routing logic
- Error handling and retries
- Rate limiting (for free tier limits)

---

## PHASE 1 — Update Agents (1 day)

### 1.1 Macro Sentiment Agent → Hugging Face

**Update `agents/macro_trends_agent.py`**:
- Replace Ollama calls with Hugging Face Mistral
- Use simple, direct prompts (no reasoning chains)
- Parse JSON output
- Handle API errors gracefully

**Prompt Template**:
```
Analyze sentiment for {ticker} based on:
- Interest rate trend: {rate_trend}
- Inflation trend: {inflation_trend}
- Sector performance: {sector_perf}

Return JSON: {"sentiment": "positive|neutral|negative", "score": 0.0-1.0}
```

### 1.2 Risk Agent → Gemini Flash

**Update `agents/risk_agent.py`**:
- Replace Ollama with Gemini Flash
- Use explicit schema for risk metrics
- Enforce constraints (volatility range, beta validation)
- Structured JSON output

**Prompt Template**:
```
Analyze risk for {ticker}:
{market_data}
{macro_data}

Return JSON schema:
{
  "volatility": float (0.0-1.0),
  "beta": float (>0),
  "drawdown": "Low|Medium|High",
  "key_risks": [string, 2-5 items],
  "reasoning": string
}
```

### 1.3 Scenario Agent → Gemini Flash

**Update `agents/scenario_agent.py`**:
- Replace Ollama with Gemini Flash
- Use explicit schema for scenarios
- Enforce probability constraints (must sum to 1.0)
- Structured reasoning for probability assignments

**Prompt Template**:
```
Generate scenarios for {ticker}:
{market_data}
{macro_data}
{risk_analysis}

Return JSON schema:
{
  "bull": {"return": float, "prob": float},
  "base": {"return": float, "prob": float},
  "bear": {"return": float, "prob": float}
}

Constraints:
- prob values must sum to 1.0
- return values as decimals (e.g., 0.25 for 25%)
```

### 1.4 Memo Writer → Gemini Flash

**Update `agents/memo_writer_agent.py`**:
- Replace Ollama with Gemini Flash
- Use structured markdown format
- Enforce professional tone
- Include all required sections

**Prompt Template**:
```
Write investment memo for {ticker}:
{all_analysis_data}

Format: Markdown with sections:
1. Executive Summary
2. Thesis
3. Supporting Data
4. Risks
5. Scenarios
6. Recommendation
7. Disclaimer

Tone: Professional, no hype language
```

✅ **Checkpoint**: All agents use new LLM services. No Ollama dependencies remain.

---

## PHASE 2 — Update LangGraph (2–3 hours)

### 2.1 Graph State (No Changes)

**`schemas/state.py`** remains unchanged:
- State structure is LLM-agnostic
- Agents still populate same fields

### 2.2 Graph Flow (No Changes)

**`graph/research_graph.py`** remains unchanged:
- Agent execution order unchanged
- Edge logic unchanged
- Error handling may need API-specific retries

### 2.3 Error Handling Updates

- Add retry logic for API rate limits
- Handle API timeouts (different from Ollama timeouts)
- Graceful degradation if API unavailable

---

## PHASE 3 — Update Web Interface (1–2 hours)

### 3.1 Backend API (No Changes)

**`backend/src/services/pythonService.ts`**:
- No changes needed (calls same Python code)
- Python service now uses Gemini/HF instead of Ollama

### 3.2 Progress Updates

**Update progress messages**:
- Remove "Warming up LLM" messages
- Update timing information (no warmup time)
- Show API call progress instead

**Example Progress Messages**:
```
[Macro Sentiment Agent] Calling Hugging Face API...
[OK] Sentiment analysis complete in 0.5s
[Risk Agent] Calling Gemini API...
[OK] Risk analysis complete in 1.2s
```

### 3.3 Frontend (No Changes)

**Frontend components** remain unchanged:
- Same API endpoints
- Same response format
- Same UI components

---

## PHASE 4 — Testing & Validation (1 day)

### 4.1 Functional Testing

- ✅ All agents produce correct outputs
- ✅ JSON schemas validated
- ✅ Constraints enforced (probabilities sum to 1.0, etc.)
- ✅ Memo format is correct

### 4.2 Performance Testing

- ✅ Compare timing: Ollama (with warmup) vs. API calls
- ✅ Measure API latency
- ✅ Test rate limiting behavior
- ✅ Verify no warmup delays

### 4.3 Error Handling

- ✅ API key errors
- ✅ Rate limit errors
- ✅ Network timeouts
- ✅ Invalid API responses

### 4.4 CLI & Web Interface

- ✅ CLI still works: `python main.py AAPL medium moderate`
- ✅ Web interface still works
- ✅ Streaming updates work
- ✅ Both produce identical results

---

## PHASE 5 — Documentation & Cleanup (2–3 hours)

### 5.1 Update README

- Remove Ollama installation instructions
- Add API key setup instructions
- Update dependencies list
- Add API rate limit notes (free tier limits)

### 5.2 Remove Ollama Files

- Remove any Ollama-specific configuration
- Clean up unused imports
- Update `.gitignore` if needed

### 5.3 Environment Template

**Update `.env.example`**:
```env
# LLM APIs
GEMINI_API_KEY=your_gemini_api_key_here
HUGGINGFACE_API_KEY=your_hf_api_key_here

# Data APIs
FRED_API_KEY=your_fred_api_key_here
```

---

## Timeline Summary

| Phase | Task | Estimated Time |
|-------|------|----------------|
| **Phase 0** | API Setup & Configuration | 2–3 hours |
| **Phase 1** | Update All Agents | 1 day |
| **Phase 2** | Update LangGraph | 2–3 hours |
| **Phase 3** | Update Web Interface | 1–2 hours |
| **Phase 4** | Testing & Validation | 1 day |
| **Phase 5** | Documentation & Cleanup | 2–3 hours |
| **Total** | | **~3–4 days** |

---

## Benefits of Version 3

### Performance
- ✅ No model warmup (instant API calls)
- ✅ Faster startup (no local model loading)
- ✅ Consistent latency (API-based, no GPU variability)

### Scalability
- ✅ No local resource constraints
- ✅ Can handle concurrent requests
- ✅ Easy to deploy (no GPU requirements)

### Cost
- ✅ Free tier available for both APIs
- ✅ Pay-as-you-go for higher usage
- ✅ No infrastructure costs

### Maintenance
- ✅ No model updates to manage
- ✅ No GPU driver issues
- ✅ Simpler deployment

---

## Migration Checklist

- [ ] Get Gemini API key
- [ ] Get Hugging Face API key (if needed)
- [ ] Update `requirements.txt`
- [ ] Create `services/llm_service.py`
- [ ] Update Macro Sentiment Agent → HF
- [ ] Update Risk Agent → Gemini
- [ ] Update Scenario Agent → Gemini
- [ ] Update Memo Writer → Gemini
- [ ] Update error handling in LangGraph
- [ ] Update progress messages
- [ ] Test all agents
- [ ] Test CLI
- [ ] Test web interface
- [ ] Update README
- [ ] Remove Ollama dependencies
- [ ] Update `.env.example`

---

## Future Enhancements (Version 2.1+)

- User authentication and saved analyses
- Comparison tool (multiple tickers)
- Historical analysis tracking
- Export to PDF/Excel
- Email notifications
- Dashboard with analytics
- Real-time stock price updates

---

# VERSION 2.1 — Stock Statistics Display

## Overview

Enhance the web interface to display key stock statistics prominently, including:
- Current price
- 52-week high and low
- Additional relevant metrics (P/E ratio, market cap, etc.)

This provides users with immediate context about the stock being analyzed without needing to scroll through the full analysis.

---

## Features to Add

### Stock Statistics Display

**Location**: Top of ResultsDisplay component, before recommendation

**Statistics to Display**:

| Statistic | Source | Format |
|-----------|--------|--------|
| **Current Price** | `market_data.valuation.current_price` | Currency ($XXX.XX) |
| **52-Week High** | `market_data.valuation.52_week_high` | Currency ($XXX.XX) |
| **52-Week Low** | `market_data.valuation.52_week_low` | Currency ($XXX.XX) |
| **P/E Ratio** | `market_data.valuation.pe_ratio` | Decimal (XX.XX) |
| **Market Cap** | `market_data.valuation.market_cap` | Formatted (e.g., "1.5T", "250B") |
| **Dividend Yield** | `market_data.valuation.dividend_yield` | Percentage (X.XX%) |

**Optional Additional Stats** (if available):
- Forward P/E
- Price-to-Book (P/B)
- Price-to-Sales (P/S)

---

## PHASE 0 — Planning & Design (30 minutes)

### 0.1 Component Design

- Create `StockStats.tsx` component OR add section to `ResultsDisplay.tsx`
- Design using Bootstrap Cards/Grid
- Responsive layout (mobile-friendly)

### 0.2 Data Structure

- Verify `market_data` is included in API response
- Map data fields from Python backend to TypeScript interface
- Handle missing/null values gracefully

---

## PHASE 1 — Backend Verification (30 minutes)

### 1.1 Verify Data Availability

- Check `tools/market_data.py` - verify `get_valuation_metrics()` returns required fields
- Verify `market_data` is included in API response
- Test with sample ticker (AAPL)

### 1.2 Update TypeScript Interfaces

- Update `AnalysisResults` interface in `api.ts` if needed
- Add type definitions for stock statistics

✅ **Checkpoint**: Backend provides all required stock statistics.

---

## PHASE 2 — Frontend Implementation (1-2 hours)

### 2.1 Create StockStats Component

**Create `web/frontend/src/components/StockStats.tsx`**

- TypeScript component with typed props
- Bootstrap Card layout
- Grid system for responsive display
- Format numbers/currency correctly
- Handle missing values (show "N/A")

**Component Structure**:
```tsx
interface StockStatsProps {
  marketData?: {
    valuation?: {
      current_price?: number
      "52_week_high"?: number
      "52_week_low"?: number
      pe_ratio?: number
      market_cap?: number
      dividend_yield?: number
      // ... other optional fields
    }
  }
}
```

### 2.2 Integrate into ResultsDisplay

- Import StockStats component
- Add before recommendation section
- Pass `market_data` prop

### 2.3 Styling

- Use Bootstrap utility classes
- Highlight current price prominently
- Show 52-week range with visual indicators
- Consistent spacing and typography

✅ **Checkpoint**: Stock statistics display correctly in web interface.

---

## PHASE 3 — Testing & Polish (30 minutes)

### 3.1 Testing

- Test with multiple tickers (AAPL, MSFT, TSLA)
- Verify all statistics display correctly
- Test with missing/null values
- Test responsive design (mobile/tablet/desktop)

### 3.2 Polish

- Format numbers consistently
- Add loading states if needed
- Error handling for missing data
- Visual indicators (e.g., price vs 52-week range)

✅ **Checkpoint**: Feature complete and tested.

---

## Implementation Notes

### Data Formatting

- **Currency**: Use `toLocaleString('en-US', { style: 'currency', currency: 'USD' })`
- **Market Cap**: Format large numbers (B for billions, T for trillions)
- **Percentages**: Format dividend yield as percentage
- **Decimals**: Limit to 2 decimal places for prices, ratios

### Error Handling

- If `market_data` is missing: Don't show component or show "Data unavailable"
- If individual stats missing: Show "N/A" for that specific stat
- Graceful degradation

### Visual Design

- Use Bootstrap Cards for grouping
- Consider color coding (e.g., green for current price if near 52-week high)
- Keep it clean and scannable
- Don't overwhelm with too many stats

---

## Timeline

| Phase | Estimated Time |
|-------|----------------|
| Planning & Design | 30 minutes |
| Backend Verification | 30 minutes |
| Frontend Implementation | 1-2 hours |
| Testing & Polish | 30 minutes |
| **Total** | **2.5-3.5 hours** |

---

## Future Enhancements (Version 2.2+)

- Historical price chart
- Comparison with sector averages
- Price change indicators (daily/weekly/monthly)
- Technical indicators visualization
