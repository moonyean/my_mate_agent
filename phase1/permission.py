from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from agent_core import ToolRequest


class RiskLevel(str, Enum):
    SAFE = "SAFE"
    CONFIRM = "CONFIRM"
    HIGH_RISK = "HIGH_RISK"
    BLOCK = "BLOCK"


@dataclass
class PermissionResult:
    risk: RiskLevel
    approved: bool
    message: str


# --- Pattern tables (checked in order; first match wins) ---

_BLOCK_PATTERNS = re.compile(
    r"""
    \bdiskpart\b |
    \bformat\s+[a-z]: |
    \breg\s+(add|delete|query|export|import)\b |
    \bregedit\b |
    set-itemproperty\s+hk |
    \bget-credential\b |
    \bnet\s+user\b |
    \bpasswd\b |
    \bsc\s+config\b |
    \bbcdedit\b |
    \bchmod\s+777\b |
    \bchown\b |
    \bshadowcopy\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_HIGH_RISK_PATTERNS = re.compile(
    r"""
    \bremove-item\b |
    \brm\s+-[rRfF] |
    \bdel\s+/ |
    \bstop-process\b |
    \btaskkill\b |
    \bkill\s+-[0-9] |
    \bkill\s+- |
    \.exe\b |
    \bstart-process\b |
    \bwscript\b |
    \bcscript\b |
    \binvoke-expression\b |
    \biex\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_CONFIRM_PATTERNS = re.compile(
    r"""
    \bset-content\b |
    \bout-file\b |
    \badd-content\b |
    \bnew-item\b |
    \bcopy-item\b |
    \bmove-item\b |
    \brename-item\b |
    \binvoke-webrequest\b |
    \biwr\b |
    \bwget\b |
    \bcurl\b |
    \bstart-bitstransfer\b |
    \bmkdir\b |
    \bmd\s
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SAFE_PATTERNS = re.compile(
    r"""
    \bget-content\b |
    \bget-childitem\b |
    \bget-location\b |
    \bget-item\b |
    \bget-itemproperty\b |
    \bselect-string\b |
    \bwhere-object\b |
    \bcat\b |
    \btype\b |
    \bls\b |
    \bdir\b |
    \bpwd\b |
    \bfind\b |
    \bgrep\b |
    \becho\b |
    \bwrite-host\b |
    \bwrite-output\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _command_string(request: ToolRequest) -> str:
    if request.action == "run_command" and request.command:
        return " ".join(request.command)
    return ""


def classify(request: ToolRequest) -> RiskLevel:
    if request.action == "write_file":
        return RiskLevel.CONFIRM

    cmd = _command_string(request).lower()

    if _BLOCK_PATTERNS.search(cmd):
        return RiskLevel.BLOCK
    if _HIGH_RISK_PATTERNS.search(cmd):
        return RiskLevel.HIGH_RISK
    if _CONFIRM_PATTERNS.search(cmd):
        return RiskLevel.CONFIRM
    if _SAFE_PATTERNS.search(cmd):
        return RiskLevel.SAFE

    # Unknown command → conservative default
    return RiskLevel.CONFIRM


def evaluate(request: ToolRequest, auto_approve_safe: bool = True) -> PermissionResult:
    risk = classify(request)

    if risk == RiskLevel.BLOCK:
        return PermissionResult(
            risk=risk,
            approved=False,
            message="이 작업은 시스템 보안상 차단되었습니다. 실행할 수 없습니다.",
        )

    if risk == RiskLevel.SAFE and auto_approve_safe:
        return PermissionResult(
            risk=risk,
            approved=True,
            message="안전한 작업으로 자동 승인되었습니다.",
        )

    if risk == RiskLevel.HIGH_RISK:
        return PermissionResult(
            risk=risk,
            approved=False,
            message="위험한 작업입니다. 파일 삭제, 프로세스 종료, 실행 파일 실행 등이 포함될 수 있습니다.",
        )

    # CONFIRM (또는 auto_approve_safe=False인 SAFE)
    return PermissionResult(
        risk=risk,
        approved=False,
        message="파일 생성/수정 또는 네트워크 작업이 포함되어 있습니다. 확인이 필요합니다.",
    )
