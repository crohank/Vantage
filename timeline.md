# 2-Week Implementation Timeline
## AI-Powered Financial Research Analyst Team

---

## Week 1: Foundation & Core Agents

### **Day 1 (Monday) — Project Setup & Foundation**
**Time: 4-6 hours**

**Morning (2-3 hours)**
- [ ] **PHASE 0**: Project Definition
  - [ ] Lock scope: Input/Output specifications
  - [ ] Confirm tech stack: Python 3.10+, LangGraph, Ollama
  - [ ] Create repository structure (all directories and empty files)
  - [ ] Initialize git repository

- [ ] **PHASE 1.1**: Environment Setup
  - [ ] Create virtual environment
  - [ ] Install Ollama (if needed)
  - [ ] Pull Ollama model: `ollama pull deepseek-r1:8b`
  - [ ] Install dependencies: `pip install langgraph langchain langchain-ollama yfinance pandas numpy scipy pandas-ta fredapi`
  - [ ] Create `.env` file with OLLAMA_BASE_URL, OLLAMA_MODEL, FRED_API_KEY
  - [ ] Create `requirements.txt`
  - [ ] Create `config.py` with LLM initialization function

**Afternoon (2-3 hours)**
- [ ] **PHASE 1.2**: Market Data Tooling
  - [ ] Create `tools/market_data.py`
  - [ ] Implement price history fetching (yfinance)
  - [ ] Implement valuation metrics (P/E, P/B, etc.)
  - [ ] Implement technical indicators (RSI, moving averages using pandas-ta)
  - [ ] Test with sample ticker (AAPL)
  - [ ] ✅ **Checkpoint**: Can fetch and print clean metrics for a ticker

- [ ] **PHASE 2**: Define Shared State
  - [ ] Create `schemas/state.py`
  - [ ] Define `ResearchState` TypedDict
  - [ ] Document state structure

---

### **Day 2 (Tuesday) — Market Data Agent**
**Time: 4-5 hours**

**Morning (2-3 hours)**
- [ ] **PHASE 3**: Market Data Agent
  - [ ] Create `agents/market_data_agent.py`
  - [ ] Implement agent function that:
    - Takes state as input
    - Calls market data tools
    - Computes indicators
    - Returns updated state with `market_data` populated
  - [ ] Add error handling
  - [ ] Test agent independently

**Afternoon (2 hours)**
- [ ] Create `tools/macro_data.py` (preparation for Day 3)
  - [ ] FRED API integration setup
  - [ ] Sector ETF data fetching (XLK, XLF)
  - [ ] Basic structure for sentiment analysis

- [ ] ✅ **Checkpoint**: `state["market_data"]` is complete and JSON-serializable

---

### **Day 3 (Wednesday) — Macro Trends Agent**
**Time: 4-5 hours**

**Morning (2-3 hours)**
- [ ] **PHASE 4**: Macro Trends Agent
  - [ ] Complete `tools/macro_data.py`
    - [ ] FRED API: interest rates, CPI data
    - [ ] Sector ETF performance comparison
    - [ ] News sentiment (simple LLM summary using ChatOllama)
  - [ ] Create `agents/macro_trends_agent.py`
  - [ ] Implement agent to populate `macro_data` in state
  - [ ] Test with sample data

**Afternoon (2 hours)**
- [ ] Create `tools/risk_metrics.py` (preparation for Day 4)
  - [ ] Volatility calculation function
  - [ ] Beta calculation function
  - [ ] Max drawdown calculation function

- [ ] ✅ **Checkpoint**: Macro agent runs independently

---

### **Day 4 (Thursday) — Risk Analyst Agent**
**Time: 4-5 hours**

**Morning (2-3 hours)**
- [ ] **PHASE 5**: Risk Analyst Agent
  - [ ] Complete `tools/risk_metrics.py`
    - [ ] Implement volatility (annualized)
    - [ ] Implement beta vs S&P 500
    - [ ] Implement max drawdown calculation
  - [ ] Create `agents/risk_agent.py`
  - [ ] Implement LLM-assisted event risk identification
  - [ ] Populate `risk_analysis` in state
  - [ ] Test risk calculations with known values

**Afternoon (2 hours)**
- [ ] **PHASE 7**: Confidence Scoring (start early)
  - [ ] Design confidence scoring function
  - [ ] Implement data completeness check
  - [ ] Implement agent agreement metric (placeholder)
  - [ ] Add volatility penalty calculation

- [ ] ✅ **Checkpoint**: Risk metrics numerically correct

---

### **Day 5 (Friday) — Scenario Analysis & Confidence**
**Time: 4-5 hours**

**Morning (2-3 hours)**
- [ ] **PHASE 6**: Scenario Analysis Agent
  - [ ] Create `agents/scenario_agent.py`
  - [ ] Implement scenario logic:
    - [ ] Combine market + macro + risk data
    - [ ] Use LLM to estimate expected returns for Bull/Base/Bear
    - [ ] Assign probabilities to scenarios
  - [ ] Populate `scenarios` in state
  - [ ] Test scenario generation

**Afternoon (2 hours)**
- [ ] **PHASE 7**: Complete Confidence Scoring
  - [ ] Finalize confidence formula implementation
  - [ ] Integrate into scenario agent or create separate function
  - [ ] Store `confidence_score` in state
  - [ ] Test confidence calculation

- [ ] ✅ **Checkpoint**: Scenarios generated with probabilities

---

## Week 2: Integration, Memo, & Polish

### **Day 6 (Monday) — Memo Writer Agent**
**Time: 4-5 hours**

**Morning (2-3 hours)**
- [ ] **PHASE 8**: Investment Memo Writer
  - [ ] Create `agents/memo_writer_agent.py`
  - [ ] Design prompt structure:
    - [ ] Executive summary
    - [ ] Thesis
    - [ ] Supporting data
    - [ ] Risks
    - [ ] Scenarios
    - [ ] Recommendation (Buy/Hold/Sell)
    - [ ] Disclaimer
  - [ ] Implement memo generation using ChatOllama
  - [ ] Ensure professional tone, no hype language

**Afternoon (2 hours)**
- [ ] Implement memo saving:
  - [ ] Create `outputs/` directory if needed
  - [ ] Save memo as `outputs/{ticker}_memo.md`
  - [ ] Test memo generation end-to-end

- [ ] ✅ **Checkpoint**: Memo generated and saved successfully

---

### **Day 7 (Tuesday) — LangGraph Orchestration**
**Time: 5-6 hours**

**Morning (3-4 hours)**
- [ ] **PHASE 9**: LangGraph Orchestration
  - [ ] Create `graph/research_graph.py`
  - [ ] Define graph structure:
    ```
    Start → MarketDataAgent → MacroTrendsAgent → RiskAgent 
    → ScenarioAgent → MemoWriterAgent → End
    ```
  - [ ] Implement typed state integration
  - [ ] Add deterministic edges
  - [ ] Implement error handling and retry logic

**Afternoon (2 hours)**
- [ ] Create `main.py`
  - [ ] Command-line interface for ticker input
  - [ ] Parse horizon and risk_profile
  - [ ] Initialize graph and run
  - [ ] Display results
  - [ ] Test with sample ticker (AAPL)

- [ ] ✅ **Checkpoint**: `main.py` runs end-to-end

---

### **Day 8 (Wednesday) — Testing & Refinement**
**Time: 4-5 hours**

**Morning (2-3 hours)**
- [ ] End-to-end testing
  - [ ] Test with multiple tickers (AAPL, MSFT, TSLA)
  - [ ] Test with different horizons (short, medium, long)
  - [ ] Test with different risk profiles
  - [ ] Verify all agents execute correctly
  - [ ] Check state transitions

**Afternoon (2 hours)**
- [ ] Bug fixes and refinements
  - [ ] Fix any discovered issues
  - [ ] Improve error messages
  - [ ] Optimize LLM prompts
  - [ ] Add input validation

---

### **Day 9 (Thursday) — Documentation & README**
**Time: 4-5 hours**

**Morning (2-3 hours)**
- [ ] **PHASE 10**: README & Documentation
  - [ ] Create comprehensive `README.md`:
    - [ ] Project overview
    - [ ] Architecture diagram (ASCII or Mermaid)
    - [ ] Agent responsibilities table
    - [ ] Installation instructions
    - [ ] Usage examples
    - [ ] Sample output
    - [ ] Disclaimer section
    - [ ] Troubleshooting guide

**Afternoon (2 hours)**
- [ ] Code documentation
  - [ ] Add docstrings to all functions
  - [ ] Add module-level documentation
  - [ ] Create example `.env.example` file
  - [ ] Add inline comments where needed

- [ ] ✅ **Checkpoint**: README complete and professional

---

### **Day 10 (Friday) — Final Polish & Optional Features**
**Time: 4-6 hours**

**Morning (2-3 hours)**
- [ ] Final testing and polish
  - [ ] Run full test suite
  - [ ] Verify all checkpoints pass
  - [ ] Code cleanup and formatting
  - [ ] Ensure consistent code style

**Afternoon (2-3 hours)**
- [ ] **PHASE 11**: Optional Enhancements (if time allows)
  - [ ] Streamlit UI (basic version)
  - [ ] PDF export functionality
  - [ ] Multi-ticker comparison feature
  - [ ] Human-in-the-loop overrides

- [ ] Final review
  - [ ] Review all code
  - [ ] Update README with any final changes
  - [ ] Prepare resume bullet point
  - [ ] Create sample outputs for portfolio

- [ ] ✅ **Final Checkpoint**: Project complete and ready for showcase

---

## Milestones & Checkpoints

### Week 1 Milestones
- ✅ **End of Day 1**: Environment set up, market data tools working
- ✅ **End of Day 2**: Market Data Agent functional
- ✅ **End of Day 3**: Macro Trends Agent functional
- ✅ **End of Day 4**: Risk Analyst Agent functional
- ✅ **End of Day 5**: Scenario Analysis and Confidence Scoring complete

### Week 2 Milestones
- ✅ **End of Day 6**: Memo Writer Agent functional
- ✅ **End of Day 7**: Full LangGraph orchestration working
- ✅ **End of Day 8**: System tested and refined
- ✅ **End of Day 9**: Documentation complete
- ✅ **End of Day 10**: Project polished and ready

---

## Time Allocation Summary

| Phase | Estimated Hours | Days |
|-------|----------------|------|
| Setup & Foundation | 6-8 hours | Day 1 |
| Market Data Agent | 4-5 hours | Day 2 |
| Macro Trends Agent | 4-5 hours | Day 3 |
| Risk Analyst Agent | 4-5 hours | Day 4 |
| Scenario & Confidence | 4-5 hours | Day 5 |
| Memo Writer | 4-5 hours | Day 6 |
| LangGraph Integration | 5-6 hours | Day 7 |
| Testing & Refinement | 4-5 hours | Day 8 |
| Documentation | 4-5 hours | Day 9 |
| Final Polish | 4-6 hours | Day 10 |
| **Total** | **43-55 hours** | **10 days** |

---

## Tips for Success

1. **Daily Standup**: Review previous day's progress and adjust timeline if needed
2. **Test Early**: Test each agent as you build it, don't wait until the end
3. **Version Control**: Commit frequently with meaningful messages
4. **Documentation**: Write docstrings as you code, not after
5. **Ollama Performance**: If Ollama is slow, consider using a smaller quantized model for testing
6. **FRED API**: Get your FRED API key early (free at https://fred.stlouisfed.org)
7. **Buffer Time**: Build in 10-20% buffer for unexpected issues

---

## Risk Mitigation

- **If behind schedule**: Focus on core agents first, defer optional enhancements
- **If Ollama issues**: Have backup plan to test with OpenAI API temporarily
- **If data issues**: Use mock data for testing agent logic, integrate real data later
- **If complexity grows**: Simplify agent responsibilities, iterate later

---

**Remember**: Building 80% of this cleanly beats 10 Kaggle notebooks. Focus on quality over quantity.

---

# VERSION 2 — Web Interface Timeline (1 week)

## Overview

Build a React + TypeScript + Node.js web interface **alongside** the existing CLI, enabling browser-based interaction with the financial research analyst. Both CLI and web interface will share the same Python backend analysis engine.

**Tech Stack**:
- **Frontend**: React 18+ with TypeScript (.tsx/.ts files)
- **Styling**: Bootstrap 5 (no custom CSS files)
- **Backend**: Node.js + Express.js with TypeScript
- **Build Tool**: Vite with TypeScript support

---

## Day 1 (Monday) — Backend API Setup

**Time: 4-5 hours**

### Morning (2-3 hours)
- [ ] **Backend Project Setup**
  - [ ] Create `backend/` directory structure
  - [ ] Initialize Node.js project (`npm init`)
  - [ ] Install Express, CORS, dotenv
  - [ ] Install TypeScript and types: `npm install -D typescript @types/node @types/express`
  - [ ] Create `tsconfig.json` for backend
  - [ ] Create `backend/src/server.ts` with basic Express setup (TypeScript)
  - [ ] Configure CORS middleware
  - [ ] Add health check endpoint (`GET /api/health`)
  - [ ] Test server starts and responds

### Afternoon (2 hours)
- [ ] **Python Service Integration**
  - [ ] Create `backend/src/services/pythonService.ts` (TypeScript)
  - [ ] Implement child process execution of Python script
  - [ ] **Capture stdout/stderr in real-time** (line by line)
  - [ ] Parse Python output (stdout/stderr)
  - [ ] Add error handling and timeout (15 min)
  - [ ] Test Python integration with sample request
  - [ ] **Verify progress messages are captured** (same as CLI output)

✅ **Checkpoint**: Backend server runs and can execute Python analysis.

---

## Day 2 (Tuesday) — Backend API Completion

**Time: 4-5 hours**

### Morning (2-3 hours)
- [ ] **Analysis Route**
  - [ ] Create `backend/src/routes/analysis.ts` (TypeScript)
  - [ ] Implement `POST /api/analyze` endpoint (standard response)
  - [ ] **Implement `POST /api/analyze/stream` endpoint (SSE for progress)**
  - [ ] Add input validation (ticker, horizon, risk_profile)
  - [ ] Integrate Python service with real-time stdout capture
  - [ ] **Stream progress events via SSE** (parse CLI progress messages)
  - [ ] Format response JSON structure
  - [ ] Add comprehensive error handling

### Afternoon (2 hours)
- [ ] **Testing & Refinement**
  - [ ] Test API with Postman/curl
  - [ ] Test all error cases (invalid input, timeout, etc.)
  - [ ] Add request logging
  - [ ] Optimize Python process execution
  - [ ] Document API endpoints

✅ **Checkpoint**: Backend API fully functional and tested.

---

## Day 3 (Wednesday) — Frontend Setup & Input Components

**Time: 4-5 hours**

### Morning (2-3 hours)
- [ ] **React Project Setup with TypeScript**
  - [ ] Create `frontend/` directory
  - [ ] Initialize React app with TypeScript (`npm create vite@latest . -- --template react-ts`)
  - [ ] Install dependencies (bootstrap, react-bootstrap, react-markdown)
  - [ ] Set up Bootstrap 5 (import CSS in main.tsx)
  - [ ] Configure TypeScript (tsconfig.json)
  - [ ] Configure API base URL

### Afternoon (2 hours)
- [ ] **Input Components (TypeScript + Bootstrap)**
  - [ ] Create `TickerInput.tsx` component with TypeScript props
  - [ ] Create `HorizonSelect.tsx` dropdown using Bootstrap Form.Select
  - [ ] Create `RiskProfileSelect.tsx` dropdown using Bootstrap Form.Select
  - [ ] Add TypeScript type definitions for props
  - [ ] Add form validation with Bootstrap validation classes
  - [ ] Style components using Bootstrap classes

✅ **Checkpoint**: Frontend form with all inputs working.

---

## Day 4 (Thursday) — Frontend API Integration & Results Display

**Time: 5-6 hours**

### Morning (3 hours)
- [ ] **API Service & Main App (TypeScript)**
  - [ ] Create `frontend/src/services/api.ts` with TypeScript interfaces
  - [ ] Implement `analyzeStock` function with TypeScript types
  - [ ] **Implement `analyzeStockWithProgress` function (SSE) with typed callbacks**
  - [ ] Update `App.tsx` with form submission and typed state
  - [ ] **Add progress display component integration**
  - [ ] Add loading state using Bootstrap spinner
  - [ ] Implement error handling in UI with Bootstrap Alert

### Afternoon (2-3 hours)
- [ ] **Results Display Components (TypeScript + Bootstrap)**
  - [ ] **Create `ProgressDisplay.tsx` component** (show real-time progress with Bootstrap)
  - [ ] Create `ResultsDisplay.tsx` component with typed props
  - [ ] Create `ScenarioCard.tsx` for scenarios using Bootstrap Card
  - [ ] Display recommendation with Bootstrap badges/colors
  - [ ] Show confidence score using Bootstrap Progress component
  - [ ] **Display timing breakdown** (from progress events) in Bootstrap ListGroup
  - [ ] Style all components using Bootstrap classes (no custom CSS)

✅ **Checkpoint**: Frontend can submit requests and display basic results.

---

## Day 5 (Friday) — Memo Viewer & Polish

**Time: 4-5 hours**

### Morning (2-3 hours)
- [ ] **Memo Viewer (TypeScript + Bootstrap)**
  - [ ] Create `MemoViewer.tsx` component with TypeScript props
  - [ ] Install and configure `react-markdown`
  - [ ] Style memo display using Bootstrap Card and typography classes
  - [ ] Add expandable sections using Bootstrap Accordion (optional)
  - [ ] Test markdown rendering

### Afternoon (2 hours)
- [ ] **UI Polish & Testing (Bootstrap)**
  - [ ] Improve overall styling using Bootstrap utility classes
  - [ ] Add loading animations using Bootstrap spinners
  - [ ] Test full user flow
  - [ ] Fix any bugs or UI issues
  - [ ] Test responsive design (Bootstrap's mobile-first approach)
  - [ ] Remove any custom CSS files (use only Bootstrap)

✅ **Checkpoint**: Complete web interface functional and polished.

---

## Day 6 (Monday) — Integration Testing & Documentation

**Time: 3-4 hours**

### Morning (2 hours)
- [ ] **End-to-End Testing**
  - [ ] Test complete flow: input → API → Python → results
  - [ ] Test error scenarios
  - [ ] Test timeout handling
  - [ ] Test on different browsers
  - [ ] Performance testing

### Afternoon (1-2 hours)
- [ ] **Documentation**
  - [ ] Update README with web interface setup
  - [ ] Document API endpoints
  - [ ] Add screenshots to README
  - [ ] Create quick start guide

✅ **Checkpoint**: System fully tested and documented.

---

## Day 7 (Tuesday) — Polish & Testing

**Time: 3-4 hours**

- [ ] **Progress Display Polish**
  - [ ] Ensure all CLI progress messages appear in web UI
  - [ ] Add auto-scroll to progress log
  - [ ] Style progress messages (colors, icons)
  - [ ] Add progress bar/step indicator
  - [ ] Test progress streaming works correctly

- [ ] **Additional Features** (Optional)
  - [ ] Recent analyses history (localStorage)
  - [ ] Export memo as PDF
  - [ ] Copy results to clipboard
  - [ ] Share analysis link

- [ ] **Deployment Prep** (Optional)
  - [ ] Environment configuration
  - [ ] Production build setup
  - [ ] Docker configuration

---

## Milestones

### Week 1 Milestones
- ✅ **End of Day 1**: Backend server running, Python integration working
- ✅ **End of Day 2**: Backend API complete and tested
- ✅ **End of Day 3**: Frontend form with inputs functional
- ✅ **End of Day 4**: Frontend displays results from API
- ✅ **End of Day 5**: Complete web interface polished
- ✅ **End of Day 6**: System tested and documented
- ✅ **End of Day 7**: Optional enhancements complete

---

## Time Allocation Summary

| Phase | Estimated Hours | Days |
|-------|----------------|------|
| Backend Setup | 4-5 hours | Day 1 |
| Backend API | 4-5 hours | Day 2 |
| Frontend Setup | 4-5 hours | Day 3 |
| Frontend Integration | 5-6 hours | Day 4 |
| Memo Viewer & Polish | 4-5 hours | Day 5 |
| Testing & Docs | 3-4 hours | Day 6 |
| Enhancements | 3-4 hours | Day 7 |
| **Total** | **27-34 hours** | **7 days** |

---

## Quick Start Commands

### Backend
```bash
cd backend
npm install
npm start  # Runs on port 3001
```

### Frontend
```bash
cd frontend
npm install
npm run dev  # Runs on port 3000
```

### Python (unchanged - shared by both CLI and web)
```bash
# Python code remains in root directory
# CLI: python main.py <ticker> <horizon> <risk_profile>
# Web: Backend calls same command via subprocess
# Both use identical Python analysis engine
```

---

## Architecture Diagram

```
┌─────────────┐         ┌─────────────┐
│   Browser   │         │   Terminal  │
│  (React)    │         │    (CLI)    │
└──────┬──────┘         └──────┬──────┘
       │                        │
       │ HTTP POST              │ Direct
       │ /api/analyze           │ python main.py
       │                        │
┌──────▼────────────────────────▼──────┐
│         Express Server                │
│         (Node.js)                     │
│         [Only for web requests]       │
└──────┬──────────────────────────────────────┘
       │ spawn/exec (web) or direct (CLI)
       │
┌──────▼────────────────────────────────┐
│      Python Analysis Engine            │
│      (Shared by both CLI and web)     │
│      - agents/                        │
│      - graph/                         │
│      - tools/                         │
│      - main.py (CLI entry point)      │
└───────────────────────────────────────┘
```

**Key Points**:
- ✅ CLI continues to work independently (no changes needed)
- ✅ Web interface uses same Python code via Express API
- ✅ Both get identical analysis results
- ✅ No code duplication

---

## Tips for Success

1. **Start Simple**: Get basic flow working first, then add polish
2. **Test Incrementally**: Test each component as you build it
3. **Error Handling**: Add comprehensive error handling early
4. **User Feedback**: Always show loading states and error messages
5. **API First**: Build and test backend API before frontend
6. **Reuse Components**: Create reusable React components

---

## Risk Mitigation

- **If Python integration is slow**: Consider Python HTTP server instead of child process
- **If CORS issues**: Double-check CORS configuration in Express
- **If timeout issues**: Increase timeout limits, add progress indicators
- **Styling**: Use Bootstrap 5 utility classes and components (no custom CSS needed)

---

# VERSION 2.1 — Stock Statistics Display Timeline (2.5-3.5 hours)

## Overview

Add stock statistics display to web interface showing key metrics like current price, 52-week high/low, P/E ratio, market cap, and dividend yield.

---

## Phase 1 — Backend Verification (30 minutes)

- [ ] Verify `tools/market_data.py` returns required fields:
  - [ ] `current_price`
  - [ ] `52_week_high`
  - [ ] `52_week_low`
  - [ ] `pe_ratio`
  - [ ] `market_cap`
  - [ ] `dividend_yield`
- [ ] Verify `market_data` is included in API response
- [ ] Test with sample ticker (AAPL) to confirm data structure
- [ ] Update TypeScript interfaces in `api.ts` if needed

✅ **Checkpoint**: Backend provides all required stock statistics.

---

## Phase 2 — Frontend Implementation (1-2 hours)

- [ ] **Create StockStats Component**
  - [ ] Create `web/frontend/src/components/StockStats.tsx`
  - [ ] Define TypeScript interface for props
  - [ ] Implement Bootstrap Card layout
  - [ ] Add responsive grid system
  - [ ] Format currency values correctly
  - [ ] Format market cap (B/T notation)
  - [ ] Format percentages (dividend yield)
  - [ ] Handle missing/null values (show "N/A")

- [ ] **Integrate into ResultsDisplay**
  - [ ] Import StockStats component
  - [ ] Add before recommendation section
  - [ ] Pass `market_data` prop from results
  - [ ] Test integration

- [ ] **Styling & Polish**
  - [ ] Highlight current price prominently
  - [ ] Show 52-week range visually
  - [ ] Consistent spacing and typography
  - [ ] Responsive design testing

✅ **Checkpoint**: Stock statistics display correctly in web interface.

---

## Phase 3 — Testing & Polish (30 minutes)

- [ ] **Testing**
  - [ ] Test with multiple tickers (AAPL, MSFT, TSLA)
  - [ ] Verify all statistics display correctly
  - [ ] Test with missing/null values (graceful degradation)
  - [ ] Test responsive design (mobile/tablet/desktop)
  - [ ] Verify data formatting (currency, percentages, etc.)

- [ ] **Final Polish**
  - [ ] Code review and cleanup
  - [ ] Consistent error handling
  - [ ] Visual consistency with rest of UI

✅ **Checkpoint**: Feature complete and tested.

---

## Time Allocation Summary

| Phase | Estimated Time |
|-------|----------------|
| Backend Verification | 30 minutes |
| Frontend Implementation | 1-2 hours |
| Testing & Polish | 30 minutes |
| **Total** | **2.5-3.5 hours** |

---

## Implementation Checklist

- [ ] Verify backend data structure
- [ ] Create StockStats.tsx component
- [ ] Define TypeScript interfaces
- [ ] Format currency values
- [ ] Format market cap (B/T)
- [ ] Format percentages
- [ ] Handle missing values
- [ ] Integrate into ResultsDisplay
- [ ] Add responsive styling
- [ ] Test with multiple tickers
- [ ] Test error cases
- [ ] Final polish and review

---

# VERSION 3 — Hybrid LLM Layer Timeline (3-4 days)

## Overview

Replace Ollama with a hybrid LLM layer using cloud-based APIs:
- **Gemini (free tier)** → reasoning-critical agents (Risk, Scenario, Memo Writer)
- **Hugging Face (free model)** → lightweight generation agents (Macro Sentiment)

**Benefits**:
- ✅ No local Ollama installation needed
- ✅ No GPU requirements
- ✅ No model warmup time
- ✅ Faster startup
- ✅ Easier deployment

**Agent → LLM Mapping**:
- Macro Sentiment Agent → **Hugging Face Mistral** (lightweight)
- Risk Agent → **Gemini Flash** (reasoning)
- Scenario Agent → **Gemini Flash** (reasoning)
- Memo Writer Agent → **Gemini Flash** (writing)

---

## Day 1 (Monday) — API Setup & LLM Service Layer

**Time: 4-5 hours**

### Morning (2-3 hours)
- [ ] **PHASE 0.1**: API Keys & Environment
  - [ ] Get Gemini API key (https://makersuite.google.com/app/apikey)
  - [ ] Get Hugging Face API key (https://huggingface.co/settings/tokens) - optional if using Inference API
  - [ ] Update `.env` file:
    - [ ] Remove `OLLAMA_BASE_URL` and `OLLAMA_MODEL`
    - [ ] Add `GEMINI_API_KEY=xxx`
    - [ ] Add `HUGGINGFACE_API_KEY=xxx` (if needed)
  - [ ] Create `.env.example` with new API keys

- [ ] **PHASE 0.2**: Install Dependencies
  - [ ] Update `requirements.txt`:
    - [ ] Remove `langchain-ollama`
    - [ ] Add `google-generativeai>=0.3.0`
    - [ ] Add `huggingface_hub>=0.20.0` (or `transformers>=4.35.0`)
  - [ ] Run `pip install -r requirements.txt`
  - [ ] Test imports work correctly

### Afternoon (2 hours)
- [ ] **PHASE 0.3**: LLM Service Layer
  - [ ] Create `services/llm_service.py`
  - [ ] Implement abstract LLM interface/base class
  - [ ] Implement Gemini client wrapper:
    - [ ] Initialize Gemini client with API key
    - [ ] Create function for Gemini Flash calls
    - [ ] Add error handling and retries
    - [ ] Add rate limiting logic (for free tier)
  - [ ] Implement Hugging Face client wrapper:
    - [ ] Initialize HF client (Inference API or transformers)
    - [ ] Create function for Mistral model calls
    - [ ] Add error handling
  - [ ] Implement agent-to-model routing logic:
    - [ ] Function to get correct LLM for each agent
    - [ ] Map: Macro Sentiment → HF, others → Gemini
  - [ ] Test LLM service with simple prompts

✅ **Checkpoint**: LLM service layer created and tested. Both APIs working.

---

## Day 2 (Tuesday) — Update All Agents

**Time: 6-7 hours**

### Morning (3-4 hours)
- [ ] **PHASE 1.1**: Macro Sentiment Agent → Hugging Face
  - [ ] Update `agents/macro_trends_agent.py`
  - [ ] Replace Ollama calls with Hugging Face Mistral
  - [ ] Update prompt template (simple, direct, no reasoning chains):
    ```
    Analyze sentiment for {ticker} based on:
    - Interest rate trend: {rate_trend}
    - Inflation trend: {inflation_trend}
    - Sector performance: {sector_perf}
    
    Return JSON: {"sentiment": "positive|neutral|negative", "score": 0.0-1.0}
    ```
  - [ ] Parse JSON output
  - [ ] Add error handling for API failures
  - [ ] Test agent independently

- [ ] **PHASE 1.2**: Risk Agent → Gemini Flash
  - [ ] Update `agents/risk_agent.py`
  - [ ] Replace Ollama with Gemini Flash
  - [ ] Update prompt template (explicit schema, constraints):
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
  - [ ] Enforce constraints (volatility range, beta validation)
  - [ ] Test structured JSON output
  - [ ] Test agent independently

### Afternoon (3 hours)
- [ ] **PHASE 1.3**: Scenario Agent → Gemini Flash
  - [ ] Update `agents/scenario_agent.py`
  - [ ] Replace Ollama with Gemini Flash
  - [ ] Update prompt template (explicit schema, probability constraints):
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
  - [ ] Add validation to ensure probabilities sum to 1.0
  - [ ] Test scenario generation
  - [ ] Test agent independently

- [ ] **PHASE 1.4**: Memo Writer → Gemini Flash
  - [ ] Update `agents/memo_writer_agent.py`
  - [ ] Replace Ollama with Gemini Flash
  - [ ] Update prompt template (structured markdown format):
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
  - [ ] Test memo format and structure
  - [ ] Test agent independently

✅ **Checkpoint**: All agents updated and tested. No Ollama dependencies remain.

---

## Day 3 (Wednesday) — Update LangGraph & Web Interface

**Time: 4-5 hours**

### Morning (2-3 hours)
- [ ] **PHASE 2**: Update LangGraph
  - [ ] Review `graph/research_graph.py` (should need minimal changes)
  - [ ] Verify state structure unchanged (LLM-agnostic)
  - [ ] Verify graph flow unchanged
  - [ ] Update error handling:
    - [ ] Add retry logic for API rate limits
    - [ ] Handle API timeouts (different from Ollama)
    - [ ] Add graceful degradation if API unavailable
  - [ ] Test graph execution end-to-end
  - [ ] Verify all agents execute in correct order

### Afternoon (2 hours)
- [ ] **PHASE 3**: Update Web Interface
  - [ ] Update progress messages in Python code:
    - [ ] Remove "Warming up LLM" messages
    - [ ] Update timing information (no warmup time)
    - [ ] Add API call progress messages:
      - `[Macro Sentiment Agent] Calling Hugging Face API...`
      - `[OK] Sentiment analysis complete in 0.5s`
      - `[Risk Agent] Calling Gemini API...`
      - `[OK] Risk analysis complete in 1.2s`
  - [ ] Test backend API (no changes needed to Express server)
  - [ ] Test frontend (no changes needed to React components)
  - [ ] Verify streaming updates work correctly

✅ **Checkpoint**: LangGraph and web interface updated. System runs end-to-end.

---

## Day 4 (Thursday) — Testing, Validation & Documentation

**Time: 5-6 hours**

### Morning (3 hours)
- [ ] **PHASE 4.1**: Functional Testing
  - [ ] Test all agents produce correct outputs
  - [ ] Validate JSON schemas (Risk, Scenario agents)
  - [ ] Verify constraints enforced:
    - [ ] Probabilities sum to 1.0 (Scenario agent)
    - [ ] Volatility in range 0.0-1.0 (Risk agent)
    - [ ] Beta is positive (Risk agent)
  - [ ] Verify memo format is correct
  - [ ] Test with multiple tickers (AAPL, MSFT, TSLA)

- [ ] **PHASE 4.2**: Performance Testing
  - [ ] Compare timing: Ollama (with warmup) vs. API calls
  - [ ] Measure API latency
  - [ ] Test rate limiting behavior
  - [ ] Verify no warmup delays
  - [ ] Document performance improvements

### Afternoon (2-3 hours)
- [ ] **PHASE 4.3**: Error Handling Testing
  - [ ] Test API key errors
  - [ ] Test rate limit errors
  - [ ] Test network timeouts
  - [ ] Test invalid API responses
  - [ ] Verify graceful error handling

- [ ] **PHASE 4.4**: CLI & Web Interface Testing
  - [ ] Test CLI: `python main.py AAPL medium moderate`
  - [ ] Test web interface end-to-end
  - [ ] Verify streaming updates work
  - [ ] Verify both produce identical results

- [ ] **PHASE 5**: Documentation & Cleanup
  - [ ] Update README:
    - [ ] Remove Ollama installation instructions
    - [ ] Add API key setup instructions
    - [ ] Update dependencies list
    - [ ] Add API rate limit notes (free tier limits)
  - [ ] Remove Ollama-specific configuration files
  - [ ] Clean up unused imports
  - [ ] Update `.gitignore` if needed
  - [ ] Update `.env.example` with new API keys

✅ **Checkpoint**: All testing complete. Documentation updated. System ready.

---

## Milestones

### Day-by-Day Milestones
- ✅ **End of Day 1**: LLM service layer created, both APIs working
- ✅ **End of Day 2**: All agents updated to use new LLM services
- ✅ **End of Day 3**: LangGraph and web interface updated
- ✅ **End of Day 4**: Testing complete, documentation updated

---

## Time Allocation Summary

| Phase | Estimated Hours | Days |
|-------|----------------|------|
| API Setup & LLM Service | 4-5 hours | Day 1 |
| Update All Agents | 6-7 hours | Day 2 |
| Update LangGraph & Web | 4-5 hours | Day 3 |
| Testing & Documentation | 5-6 hours | Day 4 |
| **Total** | **19-23 hours** | **3-4 days** |

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

## Prompt Guidelines

### Hugging Face (Mistral) - Macro Sentiment Only
- ✅ One task only (single, focused objective)
- ✅ Short prompts (concise, no unnecessary context)
- ✅ No reasoning chains (direct output)
- ✅ Simple JSON output format

### Gemini (Flash) - Risk, Scenario, Memo Writer
- ✅ Explicit schema (define exact output structure)
- ✅ Enforce constraints (validation rules, format requirements)
- ✅ Structured reasoning (when needed for complex tasks)
- ✅ JSON mode when possible (for structured outputs)

---

## Benefits Summary

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

## Tips for Success

1. **API Keys First**: Get both API keys before starting (may take a few minutes)
2. **Test Incrementally**: Test each agent as you update it
3. **Rate Limits**: Be aware of free tier rate limits (especially Gemini)
4. **Error Handling**: Add comprehensive error handling for API failures
5. **Validation**: Always validate JSON outputs from LLMs
6. **Backup Plan**: Keep old Ollama code commented until migration complete

---

## Risk Mitigation

- **If API rate limits hit**: Implement exponential backoff and retry logic
- **If API costs concern**: Monitor usage, use free tier limits wisely
- **If API unavailable**: Add fallback logic or graceful error messages
- **If JSON parsing fails**: Add validation and retry with clearer prompts
- **If migration breaks**: Keep old Ollama code as backup until fully tested

