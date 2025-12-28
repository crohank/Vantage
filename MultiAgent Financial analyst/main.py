"""
Main Entry Point

Command-line interface for running the financial research analysis.
"""

import sys
import time
import json
import os
from graph.research_graph import run_research_analysis

# Force unbuffered output for real-time streaming
try:
    # Python 3.7+
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except AttributeError:
    # Fallback for older Python versions
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, line_buffering=True)


def main():
    """
    Main function to run the research analysis.
    
    Usage:
        python main.py <ticker> <horizon> <risk_profile>
    
    Example:
        python main.py AAPL medium moderate
    """
    if len(sys.argv) != 4:
        print("Usage: python main.py <ticker> <horizon> <risk_profile>")
        print("  ticker: Stock ticker symbol (e.g., AAPL)")
        print("  horizon: short | medium | long")
        print("  risk_profile: conservative | moderate | aggressive")
        sys.exit(1)
    
    ticker = sys.argv[1].upper()
    horizon = sys.argv[2].lower()
    risk_profile = sys.argv[3].lower()
    
    # Validate inputs
    valid_horizons = ["short", "medium", "long"]
    valid_risk_profiles = ["conservative", "moderate", "aggressive"]
    
    if horizon not in valid_horizons:
        print(f"Error: horizon must be one of {valid_horizons}")
        sys.exit(1)
    
    if risk_profile not in valid_risk_profiles:
        print(f"Error: risk_profile must be one of {valid_risk_profiles}")
        sys.exit(1)
    
    print(f"\n{'='*60}", flush=True)
    print(f"AI-Powered Financial Research Analyst", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"Ticker: {ticker}", flush=True)
    print(f"Horizon: {horizon}", flush=True)
    print(f"Risk Profile: {risk_profile}", flush=True)
    print(f"{'='*60}\n", flush=True)
    
    # Start overall timer
    overall_start = time.time()
    timing_info = {}
    
    try:
        # No warmup needed with API-based LLMs (Gemini + Hugging Face)
        # APIs are instant - no model loading required
        
        # Run the research analysis
        analysis_start = time.time()
        result = run_research_analysis(ticker, horizon, risk_profile)
        analysis_time = time.time() - analysis_start
        timing_info["Analysis Pipeline"] = analysis_time
        
        # Add detailed agent timing if available
        agent_timing = result.get("_agent_timing", {})
        if agent_timing:
            for agent_name, agent_time in agent_timing.items():
                if "llm" not in agent_name.lower():  # Don't double-count LLM times
                    timing_info[f"  - {agent_name.replace('_', ' ').title()}"] = agent_time
        
        # Display results
        print(f"\n{'='*60}")
        print("ANALYSIS COMPLETE")
        print(f"{'='*60}")
        print(f"\nRecommendation: {result.get('recommendation', 'N/A')}")
        print(f"Confidence Score: {result.get('confidence_score', 0.0):.2f}")
        
        scenarios = result.get('scenarios', {})
        if scenarios:
            print(f"\nScenarios:")
            for scenario_name, scenario_data in scenarios.items():
                return_pct = scenario_data.get('return', 0) * 100
                prob_pct = scenario_data.get('prob', 0) * 100
                print(f"  {scenario_name.capitalize()}: {return_pct:+.1f}% return, {prob_pct:.0f}% probability")
        
        memo_file = f"outputs/{ticker}_memo.md"
        print(f"\nInvestment memo saved to: {memo_file}")
        
        # Display timing information
        overall_time = time.time() - overall_start
        print(f"\n{'='*60}")
        print("TIMING BREAKDOWN")
        print(f"{'='*60}")
        for step, duration in timing_info.items():
            minutes = int(duration // 60)
            seconds = duration % 60
            if minutes > 0:
                print(f"  {step}: {minutes}m {seconds:.1f}s ({duration:.1f}s)")
            else:
                print(f"  {step}: {seconds:.1f}s")
        print(f"\n  {'TOTAL TIME':<20}: {int(overall_time // 60)}m {overall_time % 60:.1f}s ({overall_time:.1f}s)")
        print(f"{'='*60}\n")
        
        # If called from API (JSON_OUTPUT env var), output JSON
        if os.getenv('JSON_OUTPUT') == 'true':
            json_output = {
                "recommendation": result.get('recommendation', ''),
                "confidence_score": result.get('confidence_score', 0),
                "scenarios": result.get('scenarios', {}),
                "memo": result.get('memo', ''),  # Memo content (will be read from file by backend)
                "market_data": result.get('market_data', {}),
                "macro_data": result.get('macro_data', {}),
                "risk_analysis": result.get('risk_analysis', {}),
                "timing": {
                    **timing_info,
                    "total_time": overall_time
                }
            }
            # Output JSON between markers for easy parsing
            print("\n===JSON_OUTPUT_START===")
            print(json.dumps(json_output, indent=2))
            print("===JSON_OUTPUT_END===")
        
    except Exception as e:
        overall_time = time.time() - overall_start
        print(f"\nError running analysis after {overall_time:.1f}s: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

