from __future__ import annotations

from pathlib import Path

_DEFAULT_LONG = "# Long-term Memory\n(No entries yet.)"
_DEFAULT_PROJECT = "# Project Memory\n(No entries yet.)"


class MarkdownMemory:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        self.long_path = data_dir / "long_memory.md"
        self.project_path = data_dir / "project_memory.md"
        if not self.long_path.exists():
            self.long_path.write_text(_DEFAULT_LONG, encoding="utf-8")
        if not self.project_path.exists():
            self.project_path.write_text(_DEFAULT_PROJECT, encoding="utf-8")

    def read_long(self) -> str:
        return self.long_path.read_text(encoding="utf-8")

    def read_project(self) -> str:
        return self.project_path.read_text(encoding="utf-8")

    def update_long(self, content: str) -> None:
        self.long_path.write_text(content, encoding="utf-8")

    def update_project(self, content: str) -> None:
        self.project_path.write_text(content, encoding="utf-8")
