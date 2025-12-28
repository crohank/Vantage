"""
LLM Service Layer

Abstract LLM interface with Gemini and Hugging Face implementations.
"""

import os
import json
import time
import requests
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

# Use REST API directly for more reliable access
GEMINI_AVAILABLE = True
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1"

try:
    from huggingface_hub import InferenceClient
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False
    print("Warning: huggingface_hub not installed. Install with: pip install huggingface_hub")


class LLMService:
    """Base class for LLM services."""
    
    def invoke(self, prompt: str, **kwargs) -> str:
        """
        Invoke LLM with prompt.
        
        Args:
            prompt: Input prompt
            **kwargs: Additional parameters (temperature, etc.)
        
        Returns:
            LLM response text
        """
        raise NotImplementedError


class GeminiService(LLMService):
    """Gemini Flash LLM service using REST API."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        """
        Initialize Gemini service.
        
        Args:
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
            model: Model name (default: gemini-1.5-flash-latest)
        """
        self.api_key = api_key or GEMINI_API_KEY
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        self.model_name = model
        self.api_url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
    
    def _test_api_key(self) -> bool:
        """Test if API key is valid by listing models."""
        try:
            list_url = f"{GEMINI_API_BASE}/models"
            response = requests.get(
                list_url,
                params={"key": self.api_key},
                timeout=10
            )
            if response.status_code == 200:
                return True
            else:
                print(f"API key test failed: {response.status_code} - {response.text[:200]}")
                return False
        except Exception as e:
            print(f"API key test error: {e}")
            return False
    
    def _list_available_models(self) -> list:
        """List available models for this API key."""
        try:
            list_url = f"{GEMINI_API_BASE}/models"
            response = requests.get(
                list_url,
                params={"key": self.api_key},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                models = [m.get("name", "").replace("models/", "") for m in data.get("models", [])]
                return models
            return []
        except Exception as e:
            print(f"Error listing models: {e}")
            return []
    
    def invoke(self, prompt: str, temperature: float = 0.7, **kwargs) -> str:
        """
        Invoke Gemini with prompt using REST API.
        
        Args:
            prompt: Input prompt
            temperature: Temperature for generation (0.0-1.0)
            **kwargs: Additional parameters
        
        Returns:
            Response text
        """
        # Try different model names if the default fails
        # Updated to use Gemini 2.5/2.0 models (as of 2024)
        models_to_try = [
            "gemini-2.5-flash",      # Latest fast model
            "gemini-2.0-flash",      # Alternative fast model
            "gemini-2.5-pro",        # More capable model
            "gemini-2.0-flash-001",  # Specific version
            "gemini-1.5-flash-latest", # Fallback (may not exist)
            "gemini-1.5-flash",      # Fallback
            "gemini-pro"             # Fallback
        ]
        
        # First, try to get available models if we haven't already
        if not hasattr(self, '_available_models'):
            print("[Gemini] Checking available models...")
            available_models = self._list_available_models()
            if available_models:
                print(f"[Gemini] Available models: {', '.join(available_models[:5])}")
                # Prefer models that are in our list
                preferred = [m for m in models_to_try if m in available_models]
                if preferred:
                    models_to_try = preferred + [m for m in models_to_try if m not in preferred]
            self._available_models = available_models
        
        last_error = None
        for model in models_to_try:
            try:
                api_url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
                
                payload = {
                    "contents": [{
                        "parts": [{
                            "text": prompt
                        }]
                    }],
                    "generationConfig": {
                        "temperature": temperature,
                        **kwargs
                    }
                }
                
                response = requests.post(
                    api_url,
                    params={"key": self.api_key},
                    json=payload,
                    timeout=120
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if "candidates" in result and len(result["candidates"]) > 0:
                        text = result["candidates"][0]["content"]["parts"][0]["text"]
                        # Update model name if we used a different one
                        if model != self.model_name:
                            self.model_name = model
                            self.api_url = api_url
                        return text.strip()
                    else:
                        last_error = "No candidates in response"
                        continue
                elif response.status_code == 404:
                    # Try next model
                    error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                    last_error = error_data.get("error", {}).get("message", f"Model {model} not found (404)")
                    continue
                elif response.status_code == 400:
                    # Bad request - might be API key issue
                    error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                    error_msg = error_data.get("error", {}).get("message", response.text[:200])
                    last_error = f"Bad request (400): {error_msg}"
                    # Don't try other models if it's a bad request
                    raise Exception(f"API Error 400: {error_msg}")
                elif response.status_code == 401 or response.status_code == 403:
                    # Authentication error - don't try other models
                    error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                    error_msg = error_data.get("error", {}).get("message", "Invalid API key or permission denied")
                    raise Exception(f"Authentication Error ({response.status_code}): {error_msg}. Please check your GEMINI_API_KEY.")
                elif response.status_code == 429:
                    # Rate limit - try next model, but warn user
                    error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                    error_msg = error_data.get("error", {}).get("message", "Rate limit exceeded")
                    last_error = f"Rate limit (429): {error_msg}"
                    if model == models_to_try[-1]:
                        raise Exception(f"Rate limit exceeded on all models. Please wait and try again, or check your quota at https://ai.dev/usage")
                    continue
                else:
                    error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                    error_msg = error_data.get("error", {}).get("message", response.text[:200])
                    last_error = f"API Error {response.status_code}: {error_msg}"
                    if model == models_to_try[-1]:
                        raise Exception(last_error)
                    continue
                    
            except requests.exceptions.RequestException as e:
                last_error = f"Request exception: {str(e)}"
                if model == models_to_try[-1]:
                    print(f"Error calling Gemini API: {e}")
                    raise
                continue
            except Exception as e:
                # If it's an auth error or bad request, don't try other models
                if "Authentication" in str(e) or "400" in str(e):
                    raise
                last_error = str(e)
                if model == models_to_try[-1]:
                    print(f"Error calling Gemini API: {e}")
                    raise
                continue
        
        # If we get here, all models failed
        error_msg = f"All model names failed. Last error: {last_error}"
        if hasattr(self, '_available_models') and self._available_models:
            error_msg += f"\nAvailable models: {', '.join(self._available_models[:10])}"
        raise Exception(error_msg)
    
    def invoke_json(self, prompt: str, temperature: float = 0.7, **kwargs) -> Dict[str, Any]:
        """
        Invoke Gemini and parse JSON response.
        
        Args:
            prompt: Input prompt (should request JSON output)
            temperature: Temperature for generation
            **kwargs: Additional parameters
        
        Returns:
            Parsed JSON dictionary
        """
        response_text = self.invoke(prompt, temperature=temperature, **kwargs)
        
        # Try to extract JSON from response
        try:
            # Remove markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON from Gemini: {e}")
            print(f"Response text: {response_text[:200]}...")
            raise


class HuggingFaceService(LLMService):
    """Hugging Face Inference API service."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "mistralai/Mistral-7B-Instruct-v0.2"):
        """
        Initialize Hugging Face service.
        
        Args:
            api_key: Hugging Face API key (defaults to HUGGINGFACE_API_KEY env var)
            model: Model name (default: mistralai/Mistral-7B-Instruct-v0.2)
        """
        if not HF_AVAILABLE:
            raise ImportError("huggingface_hub is required for Hugging Face service")
        
        self.api_key = api_key or HUGGINGFACE_API_KEY
        if not self.api_key:
            raise ValueError("HUGGINGFACE_API_KEY not found in environment variables")
        
        self.model_name = model
        self.client = InferenceClient(api_key=self.api_key)
    
    def invoke(self, prompt: str, temperature: float = 0.3, **kwargs) -> str:
        """
        Invoke Hugging Face model with prompt.
        
        Args:
            prompt: Input prompt
            temperature: Temperature for generation (0.0-1.0)
            **kwargs: Additional parameters
        
        Returns:
            Response text
        """
        try:
            # Use the InferenceClient with the correct API
            response = self.client.text_generation(
                prompt,
                model=self.model_name,
                temperature=temperature,
                max_new_tokens=512,
                return_full_text=False,
                **kwargs
            )
            
            # Response might be a string or a GeneratedText object
            if isinstance(response, str):
                return response.strip()
            else:
                # Handle GeneratedText object
                return str(response).strip()
        except Exception as e:
            print(f"Error calling Hugging Face API: {e}")
            # Try alternative API format
            try:
                response = self.client.post(
                    json={
                        "inputs": prompt,
                        "parameters": {
                            "temperature": temperature,
                            "max_new_tokens": 512,
                            "return_full_text": False
                        }
                    },
                    model=self.model_name
                )
                if isinstance(response, list) and len(response) > 0:
                    result = response[0]
                    if isinstance(result, dict):
                        return result.get("generated_text", "").strip()
                    return str(result).strip()
                return str(response).strip()
            except Exception as e2:
                print(f"Alternative Hugging Face API call also failed: {e2}")
                raise e
    
    def invoke_json(self, prompt: str, temperature: float = 0.3, **kwargs) -> Dict[str, Any]:
        """
        Invoke Hugging Face and parse JSON response.
        
        Args:
            prompt: Input prompt (should request JSON output)
            temperature: Temperature for generation
            **kwargs: Additional parameters
        
        Returns:
            Parsed JSON dictionary
        """
        response_text = self.invoke(prompt, temperature=temperature, **kwargs)
        
        # Try to extract JSON from response
        try:
            # Remove markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON from Hugging Face: {e}")
            print(f"Response text: {response_text[:200]}...")
            raise


# Global instances (lazy initialization)
_gemini_service: Optional[GeminiService] = None
_hf_service: Optional[HuggingFaceService] = None


def get_gemini_service() -> GeminiService:
    """Get or create Gemini service instance."""
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service


def get_hf_service() -> HuggingFaceService:
    """Get or create Hugging Face service instance."""
    global _hf_service
    if _hf_service is None:
        _hf_service = HuggingFaceService()
    return _hf_service


def get_llm_for_agent(agent_name: str) -> LLMService:
    """
    Get appropriate LLM service for agent.
    
    Agent → LLM Mapping:
    - macro_trends / sentiment → Hugging Face
    - risk_agent / scenario_agent / memo_writer → Gemini
    
    Args:
        agent_name: Name of the agent
    
    Returns:
        LLM service instance
    """
    agent_name_lower = agent_name.lower()
    
    # Macro Sentiment uses Hugging Face
    if "macro" in agent_name_lower or "sentiment" in agent_name_lower:
        return get_hf_service()
    
    # All other agents use Gemini
    return get_gemini_service()


# Compatibility wrapper for existing code
class LLMWrapper:
    """Wrapper to mimic ChatOllama interface for compatibility."""
    
    def __init__(self, agent_name: str, temperature: float = 0.7):
        """
        Initialize LLM wrapper.
        
        Args:
            agent_name: Name of the agent (determines which LLM to use)
            temperature: Temperature for generation
        """
        self.agent_name = agent_name
        self.temperature = temperature
        self.llm_service = get_llm_for_agent(agent_name)
    
    def invoke(self, prompt: str) -> "LLMResponse":
        """
        Invoke LLM with prompt.
        
        Args:
            prompt: Input prompt
        
        Returns:
            LLMResponse object with content attribute
        """
        response_text = self.llm_service.invoke(prompt, temperature=self.temperature)
        return LLMResponse(response_text)


class LLMResponse:
    """Response wrapper to mimic ChatOllama response."""
    
    def __init__(self, content: str):
        """
        Initialize response.
        
        Args:
            content: Response text
        """
        self.content = content
    
    def __str__(self) -> str:
        return self.content

