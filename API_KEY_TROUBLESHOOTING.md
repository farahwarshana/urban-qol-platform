# OpenAI API Key Troubleshooting

## The Problem
Your API key is being rejected with a 401 error, meaning:
- ❌ The API key is invalid, expired, or corrupted
- ❌ It may have been revoked
- ❌ Or there's a formatting issue

## Solutions (Try These in Order)

### 1. Verify Your API Key Format
Your .env file should look exactly like this:
```env
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Check for these issues:**
- ✅ No extra spaces before/after the key
- ✅ No quotes around the key (❌ `OPENAI_API_KEY="sk-..."` is wrong)
- ✅ Starts with `sk-` (or `sk-proj-` for newer keys)
- ✅ No newlines or tabs

**To verify your .env file:**
```bash
# Open the file in a terminal to see exact content
cat .env
# Or on Windows PowerShell:
Get-Content .env
```

---

### 2. Get a Fresh OpenAI API Key

**Old key might be expired. Let's create a new one:**

1. Go to: https://platform.openai.com/account/api-keys
2. Log in with your OpenAI account
3. **Delete the old key** if it shows as revoked
4. Click **"Create new secret key"**
5. Copy the entire key (it starts with `sk-proj-`)
6. **Important: Save it somewhere safe - you won't see it again!**

---

### 3. Update Your .env File

```bash
# Open .env in editor
# Windows:
notepad .env

# Mac/Linux:
nano .env
```

**Replace the entire line:**
```env
OPENAI_API_KEY=sk-proj-YourNewKeyHere
```

**Then save and close**

---

### 4. Verify API Key is Valid

Test your key with this Python script:

```bash
# Create test script
cat > test_api_key.py << 'EOF'
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
print(f"API Key found: {api_key[:20]}..." if api_key else "❌ API Key not found")

try:
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=10
    )
    print("✅ API Key is VALID!")
    print(f"Response: {response.choices[0].message.content}")
except Exception as e:
    print(f"❌ API Key INVALID: {str(e)}")
EOF

# Run the test
python test_api_key.py
```

---

### 5. Restart Backend After Updating .env

```bash
# Stop the running server (Ctrl+C in the terminal)
# Then restart it:
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Important:** The backend must be restarted to read the updated .env file

---

### 6. Check for Common Mistakes

| Issue | Example | Fix |
|-------|---------|-----|
| **Quotes around key** | `OPENAI_API_KEY="sk-..."` | Remove quotes: `OPENAI_API_KEY=sk-...` |
| **Extra spaces** | `OPENAI_API_KEY = sk-...` | Remove spaces: `OPENAI_API_KEY=sk-...` |
| **Partial key** | `sk-proj-abc123...` (incomplete) | Get full key from OpenAI dashboard |
| **Free trial expired** | Old key from trial account | Create new account or add billing |
| **Organization key** | Using org key instead of user key | Use personal API key from account/api-keys |

---

### 7. If You See This Error Message

```
"Incorrect API key provided: sk-proj-****..."
```

This means:
1. OpenAI received your key
2. But the format/content is wrong

**Solutions:**
- ✅ Double-check you copied the ENTIRE key (very long string)
- ✅ Verify no spaces or special characters were added
- ✅ Try a brand new API key from the dashboard
- ✅ Check if your OpenAI account has billing enabled

---

### 8. Verify Backend is Reading .env

Add this debug code to check if backend sees your key:

**In backend/main.py, add near the top:**
```python
from dotenv import load_dotenv
load_dotenv()
import os

api_key = os.getenv("OPENAI_API_KEY")
print(f"DEBUG: API key is set: {bool(api_key)}")
print(f"DEBUG: API key starts with: {api_key[:10] if api_key else 'NOT SET'}")
```

Then restart backend and check the logs.

---

## Quick Checklist

```
□ I created a NEW API key (not reusing old one)
□ I copied the ENTIRE key (it's very long)
□ I updated .env file with new key
□ .env file has NO quotes around the key
□ .env file has NO extra spaces
□ Backend server was RESTARTED after updating .env
□ I ran python test_api_key.py and it passed
```

---

## If You Still Get 401 Error

**Check your OpenAI account:**
1. Go to: https://platform.openai.com/account/billing/overview
2. Look for "Billing" or "Payment method"
3. Ensure you have a valid payment method or free trial credits
4. Check if your account/API access is suspended

**If billing is the issue:**
- Add a credit card to your OpenAI account
- Or contact OpenAI support if your account was limited

---

## Next: Test the Chatbot Again

Once your API key is working:

```bash
# Backend should be running
uvicorn main:app --reload

# In another terminal, test the API
python test_api_key.py

# Then open dashboard and click bot icon
```

---

## Still Stuck?

Run the health check script:
```bash
python check_chatbot.py
```

This will tell you exactly what's wrong with your setup.

---

**Common cause:** The API key is incomplete or has been revoked. Getting a fresh key from the OpenAI dashboard usually fixes this! 🔑
