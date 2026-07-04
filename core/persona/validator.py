from __future__ import annotations
import re
from .schema import Persona


class ValidationError(Exception):
    pass


_AI = re.compile(
    r"\b(gemma|gpt|claude|llama|mistral|chatgpt|copilot|bard|gemini"
    r"|anthropic|openai|google|meta ai|llm|language.?model|large language"
    r"|ai assistant|인공지능|챗봇|chatbot|대화형 ai)\b",
    re.IGNORECASE,
)
_REAL_ROLE = re.compile(
    r"\b(정치인|대통령|국회의원|의원|장관|총리|senator|president|politician"
    r"|congressman|minister|chancellor|prime minister"
    r"|연예인|가수|배우|아이돌|celebrity|celeb|actor|actress|singer|idol|influencer"
    r"|기업인|회장|대표이사|ceo|founder|entrepreneur|재벌"
    r"|실존|real person|historical figure|역사적 인물)\b",
    re.IGNORECASE,
)
_KNOWN: set[str] = {
    "이재명","윤석열","한동훈","문재인","박근혜","이명박",
    "donald trump","joe biden","barack obama","hillary clinton",
    "vladimir putin","xi jinping","시진핑","푸틴",
    "elon musk","일론 머스크","bill gates","빌 게이츠",
    "mark zuckerberg","마크 저커버그","jeff bezos","워런 버핏","이재용","정의선",
    "아이유","iu","bts","방탄소년단","블랙핑크","blackpink",
    "gemma","claude","chatgpt","gpt-4","llama",
}


def validate_persona(persona: Persona) -> tuple[bool, str]:
    name_l = persona.identity.name.lower().strip()
    role_l = persona.identity.role.lower().strip()

    for val, field in ((name_l, "이름"), (role_l, "역할")):
        if _AI.search(val):
            return False, f"AI 모델 기반 페르소나는 허용되지 않습니다. ({field}: '{val}')"

    if name_l in _KNOWN:
        return False, f"실존 인물 이름은 허용되지 않습니다: '{persona.identity.name}'"

    if _REAL_ROLE.search(role_l):
        return False, f"실존 인물 역할은 허용되지 않습니다: '{persona.identity.role}'"

    if _REAL_ROLE.search(name_l):
        return False, f"실존 인물 관련 이름은 허용되지 않습니다: '{persona.identity.name}'"

    return True, "유효한 페르소나입니다."
