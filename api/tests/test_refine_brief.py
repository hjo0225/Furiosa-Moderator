"""브리프 정제 (C-1) — 프롬프트·엔드포인트. LLM 은 목킹, 없는 것 발명 금지 계약을 고정.

정제는 표현만 다듬고 내용을 지어내지 않는다(refine.py). 특히 **빈 입력 항목을 모델이
채워 보내도 서버가 되돌린다**는 계약을 여기서 검증한다.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from api.prompts.refine import REFINE_SYSTEM, refine_user
from api.schemas.models import BriefRefineOut, RefinedField


def test_system_forbids_inventing_content():
    assert "지어내지" in REFINE_SYSTEM        # 없는 것 발명 금지
    assert "빈 칸" in REFINE_SYSTEM or "빈 문자열" in REFINE_SYSTEM


def test_refine_user_lists_four_fields():
    prompt = refine_user("아침 거르는 이유", "", "신제품 기획", "")
    assert "조사 목적" in prompt and "타깃 대상" in prompt
    assert "아침 거르는 이유" in prompt
    assert "(비어 있음)" in prompt            # 빈 항목은 명시적으로 표시


def _fake_llm(monkeypatch, out: BriefRefineOut):
    class _LLM:
        def structured(self, system, user, schema, **kw):
            return out, None
    import api.routers.projects as mod
    monkeypatch.setattr(mod, "get_llm", lambda: _LLM())


def test_endpoint_returns_refined_fields(monkeypatch):
    out = BriefRefineOut(
        topic=RefinedField(text="20대 직장인이 아침 식사를 거르는 이유를 파악한다", note="목적을 한 문장으로"),
        target=RefinedField(text="수도권 25~34세 직장인", note="연령대 명확화"),
    )
    _fake_llm(monkeypatch, out)
    client = TestClient(app)
    r = client.post("/api/projects/refine-brief", json={
        "topic": "아침 거르는 이유", "target": "직장인", "motivation": "", "utilization": "",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["topic"]["text"].startswith("20대")
    assert data["target"]["note"] == "연령대 명확화"


def test_empty_input_field_stays_empty_even_if_model_fills_it(monkeypatch):
    # 모델이 빈 입력(motivation·utilization)을 지어내 채워도 서버가 되돌린다
    out = BriefRefineOut(
        topic=RefinedField(text="다듬은 목적"),
        motivation=RefinedField(text="AI가 지어낸 동기", note="지어냄"),
        utilization=RefinedField(text="AI가 지어낸 활용", note="지어냄"),
    )
    _fake_llm(monkeypatch, out)
    client = TestClient(app)
    r = client.post("/api/projects/refine-brief", json={
        "topic": "목적만 적음", "target": "", "motivation": "", "utilization": "",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["topic"]["text"] == "다듬은 목적"
    assert data["motivation"]["text"] == ""       # 빈 입력은 빈 채로 되돌려짐
    assert data["utilization"]["text"] == ""


def test_all_empty_input_is_400():
    client = TestClient(app)
    r = client.post("/api/projects/refine-brief", json={
        "topic": "", "target": "", "motivation": "", "utilization": "",
    })
    assert r.status_code == 400
