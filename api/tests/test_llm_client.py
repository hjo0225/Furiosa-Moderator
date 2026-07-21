"""llm_client 신규 메서드(chat/embed) 단위테스트 — 네트워크 없이.

가짜 OpenAI 클라이언트를 주입해 (1) 파라미터 전달, (2) tool_calls 파싱,
(3) 임베딩 순서 보존을 검증한다. 기존 text()/structured() 는 이 티켓에서
건드리지 않았으므로 여기서 재검증하지 않는다.
"""
from __future__ import annotations

from types import SimpleNamespace

from api.services.llm_client import LLMClient


# --- 가짜 응답 조립 -----------------------------------------------------------

def _chat_resp(content=None, tool_calls=None, finish="stop"):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=msg, finish_reason=finish)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


def _tc(name, args_json):
    return SimpleNamespace(id="call_1", function=SimpleNamespace(name=name, arguments=args_json))


class _FakeCompletions:
    def __init__(self, resp):
        self.resp = resp
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.resp


def _client_with(resp):
    cli = LLMClient(api_key="k", model="m")
    fake = _FakeCompletions(resp)
    cli._cli = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return cli, fake


# --- chat() -------------------------------------------------------------------

def test_chat_passes_tools_and_parses_calls():
    tools = [{"type": "function", "function": {"name": "brief", "parameters": {}}}]
    cli, fake = _client_with(_chat_resp(tool_calls=[_tc("brief", '{"term": "배민클럽"}')], finish="tool_calls"))
    out, usage = cli.chat([{"role": "user", "content": "hi"}], tools=tools)
    assert fake.kwargs["tools"] == tools
    assert fake.kwargs["tool_choice"] == "auto"          # 자율 선택이 기본값
    assert fake.kwargs["temperature"] == 0.3             # tools 있으면 구조화 온도
    assert out.tool_calls[0].name == "brief"
    assert out.tool_calls[0].arguments == {"term": "배민클럽"}
    assert out.finish_reason == "tool_calls"
    assert usage.tokens_in == 10 and usage.tokens_out == 5


def test_chat_without_tools_returns_content():
    cli, fake = _client_with(_chat_resp(content="안녕하세요 "))
    out, _ = cli.chat([{"role": "user", "content": "hi"}])
    assert out.content == "안녕하세요"
    assert out.tool_calls == []
    assert "tools" not in fake.kwargs and "tool_choice" not in fake.kwargs
    assert fake.kwargs["temperature"] == 0.6             # tools 없으면 텍스트 온도


def test_chat_keeps_raw_on_broken_tool_args():
    cli, _ = _client_with(_chat_resp(tool_calls=[_tc("pace", "{broken")], finish="tool_calls"))
    out, _ = cli.chat([{"role": "user", "content": "hi"}], tools=[{"type": "function", "function": {"name": "pace"}}])
    assert out.tool_calls[0].arguments is None           # 파싱 실패는 None
    assert out.tool_calls[0].raw_arguments == "{broken"  # 원문 보존 — 실측이 관찰


# --- embed() ------------------------------------------------------------------

class _FakeEmbeddings:
    def __init__(self, resp):
        self.resp = resp
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.resp


def test_embed_preserves_order_and_forwards_params():
    cli = LLMClient(api_key="k", model="m")
    resp = SimpleNamespace(
        data=[SimpleNamespace(index=1, embedding=[0.2]), SimpleNamespace(index=0, embedding=[0.1])],
        usage=SimpleNamespace(prompt_tokens=7),
    )
    fake = _FakeEmbeddings(resp)
    cli._embed_cli = SimpleNamespace(embeddings=fake)
    vecs, usage = cli.embed(["a", "b"], dimensions=1024)
    assert vecs == [[0.1], [0.2]]                        # index 로 재정렬
    assert fake.kwargs["input"] == ["a", "b"]
    assert fake.kwargs["model"] == cli.embed_model
    assert fake.kwargs["dimensions"] == 1024
    assert usage.tokens_in == 7 and usage.tokens_out == 0


def test_embed_omits_dimensions_when_none():
    cli = LLMClient(api_key="k", model="m")
    resp = SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[0.5])], usage=None)
    fake = _FakeEmbeddings(resp)
    cli._embed_cli = SimpleNamespace(embeddings=fake)
    vecs, usage = cli.embed(["x"])
    assert vecs == [[0.5]]
    assert "dimensions" not in fake.kwargs               # 미지정 시 서버 기본 차원
    assert usage.tokens_in == 0
