import tempfile
import unittest
from pathlib import Path

from agent_core import AgentState, ToolRequest, ToolResult, plan_with_gemma
from memory.db import MemoryDB
from memory.markdown import MarkdownMemory
from memory.summarizer import build_agent_context
from permission import RiskLevel, evaluate
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel


def _tmp_db(tmp: str) -> MemoryDB:
    return MemoryDB(Path(tmp) / "test.db")


def _tmp_md(tmp: str) -> MarkdownMemory:
    return MarkdownMemory(Path(tmp) / "data")


# ── MemoryDB ──────────────────────────────────────────────────────────────────

class DBMessageTests(unittest.TestCase):

    def test_save_and_retrieve_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _tmp_db(tmp)
            db.save_message("s1", "user", "hello")
            db.save_message("s1", "assistant", "world")
            msgs = db.get_recent_messages("s1")
            self.assertEqual(len(msgs), 2)
            self.assertEqual(msgs[0]["role"], "user")
            self.assertEqual(msgs[1]["role"], "assistant")
            db.close()

    def test_recent_limit_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _tmp_db(tmp)
            for i in range(20):
                db.save_message("s1", "user", f"msg {i}")
            msgs = db.get_recent_messages("s1", limit=5)
            self.assertEqual(len(msgs), 5)
            # should be the last 5
            self.assertEqual(msgs[-1]["content"], "msg 19")
            db.close()

    def test_session_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _tmp_db(tmp)
            db.save_message("s1", "user", "session one")
            db.save_message("s2", "user", "session two")
            self.assertEqual(len(db.get_recent_messages("s1")), 1)
            self.assertEqual(len(db.get_recent_messages("s2")), 1)
            db.close()

    def test_get_all_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _tmp_db(tmp)
            db.save_message("s1", "user", "a")
            db.save_message("s2", "user", "b")
            db.save_message("s1", "user", "c")
            sessions = db.get_all_sessions()
            self.assertIn("s1", sessions)
            self.assertIn("s2", sessions)
            db.close()

    def test_save_tool_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _tmp_db(tmp)
            req = ToolRequest(action="run_command", task="list", reason="test",
                              command=["powershell", "-Command", "Get-ChildItem"])
            result = ToolResult(approved=True, exit_code=0, stdout="file.txt")
            db.save_tool_log("s1", req, result)
            logs = db.get_recent_tool_logs(limit=5)
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0]["action"], "run_command")
            self.assertEqual(logs[0]["exit_code"], 0)
            self.assertTrue(logs[0]["approved"])
            db.close()

    def test_save_permission_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _tmp_db(tmp)
            req = ToolRequest(action="write_file", task="write", reason="test",
                              file_path="a.txt", content="hello")
            perm = evaluate(req)
            db.save_permission_log("s1", req, perm, approved=True)
            # no exception = pass
            db.close()

    def test_empty_session_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _tmp_db(tmp)
            self.assertEqual(db.get_recent_messages("no-such-session"), [])
            db.close()


# ── MarkdownMemory ────────────────────────────────────────────────────────────

class MarkdownMemoryTests(unittest.TestCase):

    def test_defaults_created_on_init(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = _tmp_md(tmp)
            self.assertTrue(md.persona_path.exists())
            self.assertTrue(md.long_memory_path.exists())
            self.assertTrue(md.project_memory_path.exists())

    def test_read_persona_contains_keyword(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = _tmp_md(tmp)
            self.assertIn("Persona", md.read_persona())

    def test_update_long_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = _tmp_md(tmp)
            md.update_long_memory("# Long-term Memory\n- Did a thing.")
            self.assertIn("Did a thing", md.read_long_memory())

    def test_update_project_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = _tmp_md(tmp)
            md.update_project_memory("# Project Memory\n- Phase 3 test.")
            self.assertIn("Phase 3 test", md.read_project_memory())

    def test_build_context_block_contains_all_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = _tmp_md(tmp)
            block = md.build_context_block()
            self.assertIn("Persona", block)
            self.assertIn("Long-term Memory", block)
            self.assertIn("Project Memory", block)

    def test_default_not_overwritten_on_second_init(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = _tmp_md(tmp)
            md.update_long_memory("# Long-term Memory\n- Custom entry.")
            # second init should NOT reset the file
            md2 = MarkdownMemory(Path(tmp) / "data")
            self.assertIn("Custom entry", md2.read_long_memory())


# ── build_agent_context ───────────────────────────────────────────────────────

class BuildContextTests(unittest.TestCase):

    def test_empty_session_no_conversation_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _tmp_db(tmp)
            md = _tmp_md(tmp)
            ctx = build_agent_context("new-session", db, md)
            self.assertNotIn("RECENT CONVERSATION", ctx)
            db.close()

    def test_with_messages_includes_conversation_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _tmp_db(tmp)
            md = _tmp_md(tmp)
            db.save_message("s1", "user", "hello")
            db.save_message("s1", "assistant", "world")
            ctx = build_agent_context("s1", db, md)
            self.assertIn("RECENT CONVERSATION", ctx)
            self.assertIn("hello", ctx)
            db.close()

    def test_default_markdown_excluded_from_context(self):
        """Default placeholder markdown should NOT bloat the context."""
        with tempfile.TemporaryDirectory() as tmp:
            db = _tmp_db(tmp)
            md = _tmp_md(tmp)
            ctx = build_agent_context("s1", db, md)
            self.assertNotIn("MEMORY CONTEXT", ctx)
            db.close()

    def test_real_long_memory_included_in_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _tmp_db(tmp)
            md = _tmp_md(tmp)
            md.update_long_memory("# Long-term Memory\n- Session X: created hello.txt.")
            ctx = build_agent_context("s1", db, md)
            self.assertIn("MEMORY CONTEXT", ctx)
            self.assertIn("Session X", ctx)
            db.close()

    def test_recent_limit_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _tmp_db(tmp)
            md = _tmp_md(tmp)
            for i in range(10):
                db.save_message("s1", "user", f"msg {i}")
            ctx = build_agent_context("s1", db, md, recent_limit=3)
            # only last 3 should appear
            self.assertIn("msg 9", ctx)
            self.assertNotIn("msg 0", ctx)
            db.close()


# ── plan_with_gemma + memory_context integration ──────────────────────────────

class PlanWithMemoryTests(unittest.TestCase):

    def _agent(self):
        return Agent(TestModel(), output_type=ToolRequest)

    def test_plan_with_empty_context(self):
        snap = plan_with_gemma("list files", Path("."), agent=self._agent(), memory_context="")
        self.assertEqual(snap.state, AgentState.WAITING_PERMISSION)

    def test_plan_with_memory_context(self):
        ctx = "=== MEMORY CONTEXT ===\n# Long-term Memory\n- Created hello.txt last session.\n=== END MEMORY CONTEXT ==="
        snap = plan_with_gemma("list files", Path("."), agent=self._agent(), memory_context=ctx)
        self.assertEqual(snap.state, AgentState.WAITING_PERMISSION)
        self.assertIsNotNone(snap.pending_tool)


if __name__ == "__main__":
    unittest.main()
