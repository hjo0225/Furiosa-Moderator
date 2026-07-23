"""대상 청중 수집 (RAG-7) — 브리프 → 페르소나 풀 검색 → [대상 청중] 불릿.

가이드 생성 시 글로벌 페르소나 풀(personas 코퍼스)을 브리프 조건으로 검색해
프롬프트에 참고용으로 주입한다. 코퍼스가 비면(운영 현재) 통째로 무동작 —
LLM·임베딩 호출 없이 "" 를 돌려 프롬프트를 바이트 동일하게 유지한다.

모든 실패는 흡수한다(레포 관례: RAG 장애가 가이드 생성을 막아선 안 된다).
"""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from ..prompts.audience import AUDIENCE_SYSTEM, audience_user
from .llm_client import LLMError, get_llm

log = logging.getLogger(__name__)

PERSONA_CORPUS = "personas"


class AudienceSpec(BaseModel):
    """브리프에서 뽑은 페르소나 검색 조건. 명시 안 된 값은 None/빈값(fail-open)."""

    age_min: int | None = None
    age_max: int | None = None
    sex: Literal["남자", "여자"] | None = None
    keywords: list[str] = Field(default_factory=list)
    query: str = ""


def collect_personas(p) -> str:
    """브리프로 페르소나 풀을 검색해 [대상 청중] 불릿 문자열로. 모든 실패는 "" (가이드 생성을 막지 않는다)."""
    # 순환 임포트 회피 — 로컬 임포트(레포 관례).
    from ..briefing.pipeline import has_knowledge, search_knowledge

    try:
        if not has_knowledge(PERSONA_CORPUS):   # 코퍼스가 비면 LLM·임베딩 호출 없이 무동작
            return ""
    except Exception:  # noqa: BLE001 — 지식풀 조회 장애가 가이드 생성을 막아선 안 된다
        log.warning("페르소나 풀 조회 실패", exc_info=True)
        return ""

    try:
        spec, _ = get_llm().structured(
            AUDIENCE_SYSTEM,
            audience_user(p.topic, p.target, p.motivation, p.utilization),
            AudienceSpec, max_tokens=256,
        )
    except LLMError as e:
        log.warning("청중 조건 추출 실패, 무동작 (%s)", e)
        return ""

    # 하드필터는 나이·성별뿐(설계 결정). 한쪽 나이만 오면 반대편은 열어 둔다(19/99).
    meta_filters: dict = {}
    if spec.age_min is not None or spec.age_max is not None:
        meta_filters["age"] = (spec.age_min or 19, spec.age_max or 99)
    if spec.sex:
        meta_filters["sex"] = spec.sex

    query = (spec.query or f"{p.topic} {p.target}").strip()
    try:
        # candidates=20 으로 리랭커 지연을 묶는다(가이드 생성 지연이 이미 빠듯).
        hits = search_knowledge(
            query, corpus=PERSONA_CORPUS, k=8,
            meta_filters=meta_filters or None,
            keywords=(spec.keywords or None), candidates=20,
        )
    except Exception:  # noqa: BLE001 — 검색 장애가 가이드 생성을 막아선 안 된다
        log.warning("페르소나 검색 실패, 무동작 (query=%s)", query, exc_info=True)
        return ""

    lines: list[str] = []
    for h in hits:
        summary = (h["title"] or h["text"] or "")[:200].strip()
        if summary:
            lines.append(f"- {summary}")
    return "\n".join(lines[:8])
