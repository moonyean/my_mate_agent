from __future__ import annotations

import base64
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider


class AgentState(str, Enum):
    IDLE = "Idle"
    THINKING = "Thinking"
    RUNNING_TOOL = "Running Tool"
    WAITING_PERMISSION = "Waiting Permission"
    COMPLETED = "Completed"
    ERROR = "Error"


class ToolRequest(BaseModel):
    action: Literal["run_command", "write_file"] = Field(
        description="'run_command' to execute a shell command, 'write_file' to create or overwrite a text file."
    )
    task: str = Field(description="Short human-readable description of the action.")
    reason: str = Field(description="Why this action answers the user request.")

    # run_command fields
    command: list[str] | None = Field(
        default=None,
        description="Command and arguments. Required when action='run_command'.",
    )
    cwd: str | None = Field(default=None, description="Working directory (optional).")

    # write_file fields
    file_path: str | None = Field(
        default=None,
        description="Relative or absolute path of the file to write. Required when action='write_file'.",
    )
    content: str | None = Field(
        default=None,
        description="Full text content to write into the file. Required when action='write_file'.",
    )


class ToolResult(BaseModel):
    approved: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    message: str = ""


@dataclass
class RunSnapshot:
    state: AgentState = AgentState.IDLE
    user_request: str = ""
    analysis: str = ""
    pending_tool: ToolRequest | None = None
    tool_result: ToolResult | None = None
    error: str = ""
    history: list[AgentState] = field(default_factory=lambda: [AgentState.IDLE])

    def transition(self, state: AgentState) -> None:
        self.state = state
        self.history.append(state)


SYSTEM_PROMPT = """
You are a CLI computer-use agent running on Windows.

For every user request, respond with a JSON object matching this schema:

{
  "action": "run_command" | "write_file",
  "task": "<short description>",
  "reason": "<why>",

  // if action == "run_command":
  "command": ["<exe>", "<arg1>", ...],
  "cwd": null,

  // if action == "write_file":
  "file_path": "<filename or relative path>",
  "content": "<exact file content as a plain string>"
}

Rules:
- Use "write_file" whenever the user asks to create, write, or save a file.
  Put the exact file content in the "content" field — no shell quoting needed.
- Use "run_command" for everything else (listing files, running scripts, deleting files, etc.).
- For run_command on Windows, prefer PowerShell:
    ["powershell", "-NoProfile", "-Command", "<PS command>"]
- Never use shell redirection (>, |) in command arrays.
- Output only the JSON object, no markdown fences.

IMPORTANT — Do what the user explicitly asked, do not substitute a safer alternative:
- If the user says "삭제", "지워", "delete", "remove" → use Remove-Item directly.
  Example: ["powershell", "-NoProfile", "-Command", "Remove-Item -Path workspace\\*.js -Force"]
- If the user specifies a file pattern (*.js, *.txt) use that pattern directly.
- Do NOT replace a delete request with a listing command.
""".strip()


def build_agent(model_name: str | None = None, ollama_base_url: str | None = None) -> Agent[None, ToolRequest]:
    model_name = model_name or os.getenv("AGENT_MODEL", "gemma4:latest")
    ollama_base_url = ollama_base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    provider = OllamaProvider(base_url=ollama_base_url)
    model = OllamaModel(model_name, provider=provider)
    agent: Agent[None, ToolRequest] = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        output_type=ToolRequest,
        retries=2,
    )
    return agent


def _wrap_request(user_request: str, workspace: Path) -> str:
    return (
        f"User task (may be in any language): {user_request}\n"
        f"The current working directory IS already set to the workspace: {workspace}\n"
        "Rules for path handling:\n"
        "- Always set cwd to null.\n"
        "- When referring to files, use just the filename or a path relative to '.', "
        "never use 'workspace' as a path prefix.\n"
        "Respond with a JSON object ONLY. No explanation, no markdown, no extra text."
    )


def plan_with_gemma(user_request: str, workspace: Path, agent: Agent[None, ToolRequest] | None = None) -> RunSnapshot:
    snapshot = RunSnapshot(user_request=user_request)
    agent = agent or build_agent()

    try:
        snapshot.transition(AgentState.THINKING)
        result = agent.run_sync(_wrap_request(user_request, workspace))
        snapshot.pending_tool = result.output
        snapshot.transition(AgentState.WAITING_PERMISSION)
    except Exception as exc:
        snapshot.error = str(exc)
        snapshot.transition(AgentState.ERROR)

    return snapshot


def execute_tool(request: ToolRequest, workspace: Path, approved: bool, timeout_seconds: int = 60) -> ToolResult:
    if not approved:
        return ToolResult(approved=False, message="User denied permission.")

    if request.action == "write_file":
        return _execute_write_file(request, workspace)

    return _execute_run_command(request, workspace, timeout_seconds)


def _execute_write_file(request: ToolRequest, workspace: Path) -> ToolResult:
    if not request.file_path or request.content is None:
        return ToolResult(approved=True, exit_code=1, stderr="file_path and content are required.", message="Invalid request.")

    target = _resolve_cwd(request.file_path, workspace)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(request.content, encoding="utf-8")
        return ToolResult(approved=True, exit_code=0, stdout=f"Written: {target}", message="File written.")
    except Exception as exc:
        return ToolResult(approved=True, exit_code=1, stderr=str(exc), message="File write failed.")


def _execute_run_command(request: ToolRequest, workspace: Path, timeout_seconds: int) -> ToolResult:
    if not request.command:
        return ToolResult(approved=True, exit_code=1, stderr="command is required.", message="Invalid request.")

    if request.cwd:
        resolved = _resolve_cwd(request.cwd, workspace)
        cwd = resolved if resolved.is_dir() else workspace
    else:
        cwd = workspace
    command = normalize_command(request.command)
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return ToolResult(
            approved=True,
            exit_code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            message="Command executed.",
        )
    except FileNotFoundError as exc:
        return ToolResult(approved=True, exit_code=127, stderr=str(exc), message="Command not found.")
    except subprocess.TimeoutExpired as exc:
        return ToolResult(
            approved=True,
            exit_code=124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            message=f"Command timed out after {timeout_seconds} seconds.",
        )


def run_approved_tool(snapshot: RunSnapshot, workspace: Path, approved: bool) -> RunSnapshot:
    if snapshot.pending_tool is None:
        snapshot.error = "No pending tool request."
        snapshot.transition(AgentState.ERROR)
        return snapshot

    if not approved:
        snapshot.tool_result = ToolResult(approved=False, message="User denied permission.")
        snapshot.transition(AgentState.COMPLETED)
        return snapshot

    snapshot.transition(AgentState.RUNNING_TOOL)
    snapshot.tool_result = execute_tool(snapshot.pending_tool, workspace, approved=True)
    snapshot.transition(AgentState.COMPLETED)
    return snapshot


def format_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


_SHELL_OPERATORS = frozenset({">", ">>", "|", "&&", "||", ";", "&"})


def _has_shell_operator(s: str) -> bool:
    try:
        tokens = shlex.split(s)
    except ValueError:
        return True
    return any(tok in _SHELL_OPERATORS for tok in tokens)


def normalize_command(command: list[str]) -> list[str]:
    if not command:
        return command

    # Re-encode powershell -Command "..." to avoid nested quote issues.
    if (
        os.name == "nt"
        and len(command) >= 4
        and command[0].lower() in {"powershell", "powershell.exe"}
        and any(a.lower() == "-command" for a in command)
    ):
        cmd_idx = next(i for i, a in enumerate(command) if a.lower() == "-command")
        inner = " ".join(command[cmd_idx + 1:])
        return powershell_command(inner)

    # Single-string command — check for shell operators BEFORE splitting.
    if len(command) == 1:
        raw = command[0]
        if os.name == "nt" and _has_shell_operator(raw):
            return powershell_command(raw)
        command = shlex.split(raw)
        if not command:
            return command

    # Multi-token command — check for shell operators in the token list.
    if os.name == "nt" and any(tok in _SHELL_OPERATORS for tok in command):
        return powershell_command(" ".join(shlex.quote(tok) for tok in command))

    executable = command[0].lower()
    if os.name == "nt" and executable in {"ls", "dir"}:
        options, paths = [], []
        for part in command[1:]:
            if part in {"-a", "-al", "-la", "-Force"}:
                options.append("-Force")
            elif part == "-l":
                continue
            else:
                paths.append(part)
        ps_parts = ["Get-ChildItem", "-Name", *sorted(set(options)), *paths]
        return powershell_command(" ".join(shlex.quote(p) for p in ps_parts))
    if os.name == "nt" and executable == "pwd":
        return powershell_command("Get-Location")
    if os.name == "nt" and executable == "cat" and len(command) > 1:
        return powershell_command("Get-Content " + " ".join(shlex.quote(p) for p in command[1:]))
    if os.name == "nt" and executable == "echo":
        return powershell_command(" ".join(shlex.quote(tok) for tok in command))
    return command


def powershell_command(command: str) -> list[str]:
    utf8_prefix = (
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
        "$OutputEncoding = [Console]::OutputEncoding; "
    )
    full = utf8_prefix + command
    encoded = base64.b64encode(full.encode("utf-16-le")).decode("ascii")
    return ["powershell", "-NoProfile", "-EncodedCommand", encoded]


def _resolve_cwd(path_str: str, workspace: Path) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = workspace / path
    return path.resolve()
