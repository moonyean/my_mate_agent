from __future__ import annotations

import re
from pathlib import Path

from .schema import (
    Persona,
    PersonaConstraints,
    PersonaIdentity,
    PersonaMemoryBinding,
    PersonaRules,
    PersonaTone,
)
from .validator import validate_persona, ValidationError

_DEFAULT_PERSONA_MD = """\
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

_DEFAULT_USER_RULES_MD = """\
# User Rules
(사용자 정의 규칙을 여기에 추가하세요. 에이전트는 이 규칙을 항상 따릅니다.)
""".strip()


class PersonaManager:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        self.persona_path = data_dir / "persona.md"
        self.user_rules_path = data_dir / "userRules.md"
        self._init_defaults()

    # ── 초기화 ────────────────────────────────────────────────────────────────

    def _init_defaults(self) -> None:
        if not self.persona_path.exists():
            self.persona_path.write_text(_DEFAULT_PERSONA_MD, encoding="utf-8")
        if not self.user_rules_path.exists():
            self.user_rules_path.write_text(_DEFAULT_USER_RULES_MD, encoding="utf-8")

    # ── 읽기 ─────────────────────────────────────────────────────────────────

    def load_persona(self) -> Persona:
        text = self.persona_path.read_text(encoding="utf-8")
        return _parse_persona_md(text)

    def read_user_rules(self) -> str:
        return self.user_rules_path.read_text(encoding="utf-8")

    # ── 저장 (검증 포함) ──────────────────────────────────────────────────────

    def save_persona(self, persona: Persona) -> None:
        ok, msg = validate_persona(persona)
        if not ok:
            raise ValidationError(msg)
        self.persona_path.write_text(_serialize_persona(persona), encoding="utf-8")

    def save_user_rules(self, content: str) -> None:
        self.user_rules_path.write_text(content, encoding="utf-8")


# ── 파싱 ─────────────────────────────────────────────────────────────────────

def _section(text: str, header: str) -> str:
    """## Header 아래의 텍스트 블록을 반환한다."""
    pattern = rf"##\s+{re.escape(header)}\s*\n(.*?)(?=\n##|\Z)"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _kv(block: str, key: str) -> str:
    """'- Key: value' 형식에서 value를 추출한다."""
    m = re.search(rf"^-\s*{re.escape(key)}\s*:\s*(.+)$", block, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _list_items(block: str, skip_keys: set[str] | None = None) -> list[str]:
    """'- item' 형식의 항목들을 반환한다. Key: Value 형식은 제외."""
    skip_keys = skip_keys or set()
    items = []
    for line in block.splitlines():
        m = re.match(r"^-\s+(.+)$", line.strip())
        if not m:
            continue
        val = m.group(1).strip()
        # "Key: Value" 패턴이면 건너뜀
        if re.match(r"^[A-Za-z가-힣\s]+:\s+", val):
            key_part = val.split(":")[0].strip()
            if key_part in skip_keys or skip_keys == {"*"}:
                continue
        items.append(val)
    return items


def _parse_persona_md(text: str) -> Persona:
    identity_block = _section(text, "Identity")
    tone_block = _section(text, "Tone")
    rules_block = _section(text, "Rules")
    constraints_block = _section(text, "Constraints")
    memory_block = _section(text, "Memory Binding")

    name = _kv(identity_block, "Name") or "어시스턴트"
    role = _kv(identity_block, "Role") or "도우미"
    speech_style = _kv(tone_block, "Speech Style") or "친절한 말투"
    personality = _kv(tone_block, "Personality") or "도움을 주고 싶어한다"
    session_id_raw = _kv(memory_block, "Session")
    session_id = None if session_id_raw in ("(none)", "", "none") else session_id_raw
    note = _kv(memory_block, "Note")

    # Rules / Constraints: Key: Value 라인 제외, 순수 항목만
    kv_keys = {"Name", "Role", "Speech Style", "Personality", "Session", "Note",
               "이름", "역할", "말투", "성격", "세션"}
    rules = _list_items(rules_block, skip_keys=kv_keys)
    constraints = _list_items(constraints_block, skip_keys=kv_keys)

    return Persona(
        identity=PersonaIdentity(name=name, role=role),
        tone=PersonaTone(speech_style=speech_style, personality=personality),
        rules=PersonaRules(behavior=rules),
        constraints=PersonaConstraints(forbidden=constraints),
        memory_binding=PersonaMemoryBinding(session_id=session_id, note=note),
    )


def _serialize_persona(persona: Persona) -> str:
    p = persona
    rules_lines = "\n".join(f"- {r}" for r in p.rules.behavior) or "- (없음)"
    constraints_lines = "\n".join(f"- {c}" for c in p.constraints.forbidden) or "- (없음)"
    session = p.memory_binding.session_id or "(none)"
    note = p.memory_binding.note or ""

    return f"""\
# Persona

## Identity
- Name: {p.identity.name}
- Role: {p.identity.role}

## Tone
- Speech Style: {p.tone.speech_style}
- Personality: {p.tone.personality}

## Rules
{rules_lines}

## Constraints
{constraints_lines}

## Memory Binding
- Session: {session}
- Note: {note}
""".strip()
