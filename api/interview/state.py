"""인터뷰 그래프 상태 — T1 은 턴 스크래치 + 최소 세션 컨텍스트만.

T2 에서 messages·ledger 가 들어오며 '그래프가 상태를 소유'가 완성된다.
지금은 대화 이력·커버리지의 원본이 여전히 DB(store)다.
"""
from __future__ import annotations

from typing import TypedDict


class InterviewState(TypedDict, total=False):
    # 세션 컨텍스트 — 그래프 시작 시 1회 주입, 체크포인트로 유지
    project_id: str
    session_id: str
    lang: str
    guide: dict                # InterviewGuide.model_dump()
    covered: list[str]
    asked: int                 # 진행자 질문 수 (speak 가 +1)

    # 턴 스크래치 — 매 턴 덮어씀
    utterance: str             # 마스킹된 응답자 발화 (listen 의 interrupt 반환값)
    draft: str                 # 질문 초안 (T1: 만능 콜 출력)
    action: str                # probe | advance | close
    question_id: str
    is_probe: bool
    message: str               # guard 를 통과한 최종 발화
    rewritten: bool
    done: bool
