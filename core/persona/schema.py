from __future__ import annotations
from pydantic import BaseModel, Field


class PersonaIdentity(BaseModel):
    name: str
    role: str


class PersonaTone(BaseModel):
    speech_style: str
    personality: str


class PersonaRules(BaseModel):
    behavior: list[str] = Field(default_factory=list)


class PersonaConstraints(BaseModel):
    forbidden: list[str] = Field(default_factory=list)


class PersonaMemoryBinding(BaseModel):
    session_id: str | None = None
    note: str = ""


class Persona(BaseModel):
    identity: PersonaIdentity
    tone: PersonaTone
    rules: PersonaRules = Field(default_factory=PersonaRules)
    constraints: PersonaConstraints = Field(default_factory=PersonaConstraints)
    memory_binding: PersonaMemoryBinding = Field(default_factory=PersonaMemoryBinding)
