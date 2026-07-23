"""llm_client.rerank() 단위테스트 — httpx 를 monkeypatch, 네트워크 없이.

/v1/rerank 는 OpenAI SDK 에 없어 httpx 직접 호출(research._run_actor 관례)이라
가짜 httpx.post 를 주입해 (1) 파라미터 전달·점수 내림차순 정렬, (2) 빈 documents
단락, (3) 재시도 소진 후 LLMError 를 검증한다.
"""
from __future__ import annotations

import httpx
import pytest

from api.services.llm_client import LLMClient, LLMError


def _client():
    return LLMClient(api_key="k", model="m")


def test_rerank_returns_sorted_by_score_desc(monkeypatch):
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [
                {"index": 2, "relevance_score": 0.1},
                {"index": 0, "relevance_score": 0.9},
            ]}

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(httpx, "post", _fake_post)

    cli = _client()
    out = cli.rerank("q", ["a", "b", "c"], top_n=3)

    assert out == [(0, 0.9), (2, 0.1)]   # 점수 내림차순
    assert captured["url"] == f"{cli.base_url}/rerank"
    assert captured["headers"] == {"Authorization": f"Bearer {cli.rerank_api_key}"}
    assert captured["json"] == {
        "model": cli.rerank_model, "query": "q",
        "documents": ["a", "b", "c"], "top_n": 3,
    }
    assert captured["timeout"] == cli.timeout


def test_rerank_truncates_long_documents(monkeypatch):
    """장문은 max_doc_chars(기본 1200)로 잘라 보낸다 — 리랭커 타임아웃 방어(라이브 발견)."""
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [{"index": 0, "relevance_score": 0.5}]}

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(httpx, "post", _fake_post)
    _client().rerank("q", ["가" * 5000, "짧은 문서"])

    sent = captured["json"]["documents"]
    assert len(sent[0]) == 1200            # 5000자 → 1200자로 잘림
    assert sent[1] == "짧은 문서"           # 짧은 건 그대로


def test_rerank_empty_documents_skips_http_call(monkeypatch):
    calls = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: calls.append((a, k)))

    cli = _client()
    out = cli.rerank("q", [], top_n=3)

    assert out == []
    assert calls == []   # 호출 자체가 없어야 한다


def test_rerank_raises_llm_error_after_retries(monkeypatch):
    from api.services import llm_client

    monkeypatch.setattr(llm_client.time, "sleep", lambda *_: None)   # 백오프 빨리감기

    attempts = []

    def _boom(*a, **k):
        attempts.append(1)
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(httpx, "post", _boom)

    cli = _client()
    with pytest.raises(LLMError):
        cli.rerank("q", ["a"], top_n=3)

    assert len(attempts) == cli.max_retries   # max_retries 회 재시도 후 포기


def test_rerank_raises_llm_error_when_raise_for_status_fails(monkeypatch):
    from api.services import llm_client

    monkeypatch.setattr(llm_client.time, "sleep", lambda *_: None)

    class _Resp:
        def raise_for_status(self):
            raise httpx.HTTPStatusError("500", request=None, response=None)

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp())

    cli = _client()
    with pytest.raises(LLMError):
        cli.rerank("q", ["a"], top_n=3)


def test_rerank_raises_llm_error_on_missing_results_key(monkeypatch):
    """200 이지만 본문에 'results' 키가 없으면 KeyError 가 아니라 LLMError 로 변환된다
    (호출자의 except LLMError 코사인 폴백이 먹도록 — 본문 파싱을 try/except 로 감쌌다)."""
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": []}   # 'results' 키 없음

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp())

    cli = _client()
    with pytest.raises(LLMError):
        cli.rerank("q", ["a"], top_n=3)


def test_rerank_raises_llm_error_on_malformed_item(monkeypatch):
    """results 항목에 index/relevance_score 키가 빠져도 KeyError 가 아니라 LLMError 로."""
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [{"index": 0}]}   # relevance_score 없음

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp())

    cli = _client()
    with pytest.raises(LLMError):
        cli.rerank("q", ["a"], top_n=3)
