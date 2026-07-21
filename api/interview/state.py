"""인터뷰 그래프 상태 — T2: 그래프가 대화·커버리지·페이스를 소유한다.

messages 가 대화의 원본이다(add_messages 리듀서, 12턴 캡이라 통째 보관).
DB(turns/sessions)는 대시보드용 기록 — 이원화가 의도된 설계.
원장(ledger)은 출석부가 아니라 취재 수첩: 문항별 상태·알아낸 사실·안 판 떡밥.
(analysis·plan 필드는 T3 콜 분리 때 — 지금은 facts/hooks 와 action 이 그 역할.)
"""
from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class CoverageEntry(TypedDict):
    status: str            # pending | touched | satisfied | saturated
    facts: list[str]       # 이 문항에서 실제로 알아낸 것
    hooks: list[str]       # 파고들 만했는데 안 판 떡밥


def init_ledger(guide: dict) -> dict[str, CoverageEntry]:
    """가이드 문항 전부를 pending 원장으로."""
    return {
        q["id"]: CoverageEntry(status="pending", facts=[], hooks=[])
        for q in guide.get("questions", [])
        if q.get("id")
    }


class InterviewState(TypedDict, total=False):
    # 세션 컨텍스트 — 그래프 시작 시 1회 주입, 체크포인트로 유지
    project_id: str
    session_id: str
    lang: str
    guide: dict                # InterviewGuide.model_dump()

    # 그래프가 소유하는 상태 (T2, 필수③)
    messages: Annotated[list, add_messages]   # 응답자=Human, 진행자=AI
    ledger: dict[str, CoverageEntry]
    covered: list[str]         # 대시보드용 출석부 — sessions.covered 와 동기
    asked: int                 # 진행자 질문 수 (speak 가 +1)
    probe_streak: int          # 현 문항 연속 꼬리질문 수 (speak 가 갱신)

    # 턴 스크래치 — 매 턴 덮어씀
    utterance: str
    draft: str
    action: str                # probe | advance | close
    question_id: str
    is_probe: bool
    message: str
    rewritten: bool
    done: bool
    end_reason: str            # model_done | max_turns | honest_close — 종료 근거
