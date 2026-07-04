from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class AgentSettings(BaseModel):
    model_name: str = "gemma4:latest"
    ollama_base_url: str = "http://127.0.0.1:11434/v1"
    auto_approve_safe: bool = True
    timeout_seconds: int = 60


class SettingsManager:
    def __init__(self, path: Path) -> None:
        self.path = path
        if not path.exists():
            self.save(AgentSettings())

    def load(self) -> AgentSettings:
        return AgentSettings.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, settings: AgentSettings) -> None:
        self.path.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
