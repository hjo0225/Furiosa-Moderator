"""strategize — T1 은 결정론 정책만: 12턴 하드 가드. 행동 7종 선택은 T3 에서."""
from __future__ import annotations

from ..state import InterviewState

MAX_ASKED = 12  # moderator._MAX_ASKED 와 동일 값 — 구엔진 제거 시 여기가 단일 출처


def strategize(state: InterviewState) -> dict:
    # 결정론 하드 가드 — LLM 이 close 를 안 내도 12번째 질문에서 끝낸다
    if state.get("asked", 0) + 1 >= MAX_ASKED:
        return {"action": "close"}
    return {}
