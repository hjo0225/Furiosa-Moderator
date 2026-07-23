"""reflect — 슬로우패스 (Send 병렬). 응답자가 말하는 시간에 무거운 정리를 해둔다.

SSE 에서는 speak 가 토큰을 이미 다 내보낸 뒤라 여기 걸리는 시간은 체감 0.
- reflect_ledger: 직전 문답을 취재 수첩(원장)에 정리 — T3 까지 listen 이 하던 일의 이사.
- reflect_emotion 은 Task 2 에서 합류.
"""
from __future__ import annotations

import logging

from ...prompts.insight import BUCKET_CLASSIFY_SYSTEM, bucket_classify_user
from ...schemas.models import BucketAssignment
from ...services import store
from ...services.llm_client import LLMError, get_llm
from ...services.moderator import tag_emotion
from ..ledger import update_ledger
from ..prompts import REFLECT_SYSTEM, ReflectOut, reflect_user
from ..state import InterviewState

log = logging.getLogger(__name__)


def _catchall_id(buckets: list[dict]) -> str:
    """캐치올 버킷 id — 없으면 마지막 버킷으로 폴백(_normalize_buckets 가 보통 캐치올을 보장)."""
    for b in buckets:
        if b.get("is_catchall"):
            return b.get("id", "")
    return buckets[-1].get("id", "") if buckets else ""


def reflect_ledger(state: InterviewState) -> dict:
    qid = state.get("answered_qid", "")
    utterance = state.get("utterance", "")
    questions = {q["id"]: q for q in state.get("guide", {}).get("questions", []) if q.get("id")}
    if not qid or not utterance or qid not in questions:
        return {}
    try:
        out, _ = get_llm().structured(
            REFLECT_SYSTEM, reflect_user(state["guide"], qid, utterance),
            ReflectOut, max_tokens=1500,
        )
    except LLMError as e:
        log.warning("원장 갱신 실패 — 이번 턴은 건너뜀 (다음 턴에 회복): %s", e)
        return {}
    # 한 답변이 여러 문항을 건드릴 수 있다 — 문항별로 각자 페이지에 반영 (보강 B)
    led = state.get("ledger", {})
    for u in out.updates:
        led = update_ledger(led, u.question_id, u.coverage, u.facts, u.hooks)
    return {"ledger": led}


def reflect_emotion(state: InterviewState) -> dict:
    """감정 태깅 + 응답자 턴의 문항 귀속 (M-3). 다음 질문 생성에 미사용이라 슬로우패스가 제자리.

    응답자 턴은 원래 question_id 가 비어 저장된다 — 그러면 버킷 분포(F6.4)와 문항별 요약(F6.3)이
    문항으로 뭉치지 못한다. 항상 도는 이 노드가 answered_qid(방금 답한 문항)를 턴에 귀속시키는 단일 지점.
    """
    utterance = state.get("utterance", "")
    turn_id = state.get("resp_turn_id", "")
    if not utterance or not turn_id:
        return {}
    emotion, conf = tag_emotion(utterance)   # 실패 시 ("중립", 0.0) — 내부에서 처리
    patch = {"emotion": emotion, "emotion_confidence": conf}
    qid = state.get("answered_qid", "")
    if qid:
        patch["question_id"] = qid   # 분포·문항별 요약 귀속 (응답자 턴엔 원래 안 붙는다)
    store.update_turn(state["project_id"], state["session_id"], turn_id, patch)
    return {}


def reflect_bucket(state: InterviewState) -> dict:
    """응답 버킷 분류 이사 (F6.1) — reflect_emotion 과 같은 슬로우패스.

    이번 답변을 그 문항의 코드북(response_buckets) 중 하나로 분류해 턴에 남긴다.
    LLM 은 '어느 버킷'만 고른다 — 버킷별 N(분포)은 DB 실측(store.bucket_distribution)이 센다(계약 1).
    실패해도 인터뷰를 막지 않는다(best-effort): 버킷 없는 구가이드·LLMError 는 조용히 건너뛴다.
    """
    qid = state.get("answered_qid", "")
    utterance = state.get("utterance", "")
    turn_id = state.get("resp_turn_id", "")
    if not qid or not utterance or not turn_id:
        return {}
    questions = {q["id"]: q for q in state.get("guide", {}).get("questions", []) if q.get("id")}
    q = questions.get(qid)
    if not q:
        return {}
    buckets = q.get("response_buckets") or []
    if not buckets:
        return {}   # 구가이드 — 코드북이 없으면 분류 자체를 건너뛴다
    bucket_ids = {b.get("id") for b in buckets if b.get("id")}
    try:
        out, _ = get_llm().structured(
            BUCKET_CLASSIFY_SYSTEM,
            bucket_classify_user(q.get("text", ""), q.get("goal", ""), buckets, utterance),
            BucketAssignment, max_tokens=200,
        )
    except LLMError as e:
        log.warning("버킷 분류 실패 — 이번 턴은 건너뜀: %s", e)
        return {}
    # 환각·미지 id 는 캐치올로 폴백(F2.3.3) — 분류 실패로 턴을 비워두지 않는다
    bucket_id = out.bucket_id if out.bucket_id in bucket_ids else _catchall_id(buckets)
    store.update_turn(state["project_id"], state["session_id"], turn_id, {
        "bucket_id": bucket_id,
        "bucket_confidence": max(0.0, min(1.0, out.confidence)),
        "bucket_evidence": out.evidence,
    })
    return {}
