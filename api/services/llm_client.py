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
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterator, TypeVar

from pydantic import BaseModel

from ..config import get_settings

T = TypeVar("T", bound=BaseModel)

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

    def _call(self, **kwargs):
        """재시도 래퍼 — 429/5xx/연결오류에 지수 백오프, 4xx 는 즉시 raise."""
        from openai import APIConnectionError, APIStatusError, APITimeoutError

        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return self._client().chat.completions.create(**kwargs)
            except (APIStatusError, APIConnectionError, APITimeoutError) as e:
                last = e
                status = getattr(e, "status_code", None)
                if status and status < 500 and status != 429:
                    raise LLMError(f"LLM {status}: {e}") from e
                time.sleep(_BACKOFF**attempt)
        raise LLMError(f"LLM 호출이 {self.max_retries}회 모두 실패했습니다: {last}") from last

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
    ) -> tuple[T, Usage]:
        """forced tool_choice 로 Pydantic 스키마에 맞는 객체를 받는다.

        검증 실패 시 오류 문구를 덧붙여 최대 max_attempts 회 재시도(자가교정).
        재시도로 태운 토큰도 누적해 반환한다.
        tool_calls 를 못 받으면 json_object 경로로 폴백한다.
        """
        from pydantic import ValidationError

        m = model or self.model
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
            )
            u = resp.usage
            total_in += u.prompt_tokens if u else 0
            total_out += u.completion_tokens if u else 0
            choice = resp.choices[0]

            # 잘린 응답은 검증을 '통과'해도 기본값으로 위장될 수 있다(필드 default).
            # 검증 전에 토큰을 키워 재시도한다(truncation 가드).
            if choice.finish_reason == "length" and cur_max < _STRUCTURED_TOKEN_CEIL:
                cur_max = min(cur_max * 2, _STRUCTURED_TOKEN_CEIL)
                last_err = last_err or LLMError("구조화 출력이 max_tokens 에서 잘림")
                continue

            calls = choice.message.tool_calls or []
            if not calls:
                # 툴콜을 안 줬으면 json_object 로 폴백
                return self._structured_json(
                    system, user, schema, max_tokens=cur_max, model=m,
                    max_attempts=max_attempts, carry=(total_in, total_out),
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
    ) -> tuple[T, Usage]:
        """json_object 폴백 — 스키마를 프롬프트에 주입하고 검증 재시도."""
        from pydantic import ValidationError

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
