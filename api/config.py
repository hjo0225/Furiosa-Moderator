"""설정 — 환경변수 단일 소스.

시크릿은 코드·로그에 남기지 않는다(아키텍처 §9). Cloud Run 에서는 Secret Manager 가
LLM_API_KEY 를 환경변수로 주입한다.
"""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel


class Settings(BaseModel):
    # --- LLM (OpenAI 호환) ---------------------------------------------------
    # Furiosa RNGD 서빙. base_url 만 바꾸면 vLLM·OpenAI 등으로 교체된다(아키텍처 §2 이식성).
    llm_base_url: str = "https://endpoint.access.furiosa.dev/v1"
    llm_api_key: str = ""
    llm_model: str = "furiosa-ai/Qwen3-32B-FP8"
    # provider 는 '설정값'으로 판별한다. 모델명 prefix 로 판별하면 furiosa-ai/Qwen3-* 가
    # Anthropic 경로로 오분기한다(PORTING.md §2).
    llm_provider: str = "openai_compat"

    # Qwen3 는 추론 모델이라 기본값이 thinking on 이다. 켜두면 200 토큰 중 174 개를
    # 사고에 쓰고 응답이 잘린다(실측 3.44s → 0.75s). 대화형에서는 반드시 끈다.
    llm_disable_thinking: bool = True

    llm_timeout: float = 30.0
    llm_max_retries: int = 3

    # --- 임베딩/리랭커 (가이드 RAG, M-1) ---------------------------------------
    embed_model: str = "furiosa-ai/Qwen3-Embedding-8B"
    embed_api_key: str = ""
    rerank_model: str = "furiosa-ai/Qwen3-Reranker-8B"
    rerank_api_key: str = ""

    # --- GCP -----------------------------------------------------------------
    gcp_project: str = ""
    firestore_database: str = "(default)"
    tts_voice: str = "ko-KR-Chirp3-HD-Leda"
    stt_language: str = "ko-KR"
    # chirp_2 는 us-central1 에만 있다. asia-northeast3 에는 STT v2 자체가 없어
    # 어차피 리전을 맞출 수 없다. 어휘 힌트(adaptation)를 받는 게 훨씬 크다.
    stt_location: str = "us-central1"
    stt_model: str = "chirp_2"

    # --- 앱 ------------------------------------------------------------------
    cors_origins: str = "*"
    max_audio_bytes: int = 10 * 1024 * 1024

    # --- 알림 (Discord) ------------------------------------------------------
    discord_webhook_url: str = ""   # 비면 알림 비활성
    public_web_base: str = ""       # 대시보드 링크 베이스


@lru_cache
def get_settings() -> Settings:
    env = os.environ
    return Settings(
        llm_base_url=env.get("LLM_BASE_URL", Settings().llm_base_url),
        # BOM/공백이 섞여도 Authorization 헤더가 깨지지 않도록 정제
        llm_api_key=env.get("LLM_API_KEY", "").lstrip("﻿").strip(),
        llm_model=env.get("LLM_MODEL", Settings().llm_model),
        llm_provider=env.get("LLM_PROVIDER", Settings().llm_provider),
        llm_disable_thinking=env.get("LLM_DISABLE_THINKING", "1") not in ("0", "false", "False"),
        embed_api_key=env.get("EMBED_API_KEY", "").lstrip("﻿").strip(),
        rerank_api_key=env.get("RERANK_API_KEY", "").lstrip("﻿").strip(),
        gcp_project=env.get("GCP_PROJECT", "") or env.get("GOOGLE_CLOUD_PROJECT", ""),
        stt_location=env.get("STT_LOCATION", Settings().stt_location),
        stt_model=env.get("STT_MODEL", Settings().stt_model),
        cors_origins=env.get("CORS_ORIGINS", "*"),
        discord_webhook_url=env.get("DISCORD_WEBHOOK_URL", ""),
        public_web_base=env.get("PUBLIC_WEB_BASE", ""),
    )
