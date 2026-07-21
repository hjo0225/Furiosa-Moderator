"""임베딩 씬 래퍼 — 브리핑 RAG 전용. 차원은 1024 MRL(T0 실측: 서버 네이티브 지원)."""
from __future__ import annotations

from .llm_client import get_llm

EMBED_DIM = 1024


def embed_texts(texts: list[str]) -> list[list[float]]:
    vecs, _ = get_llm().embed(texts, dimensions=EMBED_DIM)
    return vecs
