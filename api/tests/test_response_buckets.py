"""응답 버킷 모델 · 정규화 (2A)."""
from __future__ import annotations

from api.prompts.guide import GUIDE_SYSTEM
from api.routers.projects import _normalize_buckets
from api.schemas.models import GuideQuestion, InterviewGuide, ResponseBucket


def test_bucket_roundtrips_inside_question():
    q = GuideQuestion(
        id="q1", text="평소 아침은 어떻게 해결하세요?", goal="아침 식사 패턴",
        response_buckets=[
            ResponseBucket(id="q1_b1", label="직접 조리", definition="집에서 밥·반찬을 차려 먹음"),
            ResponseBucket(id="q1_other", label="기타", is_catchall=True),
        ],
    )
    dumped = q.model_dump()
    assert dumped["response_buckets"][0]["label"] == "직접 조리"
    assert dumped["response_buckets"][1]["is_catchall"] is True
    # 가이드 전체 라운드트립
    g = InterviewGuide(questions=[q])
    back = InterviewGuide.model_validate(g.model_dump())
    assert back.questions[0].response_buckets[0].definition == "집에서 밥·반찬을 차려 먹음"


def test_bucket_defaults_empty():
    q = GuideQuestion(id="q1", text="t")
    assert q.response_buckets == []


def test_guide_system_has_bucket_rules():
    assert "response_buckets" in GUIDE_SYSTEM
    assert "definition" in GUIDE_SYSTEM
    assert "상호배타" in GUIDE_SYSTEM        # MECE
    assert "is_catchall" in GUIDE_SYSTEM
    assert "is_negative_case" in GUIDE_SYSTEM


def test_normalize_adds_catchall_and_ids():
    q = GuideQuestion(id="q2", text="t", response_buckets=[
        ResponseBucket(label="A", definition="a"),
        ResponseBucket(label="B", definition="b"),
    ])
    _normalize_buckets(q)
    ids = [b.id for b in q.response_buckets]
    assert ids[:2] == ["q2_b1", "q2_b2"]        # id 결정론 채움
    assert q.response_buckets[-1].is_catchall    # 캐치올 자동 추가
    assert q.response_buckets[-1].id == "q2_other"


def test_normalize_keeps_existing_catchall():
    q = GuideQuestion(id="q3", text="t", response_buckets=[
        ResponseBucket(label="A", definition="a"),
        ResponseBucket(label="기타", is_catchall=True),
    ])
    _normalize_buckets(q)
    assert sum(1 for b in q.response_buckets if b.is_catchall) == 1  # 중복 추가 안 함


def test_normalize_empty_noop():
    q = GuideQuestion(id="q4", text="t")
    _normalize_buckets(q)
    assert q.response_buckets == []   # 버킷 없으면 강제로 만들지 않음


def test_normalize_promotes_existing_gita_to_catchall():
    # LLM 이 캐치올 표시 없이 '기타' 를 만든 경우 중복 추가 대신 승격
    q = GuideQuestion(id="q5", text="t", response_buckets=[
        ResponseBucket(label="A", definition="a"),
        ResponseBucket(label="기타", definition=""),
    ])
    _normalize_buckets(q)
    labels = [b.label for b in q.response_buckets]
    assert labels.count("기타") == 1              # 중복 '기타' 없음
    assert q.response_buckets[-1].is_catchall     # 기존 기타가 캐치올로 승격됨
