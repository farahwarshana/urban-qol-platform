#!/usr/bin/env python3
"""
Chatbot Health Check Script
Verifies that all components for the Hadary chatbot are properly configured.
"""

import os
import sys
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv()

def check_env_variables():
    """Check if required environment variables are set."""
    print("=" * 60)
    print("CHECKING ENVIRONMENT VARIABLES")
    print("=" * 60)
    
    required = ["OPENAI_API_KEY"]
    optional = ["LLM_MODEL", "LLM_TEMPERATURE", "LLM_MAX_TOKENS"]
    
    found_all = True
    for var in required:
        value = os.getenv(var)
        if value:
            masked = value[:10] + "..." if len(value) > 10 else value
            print(f"✅ {var}: {masked}")
        else:
            print(f"❌ {var}: NOT SET")
            found_all = False
    
    print("\nOptional variables:")
    for var in optional:
        value = os.getenv(var, "not set")
        print(f"   {var}: {value}")
    
    return found_all


def check_python_packages():
    """Check if required Python packages are installed."""
    print("\n" + "=" * 60)
    print("CHECKING PYTHON PACKAGES")
    print("=" * 60)
    
    required_packages = {
        "fastapi": "FastAPI framework",
        "uvicorn": "ASGI server",
        "openai": "OpenAI API client",
        "pydantic": "Data validation",
        "python-dotenv": "Environment variables",
    }
    
    all_found = True
    for package, description in required_packages.items():
        try:
            __import__(package)
            print(f"✅ {package:20} - {description}")
        except ImportError:
            print(f"❌ {package:20} - {description} (NOT INSTALLED)")
            all_found = False
    
    return all_found


def check_backend_running():
    """Check if backend server is running."""
    print("\n" + "=" * 60)
    print("CHECKING BACKEND SERVER")
    print("=" * 60)
    
    url = "http://localhost:8000/health"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Backend is running")
            print(f"   Status: {data.get('status')}")
            print(f"   Message: {data.get('message')}")
            return True
        else:
            print(f"❌ Backend returned status {response.status_code}")
            return False
    except requests.ConnectionError:
        print(f"❌ Cannot connect to {url}")
        print("   Make sure to run: uvicorn main:app --reload")
        return False
    except Exception as e:
        print(f"❌ Error checking backend: {str(e)}")
        return False


def test_chat_endpoint():
    """Test the /ai/chat endpoint."""
    print("\n" + "=" * 60)
    print("TESTING CHAT ENDPOINT")
    print("=" * 60)
    
    url = "http://localhost:8000/ai/chat"
    payload = {
        "message": "Hello! Are you working?",
        "plain_text": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            reply = data.get("reply", "")
            print(f"✅ Chat endpoint is working")
            print(f"   Response: {reply[:100]}...")
            return True
        elif response.status_code == 503:
            error = response.json().get("detail", "Service unavailable")
            print(f"❌ OpenAI API not configured: {error}")
            return False
        else:
            print(f"❌ Chat endpoint returned status {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
    except requests.ConnectionError:
        print(f"❌ Cannot connect to {url}")
        print("   Make sure backend is running")
        return False
    except requests.Timeout:
        print(f"⚠️  Chat request timed out (>30 seconds)")
        print("   This might indicate a slow API connection")
        return False
    except Exception as e:
        print(f"❌ Error testing chat: {str(e)}")
        return False


def check_frontend_files():
    """Check if frontend files exist."""
    print("\n" + "=" * 60)
    print("CHECKING FRONTEND FILES")
    print("=" * 60)
    
    base_path = Path(__file__).parent / "frontend"
    files = {
        "dashboard.html": "Main dashboard",
        "css/styles.css": "Styling",
        "js/dashboard.js": "Dashboard logic",
        "js/app.js": "App logic",
    }
    
    all_found = True
    for file, description in files.items():
        full_path = base_path / file
        if full_path.exists():
            size = full_path.stat().st_size
            print(f"✅ {file:30} - {description} ({size} bytes)")
        else:
            print(f"❌ {file:30} - {description} (NOT FOUND)")
            all_found = False
    
    return all_found


def check_ai_agent():
    """Check if AI agent is properly configured."""
    print("\n" + "=" * 60)
    print("CHECKING AI AGENT SETUP")
    print("=" * 60)
    
    try:
        from ai_agent.llm_agent import call_llm, build_llm_prompt
        print(f"✅ AI agent module imports correctly")
        
        # Test build_llm_prompt
        test_summary = {"test": "data"}
        prompt = build_llm_prompt(test_summary)
        if prompt and len(prompt) > 100:
            print(f"✅ LLM prompt builder works ({len(prompt)} chars)")
        else:
            print(f"⚠️  LLM prompt builder returned short prompt")
        
        return True
    except ImportError as e:
        print(f"❌ Cannot import AI agent: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Error checking AI agent: {str(e)}")
        return False


def generate_report():
    """Generate a comprehensive health check report."""
    print("\n\n" + "=" * 60)
    print("HADARY CHATBOT - HEALTH CHECK REPORT")
    print("=" * 60)
    
    checks = {
        "Environment Variables": check_env_variables(),
        "Python Packages": check_python_packages(),
        "Frontend Files": check_frontend_files(),
        "AI Agent Setup": check_ai_agent(),
        "Backend Server": check_backend_running(),
    }
    
    # Try chat test only if backend is running
    if checks["Backend Server"]:
        checks["Chat Endpoint"] = test_chat_endpoint()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    
    for check, result in checks.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {check}")
    
    print(f"\nOverall: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n🎉 All systems operational! Ready to chat with Hadary.")
        print("Open dashboard.html and click the bot icon in the bottom-right corner.")
    else:
        print("\n⚠️  Some issues detected. See details above.")
        print("\nTo fix common issues:")
        print("1. Make sure .env file exists and has OPENAI_API_KEY set")
        print("2. Run: pip install -r backend/requirements.txt")
        print("3. Run: uvicorn backend.main:app --reload")
    
    return passed == total


if __name__ == "__main__":
    success = generate_report()
    sys.exit(0 if success else 1)
