"""벤치마크 결과 제공 — 계측 스펙 §7 출력물을 대시보드에 그대로 넘긴다.

측정 하네스는 팟에서 돌고, 그 산출 CSV 를 `scripts/bench_to_json.py` 가 이 JSON 으로
바꿔 리포에 커밋한다. 여기서는 그 파일을 읽어 넘기기만 한다 — 계산하지 않는다.
계산을 여기서 하면 "화면에 보이는 수치"와 "원자료" 사이에 검증 불가능한 층이 하나
더 생긴다(스펙 §8: 확인 안 된 값 금지).

파일이 없으면 404 를 낸다. 프론트는 404 를 null-우선 기본값으로 받아 화면을 "고장"이
아니라 "아직 측정 없음"으로 그린다(web/lib/api.ts fetchBenchmarkResult).
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/benchmark", tags=["benchmark"])

_RESULT_PATH = Path(__file__).resolve().parent.parent / "benchmark" / "latest.json"


@lru_cache(maxsize=1)
def _load() -> dict | None:
    """결과 파일을 읽어 캐시한다. 배포마다 파일이 고정이라 프로세스 수명 동안 안 바뀐다."""
    if not _RESULT_PATH.exists():
        return None
    try:
        return json.loads(_RESULT_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 깨진 결과 파일이 API 를 죽이면 안 된다
        log.exception("벤치마크 결과 파일 파싱 실패: %s", _RESULT_PATH)
        return None


@router.get("/latest")
def latest() -> dict:
    """마지막 측정 결과. 없으면 404 — 프론트가 '아직 측정 없음'으로 그린다."""
    data = _load()
    if data is None:
        raise HTTPException(404, "측정 결과가 아직 없습니다.")
    return data
