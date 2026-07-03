from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

from agent_core import AgentState, build_agent, format_command, plan_with_gemma, run_approved_tool
from memory import MemoryDB, MarkdownMemory, build_agent_context, summarize_to_long_memory
from permission import RiskLevel, PermissionResult, evaluate


_RISK_BADGE = {
    RiskLevel.SAFE:      "🟢 SAFE",
    RiskLevel.CONFIRM:   "🟡 CONFIRM",
    RiskLevel.HIGH_RISK: "🔴 HIGH RISK",
    RiskLevel.BLOCK:     "⛔ BLOCK",
}

_DATA_DIR = Path(__file__).parent / "data"
_DB_PATH = _DATA_DIR / "memory.db"
_WORKSPACE = Path(__file__).parent / "workspace"


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

    ans = input(prompt).strip().lower()
    return ans == "y"


def _strip_clixml(stderr: str) -> str:
    if "<Objs" not in stderr:
        return stderr
    plain = re.findall(r'<S S="Error">(.*?)</S>', stderr, re.DOTALL)
    return "\n".join(
        s.replace("_x000D__x000A_", "").replace("&#xD;&#xA;", "").strip()
        for s in plain
    ).strip()


def run_turn(user_input: str, session_id: str, db: MemoryDB, markdown: MarkdownMemory, agent) -> None:
    db.save_message(session_id, "user", user_input)

    context = build_agent_context(session_id, db, markdown)

    print_state(AgentState.THINKING)
    snapshot = plan_with_gemma(user_input, _WORKSPACE, agent=agent, memory_context=context)

    for state in snapshot.history[1:]:
        print_state(state)

    if snapshot.state == AgentState.ERROR:
        print(f"오류: {snapshot.error}")
        db.save_message(session_id, "assistant", f"[ERROR] {snapshot.error}")
        return

    if snapshot.pending_tool is None:
        print("AI가 실행할 작업을 결정하지 못했습니다.")
        return

    tool = snapshot.pending_tool

    print(f"\n작업: {tool.task}")
    if tool.action == "write_file":
        print(f"액션: 파일 쓰기")
        print(f"경로: {tool.file_path}")
        preview = (tool.content or "")[:200]
        print(f"내용 미리보기:\n{preview}")
    else:
        print(f"액션: 명령 실행")
        print(f"명령: {format_command(tool.command or [])}")
        if tool.cwd:
            print(f"경로: {tool.cwd}")
    print(f"이유: {tool.reason}")

    perm = evaluate(tool)
    approved = ask_permission(perm)

    db.save_permission_log(session_id, tool, perm, approved)

    if not approved:
        if perm.risk == RiskLevel.BLOCK:
            print("\n[차단] 이 작업은 실행이 허용되지 않습니다.")
        else:
            print("\n실행이 취소되었습니다.")
        db.save_message(session_id, "assistant", f"[DENIED] {tool.task}")
        return

    print_state(AgentState.RUNNING_TOOL)
    snapshot = run_approved_tool(snapshot, _WORKSPACE, approved=True)
    print_state(snapshot.state)

    result = snapshot.tool_result
    if result is None:
        return

    db.save_tool_log(session_id, tool, result)

    assistant_summary = f"[{tool.action}] {tool.task} → exit {result.exit_code}"
    db.save_message(session_id, "assistant", assistant_summary)

    print(f"\n종료 코드: {result.exit_code}")
    if result.stdout:
        print(f"출력:\n{result.stdout}")
    elif result.exit_code == 0:
        print("(출력 없음 — 작업이 조용히 완료됨)")

    if result.stderr:
        stderr = _strip_clixml(result.stderr)
        if stderr:
            print(f"오류 출력:\n{stderr}")

    if result.message:
        print(result.message)


def show_memory_status(db: MemoryDB, markdown: MarkdownMemory) -> None:
    sessions = db.get_all_sessions()
    print(f"\n=== 메모리 상태 ===")
    print(f"저장된 세션 수: {len(sessions)}")
    if sessions:
        print(f"최근 세션: {sessions[-1]}")
    print(f"\n[장기 기억 미리보기]")
    long_mem = markdown.read_long_memory()
    print(long_mem[:500] + ("..." if len(long_mem) > 500 else ""))
    print("=" * 20)


def main() -> None:
    _WORKSPACE.mkdir(exist_ok=True)
    _DATA_DIR.mkdir(exist_ok=True)

    db = MemoryDB(_DB_PATH)
    markdown = MarkdownMemory(_DATA_DIR)
    agent = build_agent()

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=== CLI Agent (Phase 3 - Memory Layer) ===")
    print(f"세션: {session_id}")
    print("종료: 'q' | 메모리 상태: 'm' | 세션 요약 저장: 's'")
    print("-" * 45)

    try:
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

            if user_input.lower() == "m":
                show_memory_status(db, markdown)
                continue

            if user_input.lower() == "s":
                print("세션 요약 중...")
                result = summarize_to_long_memory(session_id, db, markdown)
                if result.startswith("(요약 실패"):
                    print(result)
                else:
                    print("장기 기억에 저장 완료.")
                continue

            run_turn(user_input, session_id, db, markdown, agent)

    finally:
        # Auto-summarize if session had activity
        messages = db.get_recent_messages(session_id, limit=100)
        if len(messages) >= 2:
            ans = input("\n이 세션을 장기 기억에 요약 저장할까요? (y/n): ").strip().lower()
            if ans == "y":
                print("요약 중...")
                result = summarize_to_long_memory(session_id, db, markdown)
                if result.startswith("(요약 실패"):
                    print(result)
                else:
                    print("저장 완료.")
        db.close()


if __name__ == "__main__":
    main()
