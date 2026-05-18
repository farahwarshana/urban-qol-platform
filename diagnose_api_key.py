#!/usr/bin/env python3
"""
Quick API Key Diagnostic Tool
Tests your OpenAI API key and tells you what's wrong
"""

import os
import sys
from pathlib import Path

def check_env_file():
    """Check if .env file exists and is readable."""
    print("=" * 60)
    print("1. CHECKING .ENV FILE")
    print("=" * 60)
    
    env_path = Path(".env")
    if not env_path.exists():
        print("❌ .env file not found!")
        print(f"   Expected at: {env_path.absolute()}")
        print("   Fix: Run 'cp .env.example .env' in project root")
        return False
    
    print(f"✅ .env file found at: {env_path.absolute()}")
    
    # Read and check content
    with open(env_path, 'r') as f:
        content = f.read()
    
    if 'OPENAI_API_KEY' not in content:
        print("❌ OPENAI_API_KEY not found in .env")
        print("   Fix: Add 'OPENAI_API_KEY=sk-...' to .env file")
        return False
    
    print("✅ OPENAI_API_KEY found in .env")
    
    # Check for common formatting issues
    for line in content.split('\n'):
        if line.startswith('OPENAI_API_KEY'):
            if '=' not in line:
                print("❌ Invalid format (missing '='):", line)
                return False
            
            key_part = line.split('=', 1)[1].strip()
            
            if not key_part:
                print("❌ API key is empty!")
                return False
            
            if key_part.startswith('"') or key_part.startswith("'"):
                print("⚠️  WARNING: API key has quotes")
                print("   Found:", line)
                print("   Fix: Remove quotes - should be: OPENAI_API_KEY=sk-...")
                return False
            
            if not key_part.startswith('sk-'):
                print(f"❌ API key doesn't start with 'sk-'")
                print(f"   Found: {key_part[:20]}...")
                return False
            
            print(f"✅ API key format looks correct")
            print(f"   Starts with: {key_part[:20]}...")
            print(f"   Length: {len(key_part)} characters")
            return True
    
    return False


def check_env_loaded():
    """Check if environment variables are loaded."""
    print("\n" + "=" * 60)
    print("2. CHECKING ENVIRONMENT VARIABLES")
    print("=" * 60)
    
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("❌ OPENAI_API_KEY not loaded into environment!")
        print("   This means .env file wasn't properly read")
        print("   Fix: Make sure .env file is in the current directory")
        return False
    
    print(f"✅ API key loaded from .env")
    print(f"   Value: {api_key[:30]}...")
    return True


def test_openai_connection():
    """Test actual connection to OpenAI API."""
    print("\n" + "=" * 60)
    print("3. TESTING OPENAI API CONNECTION")
    print("=" * 60)
    
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ API key not available to test")
        return False
    
    try:
        from openai import OpenAI
        print("✅ OpenAI library imported successfully")
    except ImportError:
        print("❌ Cannot import OpenAI library")
        print("   Fix: Run 'pip install openai'")
        return False
    
    try:
        client = OpenAI(api_key=api_key)
        print("✅ OpenAI client created")
        
        # Try to make a simple API call
        print("   Testing API call... (this costs ~$0.0001)")
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Say 'API is working'"}],
            max_tokens=10,
            timeout=10
        )
        
        reply = response.choices[0].message.content
        print(f"✅ API CALL SUCCESSFUL!")
        print(f"   Response: '{reply}'")
        return True
        
    except Exception as e:
        error_str = str(e)
        print(f"❌ API Call Failed: {error_str[:200]}")
        
        # Provide helpful diagnosis
        if "401" in error_str or "invalid_api_key" in error_str or "Incorrect API key" in error_str:
            print("\n   🔴 PROBLEM: Invalid API Key")
            print("   Likely causes:")
            print("      1. API key is incorrect or incomplete")
            print("      2. API key has been revoked")
            print("      3. API key is from wrong account")
            print("      4. Account billing is not set up")
            print("\n   SOLUTIONS:")
            print("      1. Go to https://platform.openai.com/account/api-keys")
            print("      2. Create a NEW API key")
            print("      3. Copy the ENTIRE key (it's very long)")
            print("      4. Replace key in .env file")
            print("      5. Restart backend server")
            
        elif "rate_limit" in error_str.lower():
            print("\n   🟡 PROBLEM: Rate Limited")
            print("   You're sending too many requests")
            print("   Wait a few minutes and try again")
            
        elif "connection" in error_str.lower():
            print("\n   🟡 PROBLEM: Network Connection")
            print("   Check your internet connection")
            
        else:
            print(f"\n   Error details: {error_str}")
        
        return False


def main():
    print("\n" + "🔍 " * 20)
    print("OPENAI API KEY DIAGNOSTIC TOOL")
    print("🔍 " * 20 + "\n")
    
    checks = {
        "ENV file exists": check_env_file(),
    }
    
    if checks["ENV file exists"]:
        checks["ENV variables loaded"] = check_env_loaded()
    
    if checks.get("ENV variables loaded"):
        checks["OpenAI connection"] = test_openai_connection()
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    
    for check, result in checks.items():
        status = "✅" if result else "❌"
        print(f"{status} {check}")
    
    print(f"\nResult: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n🎉 Your API key is working! Chatbot should now work.")
    else:
        print("\n⚠️  Some checks failed. See details above for fixes.")
    
    return passed == total


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
