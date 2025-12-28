"""
Test script to verify Gemini API key and list available models.
"""

import os
import requests

# Try to load from .env file manually
API_KEY = None
try:
    with open('.env', 'r') as f:
        for line in f:
            if line.startswith('GEMINI_API_KEY='):
                API_KEY = line.split('=', 1)[1].strip().strip('"').strip("'")
                break
except:
    pass

# Fallback to environment variable
if not API_KEY:
    API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    import sys
    if len(sys.argv) > 1:
        API_KEY = sys.argv[1]
    else:
        print("ERROR: GEMINI_API_KEY not found")
        print("Usage: python test_gemini_api.py [API_KEY]")
        print("Or set GEMINI_API_KEY environment variable")
        exit(1)

print(f"Testing Gemini API with key: {API_KEY[:10]}...{API_KEY[-4:]}")
print()

# Test 1: List available models
print("Test 1: Listing available models...")
try:
    list_url = "https://generativelanguage.googleapis.com/v1/models"
    response = requests.get(
        list_url,
        params={"key": API_KEY},
        timeout=10
    )
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        models = data.get("models", [])
        print(f"Found {len(models)} models:")
        for model in models[:10]:  # Show first 10
            name = model.get("name", "").replace("models/", "")
            display_name = model.get("displayName", "")
            print(f"  - {name} ({display_name})")
        print()
    else:
        print(f"Error: {response.status_code}")
        print(f"Response: {response.text[:500]}")
        print()
except Exception as e:
    print(f"Error listing models: {e}")
    print()

# Test 2: Try to generate content with a simple model
print("Test 2: Testing content generation...")
models_to_test = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-pro",
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash",
    "gemini-pro"
]

for model in models_to_test:
    try:
        api_url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent"
        
        payload = {
            "contents": [{
                "parts": [{
                    "text": "Say hello in one word."
                }]
            }],
            "generationConfig": {
                "temperature": 0.7
            }
        }
        
        response = requests.post(
            api_url,
            params={"key": API_KEY},
            json=payload,
            timeout=30
        )
        
        print(f"Model: {model}")
        print(f"  Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if "candidates" in result and len(result["candidates"]) > 0:
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                print(f"  SUCCESS! Response: {text}")
                print(f"\n✅ Working model found: {model}")
                break
            else:
                print(f"  No candidates in response")
        else:
            error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
            error_msg = error_data.get("error", {}).get("message", response.text[:200])
            print(f"  Error: {error_msg}")
    except Exception as e:
        print(f"  Exception: {e}")
    print()

print("\nTest complete!")

