"""가이드 생성이 슬롯 요약을 주입하는지 / 자료 없으면 회귀 (LLM/store monkeypatch)."""
from __future__ import annotations

from fastapi.testclient import TestClient

import api.main as main
from api.routers import projects as pm
from api.schemas.models import GuideQuestion, InterviewGuide, Project


class _CaptureLLM:
    def __init__(self):
        self.user = ""

    def structured(self, system, user, schema, **kw):
        self.user = user
        return InterviewGuide(goal="g", questions=[GuideQuestion(id="q1", text="?", goal="x")]), None


def _wire(monkeypatch, summaries):
    llm = _CaptureLLM()
    monkeypatch.setattr(pm, "get_llm", lambda: llm)
    monkeypatch.setattr(pm.store, "get_project", lambda pid: Project(id=pid, topic="주제"))
    monkeypatch.setattr(pm.store, "get_slot_summaries", lambda pid: summaries)
    monkeypatch.setattr(pm.store, "save_guide", lambda pid, g: g)
    monkeypatch.setattr(pm.store, "has_materials", lambda pid: False)  # 자료 없음 → 근거 검색 스킵(I-1)
    return llm


def test_generate_guide_injects_slot_summaries(monkeypatch):
    llm = _wire(monkeypatch, {"현상": "현상요약입니다"})
    resp = TestClient(main.app).post("/api/projects/p_1/guide", json={})
    assert resp.status_code == 200
    assert "현상요약입니다" in llm.user
    assert "[참고 자료]" in llm.user


def test_generate_guide_no_materials_no_block(monkeypatch):
    llm = _wire(monkeypatch, {})
    resp = TestClient(main.app).post("/api/projects/p_1/guide", json={})
    assert resp.status_code == 200
    assert "[참고 자료]" not in llm.user        # 회귀: 자료 0개면 블록 없음
