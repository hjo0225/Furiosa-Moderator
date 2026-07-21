"""brief — 브리핑 팩 검색 (유일한 진짜 RAG). 발동은 구조화 출력(unknown_terms)이 지정.

T0 게이트 판정의 구현: 모델은 "모르는 용어"를 나열만 하고(명시적 분류 — 12/12 검증 유형),
검색 실행은 결정론이다. 실패는 주입 생략일 뿐 인터뷰를 막지 않는다.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def lookup(project_id: str, terms: list[str], k: int = 2) -> list[dict]:
    if not terms:
        return []
    try:
        from ...briefing.pipeline import search_chunks

        notes: list[dict] = []
        for term in terms[:2]:                    # 과잉 검색 방지 — 용어 2개까지
            notes += search_chunks(project_id, term, k=k)
        return notes
    except Exception as e:
        log.warning("brief 검색 실패 — 주입 생략 (project=%s): %s", project_id, e)
        return []
