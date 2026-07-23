"""응답 버킷 — 코드북 귀납 생성·분류 프롬프트·모델 (스펙 C).

버킷은 이제 가이드가 아니라 인사이트가 소유한다: 인터뷰가 끝난 뒤 실제 전사에서 코드북을
만들고(CODEBOOK_SYSTEM), (세션·문항)당 1회 분류한다(BUCKET_CLASSIFY_SYSTEM). 인터뷰 루프의
reflect_bucket 노드는 제거됐다(코드북이 측정 전에 없으므로 분류할 대상이 없다).

분포 카운트(store.bucket_distribution)는 sentiment_counts 처럼 라이브 DB 가 필요해
여기서는 형태(shape) 스모크만 확인한다.
"""
from __future__ import annotations

from api.prompts.insight import (
    BUCKET_CLASSIFY_SYSTEM,
    CODEBOOK_SYSTEM,
    bucket_classify_user,
    codebook_user,
)
from api.schemas.models import BucketAssignment, ResponseBucket
from api.services import store


# --- 코드북 귀납 생성 프롬프트 -----------------------------------------------

def test_codebook_system_demands_inductive_from_answers():
    assert "귀납" in CODEBOOK_SYSTEM
    assert "실제 답변에 나타난 것만" in CODEBOOK_SYSTEM   # 없는 카테고리 미리 만들지 않기
    assert "서버가 셉니다" in CODEBOOK_SYSTEM             # 개수는 LLM 이 세지 않는다(계약 1)


def test_codebook_user_lists_answers_and_question():
    prompt = codebook_user(
        "가장 최근 아침 식사를 떠올려 들려주세요.", "아침 식사 패턴",
        ["시리얼 부어 먹었어요", "김밥 사 먹었어요", "그냥 걸렀어요"],
    )
    assert "시리얼 부어 먹었어요" in prompt and "김밥 사 먹었어요" in prompt
    assert "총 3개" in prompt


# --- 분류 프롬프트 · 모델 ----------------------------------------------------

def test_system_has_pick_one_constraint():
    assert "하나만 고르" in BUCKET_CLASSIFY_SYSTEM          # 정확히 하나만
    assert "서버가 셉니다" in BUCKET_CLASSIFY_SYSTEM         # 개수는 LLM 이 세지 않는다(계약 1)


def test_classify_user_lists_bucket_ids_and_answer():
    buckets = [
        ResponseBucket(id="q1_b1", label="직접 조리", definition="집에서 차려 먹음").model_dump(),
        ResponseBucket(id="q1_b2", label="간편식", definition="시리얼·대용식").model_dump(),
        ResponseBucket(id="q1_other", label="기타", is_catchall=True).model_dump(),
    ]
    prompt = bucket_classify_user("평소 아침은?", "아침 식사 패턴", buckets, "시리얼 먹어요")
    assert "q1_b1" in prompt and "q1_b2" in prompt and "q1_other" in prompt
    assert "시리얼 먹어요" in prompt
    assert "기타/캐치올" in prompt                           # 캐치올 표식 노출


def test_bucket_assignment_roundtrips():
    a = BucketAssignment(bucket_id="q1_b2", confidence=0.8, evidence="시리얼")
    back = BucketAssignment.model_validate(a.model_dump())
    assert back.bucket_id == "q1_b2" and back.confidence == 0.8 and back.evidence == "시리얼"
    # 기본값 — confidence/evidence 는 선택
    d = BucketAssignment(bucket_id="q1_b1")
    assert d.confidence == 0.0 and d.evidence == ""


# --- 분포 실측 (store.bucket_distribution) -------------------------------------

def test_bucket_distribution_is_callable_smoke():
    # 실제 카운트는 라이브 Postgres 가 필요하다(sentiment_counts 와 동일).
    assert callable(store.bucket_distribution)
