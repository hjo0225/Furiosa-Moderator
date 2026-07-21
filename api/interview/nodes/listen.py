"""listen — 발화 대기(interrupt)와 분석·행동·초안의 만능 1콜 (T1 과도기).

interrupt() 가 노드 첫 문장인 것이 규약이다: 재개 시 노드가 처음부터 재실행돼도
interrupt 앞에 부수효과가 없어 멱등이다(전역 불변식).

T1 은 기존 모더레이터 프롬프트를 그대로 써서 분석+행동선택+질문초안을 1콜로 받는다
(콜 수·대화 품질 불변). T3 에서 분석(listen)/생성(generate) 콜로 분리된다.
"""
from __future__ import annotations

from langgraph.types import interrupt

from ...prompts.interview_moderator import interview_moderator_system
from ...schemas.models import InterviewGuide
from ...services import store
from ...services.llm_client import get_llm
from ...services.moderator import _ModeratorOut, _moderator_user
from ..state import InterviewState


def listen(state: InterviewState) -> dict:
    utterance = interrupt({"waiting": "respondent"})  # 여기서 잠든다 — 재개값 = 마스킹된 발화

    history = store.list_turns(state["project_id"], state["session_id"])
    asked = sum(1 for t in history if t.role == "moderator")
    guide = InterviewGuide.model_validate(state["guide"])
    out, _ = get_llm().structured(
        interview_moderator_system(state.get("lang", "ko")),
        _moderator_user(guide, history, asked, list(state.get("covered", []))),
        _ModeratorOut,
        max_tokens=500,
    )
    return {
        "utterance": utterance or "",
        "draft": (out.message or "").strip(),
        "action": "close" if out.done else ("probe" if out.is_probe else "advance"),
        "question_id": out.question_id or "",
        "is_probe": bool(out.is_probe),
        "asked": asked,
    }
