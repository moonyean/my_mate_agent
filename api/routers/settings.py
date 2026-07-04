from __future__ import annotations

from fastapi import APIRouter

from api.deps import get_settings_manager
from core.config import AgentSettings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings():
    return get_settings_manager().load().model_dump()


@router.put("")
def update_settings(body: AgentSettings):
    get_settings_manager().save(body)
    return {"ok": True, "settings": body.model_dump()}
