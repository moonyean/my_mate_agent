from __future__ import annotations

from pydantic import BaseModel, Field


class PersonaIdentity(BaseModel):
    name: str = Field(description="캐릭터 이름")
    role: str = Field(description="캐릭터 역할 (예: 마법사, 우주 파일럿)")


class PersonaTone(BaseModel):
    speech_style: str = Field(description="말투 (예: 친근하고 격식없는 말투)")
    personality: str = Field(description="성격 (예: 호기심 많고 열정적)")


class PersonaRules(BaseModel):
    behavior: list[str] = Field(default_factory=list, description="행동 규칙 목록")


class PersonaConstraints(BaseModel):
    forbidden: list[str] = Field(default_factory=list, description="금지 사항 목록")


class PersonaMemoryBinding(BaseModel):
    session_id: str | None = None
    note: str = ""


class Persona(BaseModel):
    identity: PersonaIdentity
    tone: PersonaTone
    rules: PersonaRules = Field(default_factory=PersonaRules)
    constraints: PersonaConstraints = Field(default_factory=PersonaConstraints)
    memory_binding: PersonaMemoryBinding = Field(default_factory=PersonaMemoryBinding)
