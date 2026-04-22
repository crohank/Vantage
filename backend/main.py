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
    if len(sys.argv) not in (4, 5):
        print("Usage: python main.py <ticker> <horizon> <risk_profile> [uploaded_file_path]")
        print("  ticker: Stock ticker symbol (e.g., AAPL)")
        print("  horizon: short | medium | long")
        print("  risk_profile: conservative | moderate | aggressive")
        sys.exit(1)
    
    ticker = sys.argv[1].upper()
    horizon = sys.argv[2].lower()
    risk_profile = sys.argv[3].lower()
    
    uploaded_gridfs_id = sys.argv[4] if len(sys.argv) == 5 else os.getenv("UPLOADED_DOC_PATH", "")
    uploaded_name = os.getenv("UPLOADED_DOC_NAME", "")

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
        uploaded_document = {}
        if uploaded_gridfs_id:
            uploaded_document = {
                "gridfs_file_id": uploaded_gridfs_id,
                "filename": uploaded_name or "uploaded.pdf",
                "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

        result = run_research_analysis(ticker, horizon, risk_profile, uploaded_document=uploaded_document)
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
        
        print("\nInvestment memo persisted to MongoDB analyses collection")
        
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

        # Display telemetry summary
        telemetry = result.get("_telemetry", {})
        totals = telemetry.get("totals", {})
        if totals:
            print(f"{'='*60}")
            print("TELEMETRY SUMMARY")
            print(f"{'='*60}")
            print(f"  LLM Calls: {totals.get('num_calls', 0)}")
            print(f"  Total Tokens: {totals.get('total_tokens', 0):,} (prompt: {totals.get('prompt_tokens', 0):,} + completion: {totals.get('completion_tokens', 0):,})")
            print(f"  Total LLM Latency: {totals.get('total_latency_ms', 0)/1000:.1f}s")
            print(f"  Estimated Cost: ${totals.get('total_cost_usd', 0):.6f}")
            calls = telemetry.get("calls", [])
            if calls:
                print(f"\n  Per-Agent Breakdown:")
                for call in calls:
                    print(f"    {call.get('agent_name', '?'):<20} | {call.get('model', '?'):<25} | {call.get('total_tokens', 0):>6} tokens | {call.get('latency_ms', 0)/1000:.1f}s | ${call.get('cost_usd', 0):.6f}")
            print(f"{'='*60}\n")
        
        # If called from API (JSON_OUTPUT env var), output JSON
        if os.getenv('JSON_OUTPUT') == 'true':
            json_output = {
                "recommendation": result.get('recommendation', ''),
                "confidence_score": result.get('confidence_score', 0),
                "scenarios": result.get('scenarios', {}),
                "memo": result.get('memo', ''),
                "market_data": result.get('market_data', {}),
                "macro_data": result.get('macro_data', {}),
                "risk_analysis": result.get('risk_analysis', {}),
                "document_sources": result.get('document_sources', []),
                "timing": {
                    **timing_info,
                    "total_time": overall_time
                },
                "telemetry": telemetry.get("totals", {})
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

