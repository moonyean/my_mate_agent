from __future__ import annotations

import asyncio
import re
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.deps import get_db, get_markdown, get_persona_manager, get_settings, get_workspace
from core.agent import AgentState, build_agent, execute_tool, plan_with_gemma
from core.memory.summarizer import build_agent_context
from core.permission import RiskLevel, evaluate
from core.persona.engine import build_persona_system_prompt

router = APIRouter()


def _strip_clixml(stderr: str) -> str:
    if "<Objs" not in stderr:
        return stderr
    plain = re.findall(r'<S S="Error">(.*?)</S>', stderr, re.DOTALL)
    return "\n".join(
        s.replace("_x000D__x000A_", "").replace("&#xD;&#xA;", "").strip()
        for s in plain
    ).strip()


@router.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket) -> None:
    await websocket.accept()

    db = get_db()
    markdown = get_markdown()
    persona_mgr = get_persona_manager()
    workspace = get_workspace()
    settings = get_settings()

    persona = persona_mgr.load_persona()
    user_rules = persona_mgr.read_user_rules()
    persona_prompt = build_persona_system_prompt(persona, user_rules)
    agent = build_agent(
        model_name=settings.model_name,
        ollama_base_url=settings.ollama_base_url,
        persona_system_prompt=persona_prompt,
    )

    # session_id: client may send it, otherwise auto-generate
    session_id: str | None = None

    # Queue for all incoming WS messages
    incoming: asyncio.Queue[dict | None] = asyncio.Queue()

    async def _recv_loop() -> None:
        try:
            while True:
                data = await websocket.receive_json()
                await incoming.put(data)
        except WebSocketDisconnect:
            await incoming.put(None)
        except Exception:
            await incoming.put(None)

    recv_task = asyncio.create_task(_recv_loop())

    async def send(payload: dict) -> None:
        try:
            await websocket.send_json(payload)
        except Exception:
            pass

    try:
        while True:
            data = await incoming.get()
            if data is None:
                break

            msg_type = data.get("type")

            # ── chat message ────────────────────────────────────────────────
            if msg_type == "chat":
                if session_id is None:
                    session_id = data.get("session_id") or datetime.now().strftime("%Y%m%d_%H%M%S")
                    await send({"type": "session_id", "session_id": session_id})

                user_text = data.get("message", "").strip()
                if not user_text:
                    continue

                db.save_message(session_id, "user", user_text)
                memory_ctx = build_agent_context(session_id, db, markdown)

                # THINKING
                await send({"type": "state", "state": AgentState.THINKING.value})

                snapshot = await plan_with_gemma(user_text, workspace, agent, memory_ctx)

                if snapshot.state == AgentState.ERROR:
                    await send({"type": "error", "message": snapshot.error})
                    db.save_message(session_id, "assistant", f"[ERROR] {snapshot.error}")
                    continue

                tool = snapshot.pending_tool
                if tool is None:
                    await send({"type": "error", "message": "에이전트가 작업을 결정하지 못했습니다."})
                    continue

                # ── respond (no permission needed) ───────────────────────
                if tool.action == "respond":
                    await send({
                        "type": "respond",
                        "text": tool.text or "",
                        "persona_name": persona.identity.name,
                    })
                    await send({"type": "state", "state": AgentState.COMPLETED.value})
                    db.save_message(session_id, "assistant", f"[respond] {tool.text or ''}")
                    continue

                # ── tool preview + permission ────────────────────────────
                perm = evaluate(tool, auto_approve_safe=settings.auto_approve_safe)

                await send({
                    "type": "tool_preview",
                    "action": tool.action,
                    "task": tool.task,
                    "reason": tool.reason,
                    "command": tool.command,
                    "file_path": tool.file_path,
                    "content_preview": (tool.content or "")[:300] if tool.content else None,
                    "risk": perm.risk.value,
                    "risk_message": perm.message,
                    "auto_approved": perm.approved,
                })

                if perm.risk == RiskLevel.BLOCK:
                    await send({"type": "state", "state": "BLOCKED"})
                    db.save_permission_log(session_id, tool, perm, False)
                    db.save_message(session_id, "assistant", f"[BLOCKED] {tool.task}")
                    continue

                if perm.approved:
                    approved = True
                else:
                    # WAITING_PERMISSION — wait for client response
                    await send({"type": "state", "state": AgentState.WAITING_PERMISSION.value})
                    perm_data = await incoming.get()
                    if perm_data is None:
                        break
                    approved = bool(perm_data.get("approved", False))

                db.save_permission_log(session_id, tool, perm, approved)

                if not approved:
                    await send({"type": "state", "state": "CANCELLED"})
                    db.save_message(session_id, "assistant", f"[CANCELLED] {tool.task}")
                    continue

                # RUNNING_TOOL
                await send({"type": "state", "state": AgentState.RUNNING_TOOL.value})
                result = await asyncio.to_thread(execute_tool, tool, workspace, True, settings.timeout_seconds)
                db.save_tool_log(session_id, tool, result)

                stderr_clean = _strip_clixml(result.stderr)
                await send({
                    "type": "result",
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": stderr_clean,
                    "message": result.message,
                })
                await send({"type": "state", "state": AgentState.COMPLETED.value})
                db.save_message(session_id, "assistant",
                                f"[{tool.action}] {tool.task} → exit {result.exit_code}")

    finally:
        recv_task.cancel()
