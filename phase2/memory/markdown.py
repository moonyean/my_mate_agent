from __future__ import annotations

from pathlib import Path

_DEFAULT_PERSONA = """\
# Persona
You are a helpful CLI computer-use agent running on Windows.
You assist users with file management, code execution, and system tasks.
You always respect user intent and ask for confirmation before dangerous operations.
""".strip()

_DEFAULT_LONG_MEMORY = """\
# Long-term Memory
(No entries yet. Summaries of past sessions will be added here automatically.)
""".strip()

_DEFAULT_PROJECT_MEMORY = """\
# Project Memory
(No entries yet. Add project-specific context here manually or via the agent.)
""".strip()


class MarkdownMemory:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        self.persona_path = data_dir / "persona.md"
        self.long_memory_path = data_dir / "long_memory.md"
        self.project_memory_path = data_dir / "project_memory.md"
        self._init_defaults()

    def _init_defaults(self) -> None:
        if not self.persona_path.exists():
            self.persona_path.write_text(_DEFAULT_PERSONA, encoding="utf-8")
        if not self.long_memory_path.exists():
            self.long_memory_path.write_text(_DEFAULT_LONG_MEMORY, encoding="utf-8")
        if not self.project_memory_path.exists():
            self.project_memory_path.write_text(_DEFAULT_PROJECT_MEMORY, encoding="utf-8")

    def read_persona(self) -> str:
        return self.persona_path.read_text(encoding="utf-8")

    def read_long_memory(self) -> str:
        return self.long_memory_path.read_text(encoding="utf-8")

    def read_project_memory(self) -> str:
        return self.project_memory_path.read_text(encoding="utf-8")

    def update_long_memory(self, content: str) -> None:
        self.long_memory_path.write_text(content, encoding="utf-8")

    def update_project_memory(self, content: str) -> None:
        self.project_memory_path.write_text(content, encoding="utf-8")

    def build_context_block(self) -> str:
        persona = self.read_persona()
        long_mem = self.read_long_memory()
        project_mem = self.read_project_memory()
        return f"{persona}\n\n{long_mem}\n\n{project_mem}"
