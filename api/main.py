"""mindlens API — FastAPI 앱 엔트리.

무인증 MVP 라 LLM 호출이 외부에 열린다. 최소 방어로 IP 기준 레이트리밋을 둔다.
운영 전에는 세션 토큰이 필요하다(PORTING.md 미해결 항목).
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .routers import projects, public, speech

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("mindlens")

app = FastAPI(title="mindlens API", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    """테이블 생성(멱등). 실패해도 앱은 뜬다 — /health 로 원인을 볼 수 있어야 한다."""
    try:
        from .services.db import init_schema

        init_schema()
        log.info("DB 스키마 준비 완료")
        if get_settings().interview_engine == "graph":
            from .interview import engine as graph_engine

            log.info("그래프 엔진: %s", "준비 완료" if graph_engine.ready() else "실패 → 구엔진 폴백")
    except Exception as e:
        log.exception("DB 스키마 초기화 실패: %s", e)

_s = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _s.cors_origins.split(",") if o.strip()] or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 레이트리밋 --------------------------------------------------------------
# LLM 을 태우는 경로만 건다. 인메모리라 인스턴스별로 독립적이다 — Cloud Run 이 스케일아웃하면
# 실질 한도가 인스턴스 수만큼 늘어난다. 정확한 제어가 필요하면 Redis 로 옮겨야 한다.
_WINDOW = 60.0
_LIMIT = 30
_hits: dict[str, deque[float]] = defaultdict(deque)
_GUARDED = ("/api/public/", "/api/speech/", "/guide", "/insight", "/material")


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    path = request.url.path
    if request.method in ("POST", "PUT") and any(g in path for g in _GUARDED):
        ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
              or (request.client.host if request.client else "unknown"))
        now = time.time()
        q = _hits[ip]
        while q and now - q[0] > _WINDOW:
            q.popleft()
        if len(q) >= _LIMIT:
            return JSONResponse({"detail": "요청이 너무 잦습니다. 잠시 후 다시 시도하세요."}, status_code=429)
        q.append(now)
    return await call_next(request)


app.include_router(projects.router)
app.include_router(public.router)
app.include_router(speech.router)


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {
        "ok": True,
        "model": s.llm_model,
        "base_url": s.llm_base_url,
        "thinking_disabled": s.llm_disable_thinking,
        "project": s.gcp_project or None,
        # 키 자체는 절대 싣지 않는다. 주입 여부만 확인한다.
        "llm_key_present": bool(s.llm_api_key),
    }
