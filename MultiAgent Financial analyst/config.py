"""
Configuration Module

Handles environment variables and LLM initialization.
"""

import os
from dotenv import load_dotenv
from services.llm_service import LLMWrapper

# Load environment variables
load_dotenv()

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

# FRED API configuration
FRED_API_KEY = os.getenv("FRED_API_KEY")


def get_llm(temperature: float = 0.7, timeout: int = 120, agent_name: str = "default") -> LLMWrapper:
    """
    Initialize and return LLM wrapper instance.
    
    Uses hybrid LLM layer:
    - Gemini Flash for reasoning agents (risk, scenario, memo)
    - Hugging Face Mistral for lightweight agents (sentiment)
    
    Args:
        temperature: Temperature for LLM responses (default: 0.7)
        timeout: Request timeout in seconds (default: 120, not used for API calls)
        agent_name: Name of the agent (determines which LLM to use)
    
    Returns:
        LLMWrapper instance (compatible with ChatOllama interface)
    """
    return LLMWrapper(agent_name=agent_name, temperature=temperature)

