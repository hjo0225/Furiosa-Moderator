"""진행 이벤트 헬퍼 — 선언/전이/직렬화/소진.

설계: docs/specs/2026-07-23-pipeline-progress-ui-design.md §3~§4.
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from api.services.progress import Pipeline, drain, sse


def test_declare_lists_steps_in_order():
    p = Pipeline([("a", "가"), ("b", "나")])
    assert p.declare() == {"steps": [{"key": "a", "label": "가"}, {"key": "b", "label": "나"}]}


def test_start_and_done_emit_status_and_measure_ms():
    p = Pipeline([("a", "가")])
    assert p.start("a") == {"step": "a", "status": "start"}
    ev = p.done("a", found=3)
    assert ev["step"] == "a"
    assert ev["status"] == "done"
    assert ev["detail"] == {"found": 3}
    assert isinstance(ev["ms"], int) and ev["ms"] >= 0


def test_done_without_start_has_no_ms():
    # start 를 안 거친 단계에 소요 시간을 지어내지 않는다 — 없으면 없는 대로 둔다.
    p = Pipeline([("a", "가")])
    assert "ms" not in p.done("a")


def test_progress_repeats_start_with_counts():
    p = Pipeline([("s", "요약")])
    assert p.progress("s", 3, 12) == {
        "step": "s", "status": "start", "detail": {"done": 3, "total": 12}
    }


def test_skip_and_fail():
    p = Pipeline([("a", "가")])
    assert p.skip("a", reason="자료 없음") == {
        "step": "a", "status": "skip", "detail": {"reason": "자료 없음"}
    }
    assert p.fail("a", "터졌습니다", status_code=400) == {
        "step": "a", "status": "error", "error": "터졌습니다", "status_code": 400
    }


def test_unknown_key_raises():
    # 선언에 없는 단계를 내보내면 프론트가 그릴 자리가 없다 — 조용히 흘리지 않고 즉시 터뜨린다.
    p = Pipeline([("a", "가")])
    with pytest.raises(KeyError):
        p.start("nope")


def test_sse_frames_are_json_lines_with_utf8():
    frames = list(sse(iter([{"step": "a", "status": "start"}, {"result": {"x": "한글"}}])))
    assert frames[0] == 'data: {"step": "a", "status": "start"}\n\n'
    assert "한글" in frames[1]                      # ensure_ascii=False
    assert frames[1].endswith("\n\n")
    assert json.loads(frames[1][len("data: "):]) == {"result": {"x": "한글"}}


def test_drain_returns_result_and_ignores_step_events():
    assert drain(iter([{"step": "a", "status": "start"}, {"result": 42}])) == 42


def test_drain_raises_http_exception_on_error_event():
    with pytest.raises(HTTPException) as e:
        drain(iter([{"step": "a", "status": "error", "error": "터짐", "status_code": 400}]))
    assert e.value.status_code == 400
    assert e.value.detail == "터짐"


def test_drain_defaults_to_502_when_status_missing():
    with pytest.raises(HTTPException) as e:
        drain(iter([{"error": "터짐"}]))
    assert e.value.status_code == 502
