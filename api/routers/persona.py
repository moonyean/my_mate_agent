from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import get_persona_manager
from core.persona.manager import serialize_persona, parse_persona_md
from core.persona.schema import Persona, PersonaIdentity, PersonaTone, PersonaRules, PersonaConstraints
from core.persona.validator import validate_persona, ValidationError

router = APIRouter(prefix="/persona", tags=["persona"])


class PersonaUpdateRequest(BaseModel):
    name: str
    role: str
    speech_style: str
    personality: str
    rules: list[str] = []
    constraints: list[str] = []


@router.get("")
def get_persona():
    mgr = get_persona_manager()
    p = mgr.load_persona()
    return {
        "raw": mgr.read_persona_raw(),
        "parsed": p.model_dump(),
    }


@router.put("")
def update_persona(body: PersonaUpdateRequest):
    persona = Persona(
        identity=PersonaIdentity(name=body.name, role=body.role),
        tone=PersonaTone(speech_style=body.speech_style, personality=body.personality),
        rules=PersonaRules(behavior=body.rules),
        constraints=PersonaConstraints(forbidden=body.constraints),
    )
    ok, msg = validate_persona(persona)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)
    try:
        get_persona_manager().save_persona(persona)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True, "persona": persona.model_dump()}


@router.post("/validate")
def validate(body: PersonaUpdateRequest):
    persona = Persona(
        identity=PersonaIdentity(name=body.name, role=body.role),
        tone=PersonaTone(speech_style=body.speech_style, personality=body.personality),
        rules=PersonaRules(behavior=body.rules),
        constraints=PersonaConstraints(forbidden=body.constraints),
    )
    ok, msg = validate_persona(persona)
    return {"valid": ok, "message": msg}


@router.get("/user-rules")
def get_user_rules():
    return {"content": get_persona_manager().read_user_rules()}


@router.put("/user-rules")
def update_user_rules(body: dict):
    content = body.get("content", "")
    get_persona_manager().save_user_rules(content)
    return {"ok": True}
