"""
core 레이어 단위 테스트
- agent.py : ToolRequest, normalize_command, execute_tool
- permission.py : classify, evaluate
- config.py : AgentSettings, SettingsManager
- memory/db.py : MemoryDB
- memory/markdown.py : MarkdownMemory
- memory/summarizer.py : build_agent_context
- persona/* : validate, parse/serialize, engine
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent import (
    AgentState, ToolRequest, ToolResult,
    execute_tool, normalize_command, powershell_cmd,
)
from core.config import AgentSettings, SettingsManager
from core.memory.db import MemoryDB
from core.memory.markdown import MarkdownMemory
from core.memory.summarizer import build_agent_context
from core.permission import RiskLevel, classify, evaluate
from core.persona.engine import build_persona_system_prompt
from core.persona.manager import PersonaManager, parse_persona_md, serialize_persona
from core.persona.schema import (
    Persona, PersonaConstraints, PersonaIdentity,
    PersonaMemoryBinding, PersonaRules, PersonaTone,
)
from core.persona.validator import validate_persona


# ── helpers ───────────────────────────────────────────────────────────────────

def run_cmd(*args: str) -> ToolRequest:
    return ToolRequest(action="run_command", task="t", reason="t", command=list(args))


def write_file(path: str = "a.txt", content: str = "hi") -> ToolRequest:
    return ToolRequest(action="write_file", task="t", reason="t", file_path=path, content=content)


def respond(text: str = "안녕!") -> ToolRequest:
    return ToolRequest(action="respond", task="t", reason="t", text=text)


def make_persona(name: str, role: str) -> Persona:
    return Persona(
        identity=PersonaIdentity(name=name, role=role),
        tone=PersonaTone(speech_style="친절한 말투", personality="도움을 주고 싶어한다"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ToolRequest 모델
# ═══════════════════════════════════════════════════════════════════════════════

class ToolRequestTests(unittest.TestCase):

    def test_run_command_valid(self):
        r = run_cmd("powershell", "-Command", "Get-ChildItem")
        self.assertEqual(r.action, "run_command")
        self.assertIsNone(r.text)

    def test_write_file_valid(self):
        r = write_file()
        self.assertEqual(r.action, "write_file")
        self.assertIsNone(r.command)

    def test_respond_valid(self):
        r = respond("*웃으며* 안녕!")
        self.assertEqual(r.action, "respond")
        self.assertIn("*웃으며*", r.text)

    def test_cwd_defaults_none(self):
        self.assertIsNone(run_cmd("ls").cwd)


# ═══════════════════════════════════════════════════════════════════════════════
# normalize_command / powershell_cmd
# ═══════════════════════════════════════════════════════════════════════════════

class NormalizeCommandTests(unittest.TestCase):

    def test_powershell_command_flag_reencoded(self):
        cmd = normalize_command(["powershell", "-NoProfile", "-Command", "Get-ChildItem"])
        self.assertIn("-EncodedCommand", cmd)

    def test_ls_becomes_get_childitem(self):
        cmd = normalize_command(["ls"])
        self.assertIn("-EncodedCommand", cmd)

    def test_pwd_becomes_get_location(self):
        cmd = normalize_command(["pwd"])
        self.assertIn("-EncodedCommand", cmd)

    def test_echo_wrapped(self):
        cmd = normalize_command(["echo", "hello"])
        self.assertIn("-EncodedCommand", cmd)

    def test_shell_operator_wrapped(self):
        cmd = normalize_command(["echo", "hi", ">", "file.txt"])
        self.assertIn("-EncodedCommand", cmd)

    def test_passthrough_unknown(self):
        cmd = normalize_command(["python", "script.py"])
        self.assertEqual(cmd, ["python", "script.py"])

    def test_empty_passthrough(self):
        self.assertEqual(normalize_command([]), [])


# ═══════════════════════════════════════════════════════════════════════════════
# execute_tool
# ═══════════════════════════════════════════════════════════════════════════════

class ExecuteToolTests(unittest.TestCase):

    def test_denied_returns_not_approved(self):
        r = execute_tool(run_cmd("ls"), Path("."), approved=False)
        self.assertFalse(r.approved)
        self.assertIsNone(r.exit_code)

    def test_write_file_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            r = execute_tool(write_file("hello.txt", "world\n"), ws, approved=True)
            self.assertEqual(r.exit_code, 0)
            self.assertEqual((ws / "hello.txt").read_text(encoding="utf-8"), "world\n")

    def test_write_file_denied_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            execute_tool(write_file("x.txt", "data"), ws, approved=False)
            self.assertFalse((ws / "x.txt").exists())

    def test_write_file_missing_path_returns_error(self):
        r = execute_tool(
            ToolRequest(action="write_file", task="t", reason="t", content="hi"),
            Path("."), approved=True,
        )
        self.assertEqual(r.exit_code, 1)

    def test_run_command_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = execute_tool(run_cmd("powershell", "-Command", "Write-Output hello"), Path(tmp), approved=True)
            self.assertEqual(r.exit_code, 0)
            self.assertIn("hello", r.stdout)

    def test_respond_approved_returns_ok(self):
        r = execute_tool(respond("안녕!"), Path("."), approved=True)
        self.assertEqual(r.exit_code, 0)

    def test_cwd_fallback_when_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            req = ToolRequest(action="run_command", task="t", reason="t",
                              command=["powershell", "-Command", "Write-Output ok"],
                              cwd="nonexistent_dir")
            r = execute_tool(req, ws, approved=True)
            self.assertEqual(r.exit_code, 0)


# ═══════════════════════════════════════════════════════════════════════════════
# Permission
# ═══════════════════════════════════════════════════════════════════════════════

class ClassifyTests(unittest.TestCase):

    def test_respond_safe(self):
        self.assertEqual(classify(respond()), RiskLevel.SAFE)

    def test_write_file_confirm(self):
        self.assertEqual(classify(write_file()), RiskLevel.CONFIRM)

    def test_get_childitem_safe(self):
        self.assertEqual(classify(run_cmd("powershell", "-Command", "Get-ChildItem")), RiskLevel.SAFE)

    def test_ls_safe(self):
        self.assertEqual(classify(run_cmd("ls")), RiskLevel.SAFE)

    def test_remove_item_high_risk(self):
        self.assertEqual(classify(run_cmd("powershell", "-Command", "Remove-Item file.txt")), RiskLevel.HIGH_RISK)

    def test_rm_rf_high_risk(self):
        self.assertEqual(classify(run_cmd("rm", "-rf", "/tmp/x")), RiskLevel.HIGH_RISK)

    def test_diskpart_block(self):
        self.assertEqual(classify(run_cmd("diskpart")), RiskLevel.BLOCK)

    def test_reg_add_block(self):
        self.assertEqual(classify(run_cmd("reg", "add", "HKLM\\test")), RiskLevel.BLOCK)

    def test_wget_confirm(self):
        self.assertEqual(classify(run_cmd("wget", "https://example.com")), RiskLevel.CONFIRM)

    def test_exe_high_risk(self):
        self.assertEqual(classify(run_cmd("setup.exe")), RiskLevel.HIGH_RISK)


class EvaluateTests(unittest.TestCase):

    def test_safe_auto_approved(self):
        r = evaluate(run_cmd("ls"))
        self.assertTrue(r.approved)

    def test_block_auto_denied(self):
        r = evaluate(run_cmd("diskpart"))
        self.assertFalse(r.approved)
        self.assertEqual(r.risk, RiskLevel.BLOCK)

    def test_confirm_not_approved(self):
        r = evaluate(write_file())
        self.assertFalse(r.approved)

    def test_high_risk_not_approved(self):
        r = evaluate(run_cmd("powershell", "-Command", "Remove-Item x"))
        self.assertFalse(r.approved)

    def test_safe_no_auto_approve(self):
        r = evaluate(run_cmd("ls"), auto_approve_safe=False)
        self.assertFalse(r.approved)

    def test_respond_auto_approved(self):
        r = evaluate(respond())
        self.assertTrue(r.approved)


# ═══════════════════════════════════════════════════════════════════════════════
# AgentSettings / SettingsManager
# ═══════════════════════════════════════════════════════════════════════════════

class SettingsTests(unittest.TestCase):

    def test_defaults(self):
        s = AgentSettings()
        self.assertEqual(s.model_name, "gemma4:latest")
        self.assertTrue(s.auto_approve_safe)

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = SettingsManager(Path(tmp) / "settings.json")
            s = AgentSettings(model_name="llama3:latest", timeout_seconds=30)
            mgr.save(s)
            loaded = mgr.load()
            self.assertEqual(loaded.model_name, "llama3:latest")
            self.assertEqual(loaded.timeout_seconds, 30)

    def test_default_file_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            SettingsManager(path)
            self.assertTrue(path.exists())


# ═══════════════════════════════════════════════════════════════════════════════
# MemoryDB
# ═══════════════════════════════════════════════════════════════════════════════

class MemoryDBTests(unittest.TestCase):

    def _db(self, tmp: str) -> MemoryDB:
        return MemoryDB(Path(tmp) / "test.db")

    def test_save_and_retrieve(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._db(tmp)
            db.save_message("s1", "user", "hello")
            db.save_message("s1", "assistant", "world")
            msgs = db.get_recent_messages("s1")
            self.assertEqual(len(msgs), 2)
            self.assertEqual(msgs[0]["role"], "user")
            db.close()

    def test_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._db(tmp)
            for i in range(10):
                db.save_message("s1", "user", f"msg{i}")
            msgs = db.get_recent_messages("s1", limit=3)
            self.assertEqual(len(msgs), 3)
            self.assertEqual(msgs[-1]["content"], "msg9")
            db.close()

    def test_session_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._db(tmp)
            db.save_message("s1", "user", "a")
            db.save_message("s2", "user", "b")
            self.assertEqual(len(db.get_recent_messages("s1")), 1)
            self.assertEqual(len(db.get_recent_messages("s2")), 1)
            db.close()

    def test_all_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._db(tmp)
            db.save_message("s1", "user", "x")
            db.save_message("s2", "user", "y")
            sessions = db.get_all_sessions()
            self.assertIn("s1", sessions)
            self.assertIn("s2", sessions)
            db.close()

    def test_save_tool_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._db(tmp)
            req = run_cmd("powershell", "-Command", "Get-ChildItem")
            result = ToolResult(approved=True, exit_code=0, stdout="file.txt")
            db.save_tool_log("s1", req, result)
            logs = db.get_recent_tool_logs(5)
            self.assertEqual(len(logs), 1)
            self.assertTrue(logs[0]["approved"])
            db.close()

    def test_empty_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._db(tmp)
            self.assertEqual(db.get_recent_messages("none"), [])
            db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# MarkdownMemory
# ═══════════════════════════════════════════════════════════════════════════════

class MarkdownMemoryTests(unittest.TestCase):

    def test_defaults_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = MarkdownMemory(Path(tmp))
            self.assertTrue(md.long_path.exists())
            self.assertTrue(md.project_path.exists())

    def test_update_long(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = MarkdownMemory(Path(tmp))
            md.update_long("# Long-term Memory\n- did a thing")
            self.assertIn("did a thing", md.read_long())

    def test_update_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = MarkdownMemory(Path(tmp))
            md.update_project("# Project\n- phase5")
            self.assertIn("phase5", md.read_project())

    def test_no_overwrite_on_reinit(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = MarkdownMemory(Path(tmp))
            md.update_long("# Long-term Memory\n- custom")
            md2 = MarkdownMemory(Path(tmp))
            self.assertIn("custom", md2.read_long())


# ═══════════════════════════════════════════════════════════════════════════════
# build_agent_context
# ═══════════════════════════════════════════════════════════════════════════════

class BuildContextTests(unittest.TestCase):

    def test_empty_session_no_convo_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = MemoryDB(Path(tmp) / "db")
            md = MarkdownMemory(Path(tmp))
            ctx = build_agent_context("new", db, md)
            self.assertNotIn("RECENT CONVERSATION", ctx)
            db.close()

    def test_messages_appear_in_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = MemoryDB(Path(tmp) / "db")
            md = MarkdownMemory(Path(tmp))
            db.save_message("s1", "user", "hello")
            ctx = build_agent_context("s1", db, md)
            self.assertIn("hello", ctx)
            db.close()

    def test_default_markdown_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = MemoryDB(Path(tmp) / "db")
            md = MarkdownMemory(Path(tmp))
            ctx = build_agent_context("s1", db, md)
            self.assertNotIn("MEMORY CONTEXT", ctx)
            db.close()

    def test_real_long_memory_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = MemoryDB(Path(tmp) / "db")
            md = MarkdownMemory(Path(tmp))
            md.update_long("# Long-term Memory\n- Session X: created hello.txt")
            ctx = build_agent_context("s1", db, md)
            self.assertIn("MEMORY CONTEXT", ctx)
            self.assertIn("Session X", ctx)
            db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Persona Validator
# ═══════════════════════════════════════════════════════════════════════════════

class PersonaValidatorTests(unittest.TestCase):

    def test_wizard_allowed(self):
        ok, _ = validate_persona(make_persona("알렉스", "마법사"))
        self.assertTrue(ok)

    def test_space_pilot_allowed(self):
        ok, _ = validate_persona(make_persona("레이나", "우주 파일럿"))
        self.assertTrue(ok)

    def test_librarian_allowed(self):
        ok, _ = validate_persona(make_persona("민준", "도서관 사서"))
        self.assertTrue(ok)

    def test_politician_blocked(self):
        ok, msg = validate_persona(make_persona("홍길동", "정치인"))
        self.assertFalse(ok)

    def test_celebrity_blocked(self):
        ok, _ = validate_persona(make_persona("김지수", "연예인"))
        self.assertFalse(ok)

    def test_known_person_blocked(self):
        ok, _ = validate_persona(make_persona("이재명", "정치인"))
        self.assertFalse(ok)

    def test_gemma_name_blocked(self):
        ok, msg = validate_persona(make_persona("Gemma", "AI"))
        self.assertFalse(ok)
        self.assertIn("AI", msg)

    def test_claude_name_blocked(self):
        ok, _ = validate_persona(make_persona("Claude", "어시스턴트"))
        self.assertFalse(ok)

    def test_llm_role_blocked(self):
        ok, _ = validate_persona(make_persona("알파", "LLM"))
        self.assertFalse(ok)

    def test_chatbot_role_blocked(self):
        ok, _ = validate_persona(make_persona("봇", "챗봇"))
        self.assertFalse(ok)


# ═══════════════════════════════════════════════════════════════════════════════
# Persona Manager (parse / serialize)
# ═══════════════════════════════════════════════════════════════════════════════

class PersonaManagerTests(unittest.TestCase):

    def _sample(self) -> Persona:
        return Persona(
            identity=PersonaIdentity(name="알렉스", role="마법사 보조"),
            tone=PersonaTone(speech_style="친근한 말투", personality="열정적"),
            rules=PersonaRules(behavior=["마법 용어 사용"]),
            constraints=PersonaConstraints(forbidden=["정치 금지"]),
            memory_binding=PersonaMemoryBinding(session_id="20260704_120000"),
        )

    def test_roundtrip(self):
        p = self._sample()
        md = serialize_persona(p)
        parsed = parse_persona_md(md)
        self.assertEqual(parsed.identity.name, "알렉스")
        self.assertEqual(parsed.rules.behavior, ["마법 용어 사용"])
        self.assertEqual(parsed.constraints.forbidden, ["정치 금지"])
        self.assertEqual(parsed.memory_binding.session_id, "20260704_120000")

    def test_none_session(self):
        p = make_persona("제나", "탐정")
        md = serialize_persona(p)
        self.assertIn("(none)", md)

    def test_save_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = PersonaManager(Path(tmp))
            mgr.save_persona(make_persona("레이나", "우주 파일럿"))
            self.assertEqual(mgr.load_persona().identity.name, "레이나")

    def test_save_invalid_raises(self):
        from core.persona.validator import ValidationError
        with tempfile.TemporaryDirectory() as tmp:
            mgr = PersonaManager(Path(tmp))
            with self.assertRaises(ValidationError):
                mgr.save_persona(make_persona("Gemma", "AI"))

    def test_user_rules_save_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = PersonaManager(Path(tmp))
            mgr.save_user_rules("# User Rules\n- 항상 한국어로")
            self.assertIn("항상 한국어로", mgr.read_user_rules())


# ═══════════════════════════════════════════════════════════════════════════════
# Persona Engine
# ═══════════════════════════════════════════════════════════════════════════════

class PersonaEngineTests(unittest.TestCase):

    def _p(self) -> Persona:
        return Persona(
            identity=PersonaIdentity(name="알렉스", role="마법사"),
            tone=PersonaTone(speech_style="친근한 말투", personality="열정적"),
            rules=PersonaRules(behavior=["마법 용어 사용"]),
            constraints=PersonaConstraints(forbidden=["정치 금지"]),
        )

    def test_character_lock(self):
        prompt = build_persona_system_prompt(self._p())
        self.assertIn("CHARACTER LOCK", prompt)
        self.assertIn("알렉스", prompt)
        self.assertIn("NOT Gemma", prompt)

    def test_tone_in_prompt(self):
        prompt = build_persona_system_prompt(self._p())
        self.assertIn("친근한 말투", prompt)

    def test_rules_in_prompt(self):
        prompt = build_persona_system_prompt(self._p())
        self.assertIn("마법 용어 사용", prompt)

    def test_constraints_in_prompt(self):
        prompt = build_persona_system_prompt(self._p())
        self.assertIn("정치 금지", prompt)

    def test_roleplay_format_in_prompt(self):
        prompt = build_persona_system_prompt(self._p())
        self.assertIn("ROLEPLAY FORMAT", prompt)
        self.assertIn("respond", prompt)

    def test_user_rules_injected(self):
        prompt = build_persona_system_prompt(self._p(), "# User Rules\n- 한국어로 대답")
        self.assertIn("한국어로 대답", prompt)

    def test_default_user_rules_header_stripped(self):
        prompt = build_persona_system_prompt(self._p(), "# User Rules\n- 규칙1")
        self.assertNotIn("# User Rules", prompt)

    def test_empty_user_rules_not_injected(self):
        prompt = build_persona_system_prompt(self._p(), "")
        self.assertNotIn("USER-DEFINED RULES", prompt)

    def test_tool_format_present(self):
        prompt = build_persona_system_prompt(self._p())
        self.assertIn("run_command", prompt)
        self.assertIn("write_file", prompt)


if __name__ == "__main__":
    unittest.main()
