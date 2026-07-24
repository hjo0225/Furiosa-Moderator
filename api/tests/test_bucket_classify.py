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


def test_codebook_user_caps_sample_and_answer_length():
    """답변이 많아도 프롬프트가 같이 커지지 않는다 — 전수를 넣었더니 모델이 답변마다
    버킷을 하나씩 뽑아 4096 토큰 상한에서도 잘렸다(라이브 34건, q3 은 아예 실패).
    표본은 앞에서 자르지 않고 균등 간격으로 훑어 전체 스펙트럼을 남긴다."""
    answers = [f"답변{i}번 " + "가" * 500 for i in range(40)]
    prompt = codebook_user("문항", "목표", answers)

    assert "총 40개 중 24개 표본" in prompt        # 잘랐다는 사실을 프롬프트가 밝힌다
    assert prompt.count("\n- ") == 24              # 상한대로 24개만
    assert "가" * 300 not in prompt                # 답변 하나가 200자로 잘렸다
    # 균등 간격(step=40/24) 이라 첫 답변과 거의 마지막 답변이 함께 들어간다 —
    # 앞에서 24개를 자르면 먼저 응답한 사람 쪽으로 코드북이 쏠린다.
    assert "답변0번" in prompt
    assert "답변38번" in prompt


def test_codebook_system_caps_bucket_count():
    assert "최대 6개" in CODEBOOK_SYSTEM
    assert "답변 하나마다 버킷을 만들지 마세요" in CODEBOOK_SYSTEM


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
