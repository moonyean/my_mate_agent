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
    action: Literal["run_command", "write_file", "respond"] = Field(
        description=(
            "'run_command' to execute a shell command, "
            "'write_file' to create or overwrite a text file, "
            "'respond' for conversational or roleplay replies."
        )
    )
    task: str = Field(description="Short human-readable description of the action.")
    reason: str = Field(description="Why this action answers the user request.")

    text: str | None = Field(
        default=None,
        description="Character reply text. Required when action='respond'. Wrap actions in *asterisks*.",
    )
    command: list[str] | None = Field(
        default=None,
        description="Command and arguments. Required when action='run_command'.",
    )
    cwd: str | None = Field(default=None, description="Working directory (always null).")
    file_path: str | None = Field(
        default=None,
        description="File path. Required when action='write_file'.",
    )
    content: str | None = Field(
        default=None,
        description="Full file content. Required when action='write_file'.",
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
    pending_tool: ToolRequest | None = None
    tool_result: ToolResult | None = None
    error: str = ""
    history: list[AgentState] = field(default_factory=lambda: [AgentState.IDLE])

    def transition(self, state: AgentState) -> None:
        self.state = state
        self.history.append(state)


_FALLBACK_SYSTEM_PROMPT = """
You are a CLI computer-use agent running on Windows.
For every user request, respond with a JSON object only.

{
  "action": "run_command" | "write_file" | "respond",
  "task": "<short description>",
  "reason": "<why>",
  "text": "<reply with *actions* when action=respond>",
  "command": ["<exe>", "<arg1>", ...],
  "cwd": null,
  "file_path": "<filename>",
  "content": "<file content>"
}

- Use "respond" for conversational input. Wrap character actions in *asterisks*.
- Use "write_file" to create/overwrite files.
- Use "run_command" for system tasks. Prefer PowerShell on Windows.
- Never use shell redirection in command arrays.
- Output ONLY the JSON object.
""".strip()


def build_agent(
    model_name: str | None = None,
    ollama_base_url: str | None = None,
    persona_system_prompt: str | None = None,
) -> Agent[None, ToolRequest]:
    model_name = model_name or os.getenv("AGENT_MODEL", "gemma4:latest")
    ollama_base_url = ollama_base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    provider = OllamaProvider(base_url=ollama_base_url)
    model = OllamaModel(model_name, provider=provider)
    system = persona_system_prompt or _FALLBACK_SYSTEM_PROMPT
    return Agent(model=model, system_prompt=system, output_type=ToolRequest, retries=3)


def _wrap_request(user_request: str, workspace: Path, memory_context: str = "") -> str:
    parts: list[str] = []
    if memory_context.strip():
        parts.append(memory_context)
        parts.append("")
    parts.extend([
        f"User task (may be in any language): {user_request}",
        f"Working directory: {workspace}",
        "- Always set cwd to null.",
        "- Use filenames relative to '.', never prefix with 'workspace'.",
        "Respond with JSON ONLY.",
    ])
    return "\n".join(parts)


async def plan_with_gemma(
    user_request: str,
    workspace: Path,
    agent: Agent[None, ToolRequest],
    memory_context: str = "",
) -> RunSnapshot:
    snapshot = RunSnapshot(user_request=user_request)
    try:
        snapshot.transition(AgentState.THINKING)
        result = await agent.run(_wrap_request(user_request, workspace, memory_context))
        snapshot.pending_tool = result.output
        snapshot.transition(AgentState.WAITING_PERMISSION)
    except Exception as exc:
        snapshot.error = str(exc)
        snapshot.transition(AgentState.ERROR)
    return snapshot


def execute_tool(request: ToolRequest, workspace: Path, approved: bool, timeout: int = 60) -> ToolResult:
    if not approved:
        return ToolResult(approved=False, message="User denied permission.")
    if request.action == "respond":
        return ToolResult(approved=True, exit_code=0, message="respond")
    if request.action == "write_file":
        return _execute_write_file(request, workspace)
    return _execute_run_command(request, workspace, timeout)


def _execute_write_file(request: ToolRequest, workspace: Path) -> ToolResult:
    if not request.file_path or request.content is None:
        return ToolResult(approved=True, exit_code=1, stderr="file_path and content required.")
    target = _resolve(request.file_path, workspace)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(request.content, encoding="utf-8")
        return ToolResult(approved=True, exit_code=0, stdout=f"Written: {target}", message="File written.")
    except Exception as exc:
        return ToolResult(approved=True, exit_code=1, stderr=str(exc), message="Write failed.")


def _execute_run_command(request: ToolRequest, workspace: Path, timeout: int) -> ToolResult:
    if not request.command:
        return ToolResult(approved=True, exit_code=1, stderr="command required.")
    if request.cwd:
        resolved = _resolve(request.cwd, workspace)
        cwd = resolved if resolved.is_dir() else workspace
    else:
        cwd = workspace
    command = normalize_command(request.command)
    try:
        proc = subprocess.run(
            command, cwd=str(cwd), text=True, encoding="utf-8",
            errors="replace", capture_output=True, timeout=timeout, check=False,
        )
        return ToolResult(
            approved=True, exit_code=proc.returncode,
            stdout=proc.stdout or "", stderr=proc.stderr or "", message="Command executed.",
        )
    except FileNotFoundError as exc:
        return ToolResult(approved=True, exit_code=127, stderr=str(exc), message="Command not found.")
    except subprocess.TimeoutExpired as exc:
        return ToolResult(approved=True, exit_code=124, stdout=exc.stdout or "",
                          stderr=exc.stderr or "", message=f"Timed out after {timeout}s.")


_SHELL_OPS = frozenset({">", ">>", "|", "&&", "||", ";", "&"})


def _has_shell_op(s: str) -> bool:
    try:
        return any(t in _SHELL_OPS for t in shlex.split(s))
    except ValueError:
        return True


def normalize_command(command: list[str]) -> list[str]:
    if not command:
        return command
    if (os.name == "nt" and len(command) >= 4
            and command[0].lower() in {"powershell", "powershell.exe"}
            and any(a.lower() == "-command" for a in command)):
        idx = next(i for i, a in enumerate(command) if a.lower() == "-command")
        return powershell_cmd(" ".join(command[idx + 1:]))
    if len(command) == 1:
        raw = command[0]
        if os.name == "nt" and _has_shell_op(raw):
            return powershell_cmd(raw)
        command = shlex.split(raw) or command
    if os.name == "nt" and any(t in _SHELL_OPS for t in command):
        return powershell_cmd(" ".join(shlex.quote(t) for t in command))
    exe = command[0].lower()
    if os.name == "nt":
        if exe in {"ls", "dir"}:
            opts = ["-Force"] if any(p in {"-a","-al","-la","-Force"} for p in command[1:]) else []
            paths = [p for p in command[1:] if not p.startswith("-")]
            return powershell_cmd(" ".join(shlex.quote(p) for p in ["Get-ChildItem", "-Name", *opts, *paths]))
        if exe == "pwd":
            return powershell_cmd("Get-Location")
        if exe == "cat" and len(command) > 1:
            return powershell_cmd("Get-Content " + " ".join(shlex.quote(p) for p in command[1:]))
        if exe == "echo":
            return powershell_cmd(" ".join(shlex.quote(t) for t in command))
    return command


def powershell_cmd(command: str) -> list[str]:
    prefix = "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); $OutputEncoding = [Console]::OutputEncoding; "
    encoded = base64.b64encode((prefix + command).encode("utf-16-le")).decode("ascii")
    return ["powershell", "-NoProfile", "-EncodedCommand", encoded]


def _resolve(path_str: str, workspace: Path) -> Path:
    p = Path(path_str)
    return (workspace / p).resolve() if not p.is_absolute() else p.resolve()
