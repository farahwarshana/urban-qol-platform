from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from ai_agent.llm_agent import chat_with_hadary, generate_recommendations, LLMError

router = APIRouter(prefix="/ai", tags=["AI"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: Optional[str] = None
    messages: Optional[List[ChatMessage]] = None


class ChatResponse(BaseModel):
    reply: str


class RecommendationsRequest(BaseModel):
    service: str
    service_label: str
    inputs: Optional[Dict[str, Any]] = None
    full_area: Optional[Dict[str, Any]] = None
    grid: Optional[Dict[str, Any]] = None


class RecommendationSection(BaseModel):
    type: str   # "insight" | "warning" | "recommendation" | "data" | "finding"
    title: str
    items: List[str]


class HighlightFilter(BaseModel):
    property: str
    op: str          # "gt" | "lt" | "gte" | "lte" | "eq" | "in"
    value: Any = None


class MapHighlight(BaseModel):
    id: str
    label: str
    color: str
    description: str
    filter: HighlightFilter


class RecommendationsResponse(BaseModel):
    headline: str
    overall_score: Optional[int] = None
    score_label: Optional[str] = None
    sections: List[RecommendationSection]
    map_highlights: List[MapHighlight] = []


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


@router.post("/recommendations", response_model=RecommendationsResponse)
def recommendations_endpoint(body: RecommendationsRequest = Body(...)):
    try:
        print(f"[AI ROUTE] Recommendations request for service: {body.service}")
        result = generate_recommendations(
            service=body.service,
            service_label=body.service_label,
            inputs=body.inputs or {},
            full_area=body.full_area or {},
            grid=body.grid,
        )
        print(f"[AI ROUTE] Recommendations ready")
        return result
    except LLMError as exc:
        print(f"[AI ROUTE] LLMError: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        print(f"[AI ROUTE] Exception: {exc}")
        raise HTTPException(status_code=500, detail=f"Recommendations backend failed: {exc}")
