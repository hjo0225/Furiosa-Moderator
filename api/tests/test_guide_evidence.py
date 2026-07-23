"""RAG-4 — 가이드 생성에 브리프 검색 근거(evidence) 주입.

프롬프트 레벨(주입/회귀) + _collect_evidence(dedup·cap·format·실패흡수·활용스킵) +
엔드포인트 배선(검색 근거가 실제 LLM user 프롬프트로 흘러가는지).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import api.briefing.pipeline as bp
import api.main as main
from api.prompts.guide import guide_user
from api.routers import projects as pm
from api.schemas.models import GuideQuestion, InterviewGuide, Project


# ── 프롬프트 레벨 ────────────────────────────────────────────────
def test_guide_user_injects_evidence():
    out = guide_user(topic="x", evidence="- 발췌1 (출처: a.pdf)")
    assert "[브리프 검색 근거]" in out
    assert "- 발췌1 (출처: a.pdf)" in out


def test_guide_user_no_evidence_regression():
    # 회귀 불변식: evidence 없음/빈 문자열은 바이트 동일 + 근거 블록 없음.
    without = guide_user("x", "y", "mat", "mot", "util")
    empty = guide_user("x", "y", "mat", "mot", "util", evidence="")
    assert without == empty
    assert "[브리프 검색 근거]" not in without
    assert "[브리프 검색 근거]" not in empty


# ── _collect_evidence ───────────────────────────────────────────
def test_collect_evidence_dedupes_caps_formats(monkeypatch):
    def fake(pid, query, k=3, *, angle=None, candidates=30):
        # 슬롯마다 공유 발췌 1개(중복) + 고유 4개.
        return [{"text": "공유발췌", "source": "dup.pdf", "score": 0.9}] + [
            {"text": f"{angle}{i}", "source": "src.pdf", "score": 0.5} for i in range(4)
        ]

    monkeypatch.setattr(bp, "search_chunks", fake)
    monkeypatch.setattr(pm.store, "has_materials", lambda pid: True)   # 자료 있음 → 근거 검색 진입
    p = Project(id="p1", topic="주제", target="20대", utilization="온보딩")
    out = pm._collect_evidence("p1", p)
    lines = out.splitlines()

    assert len(lines) == 9                          # cap: 1 + 12 고유 = 13 → 9
    assert out.count("공유발췌") == 1               # dedup: 3슬롯에 나와도 1줄
    assert "- 공유발췌 (출처: dup.pdf)" in out       # format
    assert "- 현상0 (출처: src.pdf)" in out


def test_collect_evidence_absorbs_search_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("rerank down")

    monkeypatch.setattr(bp, "search_chunks", boom)
    monkeypatch.setattr(pm.store, "has_materials", lambda pid: True)   # 자료 있음 → 근거 검색 진입
    p = Project(id="p1", topic="주제", target="20대", utilization="온보딩")
    assert pm._collect_evidence("p1", p) == ""      # 검색 실패는 흡수 → 빈 근거


def test_collect_evidence_skips_활용_when_utilization_empty(monkeypatch):
    calls: list[str | None] = []
    monkeypatch.setattr(
        bp, "search_chunks",
        lambda pid, q, k=3, *, angle=None, candidates=30: calls.append(angle) or [],
    )
    monkeypatch.setattr(pm.store, "has_materials", lambda pid: True)   # 자료 있음 → 근거 검색 진입
    p = Project(id="p1", topic="주제", target="20대")   # utilization=""
    pm._collect_evidence("p1", p)
    assert set(calls) == {"현상", "원인"}               # 활용 슬롯은 건너뜀


def test_collect_evidence_short_circuits_when_no_materials(monkeypatch):
    # 자료 풀이 비면 임베딩(search_chunks) 호출 없이 즉시 빈 근거 — 불필요 네트워크 방지(I-1).
    calls = []
    monkeypatch.setattr(bp, "search_chunks", lambda *a, **k: calls.append(1) or [])
    monkeypatch.setattr(pm.store, "has_materials", lambda pid: False)   # 자료 없음
    p = Project(id="p1", topic="주제", target="20대", utilization="온보딩")

    assert pm._collect_evidence("p1", p) == ""      # 근거 없이 빠진다
    assert calls == []                              # search_chunks 호출 자체가 없다


# ── 엔드포인트 배선 ─────────────────────────────────────────────
class _CaptureLLM:
    def __init__(self):
        self.user = ""

    def structured(self, system, user, schema, **kw):
        self.user = user
        return InterviewGuide(
            goal="g", questions=[GuideQuestion(id="q1", text="?", goal="x")]
        ), None


def test_generate_guide_injects_evidence(monkeypatch):
    llm = _CaptureLLM()
    monkeypatch.setattr(pm, "get_llm", lambda: llm)
    monkeypatch.setattr(
        pm.store, "get_project",
        lambda pid: Project(id=pid, topic="주제", target="20대", utilization="온보딩"),
    )
    monkeypatch.setattr(pm.store, "get_slot_summaries", lambda pid: {})  # 자료 요약 없음
    monkeypatch.setattr(pm.store, "save_guide", lambda pid, g: g)
    monkeypatch.setattr(pm.store, "has_materials", lambda pid: True)   # 자료 풀 있음 → 근거 검색 진입
    monkeypatch.setattr(
        bp, "search_chunks",
        lambda pid, q, k=3, *, angle=None, candidates=30: [
            {"text": "배민클럽은 구독", "source": "a.pdf", "score": 0.9}
        ],
    )
    resp = TestClient(main.app).post("/api/projects/p_1/guide", json={})
    assert resp.status_code == 200
    assert "[브리프 검색 근거]" in llm.user
    assert "배민클럽은 구독" in llm.user
    assert "출처: a.pdf" in llm.user
    assert "[참고 자료]" not in llm.user            # 슬롯 요약 없음 → 자료 블록 없음(회귀)
