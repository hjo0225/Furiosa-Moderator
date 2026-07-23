"""LLM 타임아웃 — 인터뷰 턴은 빠른 기본(30s), 가이드 생성은 무거운 단발(180s).

세 축을 검증한다:
  1) config 가 LLM_TIMEOUT/LLM_GUIDE_TIMEOUT 를 env 에서 읽고 기본값을 지킨다.
  2) structured(timeout=) 가 _call 로 전달되고, 미지정 시 timeout 키 자체가 없다
     (SDK 에서 timeout=None 은 '무제한'이라 클라이언트 기본과 다르다).
  3) 가이드 엔드포인트가 llm_guide_timeout 을 structured 로 넘긴다(인터뷰 경로는 불변).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

import api.main as main
from api.config import get_settings
from api.routers import projects as pm
from api.schemas.models import GuideQuestion, InterviewGuide, Project
from api.services.llm_client import LLMClient


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    # env 를 건드리는 테스트가 lru_cache 를 오염시키지 않도록 앞뒤로 비운다.
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── 1) config env 배선 ────────────────────────────────────────────
def test_timeouts_env_wired(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT", "45")
    monkeypatch.setenv("LLM_GUIDE_TIMEOUT", "200")
    get_settings.cache_clear()
    s = get_settings()
    assert s.llm_timeout == 45.0
    assert s.llm_guide_timeout == 200.0


def test_timeouts_defaults(monkeypatch):
    monkeypatch.delenv("LLM_TIMEOUT", raising=False)
    monkeypatch.delenv("LLM_GUIDE_TIMEOUT", raising=False)
    get_settings.cache_clear()
    s = get_settings()
    assert s.llm_timeout == 30.0
    assert s.llm_guide_timeout == 180.0


# ── 2) structured 타임아웃 전달 ───────────────────────────────────
class _Tiny(BaseModel):
    x: int


class _FakeCompletions:
    def __init__(self, resp):
        self.resp = resp
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.resp


def _tool_resp(args_json):
    tc = SimpleNamespace(id="c1", function=SimpleNamespace(name="respond", arguments=args_json))
    msg = SimpleNamespace(content=None, tool_calls=[tc])
    return SimpleNamespace(
        choices=[SimpleNamespace(message=msg, finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )


def _client_with(resp):
    cli = LLMClient(api_key="k", model="m")
    fake = _FakeCompletions(resp)
    cli._cli = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return cli, fake


def test_structured_passes_timeout_when_given():
    cli, fake = _client_with(_tool_resp('{"x": 1}'))
    out, _ = cli.structured("sys", "usr", _Tiny, timeout=123)
    assert out.x == 1
    assert fake.kwargs["timeout"] == 123


def test_structured_omits_timeout_when_not_given():
    cli, fake = _client_with(_tool_resp('{"x": 1}'))
    cli.structured("sys", "usr", _Tiny)
    assert "timeout" not in fake.kwargs   # None 이면 키 자체를 넣지 않는다(SDK 의 '무제한' 회피)


# ── 3) 가이드 엔드포인트 배선 ─────────────────────────────────────
class _CaptureGuideLLM:
    def __init__(self):
        self.kw: dict = {}

    def structured(self, system, user, schema, **kw):
        self.kw = kw
        return InterviewGuide(
            goal="g", questions=[GuideQuestion(id="q1", text="?", goal="x")]
        ), None


def test_generate_guide_passes_guide_timeout(monkeypatch):
    llm = _CaptureGuideLLM()
    monkeypatch.setattr(pm, "get_llm", lambda: llm)
    monkeypatch.setattr(pm.store, "get_project",
                        lambda pid: Project(id=pid, topic="주제", target="20대"))
    monkeypatch.setattr(pm.store, "get_slot_summaries", lambda pid: {})
    monkeypatch.setattr(pm.store, "save_guide", lambda pid, g: g)
    monkeypatch.setattr(pm.store, "has_materials", lambda pid: False)   # 자료 없음 → 근거 검색 스킵
    resp = TestClient(main.app).post("/api/projects/p_1/guide", json={})
    assert resp.status_code == 200
    assert llm.kw["timeout"] == get_settings().llm_guide_timeout
