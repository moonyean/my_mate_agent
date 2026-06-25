import unittest
from pathlib import Path
import tempfile

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from agent_core import (
    AgentState,
    ToolRequest,
    RunSnapshot,
    plan_with_gemma,
    run_approved_tool,
    execute_tool,
)


def make_test_agent() -> Agent[None, ToolRequest]:
    return Agent(TestModel(), output_type=ToolRequest)


class AgentCoreTests(unittest.TestCase):
    def test_state_machine_reaches_waiting_permission(self) -> None:
        workspace = Path.cwd()
        snapshot = plan_with_gemma("list files", workspace, agent=make_test_agent())

        self.assertEqual(snapshot.state, AgentState.WAITING_PERMISSION)
        self.assertEqual(
            snapshot.history,
            [AgentState.IDLE, AgentState.THINKING, AgentState.WAITING_PERMISSION],
        )
        self.assertIsNotNone(snapshot.pending_tool)

    def test_denied_permission_completes_without_running(self) -> None:
        workspace = Path.cwd()
        snapshot = plan_with_gemma("list files", workspace, agent=make_test_agent())
        snapshot = run_approved_tool(snapshot, workspace, approved=False)

        self.assertEqual(snapshot.state, AgentState.COMPLETED)
        self.assertIsNotNone(snapshot.tool_result)
        self.assertFalse(snapshot.tool_result.approved)
        self.assertIsNone(snapshot.tool_result.exit_code)

    def test_write_file_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            req = ToolRequest(
                action="write_file",
                task="Write hello.py",
                reason="test",
                file_path="hello.py",
                content='print("Hello, World!")\n',
            )
            result = execute_tool(req, workspace, approved=True)

            self.assertEqual(result.exit_code, 0)
            written = (workspace / "hello.py").read_text(encoding="utf-8")
            self.assertEqual(written, 'print("Hello, World!")\n')

    def test_write_file_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            req = ToolRequest(
                action="write_file",
                task="Write hello.py",
                reason="test",
                file_path="hello.py",
                content='print("Hello")\n',
            )
            result = execute_tool(req, workspace, approved=False)

            self.assertFalse(result.approved)
            self.assertFalse((workspace / "hello.py").exists())


if __name__ == "__main__":
    unittest.main()
