"""중립성 가드레일 (M-2) — 생성된 질문이 유도신문이면 재작성한다.

PRD M-2 Acceptance: "Given 후속질문, When 유도 표현 검출, Then 재작성".
PORTING.md 기준 원본에는 프롬프트 '지시문'만 있고 검사·차단 코드가 없었다. 여기가 그 신규 레이어다.

문안의 출처는 api/_reference/validation_moderator_prompt.py L162-169 —
레포 유일의 유도신문 방지 규칙("답을 정해놓고 끌어내지 마세요… 전제·방향을 깐 질문은 금지").
원본은 가상 FGI 다자토론 전용 코드라 문구만 발췌했다.

2단 구조:
  1) 정규식 사전검사 — 명백한 유도 표현. 비용 0, 지연 0.
  2) LLM 판정 — 1)을 통과했지만 애매한 경우. 사전검사에서 걸리면 생략한다.
재작성도 LLM 이 하되, 재작성본이 또 걸리면 중립 기본형으로 폴백한다(무한루프 금지).
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from .llm_client import LLMError, get_llm

# 명백한 유도 표현 — 전제를 깔거나 동의를 강요하는 어법
_LEADING_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"정말.{0,10}(확신|생각)하[시세]"), "확신 강요"),
    (re.compile(r"(그렇지\s?않(나요|습니까)|아니(신가요|겠어요))"), "동의 유도 부가의문"),
    (re.compile(r"(좋다고|나쁘다고|불편하다고|만족한다고)\s?(보|생각하)[시세]"), "평가 전제"),
    (re.compile(r"당연히"), "당연시"),
    (re.compile(r"(대부분|다들|보통)\s?(사람들[은이]|응답자[는가])"), "다수 의견 원용"),
    (re.compile(r"[을를]\s?(줄일|높일|개선할)\s?수\s?있다고"), "결론 전제"),
    (re.compile(r"(얼마나)\s?(좋|만족|불편|힘드)"), "정도 전제"),
]

_NEUTRALITY_RULES = (
    "[유도 금지] 답을 정해놓고 끌어내지 마세요. '정말 …할 수 있다고 확신하세요?', "
    "'…를 줄일 수 있다고 보시죠?' 처럼 진행자가 **응답자가 하지 않은 말**을 전제로 깔거나 "
    "특정 답으로 방향을 정하는 질문은 금지입니다.\n"
    "[콜백은 유도가 아님] 판정 기준은 '전제가 있는가'가 아니라 **'그 전제를 누가 말했는가'** 입니다. "
    "응답자 본인이 앞서 한 말을 인용·요약해 잇는 콜백('아까 야근할 때 시킨다고 하셨는데, "
    "그럴 때 앱에서 제일 아쉬운 건 뭐였어요?')은 정상적인 진행 기법이며 유도가 아닙니다. "
    "진행자가 콜백하도록 지시받고 있으므로 이를 유도로 판정하지 마세요. "
    "응답자가 실제로 하지 않은 말을 '아까 …라고 하셨죠'로 씌우는 경우에만 유도입니다.\n"
    "[고쳐 쓸 때] 구체성을 죽이지 마세요. 무엇에 대해 묻는지 사라진 두루뭉술한 질문은 "
    "중립적이어도 나쁜 질문입니다. 대상·맥락은 남기고 방향만 걷어내세요 — "
    "'그게 불편하셨죠?' → '그때 어떠셨는지 말씀해 주시겠어요?' 처럼."
)

# 재작성이 또 실패했을 때의 최후 폴백 — 어떤 맥락에서도 중립인 개방형 질문
_SAFE_FALLBACK = "그 부분에 대해 조금 더 자세히 말씀해 주시겠어요?"


class _Verdict(BaseModel):
    leading: bool
    reason: str = ""


class _Rewrite(BaseModel):
    question: str


def precheck(question: str) -> str | None:
    """정규식 사전검사 — 걸리면 사유, 아니면 None."""
    for pattern, label in _LEADING_PATTERNS:
        if pattern.search(question or ""):
            return label
    return None


def ensure_neutral(question: str, *, use_llm: bool = True) -> tuple[str, bool, str]:
    """질문의 중립성을 보장한다.

    반환: (최종질문, 재작성했는지, 사유). 사유는 통과 시 빈 문자열.
    LLM 판정·재작성이 실패해도 인터뷰는 멈추지 않는다 — 원문 또는 안전 폴백을 돌려준다.
    """
    q = (question or "").strip()
    if not q:
        return q, False, ""

    reason = precheck(q)

    # 사전검사를 통과했으면 LLM 에게 애매한 경우만 물어본다.
    if reason is None:
        if not use_llm:
            return q, False, ""
        try:
            verdict, _ = get_llm().structured(
                "당신은 정성조사 질문의 중립성을 심사하는 검수자입니다.\n" + _NEUTRALITY_RULES,
                f"다음 질문이 유도신문인지 판정하세요.\n\n질문: {q}",
                _Verdict,
                max_tokens=200,
            )
        except LLMError:
            # 심사 실패로 인터뷰를 막지는 않는다. 사전검사는 이미 통과한 질문이다.
            return q, False, ""
        if not verdict.leading:
            return q, False, ""
        reason = verdict.reason or "LLM 판정"

    # 여기 왔으면 유도로 판정됨 → 재작성
    try:
        rewritten, _ = get_llm().structured(
            "당신은 정성조사 질문을 중립적으로 고쳐 쓰는 편집자입니다.\n"
            + _NEUTRALITY_RULES
            + "\n의미와 조사 의도는 유지하되, 전제·방향을 걷어내고 열린 질문으로 바꾸세요. "
            "짧고 자연스러운 한국어 구어체 1~2문장.",
            f"다음 질문이 '{reason}' 사유로 유도신문 판정을 받았습니다. 중립적으로 고쳐 쓰세요.\n\n질문: {q}",
            _Rewrite,
            max_tokens=300,
        )
    except LLMError:
        return _SAFE_FALLBACK, True, f"{reason}(재작성 실패 → 폴백)"

    new_q = (rewritten.question or "").strip()
    # 재작성본이 또 걸리면 폴백. 재귀하지 않는다.
    if not new_q or precheck(new_q):
        return _SAFE_FALLBACK, True, f"{reason}(재작성 실패 → 폴백)"
    return new_q, True, reason
