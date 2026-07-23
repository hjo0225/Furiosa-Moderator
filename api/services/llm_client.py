"""llm_client — OpenAI 호환 엔드포인트(Furiosa-LLM on RNGD) 호출.

원본(mindlens_solution)의 Anthropic 전용 클라이언트를 OpenAI 호환으로 재작성했다.
살린 것: 재시도·지수백오프, truncation 가드, 스키마 검증 실패 시 자가교정 재시도.
버린 것: web_research(Claude 전용 서버툴), vision.

PORTING.md §2 의 3개 수정 지점이 여기서 해소된다:
  1. base_url 주입구 없음        → settings.llm_base_url
  2. OpenAI() 에 base_url 없음   → 동일
  3. 모델명 prefix 로 provider 판별 → settings.llm_provider (설정값)

추가로 Qwen3 실측에서 나온 것:
  - chat_template_kwargs.enable_thinking=False 를 붙이지 않으면 출력 토큰 대부분이
    사고에 쓰이고 응답이 잘린다(3.44s/truncated → 0.75s/정상).
  - 구조화 출력은 forced tool_choice 가 가장 안정적이고, json_object 는 폴백으로 둔다.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterator, TypeVar

from pydantic import BaseModel

from ..config import get_settings

T = TypeVar("T", bound=BaseModel)

log = logging.getLogger(__name__)

_BACKOFF = 1.5
# 구조화 출력 truncation 재시도 시 max_tokens 상한
_STRUCTURED_TOKEN_CEIL = 4096

# 샘플링 온도 — 서버 기본값(보통 1.0)에 맡기면 안 된다.
# FP8 양자화 Qwen3 는 긴 한국어 구조화 생성에서 디코딩이 무너진다. 실측으로
# 가이드 생성 문항 하나가 "…웃다른ʍ가 먽~지들이흐… Lily throne" 같은 다국어 잡음으로
# 붕괴했다. 온도를 낮추면 사라진다. 구조화 출력은 더 낮게 잡는다.
_TEMP_TEXT = 0.6
_TEMP_STRUCTURED = 0.3


@dataclass
class Usage:
    model: str
    tokens_in: int
    tokens_out: int


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


class LLMError(RuntimeError):
    """LLM 호출 실패 — 라우터가 502 로 변환한다."""


class LLMClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        s = get_settings()
        self.api_key = (api_key or s.llm_api_key).lstrip("﻿").strip()
        self.model = model or s.llm_model
        self.base_url = s.llm_base_url
        self.timeout = s.llm_timeout
        self.max_retries = s.llm_max_retries
        self._disable_thinking = s.llm_disable_thinking
        self._cli = None
        self.embed_model = s.embed_model
        self.embed_api_key = (s.embed_api_key or "").lstrip("﻿").strip()
        self.embed_base_url = s.embed_base_url or s.llm_base_url
        self._embed_cli = None
        self.rerank_model = s.rerank_model
        self.rerank_api_key = (s.rerank_api_key or "").lstrip("﻿").strip()
        self.rerank_base_url = s.rerank_base_url or s.llm_base_url

    def _client(self):
        if self._cli is None:
            from openai import OpenAI

            # SDK 자체 재시도는 끄고(_call 이 직접 백오프), 타임아웃은 명시한다.
            self._cli = OpenAI(
                api_key=self.api_key or "unused",
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=0,
            )
        return self._cli

    def _extra(self) -> dict:
        """Qwen3 thinking 비활성 — 대화형 지연의 핵심 스위치."""
        if not self._disable_thinking:
            return {}
        return {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}

    def _call(self, *, retries: int | None = None, **kwargs):
        """재시도 래퍼 — 429/5xx/연결오류에 지수 백오프, 4xx 는 즉시 raise.

        retries 는 호출별 override(best-effort 부수 작업의 벽시계 상한용) — None 이면
        self.max_retries(기본 동작 불변). kwargs 로는 절대 흘려보내지 않는다(OpenAI API 가
        모르는 파라미터).
        """
        from openai import APIConnectionError, APIStatusError, APITimeoutError

        attempts = self.max_retries if retries is None else max(1, retries)
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                return self._client().chat.completions.create(**kwargs)
            except (APIStatusError, APIConnectionError, APITimeoutError) as e:
                last = e
                status = getattr(e, "status_code", None)
                if status and status < 500 and status != 429:
                    raise LLMError(f"LLM {status}: {e}") from e
                time.sleep(_BACKOFF**attempt)
        raise LLMError(f"LLM 호출이 {attempts}회 모두 실패했습니다: {last}") from last

    def _embed_client(self):
        if self._embed_cli is None:
            from openai import OpenAI

            self._embed_cli = OpenAI(
                api_key=self.embed_api_key or "unused",
                base_url=self.embed_base_url,   # 기본은 llm_base_url, 분리 서빙 시 EMBED_BASE_URL
                timeout=self.timeout,
                max_retries=0,
            )
        return self._embed_cli

    # --- 임베딩 ---------------------------------------------------------------

    def embed(
        self, texts: list[str], *, dimensions: int | None = None, model: str | None = None
    ) -> tuple[list[list[float]], Usage]:
        """임베딩 — /v1/embeddings, EMBED_API_KEY 사용. 반환은 입력 순서 보존.

        dimensions 는 MRL 절단(§11 제안 1024). 서버 미지원이면 4xx → LLMError
        로 즉시 드러난다 — TICKET-5 에서 클라이언트 절단 폴백을 결정한다.
        재시도 루프는 _call 과 같은 정책의 의도된 중복(기존 메서드 불변 원칙).
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

    # --- 리랭크 --------------------------------------------------------------

    def rerank(self, query: str, documents: list[str], *, top_n: int = 3,
               model: str | None = None, max_doc_chars: int = 1200) -> list[tuple[int, float]]:
        """/v1/rerank 호출 — [(원본 index, relevance_score)] 를 점수 내림차순으로 반환.

        OpenAI SDK 에 rerank 가 없어 REST 를 httpx 로 직접 부른다(research._run_actor 관례).
        documents 가 비면 호출 없이 []. HTTP 실패는 max_retries 재시도 후 LLMError.
        긴 문서는 max_doc_chars 로 잘라 보낸다 — 라이브에서 장문 30개 리랭킹이 타임아웃을
        내는 걸 확인했다(코사인 폴백은 되지만 리랭커 이점을 잃음). 인덱스는 원본 순서 그대로.
        """
        if not documents:
            return []
        import httpx

        m = model or self.rerank_model
        docs = [d[:max_doc_chars] for d in documents]
        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = httpx.post(
                    f"{self.rerank_base_url}/rerank",
                    headers={"Authorization": f"Bearer {self.rerank_api_key}"},
                    json={"model": m, "query": query, "documents": docs, "top_n": top_n},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                break
            except httpx.HTTPError as e:
                last = e
                time.sleep(0.5 * (attempt + 1))
        else:
            raise LLMError(f"리랭크 호출이 {self.max_retries}회 모두 실패했습니다: {last}") from last
        try:
            results = resp.json()["results"]
            parsed = [(item["index"], item["relevance_score"]) for item in results]
        except (KeyError, ValueError, TypeError) as e:
            raise LLMError(f"리랭크 응답 파싱 실패: {e}") from e
        return sorted(parsed, key=lambda t: t[1], reverse=True)

    # --- 텍스트 --------------------------------------------------------------

    def text(
        self, system: str, user: str, *, max_tokens: int = 512, model: str | None = None
    ) -> tuple[str, Usage]:
        m = model or self.model
        resp = self._call(
            model=m,
            max_tokens=max_tokens,
            temperature=_TEMP_TEXT,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **self._extra(),
        )
        out = (resp.choices[0].message.content or "").strip()
        u = resp.usage
        return out, Usage(m, u.prompt_tokens if u else 0, u.completion_tokens if u else 0)

    def stream_text(
        self, system: str, user: str, *, max_tokens: int = 512, model: str | None = None
    ) -> Iterator[str]:
        """토큰 델타 제너레이터 — TTFT 를 낮추려는 경로(실측 0.26s)."""
        m = model or self.model
        stream = self._call(
            model=m,
            max_tokens=max_tokens,
            temperature=_TEMP_TEXT,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=True,
            **self._extra(),
        )
        for chunk in stream:
            # 서버가 choices 가 빈 keep-alive 청크를 보낼 수 있다 — 그냥 건너뛴다.
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

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

    # --- 구조화 출력 ----------------------------------------------------------

    def structured(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        max_tokens: int = 1024,
        model: str | None = None,
        max_attempts: int = 3,
        timeout: float | None = None,
        retries: int | None = None,
    ) -> tuple[T, Usage]:
        """forced tool_choice 로 Pydantic 스키마에 맞는 객체를 받는다.

        검증 실패 시 오류 문구를 덧붙여 최대 max_attempts 회 재시도(자가교정).
        재시도로 태운 토큰도 누적해 반환한다.
        tool_calls 를 못 받으면 json_object 경로로 폴백한다.
        timeout 은 호출별 override(가이드 등 무거운 단발) — None 이면 클라이언트 기본.
        retries 는 _call 의 전송 재시도 상한 override(벽시계 상한용) — None 이면 클라이언트
        기본(self.max_retries). json_object 폴백(_structured_json)에는 전달하지 않는다(불변).
        """
        from pydantic import ValidationError

        m = model or self.model
        # None 이면 timeout 키 자체를 넣지 않는다 — SDK 에서 timeout=None 은 '무제한'이라
        # 클라이언트 기본(30s)과 다르다.
        call_timeout = {"timeout": timeout} if timeout is not None else {}
        tool = {
            "type": "function",
            "function": {
                "name": "respond",
                "description": "구조화된 응답을 반환합니다.",
                "parameters": schema.model_json_schema(),
            },
        }
        total_in = total_out = 0
        last_err: Exception | None = None
        cur_user = user
        cur_max = max_tokens

        for _ in range(max(1, max_attempts)):
            resp = self._call(
                retries=retries,
                model=m,
                max_tokens=cur_max,
                temperature=_TEMP_STRUCTURED,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": cur_user},
                ],
                tools=[tool],
                tool_choice={"type": "function", "function": {"name": "respond"}},
                **self._extra(),
                **call_timeout,
            )
            u = resp.usage
            total_in += u.prompt_tokens if u else 0
            total_out += u.completion_tokens if u else 0
            choice = resp.choices[0]

            # 잘린 응답은 검증을 '통과'해도 기본값으로 위장될 수 있다(필드 default).
            # 검증 전에 토큰을 키워 재시도한다(truncation 가드).
            if choice.finish_reason == "length" and cur_max < _STRUCTURED_TOKEN_CEIL:
                new_max = min(cur_max * 2, _STRUCTURED_TOKEN_CEIL)
                log.warning(
                    "구조화 출력이 max_tokens 에서 잘려 전체를 재생성합니다 (max_tokens: %d → %d)",
                    cur_max, new_max,
                )
                cur_max = new_max
                last_err = last_err or LLMError("구조화 출력이 max_tokens 에서 잘림")
                continue

            calls = choice.message.tool_calls or []
            if not calls:
                # 툴콜을 안 줬으면 json_object 로 폴백
                return self._structured_json(
                    system, user, schema, max_tokens=cur_max, model=m,
                    max_attempts=max_attempts, carry=(total_in, total_out),
                    timeout=timeout,
                )
            try:
                payload = json.loads(calls[0].function.arguments or "{}")
                return schema.model_validate(payload), Usage(m, total_in, total_out)
            except (ValidationError, ValueError) as e:
                last_err = e
                cur_user = (
                    f"{user}\n\n[직전 응답이 스키마 검증에 실패했습니다]\n{e}\n"
                    "위 오류를 바로잡아 스키마를 정확히 지켜 respond 도구로만 다시 응답하세요."
                )
        raise LLMError(f"구조화 출력 실패: {last_err}") from last_err

    def _structured_json(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        max_tokens: int,
        model: str,
        max_attempts: int = 3,
        carry: tuple[int, int] = (0, 0),
        timeout: float | None = None,
    ) -> tuple[T, Usage]:
        """json_object 폴백 — 스키마를 프롬프트에 주입하고 검증 재시도."""
        from pydantic import ValidationError

        call_timeout = {"timeout": timeout} if timeout is not None else {}   # None 이면 키 생략(SDK '무제한' 회피)
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        sys = (
            f"{system}\n\n아래 JSON 스키마에 정확히 맞는 JSON 객체 하나로만 "
            f"응답하세요(설명·마크다운 금지):\n{schema_json}"
        )
        total_in, total_out = carry
        last_err: Exception | None = None
        cur_user = user
        for _ in range(max(1, max_attempts)):
            resp = self._call(
                model=model,
                max_tokens=max_tokens,
                temperature=_TEMP_STRUCTURED,
                messages=[
                    {"role": "system", "content": sys},
                    {"role": "user", "content": cur_user},
                ],
                response_format={"type": "json_object"},
                **self._extra(),
                **call_timeout,
            )
            u = resp.usage
            total_in += u.prompt_tokens if u else 0
            total_out += u.completion_tokens if u else 0
            txt = resp.choices[0].message.content or "{}"
            try:
                return schema.model_validate_json(txt), Usage(model, total_in, total_out)
            except (ValidationError, ValueError) as e:
                last_err = e
                cur_user = (
                    f"{user}\n\n[직전 응답이 스키마 검증에 실패했습니다]\n{e}\n"
                    "위 오류를 바로잡아 스키마를 정확히 지킨 JSON 객체로만 다시 응답하세요."
                )
        raise LLMError(f"구조화 출력(json) 실패: {last_err}") from last_err


@lru_cache
def _llm_for(api_key: str, model: str, base_url: str) -> LLMClient:
    return LLMClient(api_key=api_key, model=model)


def get_llm() -> LLMClient:
    # 싱글톤 — 매 호출 새 인스턴스면 httpx 커넥션 풀이 재사용되지 않는다.
    s = get_settings()
    return _llm_for(s.llm_api_key, s.llm_model, s.llm_base_url)
