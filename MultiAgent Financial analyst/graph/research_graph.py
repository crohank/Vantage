"""
LangGraph Orchestration

Defines the research workflow graph:
Start → MarketDataAgent → MacroTrendsAgent → RiskAgent 
→ ScenarioAgent → MemoWriterAgent → End
"""

from typing import Dict, Any
import time
from langgraph.graph import StateGraph, END
from schemas.state import ResearchState
from agents.market_data_agent import market_data_agent
from agents.macro_trends_agent import macro_trends_agent
from agents.risk_agent import risk_agent
from agents.scenario_agent import scenario_agent
from agents.memo_writer_agent import memo_writer_agent

# For parallel execution - run both data collection agents simultaneously
def run_parallel_data_collection(state: ResearchState) -> ResearchState:
    """
    Run Market Data and Macro Trends agents in parallel.
    These are independent and can run simultaneously to save time.
    """
    import concurrent.futures
    import copy
    
    # Create copies of state for each agent to avoid conflicts
    market_state = copy.deepcopy(state)
    macro_state = copy.deepcopy(state)
    
    # Run both agents in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        market_future = executor.submit(market_data_agent, market_state)
        macro_future = executor.submit(macro_trends_agent, macro_state)
        
        # Wait for both to complete
        market_result = market_future.result()
        macro_result = macro_future.result()
        
        # Merge results back into original state
        state["market_data"] = market_result.get("market_data", {})
        state["macro_data"] = macro_result.get("macro_data", {})
        
    return state

# Global timing tracker
_timing_data = {}


def create_research_graph() -> Any:
    """
    Create and configure the research analysis graph.
    
    Returns:
        Configured StateGraph instance
    """
    # Create the graph
    workflow = StateGraph(ResearchState)
    
    # Add nodes (agents)
    # OPTIMIZATION: Run market_data and macro_trends in parallel since they're independent
    workflow.add_node("data_collection", run_parallel_data_collection)
    workflow.add_node("risk_analysis", risk_agent)
    workflow.add_node("scenario_analysis", scenario_agent)
    workflow.add_node("memo_writer", memo_writer_agent)
    
    # Define the flow
    workflow.set_entry_point("data_collection")
    
    # After parallel data collection, continue with dependent agents
    workflow.add_edge("data_collection", "risk_analysis")
    workflow.add_edge("risk_analysis", "scenario_analysis")
    workflow.add_edge("scenario_analysis", "memo_writer")
    workflow.add_edge("memo_writer", END)
    
    # Compile the graph
    app = workflow.compile()
    
    return app


def run_research_analysis(ticker: str, horizon: str, risk_profile: str) -> Dict[str, Any]:
    """
    Run the complete research analysis pipeline.
    
    Args:
        ticker: Stock ticker symbol
        horizon: Time horizon (short/medium/long)
        risk_profile: Risk profile (conservative/moderate/aggressive)
    
    Returns:
        Final state with all analysis results
    """
    global _timing_data
    _timing_data = {}
    
    # Initialize state
    initial_state: ResearchState = {
        "ticker": ticker.upper(),
        "horizon": horizon.lower(),
        "risk_profile": risk_profile.lower(),
        "market_data": {},
        "macro_data": {},
        "risk_analysis": {},
        "scenarios": {},
        "recommendation": "",
        "confidence_score": 0.0,
        "memo": ""
    }
    
    # Create and run graph with timing
    graph_start = time.time()
    graph = create_research_graph()
    result = graph.invoke(initial_state)
    graph_time = time.time() - graph_start
    
    # Store timing in result for main.py to access
    result["_timing"] = _timing_data
    result["_total_analysis_time"] = graph_time
    
    return result
