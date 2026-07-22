"""슬롯 요약·가이드 주입 문자열 (LLM monkeypatch / 순수 함수)."""
from __future__ import annotations

from api.services import material as mat


def test_compose_skips_empty_slots():
    out = mat.compose_guide_material({"현상": "현상요약", "원인": "", "활용": "활용요약"})
    assert "현상요약" in out and "활용요약" in out
    assert "원인" not in out                       # 빈 슬롯 생략
    assert out.index("현상") < out.index("활용")    # 슬롯 순서 유지


def test_compose_all_empty_returns_blank():
    assert mat.compose_guide_material({}) == ""


def test_summarize_slot_empty_returns_blank():
    assert mat.summarize_slot(["  ", ""]) == ""


def test_summarize_slot_calls_llm(monkeypatch):
    class FakeLLM:
        def text(self, system, user, **kw):
            return ("요약결과", None)

    monkeypatch.setattr("api.services.llm_client.get_llm", lambda: FakeLLM())
    assert mat.summarize_slot(["원문1", "원문2"]) == "요약결과"


def test_refresh_project_survives_index_failure(monkeypatch):
    """임베딩 일시 장애로 index_project 가 터져도 refresh_project 는 전파하지 않고
    요약 루프까지 마쳐야 한다(자료는 이미 저장됨 · RAG 는 다음 refresh 로 따라잡음)."""
    from api.briefing import pipeline

    saved = {}
    monkeypatch.setattr(pipeline, "index_project", lambda pid: (_ for _ in ()).throw(RuntimeError("embed down")))
    monkeypatch.setattr("api.services.store.list_materials", lambda pid: [])
    monkeypatch.setattr("api.services.store.save_slot_summary", lambda pid, angle, summary: saved.setdefault(angle, summary))
    pipeline.refresh_project("p_1")            # must NOT raise
    assert set(saved) == {"현상", "원인", "활용"}   # summary loop still ran (empty slots -> "")
