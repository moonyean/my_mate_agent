from __future__ import annotations

import re
from pathlib import Path

from .schema import Persona, PersonaConstraints, PersonaIdentity, PersonaMemoryBinding, PersonaRules, PersonaTone
from .validator import validate_persona, ValidationError

_DEFAULT_PERSONA = """\
# Persona

## Identity
- Name: 어시스턴트
- Role: 도서관 사서

## Tone
- Speech Style: 차분하고 친절한 말투
- Personality: 꼼꼼하고 박식하며 도움을 주고 싶어한다

## Rules
- 정보를 전달할 때 출처를 언급한다
- 모르는 것은 솔직하게 모른다고 한다

## Constraints
- 정치적 의견 표명 금지
- 실존 인물에 대한 부정적 발언 금지

## Memory Binding
- Session: (none)
- Note:
""".strip()

_DEFAULT_USER_RULES = """\
# User Rules
(사용자 정의 규칙을 여기에 추가하세요.)
""".strip()


class PersonaManager:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        self.persona_path = data_dir / "persona.md"
        self.user_rules_path = data_dir / "userRules.md"
        if not self.persona_path.exists():
            self.persona_path.write_text(_DEFAULT_PERSONA, encoding="utf-8")
        if not self.user_rules_path.exists():
            self.user_rules_path.write_text(_DEFAULT_USER_RULES, encoding="utf-8")

    def load_persona(self) -> Persona:
        return parse_persona_md(self.persona_path.read_text(encoding="utf-8"))

    def read_user_rules(self) -> str:
        return self.user_rules_path.read_text(encoding="utf-8")

    def read_persona_raw(self) -> str:
        return self.persona_path.read_text(encoding="utf-8")

    def save_persona(self, persona: Persona) -> None:
        ok, msg = validate_persona(persona)
        if not ok:
            raise ValidationError(msg)
        self.persona_path.write_text(serialize_persona(persona), encoding="utf-8")

    def save_user_rules(self, content: str) -> None:
        self.user_rules_path.write_text(content, encoding="utf-8")


def _section(text: str, header: str) -> str:
    m = re.search(rf"##\s+{re.escape(header)}\s*\n(.*?)(?=\n##|\Z)", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _kv(block: str, key: str) -> str:
    m = re.search(rf"^-\s*{re.escape(key)}\s*:\s*(.+)$", block, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _items(block: str) -> list[str]:
    out = []
    for line in block.splitlines():
        m = re.match(r"^-\s+(.+)$", line.strip())
        if not m:
            continue
        val = m.group(1).strip()
        if re.match(r"^[A-Za-z가-힣\s]+:\s+", val):
            continue
        out.append(val)
    return out


def parse_persona_md(text: str) -> Persona:
    ib = _section(text, "Identity")
    tb = _section(text, "Tone")
    rb = _section(text, "Rules")
    cb = _section(text, "Constraints")
    mb = _section(text, "Memory Binding")
    sid = _kv(mb, "Session")
    return Persona(
        identity=PersonaIdentity(name=_kv(ib, "Name") or "어시스턴트", role=_kv(ib, "Role") or "도우미"),
        tone=PersonaTone(speech_style=_kv(tb, "Speech Style") or "친절한 말투", personality=_kv(tb, "Personality") or "도움을 주고 싶어한다"),
        rules=PersonaRules(behavior=_items(rb)),
        constraints=PersonaConstraints(forbidden=_items(cb)),
        memory_binding=PersonaMemoryBinding(
            session_id=None if sid in ("(none)", "", "none") else sid,
            note=_kv(mb, "Note"),
        ),
    )


def serialize_persona(p: Persona) -> str:
    rules = "\n".join(f"- {r}" for r in p.rules.behavior) or "- (없음)"
    constraints = "\n".join(f"- {c}" for c in p.constraints.forbidden) or "- (없음)"
    session = p.memory_binding.session_id or "(none)"
    return f"""\
# Persona

## Identity
- Name: {p.identity.name}
- Role: {p.identity.role}

## Tone
- Speech Style: {p.tone.speech_style}
- Personality: {p.tone.personality}

## Rules
{rules}

## Constraints
{constraints}

## Memory Binding
- Session: {session}
- Note: {p.memory_binding.note}
""".strip()
