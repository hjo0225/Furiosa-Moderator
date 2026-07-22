"""응답 버킷 모델 · 정규화 (2A)."""
from __future__ import annotations

from api.prompts.guide import GUIDE_SYSTEM
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
