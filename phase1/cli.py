from pathlib import Path

from agent_core import AgentState, format_command, plan_with_gemma, run_approved_tool
from permission import RiskLevel, PermissionResult, evaluate


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

    ans = input(prompt).strip().lower()
    return ans == "y"


def main() -> None:
    workspace = Path("./workspace")
    workspace.mkdir(exist_ok=True)

    print("=== CLI Agent (Phase 1 + Permission Layer) ===")
    user_input = input("요청: ").strip()
    if not user_input:
        print("입력이 없습니다.")
        return

    print_state(AgentState.THINKING)
    snapshot = plan_with_gemma(user_input, workspace)

    for state in snapshot.history[1:]:
        print_state(state)

    if snapshot.state == AgentState.ERROR:
        print(f"오류: {snapshot.error}")
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

    # --- Permission Layer ---
    perm = evaluate(tool)
    approved = ask_permission(perm)

    if not approved:
        if perm.risk == RiskLevel.BLOCK:
            print("\n[차단] 이 작업은 실행이 허용되지 않습니다.")
        else:
            print("\n실행이 취소되었습니다.")
        return

    print_state(AgentState.RUNNING_TOOL)
    snapshot = run_approved_tool(snapshot, workspace, approved=True)
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
        # Strip CLIXML wrapper but show the plain error text inside it
        stderr = result.stderr
        if "<Objs" in stderr:
            import re
            plain = re.findall(r'<S S="Error">(.*?)</S>', stderr, re.DOTALL)
            stderr = "\n".join(
                s.replace("_x000D__x000A_", "").replace("&#xD;&#xA;", "").strip()
                for s in plain
            ).strip()
        if stderr:
            print(f"오류 출력:\n{stderr}")
    if result.message:
        print(result.message)


if __name__ == "__main__":
    main()
