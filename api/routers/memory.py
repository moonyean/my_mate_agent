from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.deps import get_db, get_markdown
from core.memory.summarizer import summarize_to_long_memory

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/sessions")
def list_sessions():
    return {"sessions": get_db().get_all_sessions()}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, limit: int = 50):
    messages = get_db().get_recent_messages(session_id, limit=limit)
    if not messages:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"session_id": session_id, "messages": messages}


@router.get("/tool-logs")
def get_tool_logs(limit: int = 20):
    return {"logs": get_db().get_recent_tool_logs(limit=limit)}


@router.get("/long-memory")
def get_long_memory():
    return {"content": get_markdown().read_long()}


@router.put("/long-memory")
def update_long_memory(body: dict):
    get_markdown().update_long(body.get("content", ""))
    return {"ok": True}


@router.get("/project-memory")
def get_project_memory():
    return {"content": get_markdown().read_project()}


@router.put("/project-memory")
def update_project_memory(body: dict):
    get_markdown().update_project(body.get("content", ""))
    return {"ok": True}


@router.post("/summarize/{session_id}")
def summarize_session(session_id: str):
    result = summarize_to_long_memory(session_id, get_db(), get_markdown())
    if result.startswith("(요약 실패"):
        raise HTTPException(status_code=500, detail=result)
    return {"ok": True, "summary": result}
