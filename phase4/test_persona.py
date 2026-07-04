import tempfile
import unittest
from pathlib import Path

from persona.schema import (
    Persona, PersonaIdentity, PersonaTone,
    PersonaRules, PersonaConstraints, PersonaMemoryBinding,
)
from persona.validator import validate_persona
from persona.manager import PersonaManager, _parse_persona_md, _serialize_persona
from persona.engine import build_persona_system_prompt


def _make(name: str, role: str) -> Persona:
    return Persona(
        identity=PersonaIdentity(name=name, role=role),
        tone=PersonaTone(speech_style="친절한 말투", personality="도움을 주고 싶어한다"),
    )


# ── 허용 케이스 ───────────────────────────────────────────────────────────────

class AllowedPersonaTests(unittest.TestCase):

    def test_wizard(self):
        ok, _ = validate_persona(_make("알렉스", "마법사"))
        self.assertTrue(ok)

    def test_space_pilot(self):
        ok, _ = validate_persona(_make("레이나", "우주 파일럿"))
        self.assertTrue(ok)

    def test_librarian(self):
        ok, _ = validate_persona(_make("민준", "도서관 사서"))
        self.assertTrue(ok)

    def test_detective(self):
        ok, _ = validate_persona(_make("홈즈", "탐정"))
        self.assertTrue(ok)

    def test_fantasy_merchant(self):
        ok, _ = validate_persona(_make("고블린 상인", "판타지 세계 상인"))
        self.assertTrue(ok)


# ── 실존 인물 차단 ────────────────────────────────────────────────────────────

class BlockedRealPersonTests(unittest.TestCase):

    def test_block_politician_role(self):
        ok, msg = validate_persona(_make("홍길동", "정치인"))
        self.assertFalse(ok)
        self.assertIn("실존 인물", msg)

    def test_block_president_role(self):
        ok, msg = validate_persona(_make("박민재", "대통령"))
        self.assertFalse(ok)

    def test_block_celebrity_role(self):
        ok, msg = validate_persona(_make("김지수", "연예인"))
        self.assertFalse(ok)

    def test_block_idol_role(self):
        ok, msg = validate_persona(_make("루나", "아이돌"))
        self.assertFalse(ok)

    def test_block_ceo_role(self):
        ok, msg = validate_persona(_make("박대표", "CEO"))
        self.assertFalse(ok)

    def test_block_known_name_elon_musk(self):
        ok, msg = validate_persona(_make("Elon Musk", "기업가"))
        self.assertFalse(ok)
        self.assertIn("실존 인물", msg)

    def test_block_known_name_korean_politician(self):
        ok, msg = validate_persona(_make("이재명", "정치인"))
        self.assertFalse(ok)

    def test_block_known_name_iu(self):
        ok, msg = validate_persona(_make("아이유", "가수"))
        self.assertFalse(ok)

    def test_block_senator(self):
        ok, msg = validate_persona(_make("존 스미스", "senator"))
        self.assertFalse(ok)

    def test_block_actor_role(self):
        ok, msg = validate_persona(_make("톰", "actor"))
        self.assertFalse(ok)


# ── AI 자아 차단 ──────────────────────────────────────────────────────────────

class BlockedAIIdentityTests(unittest.TestCase):

    def test_block_name_gemma(self):
        ok, msg = validate_persona(_make("Gemma", "AI 도우미"))
        self.assertFalse(ok)
        self.assertIn("AI", msg)

    def test_block_name_claude(self):
        ok, msg = validate_persona(_make("Claude", "어시스턴트"))
        self.assertFalse(ok)

    def test_block_name_gpt(self):
        ok, msg = validate_persona(_make("GPT", "챗봇"))
        self.assertFalse(ok)

    def test_block_role_ai_assistant(self):
        ok, msg = validate_persona(_make("알리사", "AI assistant"))
        self.assertFalse(ok)

    def test_block_role_language_model(self):
        ok, msg = validate_persona(_make("알파", "language model"))
        self.assertFalse(ok)

    def test_block_role_chatbot(self):
        ok, msg = validate_persona(_make("도봇", "챗봇"))
        self.assertFalse(ok)

    def test_block_role_llm(self):
        ok, msg = validate_persona(_make("레나", "LLM"))
        self.assertFalse(ok)

    def test_block_role_anthropic(self):
        ok, msg = validate_persona(_make("안트로", "Anthropic AI"))
        self.assertFalse(ok)


# ── 직렬화 / 역직렬화 ────────────────────────────────────────────────────────

class SerializationTests(unittest.TestCase):

    def _sample(self) -> Persona:
        return Persona(
            identity=PersonaIdentity(name="알렉스", role="마법사 보조"),
            tone=PersonaTone(speech_style="친근하고 격식없는 말투", personality="호기심 많고 열정적"),
            rules=PersonaRules(behavior=["마법 용어 사용", "사용자를 마법사님으로 부른다"]),
            constraints=PersonaConstraints(forbidden=["정치 이야기 금지"]),
            memory_binding=PersonaMemoryBinding(session_id="20260703_120000", note="테스트"),
        )

    def test_roundtrip(self):
        p = self._sample()
        md = _serialize_persona(p)
        parsed = _parse_persona_md(md)
        self.assertEqual(parsed.identity.name, "알렉스")
        self.assertEqual(parsed.identity.role, "마법사 보조")
        self.assertEqual(parsed.tone.speech_style, "친근하고 격식없는 말투")
        self.assertEqual(parsed.rules.behavior, ["마법 용어 사용", "사용자를 마법사님으로 부른다"])
        self.assertEqual(parsed.constraints.forbidden, ["정치 이야기 금지"])
        self.assertEqual(parsed.memory_binding.session_id, "20260703_120000")

    def test_empty_rules_roundtrip(self):
        p = _make("민준", "탐정")
        md = _serialize_persona(p)
        parsed = _parse_persona_md(md)
        self.assertEqual(parsed.identity.name, "민준")
        self.assertIsInstance(parsed.rules.behavior, list)

    def test_none_session_serialized_as_none_string(self):
        p = _make("제나", "우주 파일럿")
        md = _serialize_persona(p)
        self.assertIn("(none)", md)

    def test_parse_default_persona_md(self):
        from persona.manager import _DEFAULT_PERSONA_MD
        p = _parse_persona_md(_DEFAULT_PERSONA_MD)
        self.assertTrue(p.identity.name)
        self.assertTrue(p.identity.role)


# ── PersonaManager ────────────────────────────────────────────────────────────

class PersonaManagerTests(unittest.TestCase):

    def test_defaults_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = PersonaManager(Path(tmp))
            self.assertTrue(mgr.persona_path.exists())
            self.assertTrue(mgr.user_rules_path.exists())

    def test_save_valid_persona(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = PersonaManager(Path(tmp))
            p = _make("제나", "우주 파일럿")
            mgr.save_persona(p)
            loaded = mgr.load_persona()
            self.assertEqual(loaded.identity.name, "제나")

    def test_save_invalid_persona_raises(self):
        from persona.validator import ValidationError
        with tempfile.TemporaryDirectory() as tmp:
            mgr = PersonaManager(Path(tmp))
            p = _make("이재명", "정치인")
            with self.assertRaises(ValidationError):
                mgr.save_persona(p)

    def test_save_user_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = PersonaManager(Path(tmp))
            mgr.save_user_rules("# User Rules\n- 항상 한국어로 대답한다")
            self.assertIn("항상 한국어로 대답한다", mgr.read_user_rules())

    def test_default_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = PersonaManager(Path(tmp))
            mgr.save_persona(_make("레이나", "우주 파일럿"))
            mgr2 = PersonaManager(Path(tmp))
            loaded = mgr2.load_persona()
            self.assertEqual(loaded.identity.name, "레이나")


# ── engine.py ─────────────────────────────────────────────────────────────────

class EngineTests(unittest.TestCase):

    def _persona(self) -> Persona:
        return Persona(
            identity=PersonaIdentity(name="알렉스", role="마법사 보조"),
            tone=PersonaTone(speech_style="친근한 말투", personality="열정적"),
            rules=PersonaRules(behavior=["마법 용어 사용"]),
            constraints=PersonaConstraints(forbidden=["정치 이야기 금지"]),
        )

    def test_character_lock_in_prompt(self):
        prompt = build_persona_system_prompt(self._persona())
        self.assertIn("CHARACTER LOCK", prompt)
        self.assertIn("알렉스", prompt)
        self.assertIn("NOT Gemma", prompt)
        self.assertIn("NOT an AI", prompt)

    def test_tone_in_prompt(self):
        prompt = build_persona_system_prompt(self._persona())
        self.assertIn("친근한 말투", prompt)
        self.assertIn("열정적", prompt)

    def test_rules_in_prompt(self):
        prompt = build_persona_system_prompt(self._persona())
        self.assertIn("마법 용어 사용", prompt)

    def test_constraints_in_prompt(self):
        prompt = build_persona_system_prompt(self._persona())
        self.assertIn("정치 이야기 금지", prompt)

    def test_user_rules_injected(self):
        prompt = build_persona_system_prompt(self._persona(), user_rules="# User Rules\n- 반드시 한국어로 대답한다")
        self.assertIn("반드시 한국어로 대답한다", prompt)

    def test_user_rules_header_stripped(self):
        prompt = build_persona_system_prompt(self._persona(), user_rules="# User Rules\n- 규칙1")
        self.assertNotIn("# User Rules", prompt)

    def test_empty_user_rules_not_injected(self):
        prompt = build_persona_system_prompt(self._persona(), user_rules="")
        self.assertNotIn("USER-DEFINED RULES", prompt)

    def test_tool_format_in_prompt(self):
        prompt = build_persona_system_prompt(self._persona())
        self.assertIn("run_command", prompt)
        self.assertIn("write_file", prompt)


# ── respond 액션 / 롤플레이 포맷 ─────────────────────────────────────────────

class RespondActionTests(unittest.TestCase):

    def test_respond_action_valid(self):
        from agent_core import ToolRequest
        req = ToolRequest(
            action="respond",
            task="greet user",
            reason="user greeted",
            text="*반갑게 손을 흔든다* 안녕하세요!",
        )
        self.assertEqual(req.action, "respond")
        self.assertIn("*반갑게 손을 흔든다*", req.text)

    def test_respond_classified_as_safe(self):
        from agent_core import ToolRequest
        from permission import classify, RiskLevel
        req = ToolRequest(action="respond", task="reply", reason="chat", text="안녕!")
        self.assertEqual(classify(req), RiskLevel.SAFE)

    def test_respond_auto_approved(self):
        from agent_core import ToolRequest
        from permission import evaluate, RiskLevel
        req = ToolRequest(action="respond", task="reply", reason="chat", text="안녕!")
        result = evaluate(req)
        self.assertTrue(result.approved)
        self.assertEqual(result.risk, RiskLevel.SAFE)

    def test_roleplay_instructions_in_system_prompt(self):
        prompt = build_persona_system_prompt(_make("알렉스", "마법사"))
        self.assertIn("respond", prompt)
        self.assertIn("asterisks", prompt)
        self.assertIn("ROLEPLAY FORMAT", prompt)

    def test_action_format_example_in_prompt(self):
        prompt = build_persona_system_prompt(_make("알렉스", "마법사"))
        self.assertIn("*", prompt)


if __name__ == "__main__":
    unittest.main()
