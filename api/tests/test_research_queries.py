"""브리프 → 슬롯별 검색어 (LLM monkeypatch)."""
from __future__ import annotations

from api.services import research
from api.services.llm_client import LLMError


def test_research_queries_maps_slots(monkeypatch):
    fake = research.ResearchQueries(slots=[
        research.SlotQuery(angle="현상", queries=["a", "b"]),
        research.SlotQuery(angle="원인", queries=["c", "d"]),
        research.SlotQuery(angle="활용", queries=["e", "f"]),
    ])

    class FakeLLM:
        def structured(self, system, user, schema, **kw):
            return fake, None

    monkeypatch.setattr(research, "get_llm", lambda: FakeLLM())
    d = research.research_queries("금주", "2030", "광고", "신제품")
    assert d["현상"] == ["a", "b"]
    assert d["활용"] == ["e", "f"]


def test_research_queries_falls_back_on_llm_error(monkeypatch):
    class FakeLLM:
        def structured(self, *a, **k):
            raise LLMError("boom")

    monkeypatch.setattr(research, "get_llm", lambda: FakeLLM())
    d = research.research_queries("금주", "2030", "광고", "신제품")
    assert set(d) == {"현상", "원인", "활용"}
    assert all(len(v) == 2 for v in d.values())        # 폴백도 슬롯당 2개


def test_research_queries_fills_missing_slot_from_fallback(monkeypatch):
    fake = research.ResearchQueries(slots=[
        research.SlotQuery(angle="현상", queries=["a", "b"]),
    ])  # 원인·활용 누락

    class FakeLLM:
        def structured(self, s, u, schema, **k):
            return fake, None

    monkeypatch.setattr(research, "get_llm", lambda: FakeLLM())
    d = research.research_queries("금주", "2030", "광고", "신제품")
    assert d["현상"] == ["a", "b"]              # LLM 값 유지
    assert len(d["원인"]) == 2 and len(d["활용"]) == 2   # 빈 슬롯은 폴백으로 채움
