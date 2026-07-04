from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from core.agent import ToolRequest


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


_BLOCK = re.compile(
    r"\bdiskpart\b|\bformat\s+[a-z]:|\breg\s+(add|delete|query|export|import)\b"
    r"|\bregedit\b|set-itemproperty\s+hk|\bget-credential\b|\bnet\s+user\b"
    r"|\bpasswd\b|\bsc\s+config\b|\bbcdedit\b|\bchmod\s+777\b|\bchown\b|\bshadowcopy\b",
    re.IGNORECASE,
)
_HIGH = re.compile(
    r"\bremove-item\b|\brm\s+-[rRfF]|\bdel\s+/|\bstop-process\b|\btaskkill\b"
    r"|\bkill\s+-|\b\.exe\b|\bstart-process\b|\bwscript\b|\bcscript\b"
    r"|\binvoke-expression\b|\biex\b",
    re.IGNORECASE,
)
_CONFIRM = re.compile(
    r"\bset-content\b|\bout-file\b|\badd-content\b|\bnew-item\b|\bcopy-item\b"
    r"|\bmove-item\b|\brename-item\b|\binvoke-webrequest\b|\biwr\b|\bwget\b"
    r"|\bcurl\b|\bstart-bitstransfer\b|\bmkdir\b|\bmd\s",
    re.IGNORECASE,
)
_SAFE = re.compile(
    r"\bget-content\b|\bget-childitem\b|\bget-location\b|\bget-item\b"
    r"|\bselect-string\b|\bwhere-object\b|\bcat\b|\btype\b|\bls\b|\bdir\b"
    r"|\bpwd\b|\bfind\b|\bgrep\b|\becho\b|\bwrite-host\b|\bwrite-output\b",
    re.IGNORECASE,
)


def classify(request: ToolRequest) -> RiskLevel:
    if request.action == "respond":
        return RiskLevel.SAFE
    if request.action == "write_file":
        return RiskLevel.CONFIRM
    cmd = " ".join(request.command or []).lower()
    if _BLOCK.search(cmd):
        return RiskLevel.BLOCK
    if _HIGH.search(cmd):
        return RiskLevel.HIGH_RISK
    if _CONFIRM.search(cmd):
        return RiskLevel.CONFIRM
    if _SAFE.search(cmd):
        return RiskLevel.SAFE
    return RiskLevel.CONFIRM


def evaluate(request: ToolRequest, auto_approve_safe: bool = True) -> PermissionResult:
    risk = classify(request)
    if risk == RiskLevel.BLOCK:
        return PermissionResult(risk=risk, approved=False,
                                message="시스템 보안상 차단된 작업입니다.")
    if risk == RiskLevel.SAFE and auto_approve_safe:
        return PermissionResult(risk=risk, approved=True,
                                message="안전한 작업으로 자동 승인되었습니다.")
    if risk == RiskLevel.HIGH_RISK:
        return PermissionResult(risk=risk, approved=False,
                                message="위험한 작업입니다. 파일 삭제 또는 프로세스 종료가 포함될 수 있습니다.")
    return PermissionResult(risk=risk, approved=False,
                            message="파일 생성/수정 또는 네트워크 작업이 포함되어 있습니다.")
