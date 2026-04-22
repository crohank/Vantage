# Vantage

A multi-agent AI system built with LangGraph that generates structured investment research reports with risk modeling and scenario analysis. The system features a full-stack web application with real-time progress tracking and a Python backend orchestrating specialized AI agents.

## 🎯 Project Overview

This is a **decision-support research system** (NOT a trading bot) that analyzes stocks and generates investment recommendations based on:

- Market data analysis
- Macroeconomic trends
- Risk assessment
- Scenario modeling (Bull/Base/Bear)
- Professional investment memos

The system uses a multi-agent architecture where specialized agents collaborate to produce comprehensive investment research reports.

## 📋 Input/Output

### Input
- Stock ticker (e.g., AAPL, MSFT)
- Time horizon: `short` | `medium` | `long`
- Risk profile: `conservative` | `moderate` | `aggressive`

### Output
- Buy / Hold / Sell recommendation
- Confidence score (0–1)
- Bull / Base / Bear scenarios with probabilities and expected returns
- Investment memo (Markdown format)
- Comprehensive market data, macro analysis, and risk metrics

## 🛠️ Technology Stack

### Backend (Python)
- **Language**: Python 3.10+
- **Multi-agent Framework**: LangGraph 0.2.0+
- **LLM Integration**: LangChain 0.3.0+ with LangChain-Ollama 0.1.0+
- **LLM Model**: Ollama (deepseek-r1:8b) - 8 billion parameter reasoning model
- **Data Sources**:
  - `yfinance` 0.2.0+ (market data, stock prices, valuation metrics)
  - `fredapi` 0.5.0+ (Federal Reserve Economic Data - macroeconomic indicators)
- **Quantitative Libraries**:
  - `pandas` 2.0.0+ (data manipulation)
  - `numpy` 1.24.0+ (numerical computations)
  - `scipy` 1.10.0+ (statistical functions)
  - `pandas-ta` (technical analysis indicators - optional)
- **Configuration**: `python-dotenv` 1.0.0+ (environment variable management)

### Frontend (Web Application)
- **Framework**: React 18.2.0+ with TypeScript 5.9.3+
- **Build Tool**: Vite 5.0.0+
- **UI Library**: React Bootstrap 2.10.10+ (Bootstrap 5.3.8+)
- **HTTP Client**: Axios 1.6.0+
- **Markdown Rendering**: react-markdown 9.0.0+
- **Styling**: Bootstrap CSS with custom gradients

### Backend API (Node.js)
- **Runtime**: Node.js with TypeScript
- **Framework**: Express 4.18.2+
- **Development**: 
  - TSX 4.21.0+ (TypeScript execution)
  - Nodemon 3.1.11+ (hot reload)
- **CORS**: cors 2.8.5+
- **Communication**: Server-Sent Events (SSE) for real-time progress streaming

### Architecture Pattern
- **State Management**: LangGraph StateGraph with TypedDict state schema
- **Execution Model**: Sequential pipeline with parallel data collection optimization
- **Inter-process Communication**: Node.js spawns Python subprocess with real-time stdout capture

## 📁 Repository Structure

```
analyst/
│
├── frontend/                      # React Web Frontend
│   ├── src/
│   │   ├── App.tsx                # Main application component
│   │   ├── components/            # React components
│   │   │   ├── TickerInput.tsx
│   │   │   ├── HorizonSelect.tsx
│   │   │   ├── RiskProfileSelect.tsx
│   │   │   ├── ProgressDisplay.tsx
│   │   │   ├── ResultsDisplay.tsx
│   │   │   ├── ScenarioCard.tsx
│   │   │   └── MemoViewer.tsx
│   │   └── services/
│   │       └── api.ts             # API client with SSE support
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
│
├── backend/                       # Python Agents + Express API
│   ├── agents/                    # AI Agent Implementations
│   │   ├── market_data_agent.py
│   │   ├── macro_trends_agent.py
│   │   ├── risk_agent.py
│   │   ├── scenario_agent.py
│   │   └── memo_writer_agent.py
│   ├── graph/                     # LangGraph Orchestration
│   │   └── research_graph.py
│   ├── tools/                     # Data Fetching & Processing
│   │   ├── market_data.py
│   │   ├── macro_data.py
│   │   ├── risk_metrics.py
│   │   └── sentiment.py
│   ├── schemas/                   # Type Definitions
│   │   └── state.py
│   ├── src/                       # Express API Server (Node.js)
│   │   ├── server.ts
│   │   ├── routes/analysis.ts
│   │   └── services/pythonService.ts
│   ├── outputs/                   # Generated Investment Memos
│   │   └── {TICKER}_memo.md
│   ├── config.py
│   ├── main.py
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── Dockerfile.backend
│   └── package.json
│
├── docs/                          # Documentation & Learning Guides
│   ├── DEPLOYMENT.md
│   ├── USE.md
│   └── ...
│
├── tests/                         # Test Scripts
│   ├── test_components.py
│   └── test_gemini_api.py
│
├── docker-compose.yml
├── render.yaml
├── .env.example
└── README.md
```

## 🤖 Agent Architecture & Responsibilities

The system uses a multi-agent architecture where each agent has a specific responsibility and populates designated fields in the shared `ResearchState` object.

### Agent Workflow

```
Start
  ↓
[Data Collection Node] (Parallel Execution)
  ├── Market Data Agent ──┐
  └── Macro Trends Agent ──┘
  ↓
Risk Analyst Agent
  ↓
Scenario Analysis Agent
  ↓
Memo Writer Agent
  ↓
End
```

### Agent Details

| Agent | Responsibility | Output | LLM Usage | Typical Runtime |
|-------|---------------|--------|-----------|----------------|
| **Market Data Agent** | Fetches stock price history, valuation metrics (P/E, P/B, P/S), and technical indicators (RSI, moving averages, MACD, Bollinger Bands). Determines price trends over 6-month periods. | `market_data` | None | 30-60 seconds |
| **Macro Trends Agent** | Analyzes macroeconomic conditions via FRED API (interest rates, inflation trends), compares sector ETF performance across 11 sectors, and performs LLM-based sentiment analysis. | `macro_data` | Yes (sentiment analysis) | 60-120 seconds (includes ~30-60s LLM call) |
| **Risk Analyst Agent** | Computes quantitative risk metrics (annualized volatility, beta vs S&P 500, maximum drawdown) and uses LLM to identify key risks based on market, macro, and risk data. | `risk_analysis` | Yes (risk identification) | 60-120 seconds (includes ~30-60s LLM call) |
| **Scenario Agent** | Generates three investment scenarios (Bull/Base/Bear) with expected returns (as decimals) and probabilities (must sum to 1.0) based on comprehensive analysis of all previous agent outputs. | `scenarios` | Yes (scenario generation) | 30-120 seconds (LLM call) |
| **Memo Writer Agent** | Generates professional investment memo in Markdown format with executive summary, investment thesis, key risks, scenarios, and recommendation. Calculates confidence score and determines Buy/Hold/Sell recommendation. | `memo`, `recommendation`, `confidence_score` | Yes (memo generation) | 60-120 seconds (LLM call) |

### Design Decisions

1. **Parallel Data Collection**: Market Data and Macro Trends agents run in parallel using `ThreadPoolExecutor` since they are independent and can save ~30-60 seconds of execution time.

2. **LLM Model**: Uses Ollama with `deepseek-r1:8b` - a reasoning model optimized for analytical tasks. The 8B parameter size provides a good balance between quality and speed for local execution.

3. **State Schema**: Uses TypedDict for type safety and clear contract between agents. Each agent only modifies its designated fields.

4. **Warmup Optimization**: LLM model is warmed up on first run (3-5 minutes) and cached for subsequent runs within 1 hour, significantly improving subsequent execution times.

5. **Real-time Progress**: Backend captures Python stdout/stderr in real-time and streams progress updates via Server-Sent Events to the frontend, providing transparency into long-running operations.

## ⏱️ Runtime Performance

### Execution Time Breakdown

| Step | Duration | Notes |
|------|----------|-------|
| **LLM Warmup** | 3-5 minutes | First run only (cached for 1 hour) |
| **Market Data Agent** | 30-60 seconds | yfinance API calls (price history, valuation metrics) |
| **Macro Trends Agent** | 60-120 seconds | FRED API calls + sector ETF data + LLM sentiment (~30-60s) |
| **Risk Analyst Agent** | 60-120 seconds | Risk calculations + LLM risk identification (~30-60s) |
| **Scenario Agent** | 30-120 seconds | LLM scenario generation (JSON response parsing) |
| **Memo Writer Agent** | 60-120 seconds | LLM memo generation (longest LLM call) |
| **Graph Orchestration** | ~5-10 seconds | LangGraph overhead, state management |

### Overall Runtime

- **First Run** (with LLM warmup): ~10-15 minutes
- **Subsequent Runs** (no warmup): ~5-10 minutes
- **Optimized Runs** (parallel data collection + cached model): ~4-8 minutes

### Performance Optimizations

1. **Parallel Data Collection**: Market and Macro agents run concurrently
2. **LLM Warmup Caching**: Model kept in memory for 1 hour, avoiding reload
3. **Shorter Prompts**: Optimized LLM prompts to reduce token count and response time
4. **Reduced Data Periods**: Uses 6-month and 1-year periods instead of full history for faster data fetching
5. **Efficient State Management**: TypedDict with minimal copying, direct state updates

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+ (for web application)
- Ollama installed ([download here](https://ollama.ai))

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd analyst
   ```

2. **Set up Python environment**
   ```bash
   # Create virtual environment
   python -m venv venv
   
   # Activate virtual environment
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install Ollama and pull model**
   ```bash
   # Install Ollama (if not already installed)
   # Visit https://ollama.ai for installation instructions
   
   # Pull the model
   ollama pull deepseek-r1:8b
   ```

4. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Set up environment variables**
   
   Create a `.env` file in the project root:
   ```env
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=deepseek-r1:8b
   FRED_API_KEY=your_fred_api_key_here
   ```
   
   Get your free FRED API key at: https://fred.stlouisfed.org/docs/api/api_key.html
   
   **Note**: The FRED API key is optional but recommended for better macroeconomic analysis. The system will work without it but macro analysis will be limited.

6. **Set up Web Application (Optional)**
   ```bash
   # Backend (Node.js API)
   cd backend
   npm install
   
   # Frontend (React)
   cd ../frontend
   npm install
   ```

### Usage

#### Command Line Interface

```bash
python main.py <ticker> <horizon> <risk_profile>
```

**Example:**
```bash
python main.py AAPL medium moderate
```

**Output:**
- Console display with recommendation, confidence score, and scenarios
- Timing breakdown for each agent and overall execution
- Investment memo saved to `outputs/{TICKER}_memo.md`

#### Web Application

1. **Start the backend server**
   ```bash
   cd backend
   npm run dev
   # Server runs on http://localhost:3001
   ```

2. **Start the frontend development server**
   ```bash
   cd frontend
   npm run dev
   # Application runs on http://localhost:5173
   ```

3. **Access the application**
   - Open http://localhost:5173 in your browser
   - Enter a stock ticker, select time horizon and risk profile
   - Click "Run Analysis" and watch real-time progress updates
   - View results including recommendation, scenarios, and investment memo

## 🏗️ System Architecture

### State Management

The system uses a shared state object (`ResearchState`) that flows through the LangGraph state machine:

```python
class ResearchState(TypedDict):
    ticker: str
    horizon: str
    risk_profile: str
    
    market_data: Dict[str, Any]      # From Market Data Agent
    macro_data: Dict[str, Any]       # From Macro Trends Agent
    risk_analysis: Dict[str, Any]    # From Risk Analyst Agent
    scenarios: Dict[str, Any]        # From Scenario Agent
    
    recommendation: str              # From Memo Writer Agent
    confidence_score: float          # From Memo Writer Agent
    memo: str                        # From Memo Writer Agent
```

### Data Flow

1. **Input Validation**: CLI/web UI validates inputs (ticker, horizon, risk_profile)
2. **State Initialization**: Initial state object created with empty data fields
3. **Agent Execution**: Agents execute sequentially (with parallel data collection), each populating their designated fields
4. **State Accumulation**: Each agent reads previous agents' outputs and adds its own analysis
5. **Final Output**: Memo Writer agent generates final recommendation and memo using all accumulated data

### LLM Integration

- **Provider**: Ollama (local deployment)
- **Model**: deepseek-r1:8b (8 billion parameters, reasoning-optimized)
- **Usage Pattern**: 
  - Each LLM call is independent (no conversation history)
  - Prompts are carefully crafted to include all necessary context
  - Temperature settings vary by agent (0.3-0.7) based on required creativity vs consistency
  - Timeout: 120 seconds per LLM call (600 seconds for warmup)

## 📊 Current Implementation Status

### ✅ Completed Features

- [x] Multi-agent architecture with LangGraph orchestration
- [x] Market data agent with yfinance integration
- [x] Macro trends agent with FRED API integration
- [x] Risk analyst agent with quantitative metrics and LLM risk identification
- [x] Scenario analysis agent generating Bull/Base/Bear scenarios
- [x] Memo writer agent generating professional investment memos
- [x] Confidence scoring algorithm
- [x] Recommendation engine (Buy/Hold/Sell)
- [x] CLI interface with timing breakdown
- [x] Web application with React frontend and Express backend
- [x] Real-time progress tracking via Server-Sent Events
- [x] LLM warmup caching for performance optimization
- [x] Parallel data collection for improved performance
- [x] Error handling and graceful degradation
- [x] Investment memo generation and file output

### 🔄 Known Limitations

- FRED API key is optional but recommended for full macro analysis
- pandas-ta is optional (system falls back to basic pandas calculations)
- LLM responses may occasionally require retry logic (handled gracefully)
- First run requires 3-5 minute warmup (subsequent runs are faster)
- Analysis is limited to publicly traded US stocks with available data

### 🚧 Potential Future Enhancements

- PDF export functionality for investment memos
- Multi-ticker comparison feature
- Historical analysis and backtesting
- Integration with additional data sources (news APIs, earnings data)
- Human-in-the-loop review and override capabilities
- Database storage for analysis history
- User authentication and saved analysis portfolios
- API rate limiting and request queuing
- Docker containerization for easier deployment

## ⚠️ Disclaimer

This system is for **research and educational purposes only**. It does not provide financial advice. Always consult with qualified financial advisors before making investment decisions. The recommendations and analyses generated by this system should not be used as the sole basis for investment decisions.

## 📝 License

[Add your license here]

## 🤝 Contributing

[Add contribution guidelines here]

---

**Built with**: LangGraph, LangChain, Ollama (deepseek-r1:8b), React, TypeScript, Express, and Python
