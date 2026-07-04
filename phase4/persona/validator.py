from __future__ import annotations

import re

from .schema import Persona


class ValidationError(Exception):
    pass


# ── AI 자아 차단 ───────────────────────────────────────────────────────────────
# 모델이 자신의 본래 정체성으로 돌아오는 것을 막는다.

_AI_IDENTITY = re.compile(
    r"\b("
    r"gemma|gpt|claude|llama|mistral|chatgpt|copilot|bard|gemini"
    r"|anthropic|openai|google|meta ai"
    r"|llm|language.?model|large language"
    r"|ai assistant|인공지능|챗봇|chatbot|대화형 ai"
    r")\b",
    re.IGNORECASE,
)

# ── 실존 인물 역할 패턴 ────────────────────────────────────────────────────────

_REAL_ROLE = re.compile(
    r"\b("
    # 정치
    r"정치인|대통령|국회의원|의원|장관|총리|국무|senator|president|politician"
    r"|congressman|minister|chancellor|prime minister"
    # 연예
    r"|연예인|가수|배우|아이돌|celebrity|celeb|actor|actress|singer|idol|influencer"
    # 기업
    r"|기업인|회장|대표이사|ceo|founder|entrepreneur|재벌"
    # 명시적 실존
    r"|실존|real person|historical figure|역사적 인물"
    r")\b",
    re.IGNORECASE,
)

# ── 알려진 실존 인물 이름 ──────────────────────────────────────────────────────

_KNOWN_FIGURES: set[str] = {
    # 정치
    "이재명", "윤석열", "한동훈", "문재인", "박근혜", "이명박",
    "donald trump", "joe biden", "barack obama", "hillary clinton",
    "vladimir putin", "xi jinping", "시진핑", "푸틴",
    # 기업
    "elon musk", "일론 머스크", "bill gates", "빌 게이츠",
    "mark zuckerberg", "마크 저커버그", "jeff bezos", "워런 버핏",
    "이재용", "정의선",
    # 연예
    "아이유", "iu", "bts", "방탄소년단", "블랙핑크", "blackpink",
    "김태희", "송중기", "박보검",
    # AI 모델명 (이름으로 쓰는 경우)
    "gemma", "claude", "chatgpt", "gpt-4", "llama",
}


def validate_persona(persona: Persona) -> tuple[bool, str]:
    """
    Returns (is_valid, message).
    저장 전에 반드시 호출한다.
    """
    name = persona.identity.name
    role = persona.identity.role
    name_l = name.lower().strip()
    role_l = role.lower().strip()

    # 1. AI 자아 차단 (이름/역할 모두 검사)
    for field_val, field_name in ((name_l, "이름"), (role_l, "역할")):
        if _AI_IDENTITY.search(field_val):
            return False, f"AI 모델 기반 페르소나는 허용되지 않습니다. ({field_name}: '{field_val}')"

    # 2. 알려진 실존 인물 이름
    if name_l in _KNOWN_FIGURES:
        return False, f"실존 인물 이름은 허용되지 않습니다: '{name}'"

    # 3. 실존 인물 역할 키워드
    if _REAL_ROLE.search(role_l):
        return False, f"실존 인물 역할은 허용되지 않습니다: '{role}'"

    # 4. 이름이 "실존" 키워드를 포함하는 경우
    if _REAL_ROLE.search(name_l):
        return False, f"실존 인물 관련 이름은 허용되지 않습니다: '{name}'"

    return True, "유효한 페르소나입니다."
