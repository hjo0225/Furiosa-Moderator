# TICKET-0 — 기반 공사 + Qwen3 도구선택 실측 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LangGraph 도입 전 토대(llm_client `chat(tools=)`·`embed()`, langgraph 의존성, pgvector)를 깔고, 최대 리스크인 **Qwen3 자율 tool choice를 실측**해 게이트를 통과/폴백 판정한다.

**Architecture:** 기존 `LLMClient`(OpenAI 호환, Furiosa RNGD)에 메서드를 **추가만** 한다 — `text()`/`stream_text()`/`structured()`는 불변(Qwen3 튜닝 보존). pgvector는 `init_schema()`에 멱등·비치명으로 얹는다. 실측은 새 `chat()`을 그대로 사용하는 독립 스크립트로, TICKET-5의 도구 4종 스키마를 후보로 쓴다.

**Tech Stack:** Python 3.11 · FastAPI · openai SDK 1.59 (OpenAI 호환 → Furiosa) · langgraph 1.x · langgraph-checkpoint-postgres 2.x · psycopg3 · SQLAlchemy 2 + pg8000 (기존 유지) · pytest

**브랜치:** `feat/langgraph-ticket-0` (main 기준, 생성 완료)

## Global Constraints (TICKETS.md 전역 불변식 중 TICKET-0 해당분)

- `llm_client`의 **기존 메서드 불변** — Qwen3 튜닝(enable_thinking=False, 온도 0.6/0.3, truncation 가드, 재시도 백오프) 보존. **추가만** 한다.
- NPU 순수성 — LLM·임베딩 전부 Furiosa 엔드포인트 (`https://endpoint.access.furiosa.dev/v1`).
- 임베딩은 같은 base_url의 `/v1/embeddings`, 키만 `EMBED_API_KEY` (근거: `check_npu_endpoint.sh`).
- 온도 정책 유지: tools 있는 호출은 `_TEMP_STRUCTURED`(0.3), 없으면 `_TEMP_TEXT`(0.6)를 기본값으로.
- DB 접속 방식 불변(pg8000 + Cloud SQL Connector). psycopg3는 **langgraph 체크포인터 전용**으로 설치만(연결은 TICKET-1).
- 마이그레이션 도구 없음 정책 유지 — DDL은 `init_schema()`의 멱등 실행.
- 실측 게이트 기준(사전 고정, §8): **도구 시나리오 정확도 ≥ 80% · 무도구 시나리오 오발동률 ≤ 20% · tool_calls 인자 JSON 유효율 100%**. 하나라도 미달이면 폴백(도구 선택만 구조화 출력 강제)으로 방향 확정.

**라이브 검증 전제:** `LLM_API_KEY`/`EMBED_API_KEY`(Task 5·6, Task 2 라이브 확인), DB env(`DATABASE_URL` 또는 `INSTANCE_CONNECTION_NAME`+`DB_*`)(Task 4 검증)가 셸에 있어야 한다. 키 값은 `check_npu_endpoint.sh`에 있다.
⚠️ 보안 메모(범위 외, 사용자 판단): `check_npu_endpoint.sh`에 실키가 커밋되어 있다 — 로테이션 + `.env` 이동 권장.

---

### Task 1: `chat(tools=)` — 범용 chat 메서드 (tool-loop 재료)

**Files:**
- Modify: `api/services/llm_client.py` (dataclass 2개 + 메서드 1개 추가)
- Test: `api/tests/test_llm_client.py` (신규)

**Interfaces:**
- Consumes: 기존 `LLMClient._call()`(재시도 래퍼), `_extra()`(thinking off), `_TEMP_*` 상수 — 전부 불변.
- Produces (Task 5와 TICKET-1·5가 사용):
  - `ToolCall(id: str, name: str, arguments: dict | None, raw_arguments: str)` — JSON 파싱 실패 시 `arguments=None`, 원문은 `raw_arguments`에 보존(실측이 유효율을 측정해야 하므로 삼키지 않는다)
  - `ChatOut(content: str, tool_calls: list[ToolCall], finish_reason: str)`
  - `LLMClient.chat(messages: list[dict], *, tools: list[dict] | None = None, tool_choice: str | dict | None = None, max_tokens: int = 512, temperature: float | None = None, model: str | None = None) -> tuple[ChatOut, Usage]`

- [ ] **Step 1: 실패하는 테스트 작성** — `api/tests/test_llm_client.py` 생성:

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest api/tests/test_llm_client.py -v`
Expected: FAIL — `ImportError`/`AttributeError: 'LLMClient' object has no attribute 'chat'`

- [ ] **Step 3: 구현** — `api/services/llm_client.py`의 `Usage` dataclass 아래에 추가:

```python
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict | None   # JSON 파싱 실패 시 None — raw_arguments 로 관찰
    raw_arguments: str


@dataclass
class ChatOut:
    content: str
    tool_calls: list[ToolCall]
    finish_reason: str
```

그리고 `LLMClient` 클래스의 `# --- 구조화 출력 ---` 섹션 앞에 메서드 추가:

```python
    # --- 범용 chat (tool-loop 재료) --------------------------------------------

    def chat(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        max_tokens: int = 512,
        temperature: float | None = None,
        model: str | None = None,
    ) -> tuple[ChatOut, Usage]:
        """messages 를 그대로 넘기는 범용 호출 — LangGraph tool-loop 용.

        tools 가 있으면 tool_choice 기본 "auto"(자율 선택 — TICKET-0 실측 대상),
        온도는 구조화 값(0.3). 기존 text()/structured() 는 불변.
        """
        m = model or self.model
        if temperature is None:
            temperature = _TEMP_STRUCTURED if tools else _TEMP_TEXT
        kwargs: dict = dict(
            model=m, max_tokens=max_tokens, temperature=temperature,
            messages=messages, **self._extra(),
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"
        resp = self._call(**kwargs)
        choice = resp.choices[0]
        calls: list[ToolCall] = []
        for c in choice.message.tool_calls or []:
            raw = c.function.arguments or ""
            try:
                parsed = json.loads(raw) if raw else {}
            except ValueError:
                parsed = None
            calls.append(ToolCall(id=c.id, name=c.function.name, arguments=parsed, raw_arguments=raw))
        u = resp.usage
        return (
            ChatOut(
                content=(choice.message.content or "").strip(),
                tool_calls=calls,
                finish_reason=choice.finish_reason or "",
            ),
            Usage(m, u.prompt_tokens if u else 0, u.completion_tokens if u else 0),
        )
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest api/tests/test_llm_client.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 기존 테스트 회귀 확인**

Run: `python -m pytest api/tests -q`
Expected: 전부 PASS (기존 메서드 불변 검증)

- [ ] **Step 6: Commit**

```bash
git add api/services/llm_client.py api/tests/test_llm_client.py
git commit -m "feat(llm): 범용 chat(tools=) 추가 — tool-loop 재료 (TICKET-0)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `embed()` — Furiosa 임베딩 호출

**Files:**
- Modify: `api/services/llm_client.py` (`__init__` 3줄 + 클라이언트 1개 + 메서드 1개)
- Test: `api/tests/test_llm_client.py` (테스트 2개 추가)

**Interfaces:**
- Consumes: `Settings.embed_model`("furiosa-ai/Qwen3-Embedding-8B") · `Settings.embed_api_key` — config.py에 이미 존재. base_url은 LLM과 동일.
- Produces (TICKET-5 `api/services/embeddings.py`가 사용):
  - `LLMClient.embed(texts: list[str], *, dimensions: int | None = None, model: str | None = None) -> tuple[list[list[float]], Usage]` — 반환 벡터는 입력 순서 보존. `dimensions`는 §11 MRL 1024 결정용 — 서버 미지원이면 `LLMError`로 드러난다(폴백은 TICKET-5에서).

- [ ] **Step 1: 실패하는 테스트 추가** — `api/tests/test_llm_client.py` 끝에:

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest api/tests/test_llm_client.py -v -k embed`
Expected: FAIL — `AttributeError: 'LLMClient' object has no attribute 'embed'`(또는 `embed_model`)

- [ ] **Step 3: 구현** — `LLMClient.__init__` 끝에 3줄 추가:

```python
        self.embed_model = s.embed_model
        self.embed_api_key = (s.embed_api_key or "").lstrip("﻿").strip()
        self._embed_cli = None
```

`_extra()` 아래에 임베딩 클라이언트 + 메서드 추가 (재시도 루프는 `_call`과 같은 정책을 임베딩 대상으로 반복 — `_call` 내부를 건드리지 않기 위한 의도된 중복):

```python
    def _embed_client(self):
        if self._embed_cli is None:
            from openai import OpenAI

            self._embed_cli = OpenAI(
                api_key=self.embed_api_key or "unused",
                base_url=self.base_url,   # 같은 Furiosa 엔드포인트, 키만 다르다
                timeout=self.timeout,
                max_retries=0,
            )
        return self._embed_cli

    def embed(
        self, texts: list[str], *, dimensions: int | None = None, model: str | None = None
    ) -> tuple[list[list[float]], Usage]:
        """임베딩 — /v1/embeddings, EMBED_API_KEY 사용. 반환은 입력 순서 보존.

        dimensions 는 MRL 절단(§11 제안 1024). 서버 미지원이면 4xx → LLMError
        로 즉시 드러난다 — TICKET-5 에서 클라이언트 절단 폴백을 결정한다.
        """
        from openai import APIConnectionError, APIStatusError, APITimeoutError

        m = model or self.embed_model
        kwargs: dict = dict(model=m, input=texts)
        if dimensions is not None:
            kwargs["dimensions"] = dimensions
        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self._embed_client().embeddings.create(**kwargs)
                break
            except (APIStatusError, APIConnectionError, APITimeoutError) as e:
                last = e
                status = getattr(e, "status_code", None)
                if status and status < 500 and status != 429:
                    raise LLMError(f"임베딩 {status}: {e}") from e
                time.sleep(_BACKOFF**attempt)
        else:
            raise LLMError(f"임베딩 호출이 {self.max_retries}회 모두 실패했습니다: {last}") from last
        data = sorted(resp.data, key=lambda d: d.index)
        u = resp.usage
        return [d.embedding for d in data], Usage(m, getattr(u, "prompt_tokens", 0) if u else 0, 0)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest api/tests/test_llm_client.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: (라이브, EMBED_API_KEY 있으면) 실제 차원 확인 — §11 결정 재료**

```bash
python -c "from api.services.llm_client import LLMClient; v,u=LLMClient().embed(['테스트 문장']); print('기본 차원:', len(v[0]))"
python -c "from api.services.llm_client import LLMClient; v,u=LLMClient().embed(['테스트 문장'], dimensions=1024); print('1024 지원:', len(v[0]))"
```

Expected: 기본 차원 출력(Qwen3-Embedding-8B는 4096). 두 번째가 1024를 내면 MRL 서버 지원 확정, `LLMError`(400)면 "dimensions 미지원 — 클라이언트 절단 필요"로 기록. **결과를 Task 6 결과 문서 §임베딩에 기록.**

- [ ] **Step 6: Commit**

```bash
git add api/services/llm_client.py api/tests/test_llm_client.py
git commit -m "feat(llm): embed() 추가 — Furiosa 임베딩, 순서 보존·MRL dimensions (TICKET-0)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: langgraph 의존성 설치

**Files:**
- Modify: `api/requirements.txt`

**Interfaces:**
- Produces: `langgraph`(StateGraph·interrupt — TICKET-1), `langgraph-checkpoint-postgres`(PostgresSaver — TICKET-1), `psycopg[binary]`(체크포인터 드라이버; 기존 pg8000 경로 불변).

- [ ] **Step 1: 설치 후 실제 버전으로 핀 고정**

```bash
pip install langgraph langgraph-checkpoint-postgres "psycopg[binary]"
pip list --format=freeze | grep -iE "^(langgraph|psycopg)"
```

Expected: langgraph 1.x, langgraph-checkpoint-postgres 2.x, psycopg 3.2.x 설치. 출력된 **정확한 버전**을 requirements.txt 끝에 추가:

```
langgraph==<설치된 버전>
langgraph-checkpoint-postgres==<설치된 버전>
psycopg[binary]==<설치된 버전>
```

(langgraph의 부수 의존성 langgraph-checkpoint·langgraph-sdk 등은 핀하지 않는다 — 직접 import하는 최상위 3개만. 기존 파일의 "직접 의존성만 나열" 스타일 유지.)

- [ ] **Step 2: import 스모크 + 기존 스택 충돌 확인**

```bash
python -c "from langgraph.graph import StateGraph, START, END; from langgraph.types import interrupt, Command; from langgraph.checkpoint.postgres import PostgresSaver; import psycopg; print('langgraph ok')"
pip check
python -m pytest api/tests -q
```

Expected: `langgraph ok` · `pip check` 무충돌(pydantic 2.10 호환) · 테스트 전부 PASS

- [ ] **Step 3: Commit**

```bash
git add api/requirements.txt
git commit -m "chore(deps): langgraph + postgres 체크포인터 의존성 (TICKET-0)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: pgvector — `CREATE EXTENSION vector` (멱등·비치명)

**Files:**
- Modify: `api/services/db.py` (`init_schema()` — 4줄)

**Interfaces:**
- Consumes: 기존 `_engine()` 싱글톤.
- Produces: DB에 `vector` 확장(TICKET-5 `briefing_chunks`, TICKET-1 체크포인트와 같은 Cloud SQL). 로컬 PG에 확장이 없어도 앱은 뜬다(비치명 — briefing 전까지 무영향).

- [ ] **Step 1: 구현** — `db.py`의 `init_schema()`를 다음으로 교체 (import에 `text` 추가: `from sqlalchemy import (..., text)` — 기존 import 목록에 한 단어):

```python
def init_schema() -> None:
    """테이블 생성(멱등). 마이그레이션 도구는 MVP 범위 밖이라 create_all 로 둔다."""
    eng = _engine()
    # pgvector — briefing_chunks(TICKET-5)의 전제. 로컬 PG 에 확장이 없어도
    # 앱은 떠야 하므로 비치명(경고만). Cloud SQL PG15 는 기본 지원.
    try:
        with eng.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except Exception:
        import logging

        logging.getLogger("mindlens").warning(
            "pgvector 확장 생성 실패 — briefing RAG(TICKET-5) 전까지는 영향 없음", exc_info=True
        )
    Base.metadata.create_all(eng)
```

- [ ] **Step 2: 라이브 검증 (DB env 필요 — DATABASE_URL 또는 INSTANCE_CONNECTION_NAME)**

```bash
python -c "
from api.services.db import init_schema, db_session
from sqlalchemy import text
init_schema()
with db_session() as s:
    print('extversion:', s.execute(text(\"SELECT extversion FROM pg_extension WHERE extname='vector'\")).scalar())
    print('cast ok:', s.execute(text(\"SELECT '[1,2,3]'::vector(3)\")).scalar())
"
```

Expected: `extversion: 0.x.x` + `cast ok: [1,2,3]`. (env 없으면 이 단계는 배포 환경에서 수행하고 결과만 기록.)

- [ ] **Step 3: 기존 테스트 회귀 확인**

Run: `python -m pytest api/tests -q`
Expected: 전부 PASS

- [ ] **Step 4: Commit**

```bash
git add api/services/db.py
git commit -m "feat(db): CREATE EXTENSION vector 멱등 실행 — pgvector 기반 (TICKET-0)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Qwen3 자율 tool choice 실측 스크립트

**Files:**
- Create: `scripts/exp_tool_choice.py`

**Interfaces:**
- Consumes: Task 1의 `LLMClient.chat()` — 실측이 곧 신규 메서드의 라이브 검증이기도 하다.
- Produces: 마크다운 결과 문서(기본 `docs/experiments/2026-07-21-qwen3-tool-choice.md`) + exit code(게이트 통과 0 / 미달 1).

**설계 요점:**
- 도구 4종 스키마는 TICKET-5(계획 §3.3)와 동일한 이름·시그니처: `brief(term)` `playbook(situation)` `ledger_report()` `pace()`.
- 시나리오 10종 × 기본 3회 시행. 판정은 시나리오별 **허용 도구 집합 목록**(`ok`) — 정답이 애매한 상황(모순 확인 등)은 복수 정답 허용.
- 게이트(사전 고정): 도구 시나리오 정확도 ≥ 80% · 무도구 오발동률 ≤ 20% · 인자 JSON 유효율 100%.
- `--thinking` 플래그로 enable_thinking=True 재실행 비교(프로덕션은 off — off가 기준, on은 참고).

- [ ] **Step 1: 스크립트 작성** — `scripts/exp_tool_choice.py`:

```python
"""TICKET-0 게이트 — Qwen3-32B-FP8 자율 tool choice 실측.

도구 4종(TICKET-5 후보)을 주고 tool_choice="auto" 로 시나리오 10종 × N회를
돌려, (1) 맞는 도구를 고르는가 (2) 안 쓸 때 안 쓰는가 (3) 인자 JSON 이
유효한가를 측정한다. 게이트 미달이면 폴백(구조화 출력 강제)으로 방향 확정.

사용:  python scripts/exp_tool_choice.py [--trials 3] [--thinking] [--out PATH]
전제:  LLM_API_KEY 환경변수 (check_npu_endpoint.sh 참고)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

GATE_TOOL_ACC = 0.80    # 도구 시나리오 정확도
GATE_SPURIOUS = 0.20    # 무도구 시나리오 오발동률 상한
GATE_JSON_OK = 1.00     # 인자 JSON 유효율

TOOLS = [
    {"type": "function", "function": {
        "name": "brief",
        "description": "의뢰자의 도메인 용어·브랜드·제도·사실을 브리핑 자료에서 검색한다. 응답자가 언급한 용어를 모르거나 의뢰자 회사 고유의 것일 때 사용.",
        "parameters": {"type": "object", "properties": {"term": {"type": "string", "description": "검색할 용어"}}, "required": ["term"]}}},
    {"type": "function", "function": {
        "name": "playbook",
        "description": "정성조사 기법 사전(5 Why, 래더링, CIT, 모순 확인 등)에서 지금 상황에 맞는 질문 기법을 찾는다. 응답이 겉돌거나 모순되거나 파고들기 어려울 때 사용.",
        "parameters": {"type": "object", "properties": {"situation": {"type": "string", "description": "현재 인터뷰 상황 요약"}}, "required": ["situation"]}}},
    {"type": "function", "function": {
        "name": "ledger_report",
        "description": "커버리지 원장 요약 — 남은 목표, 답이 빈약한 문항, 회수 안 한 떡밥 목록을 확인한다.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "pace",
        "description": "남은 턴 예산과 페이스 경고를 확인한다. 인터뷰를 접을지 더 갈지 판단할 때 사용.",
        "parameters": {"type": "object", "properties": {}}}},
]

SYSTEM = (
    "당신은 정성조사 인터뷰 진행자다. 연구 주제에 맞춰 다음 질문 한 문장을 만든다.\n"
    "필요하면 도구를 먼저 호출해 정보를 얻고, 필요 없으면 도구 없이 바로 질문을 출력한다.\n"
    "모르는 용어를 아는 척하지 말 것. 질문은 한국어 존댓말 한 문장."
)

# ok = 허용되는 '호출 도구 이름 집합' 목록. frozenset() 은 무도구가 정답.
# arg_must = brief 호출 시 term 인자에 반드시 포함돼야 하는 문자열.
SCENARIOS = [
    {"id": "brand-unknown", "ok": [{"brief"}], "arg_must": "배민클럽",
     "user": "연구 주제: 배달앱 전환 요인\n[응답자] 요즘은 배민클럽 때문에 다른 앱으로 갈아탔어요."},
    {"id": "client-jargon", "ok": [{"brief"}], "arg_must": "멤버스딜",
     "user": "연구 주제: 편의점 앱 사용 경험\n[응답자] 저희 동네 점포는 멤버스딜 들어오고 나서 확 달라졌어요."},
    {"id": "shallow-answer", "ok": [{"playbook"}],
     "user": "연구 주제: 구독 해지 이유\n[응답자] (세 번 연속 같은 답) 그냥요. 별 이유 없어요. 그냥 그랬어요."},
    {"id": "contradiction", "ok": [{"playbook"}, frozenset()],
     "user": "연구 주제: 장보기 습관\n[3턴 전 응답자] 가격은 잘 안 봐요.\n[방금 응답자] 무조건 최저가만 골라서 사요."},
    {"id": "coverage-check", "ok": [{"ledger_report"}],
     "user": "연구 주제: 재택근무 경험\n[상황] 진행 15분 경과. 어떤 문항이 아직 빈약한지 확인하고 다음 질문을 정해야 한다."},
    {"id": "pace-check", "ok": [{"pace"}],
     "user": "연구 주제: 중고거래 경험\n[상황] 응답자가 말이 길다. 남은 턴 예산을 보고 이 주제를 더 팔지 접을지 정해야 한다."},
    {"id": "smalltalk", "ok": [frozenset()],
     "user": "연구 주제: 카페 이용 행태\n[응답자] 안녕하세요, 잘 부탁드립니다!"},
    {"id": "clear-story", "ok": [frozenset()],
     "user": "연구 주제: 온라인 쇼핑 반품 경험\n[응답자] 지난달에 산 신발이 작아서 반품했는데, 앱에서 버튼 몇 번 누르니까 다음날 기사님이 바로 가져가셨어요."},
    {"id": "multi-brief-pace", "ok": [{"brief", "pace"}, {"brief"}], "arg_must": "프로여관러",
     "user": "연구 주제: 숙박앱 이용 행태\n[상황] 진행 후반부, 남은 턴이 빠듯할 수 있다.\n[응답자] 저는 '프로여관러'라서 웬만한 건 다 시도해봤어요."},
    {"id": "common-term-trap", "ok": [frozenset()],
     "user": "연구 주제: 이커머스 배송 만족도\n[응답자] 쿠팡에서 로켓배송으로 시켰더니 다음날 새벽에 왔어요."},
]


def run(trials: int) -> dict:
    from api.services.llm_client import LLMClient

    cli = LLMClient()
    rows, lat = [], []
    for sc in SCENARIOS:
        for t in range(trials):
            t0 = time.perf_counter()
            out, usage = cli.chat(
                [{"role": "system", "content": SYSTEM}, {"role": "user", "content": sc["user"]}],
                tools=TOOLS, max_tokens=256,
            )
            dt = time.perf_counter() - t0
            lat.append(dt)
            called = {c.name for c in out.tool_calls}
            json_ok = all(c.arguments is not None for c in out.tool_calls)
            arg_ok = True
            if "brief" in called and sc.get("arg_must"):
                briefs = [c for c in out.tool_calls if c.name == "brief" and c.arguments]
                arg_ok = any(sc["arg_must"] in str(c.arguments.get("term", "")) for c in briefs)
            choice_ok = any(called == set(okset) for okset in sc["ok"])
            rows.append({
                "id": sc["id"], "trial": t + 1, "called": sorted(called) or ["-"],
                "expected": [sorted(s) or ["-"] for s in map(set, sc["ok"])],
                "choice_ok": choice_ok, "json_ok": json_ok, "arg_ok": arg_ok,
                "pass": choice_ok and json_ok and arg_ok,
                "latency_s": round(dt, 2), "tokens_out": usage.tokens_out,
                "content_head": out.content[:40],
            })
            print(f"  {sc['id']:18s} #{t+1}  called={sorted(called) or '-'}  "
                  f"{'PASS' if rows[-1]['pass'] else 'FAIL'}  {dt:.2f}s")
    none_ids = {"smalltalk", "clear-story", "common-term-trap"}   # 무도구가 정답인 3종
    none_rows = [r for r in rows if r["id"] in none_ids]
    tool_rows = [r for r in rows if r["id"] not in none_ids]
    acc = sum(r["pass"] for r in tool_rows) / len(tool_rows)
    spurious = sum(1 for r in none_rows if r["called"] != ["-"]) / len(none_rows)
    json_rate = sum(r["json_ok"] for r in rows) / len(rows)
    lat_sorted = sorted(lat)
    return {
        "rows": rows, "tool_acc": acc, "spurious": spurious, "json_rate": json_rate,
        "lat_mean": sum(lat) / len(lat), "lat_p95": lat_sorted[int(len(lat_sorted) * 0.95) - 1],
        "gate": acc >= GATE_TOOL_ACC and spurious <= GATE_SPURIOUS and json_rate >= GATE_JSON_OK,
    }


def to_md(res: dict, trials: int, thinking: bool) -> str:
    L = [
        "# Qwen3 자율 tool choice 실측 (TICKET-0 게이트)", "",
        f"- 모델: furiosa-ai/Qwen3-32B-FP8 · thinking={'on' if thinking else 'off(프로덕션 설정)'} · 시나리오 10종 × {trials}회",
        f"- **게이트 판정: {'✅ 통과 — 자율 tool choice 채택' if res['gate'] else '❌ 미달 — 폴백(도구 선택 구조화 출력 강제) 채택'}**", "",
        "| 지표 | 결과 | 기준 |", "|---|---|---|",
        f"| 도구 시나리오 정확도 | {res['tool_acc']:.0%} | ≥ {GATE_TOOL_ACC:.0%} |",
        f"| 무도구 오발동률 | {res['spurious']:.0%} | ≤ {GATE_SPURIOUS:.0%} |",
        f"| 인자 JSON 유효율 | {res['json_rate']:.0%} | = 100% |",
        f"| 지연 mean / p95 | {res['lat_mean']:.2f}s / {res['lat_p95']:.2f}s | (참고) |",
        "", "## 시행 상세", "",
        "| 시나리오 | 회 | 호출 | 기대 | 판정 | 지연 | 응답 앞부분 |", "|---|---|---|---|---|---|---|",
    ]
    for r in res["rows"]:
        L.append(f"| {r['id']} | {r['trial']} | {','.join(r['called'])} | "
                 f"{' 또는 '.join(','.join(e) for e in r['expected'])} | "
                 f"{'PASS' if r['pass'] else 'FAIL'} | {r['latency_s']}s | {r['content_head']} |")
    L += ["", "## 임베딩 (Task 2 Step 5 결과 — 수동 기입)", "",
          "- 기본 차원: (기입)", "- dimensions=1024 지원 여부: (기입) → §11 결정 재료", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--thinking", action="store_true", help="enable_thinking=True 비교 실행")
    ap.add_argument("--out", default="docs/experiments/2026-07-21-qwen3-tool-choice.md")
    a = ap.parse_args()
    if not os.environ.get("LLM_API_KEY"):
        print("LLM_API_KEY 가 필요합니다 (check_npu_endpoint.sh 참고)"); return 2
    os.environ["LLM_DISABLE_THINKING"] = "0" if a.thinking else "1"
    from api.config import get_settings
    get_settings.cache_clear()

    res = run(a.trials)
    md = to_md(res, a.trials, a.thinking)
    out = Path(a.out if not a.thinking else a.out.replace(".md", "-thinking.md"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"\n결과 저장: {out}")
    print(f"게이트: {'통과' if res['gate'] else '미달 — 폴백 확정'}")
    return 0 if res["gate"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 문법·시나리오 스모크 (네트워크 없이)**

```bash
python -c "import ast; ast.parse(open('scripts/exp_tool_choice.py', encoding='utf-8').read()); print('syntax ok')"
python scripts/exp_tool_choice.py --trials 1 2>&1 | head -3
```

Expected: `syntax ok` · 키 없으면 `LLM_API_KEY 가 필요합니다` 안내 후 exit 2 (키 있으면 바로 실행돼도 무방)

- [ ] **Step 3: Commit**

```bash
git add scripts/exp_tool_choice.py
git commit -m "test(exp): Qwen3 자율 tool choice 실측 스크립트 — TICKET-0 게이트

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: 실측 실행 + 게이트 판정 기록

**Files:**
- Create: `docs/experiments/2026-07-21-qwen3-tool-choice.md` (스크립트가 생성)
- Modify: `docs/TICKETS.md` (TICKET-0 체크박스 + 게이트 결과 1줄)

- [ ] **Step 1: 실측 실행 (LLM_API_KEY 필요, ~10분)**

```bash
export LLM_API_KEY=<check_npu_endpoint.sh 의 LLM_API 값>
python scripts/exp_tool_choice.py --trials 3
```

Expected: 30회 호출 진행 로그 → `docs/experiments/2026-07-21-qwen3-tool-choice.md` 생성, 게이트 판정 출력.

- [ ] **Step 2: (참고) thinking on 비교 — off 결과가 애매(70~85%)할 때만**

```bash
python scripts/exp_tool_choice.py --trials 3 --thinking
```

Expected: `...-thinking.md` 별도 저장. 판단은 여전히 off(프로덕션 설정) 기준.

- [ ] **Step 3: Task 2 Step 5의 임베딩 차원 결과를 결과 문서 §임베딩에 기입**

- [ ] **Step 4: TICKETS.md 갱신** — TICKET-0 작업 체크박스 5개를 `[x]`로, 검증 줄 아래에 결과 1줄 추가:

```markdown
**결과(2026-07-21).** 게이트 <통과/미달 — 폴백 확정>: 정확도 NN% · 오발동 NN% · JSON NN% (상세: [실측 문서](./experiments/2026-07-21-qwen3-tool-choice.md))
```

- [ ] **Step 5: Commit**

```bash
git add docs/experiments/ docs/TICKETS.md
git commit -m "docs(exp): tool choice 실측 결과 + TICKET-0 게이트 판정

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## 검증 (전체)

1. **단위**: `python -m pytest api/tests -q` — 신규 5개 포함 전부 PASS, 기존 테스트 무손상.
2. **의존성**: `pip check` 무충돌 + langgraph/PostgresSaver/psycopg import 성공.
3. **pgvector**: 라이브 DB에서 `extversion` 조회 + `'[1,2,3]'::vector(3)` 캐스트 성공.
4. **임베딩 라이브**: `embed(['테스트 문장'])` 차원 확인, `dimensions=1024` 지원 여부 기록.
5. **게이트**: 실측 문서의 3개 지표가 기준선과 함께 기록되고, 통과/폴백이 명시됨 — **이것이 TICKET-1 착수 조건.**

## 범위 밖 (이 티켓에서 하지 않는 것)

- PostgresSaver **연결·setup()** — TICKET-1 (여기선 설치만).
- `briefing_chunks` 테이블·인덱싱 파이프라인 — TICKET-5.
- 리랭커 — §8, API 형태 확인 후.
- `check_npu_endpoint.sh` 키 로테이션 — 사용자 판단(권장만).
