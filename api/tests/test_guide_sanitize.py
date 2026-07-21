"""가이드 생성 후 서버 보정 — 모델이 goal 을 text 에 이어 붙여 보내는 사고를 결정론으로 분리.

Qwen3 가 "질문? 이 질문으로 알아내려는 것: …" 형태로 text 한 필드에 몰아넣고
goal 을 비워 보낸 실사고. goal 에 default("") 가 있어 스키마 검증은 통과하므로
order/id 확정과 같은 계열의 서버 보정으로 잡는다.
"""
from __future__ import annotations

from api.prompts.guide import GUIDE_SYSTEM
from api.routers.projects import _split_goal_from_text
from api.schemas.models import GuideQuestion


def test_moves_embedded_goal_to_goal_field():
    q = GuideQuestion(
        id="q1",
        text="평소 아침은 어떻게 해결하세요? 이 질문으로 알아내려는 것: 아침 식사 패턴 파악",
    )
    _split_goal_from_text(q)
    assert q.text == "평소 아침은 어떻게 해결하세요?"
    assert q.goal == "아침 식사 패턴 파악"


def test_keeps_existing_goal_but_still_cleans_text():
    q = GuideQuestion(
        id="q1", text="질문? 이 질문으로 알아내려는 것: 새 목표", goal="원래 목표"
    )
    _split_goal_from_text(q)
    assert q.text == "질문?"
    assert q.goal == "원래 목표"  # 모델이 채운 goal 이 있으면 덮어쓰지 않는다


def test_no_marker_untouched():
    q = GuideQuestion(id="q1", text="평소 아침은 어떻게 해결하세요?", goal="패턴")
    _split_goal_from_text(q)
    assert q.text == "평소 아침은 어떻게 해결하세요?"
    assert q.goal == "패턴"


def test_guide_system_locks_field_separation_rules():
    # 프롬프트 회귀 방지 — 규칙 문구가 빠지면 사고가 재발한다.
    assert "딱 1문장" in GUIDE_SYSTEM
    assert "goal 필드에만" in GUIDE_SYSTEM
    assert "물음표(?)는 문항당 1개만" in GUIDE_SYSTEM


def test_generation_schema_requires_goal():
    # LLM 에 보내는 스키마에서 goal 이 required 여야 생략 시 자가교정 재시도가 발동한다.
    from api.routers.projects import _GenGuide

    schema = _GenGuide.model_json_schema()
    question_def = schema["$defs"]["_GenQuestion"]
    assert "goal" in question_def["required"]
