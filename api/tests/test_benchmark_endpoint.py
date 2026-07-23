"""벤치마크 결과 엔드포인트 — 계측 스펙 §7 출력물을 그대로 넘기는지.

이 라우터는 계산하지 않는다. 계산이 여기 있으면 "화면 수치"와 "원자료" 사이에
검증 불가능한 층이 생긴다 — 그래서 테스트도 "파일을 그대로 넘기는가"만 본다.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.routers import benchmark as bm


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_cache():
    bm._load.cache_clear()
    yield
    bm._load.cache_clear()


def test_route_registered():
    paths = {r.path for r in main.app.routes if hasattr(r, "path")}
    assert "/api/benchmark/latest" in paths


def test_returns_committed_result(client):
    """리포에 커밋된 실제 결과 파일이 그대로 나와야 한다."""
    r = client.get("/api/benchmark/latest")
    assert r.status_code == 200
    body = r.json()
    on_disk = json.loads(bm._RESULT_PATH.read_text(encoding="utf-8"))
    assert body == on_disk


def test_missing_file_is_404(client, monkeypatch, tmp_path):
    monkeypatch.setattr(bm, "_RESULT_PATH", tmp_path / "nope.json")
    bm._load.cache_clear()
    assert client.get("/api/benchmark/latest").status_code == 404


def test_broken_file_is_404_not_500(client, monkeypatch, tmp_path):
    """깨진 결과 파일이 API 를 죽이면 안 된다 — 화면은 '측정 없음'으로 떨어진다."""
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(bm, "_RESULT_PATH", bad)
    bm._load.cache_clear()
    assert client.get("/api/benchmark/latest").status_code == 404


def test_committed_result_matches_ui_contract():
    """web/lib/api.ts 의 BenchmarkResult 와 필드가 어긋나면 화면이 조용히 빈다."""
    d = json.loads(bm._RESULT_PATH.read_text(encoding="utf-8"))
    for key in (
        "latency", "m1_sessions_per_card", "sla_target_ms", "turn_breakdown",
        "rewrite_rate", "energy", "idle_baseline_w", "power_timeseries",
        "model_placement", "out_of_scope", "measured_at", "meta",
    ):
        assert key in d, f"필드 누락: {key}"

    for row in d["latency"]:
        assert {"slots", "turns", "failures", "p50_ms", "p95_ms"} <= row.keys()
    for stage in d["turn_breakdown"]:
        assert {"key", "label", "p50_ms", "share", "parallel"} <= stage.keys()


def test_m1_unmet_is_not_zero():
    """전 구간 SLA 미달은 0 이 아니라 'unmet' — 다른 결론이기 때문(스펙 §1)."""
    d = json.loads(bm._RESULT_PATH.read_text(encoding="utf-8"))
    if d["m1_sessions_per_card"] is not None:
        assert d["m1_sessions_per_card"] != 0
