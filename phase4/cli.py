from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

from agent_core import AgentState, build_agent, format_command, plan_with_gemma, run_approved_tool
from permission import RiskLevel, PermissionResult, evaluate
from persona import PersonaManager, build_persona_system_prompt, validate_persona
from persona.manager import _parse_persona_md, _serialize_persona
from persona.schema import (
    Persona, PersonaIdentity, PersonaTone,
    PersonaRules, PersonaConstraints, PersonaMemoryBinding,
)
from persona.validator import ValidationError

_DATA_DIR = Path(__file__).parent / "data"
_WORKSPACE = Path(__file__).parent / "workspace"

_RISK_BADGE = {
    RiskLevel.SAFE:      "🟢 SAFE",
    RiskLevel.CONFIRM:   "🟡 CONFIRM",
    RiskLevel.HIGH_RISK: "🔴 HIGH RISK",
    RiskLevel.BLOCK:     "⛔ BLOCK",
}


def print_state(state: AgentState) -> None:
    icons = {
        AgentState.IDLE:               "💤",
        AgentState.THINKING:           "🤔",
        AgentState.RUNNING_TOOL:       "⚙️",
        AgentState.WAITING_PERMISSION: "🔐",
        AgentState.COMPLETED:          "✅",
        AgentState.ERROR:              "❌",
    }
    print(f"[{icons.get(state, '?')} {state.value}]")


def ask_permission(perm: PermissionResult) -> bool:
    badge = _RISK_BADGE[perm.risk]
    print(f"\n위험도: {badge}")
    print(f"안내: {perm.message}")

    if perm.risk == RiskLevel.BLOCK:
        return False
    if perm.risk == RiskLevel.SAFE and perm.approved:
        print("→ 자동 승인")
        return True

    prompt = "실행하시겠습니까? (y/n): "
    if perm.risk == RiskLevel.HIGH_RISK:
        prompt = "⚠️  정말 실행하시겠습니까? (y/n): "
    return input(prompt).strip().lower() == "y"


def _print_agent_response(text: str, name: str = "에이전트") -> None:
    """respond 액션 출력. *행동* 부분은 이탤릭처럼 구분 표시."""
    import re
    # *행동* 부분을 괄호로 강조 (터미널 ANSI 없이도 구분됨)
    formatted = re.sub(r"\*([^*]+)\*", r"(\1)", text)
    print(f"\n{name}: {formatted}")


def _strip_clixml(stderr: str) -> str:
    if "<Objs" not in stderr:
        return stderr
    plain = re.findall(r'<S S="Error">(.*?)</S>', stderr, re.DOTALL)
    return "\n".join(
        s.replace("_x000D__x000A_", "").replace("&#xD;&#xA;", "").strip()
        for s in plain
    ).strip()


# ── 페르소나 가이드 생성 ───────────────────────────────────────────────────────

def _collect_list(prompt: str) -> list[str]:
    print(f"{prompt} (빈 줄 입력 시 완료)")
    items = []
    while True:
        val = input("  > ").strip()
        if not val:
            break
        items.append(val)
    return items


def create_persona_interactive(manager: PersonaManager) -> bool:
    print("\n=== 페르소나 생성 ===")
    name = input("이름: ").strip()
    role = input("역할 (예: 마법사, 우주 파일럿, 도서관 사서): ").strip()
    speech_style = input("말투 (예: 친근하고 격식없는 말투): ").strip()
    personality = input("성격 (예: 호기심 많고 열정적): ").strip()
    rules = _collect_list("행동 규칙")
    constraints = _collect_list("금지 사항")

    persona = Persona(
        identity=PersonaIdentity(name=name, role=role),
        tone=PersonaTone(speech_style=speech_style, personality=personality),
        rules=PersonaRules(behavior=rules),
        constraints=PersonaConstraints(forbidden=constraints),
        memory_binding=PersonaMemoryBinding(),
    )

    ok, msg = validate_persona(persona)
    if not ok:
        print(f"\n[차단] {msg}")
        return False

    try:
        manager.save_persona(persona)
        print(f"\n✅ 페르소나 '{name}' 저장 완료.")
        return True
    except ValidationError as e:
        print(f"\n[차단] {e}")
        return False


def show_persona(manager: PersonaManager) -> None:
    print("\n=== 현재 페르소나 ===")
    print(manager.persona_path.read_text(encoding="utf-8"))
    print("=" * 20)


def show_user_rules(manager: PersonaManager) -> None:
    print("\n=== User Rules ===")
    print(manager.user_rules_path.read_text(encoding="utf-8"))
    print("=" * 20)


# ── 메인 루프 ─────────────────────────────────────────────────────────────────

def run_turn(user_input: str, agent, persona_name: str = "에이전트") -> None:
    print_state(AgentState.THINKING)
    snapshot = plan_with_gemma(user_input, _WORKSPACE, agent=agent)

    for state in snapshot.history[1:]:
        print_state(state)

    if snapshot.state == AgentState.ERROR:
        print(f"오류: {snapshot.error}")
        return

    if snapshot.pending_tool is None:
        print("AI가 실행할 작업을 결정하지 못했습니다.")
        return

    tool = snapshot.pending_tool

    # ── respond: permission 없이 바로 출력 ───────────────────────────────────
    if tool.action == "respond":
        _print_agent_response(tool.text or "", name=persona_name)
        return

    print(f"\n작업: {tool.task}")
    if tool.action == "write_file":
        print(f"액션: 파일 쓰기  |  경로: {tool.file_path}")
        print(f"내용 미리보기:\n{(tool.content or '')[:200]}")
    else:
        print(f"액션: 명령 실행  |  명령: {format_command(tool.command or [])}")
    print(f"이유: {tool.reason}")

    perm = evaluate(tool)
    approved = ask_permission(perm)

    if not approved:
        print("\n[차단]" if perm.risk == RiskLevel.BLOCK else "\n실행이 취소되었습니다.")
        return

    print_state(AgentState.RUNNING_TOOL)
    snapshot = run_approved_tool(snapshot, _WORKSPACE, approved=True)
    print_state(snapshot.state)

    result = snapshot.tool_result
    if result is None:
        return

    print(f"\n종료 코드: {result.exit_code}")
    if result.stdout:
        print(f"출력:\n{result.stdout}")
    elif result.exit_code == 0:
        print("(출력 없음 — 작업이 조용히 완료됨)")
    if result.stderr:
        stderr = _strip_clixml(result.stderr)
        if stderr:
            print(f"오류 출력:\n{stderr}")


def main() -> None:
    _WORKSPACE.mkdir(exist_ok=True)

    manager = PersonaManager(_DATA_DIR)

    persona = manager.load_persona()
    user_rules = manager.read_user_rules()
    persona_prompt = build_persona_system_prompt(persona, user_rules)
    agent = build_agent(persona_system_prompt=persona_prompt)

    print("=== CLI Agent (Phase 4 - Persona Engine) ===")
    print(f"페르소나: {persona.identity.name} ({persona.identity.role})")
    print("명령: p(페르소나 보기) | pe(페르소나 생성) | ur(사용자 규칙) | q(종료)")
    print("-" * 48)

    while True:
        try:
            user_input = input("\n요청: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("q", "quit", "exit", "종료"):
            break

        if user_input.lower() == "p":
            show_persona(manager)
            continue

        if user_input.lower() == "pe":
            if create_persona_interactive(manager):
                persona = manager.load_persona()
                user_rules = manager.read_user_rules()
                persona_prompt = build_persona_system_prompt(persona, user_rules)
                agent = build_agent(persona_system_prompt=persona_prompt)
                print(f"에이전트가 '{persona.identity.name}' 페르소나로 재설정되었습니다.")
            continue

        if user_input.lower() == "ur":
            show_user_rules(manager)
            continue

        run_turn(user_input, agent, persona_name=persona.identity.name)


if __name__ == "__main__":
    main()
