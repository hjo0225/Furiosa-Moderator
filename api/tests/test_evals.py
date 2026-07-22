"""품질 Evals (F8) — 결정론·오프라인 측정 함수 검증.

LLM 을 태우지 않는 순수 규칙이라 CI 에서 그대로 돈다(NPU 미호출).
"""
from __future__ import annotations

from api.schemas.models import GuideQuestion, InterviewGuide, ResponseBucket
from api.services import evals


# --- is_leading_question (F2.3.6) ------------------------------------------

def test_prd_bad_example_is_leading():
    # PRD 나쁜 예: 불편을 전제하고 동의를 끌어내는 확인 어미('…죠?').
    leading, reason = evals.is_leading_question("배송이 느려서 불편하셨죠?")
    assert leading is True
    assert reason  # 사유 문자열이 비어있지 않음


def test_prd_neutral_examples_not_leading():
    # PRD 중립 예 — 열린 질문이라 걸리면 안 된다.
    assert evals.is_leading_question("그때 어떠셨나요?")[0] is False
    assert evals.is_leading_question("배송 과정은 어떠셨나요?")[0] is False


def test_double_barreled_is_leading():
    # 접속사로 두 질문을 묶음.
    assert evals.is_leading_question("배송 속도는 어땠고 그리고 포장은 어떠셨나요?")[0] is True
    # 물음표 2개.
    assert evals.is_leading_question("배송은 어떠셨나요? 포장은요?")[0] is True


def test_plain_open_question_not_leading():
    assert evals.is_leading_question("평소 배송에 대해 어떻게 생각하세요?")[0] is False


def test_valence_presupposition_is_leading():
    # '얼마나 <감정어>' — 감정을 단정하고 정도만 묻는 유도.
    assert evals.is_leading_question("얼마나 불편하셨나요?")[0] is True
    assert evals.is_leading_question("얼마나 만족스러우셨나요?")[0] is True


def test_empty_question_not_leading():
    assert evals.is_leading_question("")[0] is False
    assert evals.is_leading_question("   ")[0] is False


# --- bucket_overlap_warnings (F2.3.1) --------------------------------------

def test_identical_labels_warn():
    buckets = [
        ResponseBucket(label="배송 지연", definition="물건이 늦게 옴"),
        ResponseBucket(label="배송지연", definition="예정보다 늦게 도착"),  # 정규화하면 동일
        ResponseBucket(label="기타", is_catchall=True),
    ]
    warns = evals.bucket_overlap_warnings(buckets)
    assert len(warns) >= 1


def test_token_overlap_warn():
    # 라벨은 다르지만 라벨+정의 토큰이 크게 겹침 (Jaccard >= 0.6).
    buckets = [
        ResponseBucket(label="가격 불만", definition="가격이 비싸서 불만이다"),
        ResponseBucket(label="요금 불만", definition="가격이 비싸서 불만이다"),
    ]
    assert len(evals.bucket_overlap_warnings(buckets)) >= 1


def test_distinct_buckets_clean():
    buckets = [
        ResponseBucket(label="직접 조리", definition="집에서 밥과 반찬을 차려 먹음"),
        ResponseBucket(label="배달 주문", definition="앱으로 음식을 시켜 먹음"),
        ResponseBucket(label="외식", definition="식당에 가서 사 먹음"),
        ResponseBucket(label="기타", is_catchall=True),
    ]
    assert evals.bucket_overlap_warnings(buckets) == []


def test_catchall_excluded_from_overlap():
    # 두 캐치올 라벨이 같아도(둘 다 '기타') 경고하지 않는다 — 캐치올은 겹침 판정 제외.
    buckets = [
        ResponseBucket(label="A", definition="가"),
        ResponseBucket(label="기타", is_catchall=True),
        ResponseBucket(label="기타", is_catchall=True),
    ]
    assert evals.bucket_overlap_warnings(buckets) == []


def test_bucket_overlap_accepts_dicts():
    buckets = [
        {"label": "배송 지연", "definition": "늦게 옴"},
        {"label": "배송지연", "definition": "늦게 도착"},
    ]
    assert len(evals.bucket_overlap_warnings(buckets)) >= 1


# --- leak_overlap (F1.5.9) --------------------------------------------------

def test_leak_high_when_quoting_source():
    sources = ["이 서비스는 무료 반품을 최대 30일까지 보장한다고 안내합니다."]
    utterance = "이 서비스는 무료 반품을 최대 30일까지 보장한다고 안내합니다."
    assert evals.leak_overlap(utterance, sources) > 0.5


def test_leak_low_when_unrelated():
    sources = ["이 서비스는 무료 반품을 최대 30일까지 보장한다고 안내합니다."]
    utterance = "저는 어제 친구랑 영화를 보고 저녁으로 국수를 먹었어요."
    assert evals.leak_overlap(utterance, sources) < 0.2


def test_leak_empty_inputs_zero():
    assert evals.leak_overlap("", ["출처 문장"]) == 0.0
    assert evals.leak_overlap("발화", []) == 0.0
    assert evals.leak_overlap("", []) == 0.0


# --- guide_quality_report --------------------------------------------------

def _mixed_guide() -> InterviewGuide:
    # q1: 유도(확인 어미) + 겹치는 버킷 쌍. q2: 중립 + 서로 다른 버킷.
    q1 = GuideQuestion(
        id="q1",
        text="배송이 느려서 불편하셨죠?",
        response_buckets=[
            ResponseBucket(id="q1_b1", label="배송 지연", definition="늦게 옴"),
            ResponseBucket(id="q1_b2", label="배송지연", definition="예정보다 늦음"),
            ResponseBucket(id="q1_other", label="기타", is_catchall=True),
        ],
    )
    q2 = GuideQuestion(
        id="q2",
        text="배송 과정은 어떠셨나요?",
        response_buckets=[
            ResponseBucket(id="q2_b1", label="포장 상태", definition="박스 손상 여부"),
            ResponseBucket(id="q2_b2", label="배송 속도", definition="도착까지 걸린 시간"),
            ResponseBucket(id="q2_other", label="기타", is_catchall=True),
        ],
    )
    return InterviewGuide(project_id="p1", goal="배송 경험", questions=[q1, q2])


def test_report_mixed_guide():
    report = evals.guide_quality_report(_mixed_guide())
    assert report["leading"] == ["q1"]
    assert report["n_leading"] == 1
    assert report["n_questions"] == 2
    assert "q1" in report["bucket_warnings"]
    assert "q2" not in report["bucket_warnings"]
    assert report["mece_ok"] is False


def test_report_clean_guide():
    q = GuideQuestion(
        id="q1",
        text="평소 아침은 어떻게 해결하세요?",
        response_buckets=[
            ResponseBucket(id="q1_b1", label="직접 조리", definition="집에서 차려 먹음"),
            ResponseBucket(id="q1_b2", label="편의점", definition="편의점 음식으로 해결"),
            ResponseBucket(id="q1_other", label="기타", is_catchall=True),
        ],
    )
    report = evals.guide_quality_report(InterviewGuide(questions=[q]))
    assert report["leading"] == []
    assert report["n_leading"] == 0
    assert report["mece_ok"] is True


def test_report_accepts_dict_guide():
    guide = {
        "questions": [
            {"id": "q1", "text": "얼마나 불편하셨나요?", "response_buckets": []},
        ]
    }
    report = evals.guide_quality_report(guide)
    assert report["leading"] == ["q1"]
    assert report["mece_ok"] is True  # 버킷 없으면 겹침 경고도 없음
