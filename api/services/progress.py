"""무거운 작업의 진행 이벤트 — 스트림과 비스트림이 같은 제너레이터를 공유하게 하는 헬퍼.

설계 근거: docs/specs/2026-07-23-pipeline-progress-ui-design.md §3~§4.

로직을 두 벌 쓰면 반드시 갈라진다. 그래서 각 작업의 본문은 이벤트를 yield 하는
제너레이터 하나로만 존재하고, 여기 헬퍼가 두 겹의 노출을 만든다:
  · sse()   — SSE 프레임으로 감싼다 (신규 /stream 엔드포인트)
  · drain() — 소진해 result 만 돌려준다 (기존 POST 엔드포인트, 계약 그대로)

도메인 로직은 여기 없다. 단계 선언과 전이만 다룬다.
"""
from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

from fastapi import HTTPException

Event = dict[str, Any]

# 프록시가 스트림을 버퍼링하면 진행 표시가 통째로 뭉쳐 마지막에 한 번에 온다.
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class Pipeline:
    """단계를 미리 선언하고, 그 단계들의 전이 이벤트를 만든다.

    선언(declare)을 먼저 보내야 프론트가 아직 오지 않은 단계까지 회색으로 그려
    전체 길이를 처음부터 보여줄 수 있다. 선언에 없는 키를 내보내려 하면 KeyError 로
    즉시 터뜨린다 — 그릴 자리가 없는 이벤트를 조용히 흘리면 선언과 실제가 갈라지고,
    그 어긋남은 화면에서만 드러난다.
    """

    def __init__(self, steps: list[tuple[str, str]]) -> None:
        self._labels: dict[str, str] = dict(steps)
        self._decl: list[dict[str, str]] = [{"key": k, "label": lbl} for k, lbl in steps]
        self._t0: dict[str, float] = {}

    def declare(self) -> Event:
        return {"steps": self._decl}

    def start(self, key: str, **detail: Any) -> Event:
        self._check(key)
        self._t0[key] = time.perf_counter()
        return self._event(key, "start", detail)

    def progress(self, key: str, done: int, total: int) -> Event:
        """진행 중 갱신 — 같은 키의 start 를 덮어쓰는 형태로 여러 번 보낸다."""
        self._check(key)
        return {"step": key, "status": "start", "detail": {"done": done, "total": total}}

    def done(self, key: str, **detail: Any) -> Event:
        self._check(key)
        ev = self._event(key, "done", detail)
        t0 = self._t0.get(key)
        if t0 is not None:   # start 를 안 거쳤으면 소요 시간을 지어내지 않는다
            ev["ms"] = int((time.perf_counter() - t0) * 1000)
        return ev

    def skip(self, key: str, **detail: Any) -> Event:
        self._check(key)
        return self._event(key, "skip", detail)

    def fail(self, key: str, message: str, status_code: int = 502) -> Event:
        self._check(key)
        return {"step": key, "status": "error", "error": message, "status_code": status_code}

    def _check(self, key: str) -> None:
        if key not in self._labels:
            raise KeyError(f"선언되지 않은 단계: {key}")

    @staticmethod
    def _event(key: str, status: str, detail: dict[str, Any]) -> Event:
        ev: Event = {"step": key, "status": status}
        if detail:
            ev["detail"] = detail
        return ev


def sse(events: Iterator[Event]) -> Iterator[str]:
    """SSE 프레임으로 감싼다. public.py 의 _sse 와 같은 포맷."""
    for e in events:
        yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"


def drain(events: Iterator[Event]) -> Any:
    """소진해 result 만 돌려준다. error 이벤트는 기존과 같은 HTTP 예외로 승격한다."""
    result: Any = None
    for e in events:
        if "error" in e:
            raise HTTPException(int(e.get("status_code", 502)), str(e["error"]))
        if "result" in e:
            result = e["result"]
    return result
