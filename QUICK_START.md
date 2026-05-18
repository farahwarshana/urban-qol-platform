# Quick Start: Hadary Chatbot (5 minutes)

## 1. Get Your OpenAI API Key
- Go to https://platform.openai.com/api-keys
- Create a new API key
- Copy it (you'll use it in step 2)

## 2. Create .env File
```bash
# In project root directory, create .env file
cp .env.example .env

# Edit .env and add:
OPENAI_API_KEY=sk-your-api-key-here
```

## 3. Install Backend Dependencies
```bash
cd backend
pip install -r requirements.txt
pip install openai  # Make sure this is installed
```

## 4. Start Backend Server
```bash
# From backend directory
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Wait until you see: `Uvicorn running on http://0.0.0.0:8000`

## 5. Open Dashboard in Browser
```
File → Open → C:\Users\Mr Mohammed\urban-qol-platform\frontend\dashboard.html
```

Or if using a server:
```
http://localhost:8080/dashboard.html
```

## 6. Test the Chatbot
1. **Click the bot icon** in bottom-right corner
2. **Type:** "Hello! Who are you?"
3. **Press Enter** and wait for response

---

## ✅ It's Working If:
- ✅ Chat window opens and closes smoothly
- ✅ You can type messages
- ✅ Bot responds within 5-10 seconds
- ✅ No red error messages in browser console (F12)

## ❌ Troubleshooting

| Problem | Solution |
|---------|----------|
| "Couldn't connect" | Check backend is running on http://localhost:8000/health |
| "API key not configured" | Verify .env file exists and OPENAI_API_KEY is set |
| Slow responses | Use gpt-3.5-turbo instead of gpt-4 in .env |
| Typing forever | Check backend logs for errors, restart server |

---

## Next Steps
- Read full guide: [CHATBOT_SETUP.md](CHATBOT_SETUP.md)
- Customize Hadary's behavior (see Development section)
- Deploy to production (see Deployment section)

**Questions?** Check the backend logs (terminal where you ran uvicorn)
