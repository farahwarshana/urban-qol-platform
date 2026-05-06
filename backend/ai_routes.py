from typing import List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from ai_agent.llm_agent import chat_with_hadary, LLMError

router = APIRouter(prefix="/ai", tags=["AI"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: Optional[str] = None
    messages: Optional[List[ChatMessage]] = None


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(body: ChatRequest = Body(...)):
    if body.messages:
        messages = body.messages
    elif body.message:
        messages = [ChatMessage(role="user", content=body.message)]
    else:
        raise HTTPException(status_code=422, detail="Request must include 'message' or 'messages'.")

    try:
        print(f"[AI ROUTE] Chat request received with {len(messages)} messages")
        reply = chat_with_hadary(messages)
        print(f"[AI ROUTE] Chat response ready")
        return ChatResponse(reply=reply)
    except LLMError as exc:
        print(f"[AI ROUTE] LLMError: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        print(f"[AI ROUTE] Exception: {exc}")
        raise HTTPException(status_code=500, detail=f"Chat backend failed: {exc}")
