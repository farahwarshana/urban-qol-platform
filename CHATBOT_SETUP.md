# Hadary AI Chatbot Setup Guide

This guide explains how to connect the **Hadary Frontend** with the **Backend LLM** to create a fully functional chatbot.

---

## Overview

The Urban QOL Platform now includes **Hadary**, an AI-powered chatbot that:
- Provides real-time chat assistance about urban quality of life analysis
- Integrates with your analysis results for contextual responses
- Uses OpenAI's API (GPT-4 or GPT-3.5) for intelligent conversations
- Appears as a floating widget in the bottom-right corner of the dashboard

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (HTML/CSS/JS)                   │
│  • dashboard.html - Chatbot UI in floating widget            │
│  • js/dashboard.js - Chatbot logic & message handling        │
│  • css/styles.css - Chatbot styling & animations            │
└────────────────┬────────────────────────────────────────────┘
                 │ HTTP Requests to /ai/chat
                 ↓
┌─────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI)                         │
│  • backend/main.py - FastAPI app configuration              │
│  • backend/ai_routes.py - Chat endpoint & message handling  │
│  • ai_agent/llm_agent.py - LLM integration with OpenAI     │
└────────────────┬────────────────────────────────────────────┘
                 │ API calls
                 ↓
┌─────────────────────────────────────────────────────────────┐
│              OpenAI API (GPT-4 / GPT-3.5)                    │
│  • Processes natural language requests                       │
│  • Generates contextual responses                            │
└─────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

1. **Python 3.8+** installed
2. **Node.js & npm** (optional, for frontend development)
3. **OpenAI API Key** (get one at https://platform.openai.com/api-keys)
4. **PostgreSQL** (if using database features)

---

## Setup Instructions

### 1. Create Environment Configuration

```bash
# Copy the example .env file
cp .env.example .env

# Edit .env and add your OpenAI API key
# Windows (PowerShell):
notepad .env

# Or Mac/Linux:
nano .env
```

**Required Variables:**
```env
# Your OpenAI API key (required for chatbot)
OPENAI_API_KEY=sk-your-api-key-here

# Optional: Select model and parameters
LLM_MODEL=gpt-4-turbo        # or gpt-3.5-turbo for faster/cheaper
LLM_TEMPERATURE=0.7          # 0.0 (deterministic) to 1.0 (creative)
LLM_MAX_TOKENS=1500          # Response length limit
```

### 2. Install Python Dependencies

```bash
# Navigate to backend directory
cd backend

# Install required packages
pip install -r requirements.txt

# Verify OpenAI package is installed
pip install openai
```

### 3. Start the Backend Server

```bash
# From backend directory
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Or on Windows:
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### 4. Open Frontend in Browser

```bash
# Navigate to frontend directory
cd frontend

# Start a simple HTTP server (Python)
python -m http.server 8080

# Or use Node.js:
npx http-server

# Or open directly in browser:
file:///path/to/urban-qol-platform/frontend/dashboard.html
```

**Access the app:** http://localhost:8080/dashboard.html

---

## Using the Chatbot

### Opening the Chatbot
1. **Click the bot icon** (bottom-right corner of dashboard)
2. The chat window will slide up

### Sending Messages
1. **Type your message** in the input field
2. **Press Enter** or click **Send**
3. **Wait for Hadary's response** (typing indicator shows while processing)

### Example Queries
- "What does NDVI mean?"
- "How can I improve vegetation coverage?"
- "What's causing high heat index in my analysis?"
- "What analysis services are available?"
- "Recommend an intervention for my area"

---

## Troubleshooting

### Issue: "Couldn't connect to the AI backend"

**Solutions:**
1. Check backend is running: http://localhost:8000/health
2. Verify CORS is enabled (should be in main.py)
3. Check browser console for error details (F12 → Console tab)
4. Verify frontend is accessing correct API_BASE_URL

### Issue: "OpenAI API key not configured"

**Solutions:**
1. Verify .env file exists in project root
2. Check OPENAI_API_KEY is set correctly (no extra spaces)
3. Test API key at: https://platform.openai.com/account/api-keys
4. Restart backend server after updating .env

### Issue: Slow responses

**Solutions:**
1. Use faster model: Change LLM_MODEL to `gpt-3.5-turbo`
2. Reduce LLM_MAX_TOKENS value
3. Check internet connection
4. Check OpenAI API status: https://status.openai.com

### Issue: "typing indicator stays forever"

**Solutions:**
1. Check backend logs for errors
2. Verify OpenAI API isn't rate limited
3. Increase timeout in frontend (dashboard.js, line ~50)
4. Clear browser cache and reload

---

## Development

### Frontend Modifications

**Chat Functions** (frontend/js/dashboard.js):
- `toggleChatbot()` - Open/close chatbot
- `sendChatMessage()` - Send message and get response
- `addBotMessage(text)` - Display bot response
- `clearChatHistory()` - Clear conversation

**Chat Styling** (frontend/css/styles.css):
- `.chatbot` - Main container
- `.chat-msg` - Message styling
- `.typing-indicator` - Animated typing bubble

### Backend Modifications

**Main Route** (backend/ai_routes.py):
- `POST /ai/chat` - Chat endpoint
- Accepts: `message`, `messages`, `plain_text`, `analysis_context`
- Returns: `{ "reply": "..." }`

**LLM Integration** (ai_agent/llm_agent.py):
- `call_llm(prompt)` - Send prompt to OpenAI
- `build_llm_prompt()` - Construct system prompts
- Uses environment variables for configuration

---

## Advanced Features

### Integrating with Analysis Results

The chatbot can receive context from recent analyses:

```javascript
// In frontend, analysis context is automatically captured
const analysisContext = {
  service: "heat-index",  // Last analysis type
  score: 75,              // Analysis score
  area: "Khartoum"        // Area name (if available)
};

// Automatically sent with chat requests
```

### Customizing Hadary's Behavior

Edit the **system prompt** in `ai_agent/llm_agent.py`:

```python
def build_llm_prompt(summary, user_analysis=None, ...):
    guidance = (
        "You are an expert in urban quality of life. "
        "Focus on: vegetation, heat mitigation, safety, transport..."
    )
    # Modify guidance to change Hadary's expertise
```

### Rate Limiting

For production, add rate limiting to prevent abuse:

```python
# In backend/main.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/chat")
@limiter.limit("10/minute")  # 10 requests per minute
def chat_endpoint(body: ChatRequest):
    ...
```

---

## Deployment

### Production Checklist

- [ ] Set `OPENAI_API_KEY` in production environment
- [ ] Disable debug mode: Change `--reload` to no reload
- [ ] Set up HTTPS/SSL certificates
- [ ] Configure CORS for production domain
- [ ] Enable logging to file
- [ ] Set up rate limiting
- [ ] Monitor OpenAI API costs
- [ ] Test with multiple concurrent users

### Deploying to Cloud

#### Option 1: Heroku
```bash
# Create Procfile
web: gunicorn -w 4 -b 0.0.0.0:$PORT backend.main:app

# Deploy
heroku create
heroku config:set OPENAI_API_KEY=sk-...
git push heroku main
```

#### Option 2: Docker
```bash
# Create Dockerfile (in backend/)
FROM python:3.10
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# Build and run
docker build -t urban-qol-api .
docker run -e OPENAI_API_KEY=sk-... -p 8000:8000 urban-qol-api
```

#### Option 3: AWS Lambda
- Use AWS API Gateway + Lambda for serverless deployment
- Store OPENAI_API_KEY in AWS Secrets Manager
- Use AWS S3 for frontend hosting

---

## Cost Estimation

**OpenAI API Pricing (as of 2024):**
- GPT-4 Turbo: ~$0.01 per 1K input tokens
- GPT-3.5 Turbo: ~$0.0005 per 1K input tokens

**Typical conversation costs:**
- GPT-4: ~$0.01-0.05 per interaction
- GPT-3.5: ~$0.0005-0.002 per interaction

**Monitor costs:** https://platform.openai.com/account/billing/overview

---

## Support & Documentation

- **OpenAI Docs:** https://platform.openai.com/docs
- **FastAPI Docs:** https://fastapi.tiangolo.com
- **Local API Docs:** http://localhost:8000/docs (when server running)

---

## License & Credits

- **Framework:** FastAPI, Leaflet.js, Bootstrap 5
- **AI Engine:** OpenAI GPT
- **Chatbot Name:** Hadary (meaning "The Guide" in Arabic)

---

**Last Updated:** May 17, 2024
**Version:** 1.0.0
