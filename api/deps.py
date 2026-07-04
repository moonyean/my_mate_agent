from __future__ import annotations

from pathlib import Path

from core.config import AgentSettings, SettingsManager
from core.memory.db import MemoryDB
from core.memory.markdown import MarkdownMemory
from core.persona.manager import PersonaManager

DATA_DIR = Path(__file__).parent.parent / "data"
WORKSPACE = Path(__file__).parent.parent / "workspace"

_db: MemoryDB | None = None
_markdown: MarkdownMemory | None = None
_persona_manager: PersonaManager | None = None
_settings_manager: SettingsManager | None = None


def init_services() -> None:
    global _db, _markdown, _persona_manager, _settings_manager
    DATA_DIR.mkdir(exist_ok=True)
    WORKSPACE.mkdir(exist_ok=True)
    _db = MemoryDB(DATA_DIR / "memory.db")
    _markdown = MarkdownMemory(DATA_DIR)
    _persona_manager = PersonaManager(DATA_DIR)
    _settings_manager = SettingsManager(DATA_DIR / "settings.json")


def shutdown_services() -> None:
    if _db:
        _db.close()


def get_db() -> MemoryDB:
    assert _db is not None
    return _db


def get_markdown() -> MarkdownMemory:
    assert _markdown is not None
    return _markdown


def get_persona_manager() -> PersonaManager:
    assert _persona_manager is not None
    return _persona_manager


def get_settings_manager() -> SettingsManager:
    assert _settings_manager is not None
    return _settings_manager


def get_workspace() -> Path:
    return WORKSPACE


def get_settings() -> AgentSettings:
    return get_settings_manager().load()
