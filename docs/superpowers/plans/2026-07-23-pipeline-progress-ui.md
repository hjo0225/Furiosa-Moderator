# 무거운 작업의 실시간 진행 화면 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 가이드 생성·인사이트 생성·자료 수집이 도는 동안 서버가 실제 파이프라인 단계를 SSE로 흘려보내고, 전체 화면 진행 뷰가 실측 수치(소요 ms·토큰·모델명·근거 스니펫)와 함께 보여준다.

**Architecture:** 각 작업의 본문을 **이벤트를 yield하는 제너레이터 한 벌**로 옮기고, 기존 POST 엔드포인트는 그 제너레이터를 `drain()`으로 소진해 지금과 똑같은 응답을 돌려주고, 신규 `/stream` 엔드포인트는 같은 제너레이터를 `sse()`로 감싼다. 로직이 두 벌이 되지 않으므로 갈라질 수 없다. 프론트는 `fetch` + `ReadableStream` 파서 하나와 진행 뷰 컴포넌트 하나를 세 화면이 공유한다.

**Tech Stack:** FastAPI `StreamingResponse` (`text/event-stream`) · pytest + `fastapi.testclient.TestClient` · Next.js 14 App Router · TypeScript strict · Tailwind + `design.md` 토큰 · `lucide-react`

**설계 근거 문서:** `docs/specs/2026-07-23-pipeline-progress-ui-design.md` (커밋 `edfa7a6`)

## Global Constraints

- **기존 엔드포인트 4개의 시그니처·응답 스키마·에러 코드는 바뀌지 않는다.** API 테스트는 전부 통과해야 한다.
- **추론은 전부 NPU.** 상용 LLM API 폴백 경로를 만들지 않는다 (AGENTS.md §0.1 계약 4).
- **집계 숫자는 LLM이 세지 않는다.** `sentiment`·`mention_count`·`bucket_distribution`은 DB 실측으로 덮어쓰는 현재 동작을 그대로 둔다 (AGENTS.md §0.1 계약 1).
- **화면의 모든 수치는 실측.** 추정치를 실측처럼 보여주지 않는다. 값이 없으면 `—`.
- **모델명을 프론트에 하드코딩하지 않는다.** 서버가 `detail.model`로 실어 보낸다 — LLM은 `Usage.model`, 임베딩은 `get_settings().embed_model`.
- **아이콘은 `lucide-react`. 시각 UI에 이모지 금지** (AGENTS.md §2 하드룰).
- **에러 톤은 `maroon`.** brand `red`와 절대 섞지 않는다 (`design.md` §1 시맨틱).
- Python은 `from __future__ import annotations`로 시작한다. 주석·문구는 한국어.
- 커밋은 작업 단위로 자주. **`main` 머지·배포는 하드게이트 — 사람 승인 없이 하지 않는다** (AGENTS.md §1).
- 로컬 검증 4종: `./.venv/Scripts/python.exe -m pytest api/tests -q` · `cd web && npm run typecheck` · `npm run build` · `npm run lint`

---

## File Structure

| 파일 | 책임 |
|---|---|
| `api/services/progress.py` (신규) | 이벤트 타입 · `Pipeline`(단계 선언/전이) · `sse()` · `drain()`. 도메인 로직 없음. |
| `api/routers/projects.py` (수정) | `run_guide` / `run_insight` / `run_material` / `run_research` / `run_web_materials` 제너레이터 + `/stream` 엔드포인트 5개. |
| `api/tests/test_progress.py` (신규) | `Pipeline`·`sse`·`drain` 단위 테스트. |
| `api/tests/test_pipeline_streams.py` (신규) | 5개 스트림의 선언/방출 일치 · `drain` 동치 · 실패 · skip. |
| `web/lib/sse.ts` (신규) | SSE 프레임 파서(순수 함수) + `streamSse()`. |
| `web/lib/pipeline.ts` (신규) | 이벤트 타입 + `usePipeline()` 훅. |
| `web/components/shared/pipeline-progress.tsx` (신규) | 전체 화면 진행 뷰(프레젠테이션 전용). |
| `web/lib/api.ts` (수정) | `apiUrl()` export + 스트림 경로 상수 + `uploadMaterial` angle 인자. |
| `design.md` (수정) | §5에 `작업 진행(파이프라인) 화면` 절 추가. |
| `web/app/projects/[id]/guide-panel.tsx` · `results-panel.tsx` · `web/app/projects/new/new-project-form.tsx` (수정) | 진행 뷰 연결. |

---

## Task 0: 자료 업로드 `angle` 누락 수정 (선행 블로커)

**왜 먼저인가:** `POST /api/projects/{pid}/material`은 `angle: str = Form(...)`을 **필수**로 받는데(`api/routers/projects.py:326`), 웹 클라이언트는 `form.append("file", file)`만 보낸다(`web/lib/api.ts:203-210`). 실제 요청은 FastAPI 검증에서 **422**로 떨어지고, 호출부는 그 예외를 조용히 삼킨다(`new-project-form.tsx:48-51`). 즉 **새 프로젝트 폼의 자료 업로드는 지금 동작하지 않는다.** 깨진 경로 위에 진행 화면을 얹으면 진행 화면이 실패만 보여준다.

**결정 사항:** 새 프로젝트 폼에는 슬롯 선택 UI가 없다. `angle` 기본값을 `"현상"`으로 둔다 — 폼 카피가 "도메인 자료를 올리면 그 용어·맥락을 반영해 질문을 만들어요"라 현상 슬롯이 가장 가깝다. 슬롯 선택 UI 추가는 이 계획의 범위 밖이다.

**Files:**
- Modify: `web/lib/api.ts:203-210`
- Modify: `web/app/projects/new/new-project-form.tsx:47`
- Test: `api/tests/test_material_endpoint.py` (기존 — 회귀 확인만)

- [ ] **Step 1: 현재 실패를 눈으로 확인한다**

API를 띄우고 angle 없이 업로드해 422를 재현한다.

```bash
./.venv/Scripts/python.exe -m uvicorn api.main:app --port 8099 &
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  -F "file=@README.md" http://localhost:8099/api/projects/PID/material
```

Expected: `422` (프로젝트가 없으면 먼저 `POST /api/projects`로 하나 만든다)

- [ ] **Step 2: 클라이언트가 angle 을 보내게 고친다**

`web/lib/api.ts`:

```ts
/** 참고 자료 업로드 (선택). 업로드하면 가이드 생성 시 도메인 맥락이 프롬프트에 주입된다.
 *  multipart 라 JSON 헬퍼가 아니라 transcribeAudio 처럼 FormData 로 보낸다.
 *  angle 은 서버 필수값(현상·원인·활용) — 빠지면 422 다. */
export async function uploadMaterial(
  pid: string,
  file: File,
  angle: MaterialAngle = "현상",
): Promise<MaterialUploadResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("angle", angle);
  const res = await fetch(`${BASE}/api/projects/${pid}/material`, { method: "POST", body: form });
  if (!res.ok) throw new ApiError(res.status, `upload material → ${res.status}`);
  return (await res.json()) as MaterialUploadResult;
}
```

같은 파일 타입 구역(`MaterialUploadResult` 선언 근처, `web/lib/api.ts:36`)에 추가:

```ts
/** 자료 슬롯 — api/routers/projects.py 의 검증값과 1:1. */
export type MaterialAngle = "현상" | "원인" | "활용";
```

- [ ] **Step 3: 실패를 삼키지 않게 고친다**

`new-project-form.tsx:45-51`을 교체:

```tsx
      if (file) {
        try {
          await uploadMaterial(p.id, file);
        } catch {
          // 프로젝트는 이미 생성됨 — 자료 업로드만 실패. 상세로 이동해 이어가게 두되,
          // 조용히 삼키지 않고 무엇이 안 됐는지 남긴다(원본: 한 달간 조용히 실패).
          setFormError("프로젝트는 만들었지만 자료 업로드에 실패했어요. 상세에서 다시 올려 주세요.");
        }
      }
```

- [ ] **Step 4: 재현 curl 이 200 이 되는지 확인**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  -F "file=@README.md" -F "angle=현상" http://localhost:8099/api/projects/PID/material
```

Expected: `200`

- [ ] **Step 5: 기존 테스트·타입 확인**

```bash
./.venv/Scripts/python.exe -m pytest api/tests/test_material_endpoint.py api/tests/test_project_material.py -q
cd web && npm run typecheck
```

Expected: 전부 통과

- [ ] **Step 6: 커밋**

```bash
git add web/lib/api.ts web/app/projects/new/new-project-form.tsx
git commit -m "자료 업로드가 필수 angle 을 빠뜨려 422 로 죽던 것을 고친다"
```

---

## Task 1: 진행 이벤트 헬퍼 (`api/services/progress.py`)

**Files:**
- Create: `api/services/progress.py`
- Test: `api/tests/test_progress.py`

**Interfaces:**
- Consumes: 없음 (신규 모듈)
- Produces:
  - `Event = dict[str, Any]`
  - `class Pipeline` — `__init__(steps: list[tuple[str, str]])`, `declare() -> Event`, `start(key, **detail) -> Event`, `progress(key, done: int, total: int) -> Event`, `done(key, **detail) -> Event`, `skip(key, **detail) -> Event`, `fail(key, message: str, status_code: int = 502) -> Event`
  - `sse(events: Iterator[Event]) -> Iterator[str]`
  - `drain(events: Iterator[Event]) -> Any`
  - `SSE_HEADERS: dict[str, str]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`api/tests/test_progress.py`:

```python
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
    assert p.progress("s", 3, 12) == {"step": "s", "status": "start", "detail": {"done": 3, "total": 12}}


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
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_progress.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.services.progress'`

- [ ] **Step 3: 최소 구현을 쓴다**

`api/services/progress.py`:

```python
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

# 프록시가 스트림을 버퍼링하면 진행 표시가 통째로 뭉쳐서 마지막에 한 번에 온다.
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class Pipeline:
    """단계를 미리 선언하고, 그 단계들의 전이 이벤트를 만든다.

    선언(declare)을 먼저 보내야 프론트가 아직 오지 않은 단계까지 회색으로 그려
    전체 길이를 처음부터 보여줄 수 있다. 선언에 없는 키를 내보내려 하면
    KeyError 로 즉시 터뜨린다 — 그릴 자리가 없는 이벤트를 조용히 흘리면
    선언과 실제가 갈라지고, 그 어긋남은 화면에서만 드러난다.
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
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_progress.py -q`
Expected: PASS (11 passed)

- [ ] **Step 5: 커밋**

```bash
git add api/services/progress.py api/tests/test_progress.py
git commit -m "진행 이벤트 헬퍼를 추가한다 — 스트림과 비스트림이 제너레이터 한 벌을 공유한다"
```

---

## Task 2: 가이드 생성 스트림

**Files:**
- Modify: `api/routers/projects.py:218-264` (`generate_guide`)
- Test: `api/tests/test_pipeline_streams.py` (신규)

**Interfaces:**
- Consumes: `Pipeline`, `sse`, `drain`, `SSE_HEADERS` (Task 1)
- Produces: `run_guide(p: Project, body: GuideGenerateIn) -> Iterator[Event]` — 마지막 이벤트가 `{"result": <InterviewGuide 를 model_dump 한 dict>}`

**단계 (6):** `material` 자료 요약 조합 · `evidence` 근거 검색 · `audience` 대상 청중 수집 · `llm` 문항 생성 · `normalize` 응답 버킷 정규화 · `quality` 품질 점검

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`api/tests/test_pipeline_streams.py`:

```python
"""무거운 작업의 SSE 스트림 — 선언/방출 일치 · drain 동치 · 실패 · skip.

LLM 은 전부 목킹한다(test_interview_moderator.py 패턴). 네트워크를 타지 않는다.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.routers import projects as pm
from api.schemas.models import GuideQuestion, InterviewGuide
from api.services.llm_client import LLMError, Usage


def _events(body: str) -> list[dict]:
    """SSE 응답 본문 → 이벤트 리스트."""
    return [json.loads(line[len("data: "):]) for line in body.split("\n\n") if line.startswith("data: ")]


@pytest.fixture()
def client():
    return TestClient(main.app)


@pytest.fixture()
def project(client):
    r = client.post("/api/projects", json={"topic": "아침 결식", "target": "20대 직장인"})
    assert r.status_code == 200
    return r.json()["id"]


@pytest.fixture()
def fake_guide_llm(monkeypatch):
    """가이드 생성 LLM 을 결정론 목으로 바꾼다."""
    guide = InterviewGuide(
        goal="왜 거르는가",
        questions=[GuideQuestion(id="q1", text="아침을 거르시나요?", goal="현상 확인", order=0,
                                 response_buckets=[])],
    )

    class _FakeLLM:
        def structured(self, *a, **k):
            return guide, Usage("furiosa-ai/Qwen3-32B-FP8", 120, 340)

    monkeypatch.setattr(pm, "get_llm", lambda: _FakeLLM())
    return guide


# ── 가이드 ───────────────────────────────────────────────────────
def test_guide_stream_declares_then_emits_only_declared_steps(client, project, fake_guide_llm):
    r = client.post(f"/api/projects/{project}/guide/stream", json={})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    evs = _events(r.text)

    assert "steps" in evs[0], "첫 이벤트는 단계 선언이어야 한다"
    declared = {s["key"] for s in evs[0]["steps"]}
    emitted = {e["step"] for e in evs if "step" in e}
    assert emitted <= declared, f"선언에 없는 단계가 방출됨: {emitted - declared}"
    assert declared == emitted, f"선언했지만 방출되지 않은 단계: {declared - emitted}"


def test_guide_stream_last_event_is_result(client, project, fake_guide_llm):
    evs = _events(client.post(f"/api/projects/{project}/guide/stream", json={}).text)
    assert "result" in evs[-1]
    assert evs[-1]["result"]["goal"] == "왜 거르는가"


def test_guide_stream_llm_step_carries_measured_usage(client, project, fake_guide_llm):
    evs = _events(client.post(f"/api/projects/{project}/guide/stream", json={}).text)
    llm_done = next(e for e in evs if e.get("step") == "llm" and e["status"] == "done")
    assert llm_done["detail"]["model"] == "furiosa-ai/Qwen3-32B-FP8"
    assert llm_done["detail"]["tokens"] == 340        # completion_tokens 실측
    assert llm_done["ms"] >= 0


def test_guide_stream_skips_evidence_without_materials(client, project, fake_guide_llm):
    # 자료가 없으면 RAG 검색을 통째로 건너뛴다(projects.py). "완료"로 위장하지 않는다.
    evs = _events(client.post(f"/api/projects/{project}/guide/stream", json={}).text)
    ev = next(e for e in evs if e.get("step") == "evidence" and e["status"] in ("done", "skip"))
    assert ev["status"] == "skip"


def test_guide_nonstream_matches_stream_result(client, project, fake_guide_llm):
    """두 겹 노출의 핵심 보증 — drain 경로가 스트림의 result 와 같아야 한다."""
    stream_result = _events(client.post(f"/api/projects/{project}/guide/stream", json={}).text)[-1]["result"]
    plain = client.post(f"/api/projects/{project}/guide", json={})
    assert plain.status_code == 200
    assert plain.json()["goal"] == stream_result["goal"]
    assert len(plain.json()["questions"]) == len(stream_result["questions"])


def test_guide_stream_emits_error_event_on_llm_failure(client, project, monkeypatch):
    class _BoomLLM:
        def structured(self, *a, **k):
            raise LLMError("NPU 응답 없음")

    monkeypatch.setattr(pm, "get_llm", lambda: _BoomLLM())
    evs = _events(client.post(f"/api/projects/{project}/guide/stream", json={}).text)
    err = next(e for e in evs if e.get("status") == "error")
    assert "가이드 생성에 실패했습니다" in err["error"]
    assert err["status_code"] == 502


def test_guide_nonstream_still_raises_502_on_llm_failure(client, project, monkeypatch):
    """기존 계약 회귀 — 비스트림은 지금과 똑같이 502 로 떨어져야 한다."""
    class _BoomLLM:
        def structured(self, *a, **k):
            raise LLMError("NPU 응답 없음")

    monkeypatch.setattr(pm, "get_llm", lambda: _BoomLLM())
    assert client.post(f"/api/projects/{project}/guide", json={}).status_code == 502


def test_guide_stream_404_before_stream_starts(client, fake_guide_llm):
    # 없는 프로젝트는 SSE 200 + 인밴드 에러가 아니라 진짜 404 여야 한다.
    assert client.post("/api/projects/nope/guide/stream", json={}).status_code == 404
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_pipeline_streams.py -q`
Expected: FAIL — `/guide/stream` 이 없어 404 (`assert r.status_code == 200` 실패)

- [ ] **Step 3: 구현한다**

`api/routers/projects.py` 상단 import 에 추가:

```python
from fastapi.responses import StreamingResponse

from ..services.progress import SSE_HEADERS, Event, Pipeline, drain, sse
```

그리고 `collections.abc.Iterator` 도 추가:

```python
from collections.abc import Iterator
```

`generate_guide`(218-264행)를 통째로 아래로 교체:

```python
_GUIDE_STEPS = [
    ("material", "자료 요약 조합"),
    ("evidence", "근거 검색"),
    ("audience", "대상 청중 수집"),
    ("llm", "문항 생성"),
    ("normalize", "응답 버킷 정규화"),
    ("quality", "품질 점검"),
]


def run_guide(p: Project, body: GuideGenerateIn) -> Iterator[Event]:
    """C-2 가이드 자동 생성 — 단계마다 이벤트를 흘리고 마지막에 result 를 낸다.

    이 제너레이터가 유일한 구현이다. 비스트림 엔드포인트는 drain 으로 소진하고,
    /stream 은 sse 로 감싼다. p 는 이미 검증된 프로젝트다(404 는 엔드포인트에서).
    """
    pid = p.id
    topic = body.topic.strip() or p.topic
    target = body.target.strip() or p.target
    pipe = Pipeline(_GUIDE_STEPS)
    yield pipe.declare()

    # 1. 자료 요약 조합
    yield pipe.start("material")
    slots = store.get_slot_summaries(pid)
    material = compose_guide_material(slots)
    yield pipe.done("material", slots=sum(1 for v in slots.values() if v))

    # 2. RAG 근거 검색 — 자료가 없으면 통째로 건너뛴다(임베딩 호출 자체를 안 한다)
    yield pipe.start("evidence")
    if not store.list_materials(pid):
        evidence = ""
        yield pipe.skip("evidence", reason="참고 자료 없음")
    else:
        evidence = _collect_evidence(pid, p)
        lines = [ln for ln in evidence.splitlines() if ln.strip()]
        yield pipe.done("evidence", found=len(lines), samples=_evidence_samples(lines))

    # 3. 대상 청중
    yield pipe.start("audience")
    audience = collect_personas(p)
    if audience:
        yield pipe.done("audience", personas=len(audience.splitlines()))
    else:
        yield pipe.skip("audience", reason="페르소나 코퍼스 비어 있음")

    # 4. 문항 생성 (NPU)
    yield pipe.start("llm")
    try:
        guide, usage = get_llm().structured(
            GUIDE_SYSTEM,
            guide_user(topic, target, material, p.motivation, p.utilization,
                       evidence=evidence, audience=audience),
            _GenGuide,  # goal 필수 스키마 — 비워 보내면 자가교정 재시도가 발동
            max_tokens=2000,
            timeout=get_settings().llm_guide_timeout,   # 무거운 단발 생성 — 인터뷰 30s 와 분리
        )
    except LLMError as e:
        yield pipe.fail("llm", f"가이드 생성에 실패했습니다: {e}", status_code=502)
        return
    yield pipe.done("llm", model=usage.model, tokens=usage.completion_tokens,
                    questions=len(guide.questions))

    # 5. 정규화 — 모델이 order/id 를 비워 보낼 수 있어 서버에서 확정한다. goal 이 text 에
    #    박혀 오는 사고도 여기서 결정론으로 분리한다.
    yield pipe.start("normalize")
    for i, q in enumerate(guide.questions):
        _split_goal_from_text(q)
        q.order = i
        q.id = q.id or f"q{i + 1}"
        _normalize_buckets(q)
    guide.goal = guide.goal or topic
    yield pipe.done("normalize", buckets=sum(len(q.response_buckets) for q in guide.questions))

    # 6. 저장을 품질 점검보다 먼저 한다 — 스트림이 끊겨도 3분짜리 NPU 작업이 날아가지
    #    않게. 품질 점검은 반환 가이드를 바꾸지 않는 로그 전용이라 뒤로 가도 의미가 같다.
    saved = store.save_guide(pid, guide)

    # 7. 비차단 품질 로그 (F8) — 유도신문·버킷 MECE 를 오프라인 규칙으로 자기평가한다.
    yield pipe.start("quality")
    try:
        report = evals.guide_quality_report(saved)
        if report["n_leading"] or report["bucket_warnings"]:
            log.warning(
                "guide quality: project=%s n_questions=%d n_leading=%d leading=%s bucket_warnings=%s",
                pid, report["n_questions"], report["n_leading"],
                report["leading"], report["bucket_warnings"],
            )
        yield pipe.done("quality", leading=report["n_leading"],
                        warnings=len(report["bucket_warnings"]))
    except Exception as e:  # noqa: BLE001 — 품질 로그가 가이드 생성을 막아선 안 된다
        log.warning("guide quality eval 실패", exc_info=True)
        yield pipe.skip("quality", reason=str(e))

    yield {"result": saved.model_dump()}


def _evidence_samples(lines: list[str]) -> list[dict[str, str]]:
    """발표 화면용 근거 미리보기 — 최대 2건, 각 120자. 자료 본문을 통째로 흘리지 않는다."""
    out: list[dict[str, str]] = []
    for ln in lines[:2]:
        text = ln.lstrip("- ")
        source = ""
        if " (출처: " in text:
            text, _, tail = text.partition(" (출처: ")
            source = tail.rstrip(")")
        out.append({"text": text[:120], "source": source})
    return out


@router.post("/{pid}/guide", response_model=InterviewGuide)
def generate_guide(pid: str, body: GuideGenerateIn) -> InterviewGuide:
    """C-2 가이드 자동 생성. 스트림과 같은 제너레이터를 소진해 결과만 돌려준다."""
    return drain(run_guide(_require(pid), body))


@router.post("/{pid}/guide/stream")
def generate_guide_stream(pid: str, body: GuideGenerateIn) -> StreamingResponse:
    """C-2 가이드 자동 생성 — 진행 화면용 SSE. 404 는 스트림 시작 전에 낸다."""
    p = _require(pid)
    return StreamingResponse(sse(run_guide(p, body)),
                             media_type="text/event-stream", headers=SSE_HEADERS)
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_pipeline_streams.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: 가이드 관련 기존 테스트가 안 깨졌는지 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest api/tests -q -k "guide or evidence or audience or material"`
Expected: 전부 통과. `response_model=InterviewGuide`가 dict 를 받아 검증하므로 `drain`이 dict 를 돌려줘도 응답 스키마는 동일하다.

- [ ] **Step 6: 커밋**

```bash
git add api/routers/projects.py api/tests/test_pipeline_streams.py
git commit -m "가이드 생성을 진행 이벤트 제너레이터로 바꾸고 /guide/stream 을 연다"
```

---

## Task 3: 인사이트 생성 스트림

**Files:**
- Modify: `api/routers/projects.py:450-541` (`build_insight`)
- Test: `api/tests/test_pipeline_streams.py` (Task 2 파일에 추가)

**Interfaces:**
- Consumes: `Pipeline`, `sse`, `drain`, `SSE_HEADERS` (Task 1)
- Produces: `run_insight(p: Project, sessions: list) -> Iterator[Event]`, `_completed_sessions(pid: str) -> list` (400 을 던지는 검증 함수 — 두 엔드포인트가 공유)

**단계 (5):** `sessions` 완료 세션 수집 · `summarize` 세션 요약 · `insight` 종합 인사이트 · `counts` 집계(DB 실측) · `qsummary` 문항별 요약

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`api/tests/test_pipeline_streams.py` 하단에 추가:

```python
# ── 인사이트 ──────────────────────────────────────────────────────
@pytest.fixture()
def two_completed_sessions(project, monkeypatch):
    """완료 세션 2건을 요약 없이 심는다 — summarize 단계가 LLM 을 2번 타게."""
    from api.schemas.models import Session, Turn
    from api.services import store as st

    sessions = [
        Session(id=f"s{i}", project_id=project, status="completed", asked=3) for i in (1, 2)
    ]
    turns = {
        "s1": [Turn(session_id="s1", role="respondent", text="시간이 없어서요")],
        "s2": [Turn(session_id="s2", role="respondent", text="입맛이 없어요")],
    }
    monkeypatch.setattr(st, "list_sessions", lambda pid: sessions)
    monkeypatch.setattr(st, "list_turns", lambda pid, sid: turns.get(sid, []))
    monkeypatch.setattr(st, "update_session", lambda pid, sid, patch: None)
    monkeypatch.setattr(st, "sentiment_counts", lambda pid: {"positive": 1, "negative": 1})
    monkeypatch.setattr(st, "theme_mention_counts", lambda pid, kw: {})
    monkeypatch.setattr(st, "bucket_distribution", lambda pid: {})
    monkeypatch.setattr(st, "save_insight", lambda pid, ins: ins)
    return sessions


@pytest.fixture()
def fake_insight_llm(monkeypatch):
    from api.schemas.models import Insight

    class _FakeLLM:
        def text(self, *a, **k):
            return "요약본", Usage("furiosa-ai/Qwen3-32B-FP8", 90, 40)

        def structured(self, system, user, schema, **k):
            return schema(overall="전체 요약", themes=[]), Usage("furiosa-ai/Qwen3-32B-FP8", 200, 500)

    monkeypatch.setattr(pm, "get_llm", lambda: _FakeLLM())
    return Insight


def test_insight_stream_reports_session_progress(client, project, two_completed_sessions,
                                                 fake_insight_llm):
    evs = _events(client.post(f"/api/projects/{project}/insight/stream").text)
    prog = [e for e in evs if e.get("step") == "summarize" and e.get("detail", {}).get("total")]
    assert prog, "세션 요약은 done/total 진행을 보고해야 한다"
    assert prog[-1]["detail"] == {"done": 2, "total": 2}


def test_insight_stream_counts_step_is_labelled_db_measured(client, project,
                                                            two_completed_sessions, fake_insight_llm):
    """AGENTS.md §0.1 계약 1 — 집계는 LLM 이 아니라 DB 가 센다. 화면에 그렇게 드러난다."""
    evs = _events(client.post(f"/api/projects/{project}/insight/stream").text)
    decl = next(e for e in evs if "steps" in e)["steps"]
    counts = next(s for s in decl if s["key"] == "counts")
    assert "DB" in counts["label"]
    done = next(e for e in evs if e.get("step") == "counts" and e["status"] == "done")
    assert done["detail"]["source"] == "db-group-by"


def test_insight_stream_no_completed_sessions_is_400(client, project, fake_insight_llm):
    assert client.post(f"/api/projects/{project}/insight/stream").status_code == 400


def test_insight_nonstream_matches_stream_result(client, project, two_completed_sessions,
                                                 fake_insight_llm):
    streamed = _events(client.post(f"/api/projects/{project}/insight/stream").text)[-1]["result"]
    plain = client.post(f"/api/projects/{project}/insight")
    assert plain.status_code == 200
    assert plain.json()["overall"] == streamed["overall"]
    assert plain.json()["session_count"] == streamed["session_count"]
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_pipeline_streams.py -q -k insight`
Expected: FAIL — `/insight/stream` 없음 (404 ≠ 200)

- [ ] **Step 3: 구현한다**

`api/routers/projects.py`의 `build_insight`(450-541행)를 아래로 교체:

```python
_INSIGHT_STEPS = [
    ("sessions", "완료 세션 수집"),
    ("summarize", "세션 요약"),
    ("insight", "종합 인사이트"),
    ("counts", "감정·테마·버킷 분포 — DB group-by (LLM 아님)"),
    ("qsummary", "문항별 요약"),
]


def _completed_sessions(pid: str) -> list:
    """완료 세션 목록. 없으면 기존과 같은 400 을 낸다(스트림 시작 전에 판정)."""
    sessions = [s for s in store.list_sessions(pid) if s.status == "completed"]
    if not sessions:
        raise HTTPException(400, "완료된 인터뷰가 아직 없습니다.")
    return sessions


def run_insight(p: Project, sessions: list) -> Iterator[Event]:
    """M-4 요약·집계 — 완료 세션의 요약을 모아 프로젝트 인사이트를 만든다."""
    pid = p.id
    guide = store.get_guide(pid)
    goal = guide.goal if guide else p.topic
    pipe = Pipeline(_INSIGHT_STEPS)
    yield pipe.declare()

    yield pipe.start("sessions")
    yield pipe.done("sessions", total=len(sessions))

    # 1. 세션 요약 — 이미 요약이 있으면 LLM 을 안 태운다(재분석이 왜 빠른지 화면에 설명된다)
    llm = get_llm()
    yield pipe.start("summarize")
    summaries: list[str] = []
    cached = 0
    for i, s in enumerate(sessions, start=1):
        if s.summary:
            summaries.append(s.summary)
            cached += 1
            yield pipe.progress("summarize", i, len(sessions))
            continue
        turns = store.list_turns(pid, s.id)
        if not turns:
            yield pipe.progress("summarize", i, len(sessions))
            continue
        transcript = "\n".join(
            f"{'진행자' if t.role == 'moderator' else '응답자'}: {t.text}" for t in turns
        )
        try:
            summary, _ = llm.text(
                SESSION_SUMMARY_SYSTEM, session_summary_user(goal, transcript), max_tokens=500
            )
        except LLMError as e:
            log.warning("세션 요약 실패 (%s): %s", s.id, e)
            yield pipe.progress("summarize", i, len(sessions))
            continue
        store.update_session(pid, s.id, {"summary": summary})
        summaries.append(summary)
        yield pipe.progress("summarize", i, len(sessions))

    if not summaries:
        yield pipe.fail("summarize", "세션 요약 생성에 모두 실패했습니다.", status_code=502)
        return
    yield pipe.done("summarize", done=len(summaries), total=len(sessions), cached=cached)

    # 2. 종합 인사이트
    yield pipe.start("insight")
    try:
        insight, usage = llm.structured(
            INSIGHT_SYSTEM, insight_user(p.topic, summaries), Insight, max_tokens=3000
        )
    except LLMError as e:
        yield pipe.fail("insight", f"집계 생성에 실패했습니다: {e}", status_code=502)
        return

    # overall 이 비는 경우가 실제로 나온다(구조화 출력에서 긴 필드가 누락).
    # 대시보드 최상단이라 비어 있으면 티가 크다 — 텍스트 호출로 한 번 더 받는다.
    if not (insight.overall or "").strip():
        log.warning("insight.overall 이 비어 재생성 (project=%s)", pid)
        try:
            insight.overall, _ = llm.text(
                SESSION_SUMMARY_SYSTEM,
                insight_user(p.topic, summaries) + "\n\n위 응답 전체를 3~5문장으로 요약하세요.",
                max_tokens=600,
            )
        except LLMError as e:
            log.warning("overall 재생성 실패: %s", e)
    yield pipe.done("insight", model=usage.model, tokens=usage.completion_tokens,
                    themes=len(insight.themes))

    # 3. LLM 이 낸 '숫자'는 버리고 DB 실측으로 덮어쓴다.
    #    주제·요약·인용 같은 해석은 LLM 이 잘하지만, 세는 일은 LLM 에게 맡기면 안 된다.
    yield pipe.start("counts")
    insight.sentiment = store.sentiment_counts(pid)
    mentions = store.theme_mention_counts(pid, {t.theme: t.keywords for t in insight.themes})
    for t in insight.themes:
        t.mention_count = mentions.get(t.theme, 0)
    insight.bucket_distribution = store.bucket_distribution(pid)   # F6.4 — 계약 1 과 동일
    insight.session_count = len(summaries)
    yield pipe.done("counts", source="db-group-by",
                    sentiment=sum(insight.sentiment.values()),
                    buckets=len(insight.bucket_distribution))

    # 4. 문항별 AI 요약(F6.3) — 여기부터 다시 LLM '해석' 출력이다. 위 DB 실측 카운트는
    #    절대 건드리지 않는다. best-effort: 실패해도 인사이트 전체를 막지 않는다.
    yield pipe.start("qsummary")
    grouped = _answers_by_question([store.list_turns(pid, s.id) for s in sessions])
    items = []
    if grouped:
        questions = guide.questions if guide else []
        items = [
            {"question_id": q.id, "question_text": q.text, "answers": grouped[q.id]}
            for q in questions
            if grouped.get(q.id)
        ]
    if not items:
        yield pipe.skip("qsummary", reason="요약할 문항 응답 없음")
    else:
        try:
            qs_out, _ = llm.structured(
                QUESTION_SUMMARY_SYSTEM, question_summary_user(items),
                QuestionSummariesOut, max_tokens=3000,
            )
            insight.question_summaries = qs_out.items
            yield pipe.done("qsummary", items=len(qs_out.items))
        except LLMError as e:
            log.warning("문항별 요약 생성 실패 (project=%s): %s", pid, e)
            yield pipe.skip("qsummary", reason=str(e))

    yield {"result": store.save_insight(pid, insight).model_dump()}


@router.post("/{pid}/insight", response_model=Insight)
def build_insight(pid: str) -> Insight:
    """M-4 요약·집계. 스트림과 같은 제너레이터를 소진해 결과만 돌려준다."""
    p = _require(pid)
    return drain(run_insight(p, _completed_sessions(pid)))


@router.post("/{pid}/insight/stream")
def build_insight_stream(pid: str) -> StreamingResponse:
    """M-4 요약·집계 — 진행 화면용 SSE. 404·400 은 스트림 시작 전에 낸다."""
    p = _require(pid)
    sessions = _completed_sessions(pid)
    return StreamingResponse(sse(run_insight(p, sessions)),
                             media_type="text/event-stream", headers=SSE_HEADERS)
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_pipeline_streams.py -q`
Expected: PASS (12 passed)

- [ ] **Step 5: 인사이트 관련 기존 테스트 회귀 확인**

Run: `./.venv/Scripts/python.exe -m pytest api/tests -q -k "insight or question_summ or bucket"`
Expected: 전부 통과

- [ ] **Step 6: 커밋**

```bash
git add api/routers/projects.py api/tests/test_pipeline_streams.py
git commit -m "인사이트 생성을 진행 이벤트 제너레이터로 바꾸고 /insight/stream 을 연다"
```

---

## Task 4: 자료 업로드 · 웹 리서치 스트림

**Files:**
- Modify: `api/routers/projects.py:267-346` (`research_candidates`, `add_web_materials`, `upload_material`)
- Test: `api/tests/test_pipeline_streams.py` (추가)

**Interfaces:**
- Consumes: `Pipeline`, `sse`, `drain`, `SSE_HEADERS` (Task 1)
- Produces: `run_material(pid: str, filename: str, raw: bytes, angle: str) -> Iterator[Event]` · `run_research(p: Project) -> Iterator[Event]` · `run_web_materials(pid: str, picked: list, skipped: list[str]) -> Iterator[Event]`

**단계:** 자료 = `extract`·`chunk`·`embed`·`slot` / 리서치 = `queries`·`serp` / 웹 자료 = `crawl`·`store`·`embed`·`slot`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`api/tests/test_pipeline_streams.py` 하단에 추가:

```python
# ── 자료 업로드 ───────────────────────────────────────────────────
def test_material_stream_reports_chunks_and_embed_model(client, project, monkeypatch):
    import api.briefing.pipeline as bp

    monkeypatch.setattr(bp, "embed_texts", lambda texts: [[0.0] * 8 for _ in texts])
    monkeypatch.setattr(pm.briefing_pipeline, "refresh_slot", lambda pid, angle: None)

    r = client.post(
        f"/api/projects/{project}/material/stream",
        files={"file": ("brief.txt", "아침을 거르는 이유에 대한 조사 자료. " * 40, "text/plain")},
        data={"angle": "현상"},
    )
    assert r.status_code == 200
    evs = _events(r.text)
    declared = {s["key"] for s in evs[0]["steps"]}
    assert declared == {"extract", "chunk", "embed", "slot"}

    chunk = next(e for e in evs if e.get("step") == "chunk" and e["status"] == "done")
    assert chunk["detail"]["chunks"] >= 1
    embed = next(e for e in evs if e.get("step") == "embed" and e["status"] == "done")
    assert embed["detail"]["model"] == "furiosa-ai/Qwen3-Embedding-8B"   # 설정값, 하드코딩 아님
    assert "result" in evs[-1]


def test_material_stream_rejects_bad_angle_before_streaming(client, project):
    r = client.post(
        f"/api/projects/{project}/material/stream",
        files={"file": ("a.txt", "본문", "text/plain")},
        data={"angle": "엉뚱한슬롯"},
    )
    assert r.status_code == 400


# ── 웹 리서치 ─────────────────────────────────────────────────────
def test_research_stream_declares_queries_and_serp(client, project, monkeypatch):
    from api.services import research as rs

    monkeypatch.setattr(pm.research, "research_queries",
                        lambda *a, **k: {"현상": ["아침 결식률"]})
    monkeypatch.setattr(pm.research, "search",
                        lambda sq: [rs.Candidate(angle="현상", title="t", url="http://x", snippet="s")])

    evs = _events(client.post(f"/api/projects/{project}/research/stream").text)
    assert {s["key"] for s in evs[0]["steps"]} == {"queries", "serp"}
    serp = next(e for e in evs if e.get("step") == "serp" and e["status"] == "done")
    assert serp["detail"]["candidates"] == 1
    assert evs[-1]["result"]["candidates"][0]["url"] == "http://x"


def test_research_nonstream_unchanged(client, project, monkeypatch):
    from api.services import research as rs

    monkeypatch.setattr(pm.research, "research_queries", lambda *a, **k: {"현상": ["q"]})
    monkeypatch.setattr(pm.research, "search",
                        lambda sq: [rs.Candidate(angle="현상", title="t", url="http://x", snippet="s")])
    r = client.post(f"/api/projects/{project}/research")
    assert r.status_code == 200
    assert r.json()["candidates"][0]["url"] == "http://x"
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_pipeline_streams.py -q -k "material_stream or research_stream"`
Expected: FAIL — 스트림 엔드포인트 없음

- [ ] **Step 3: 구현한다**

`api/routers/projects.py`에 추가 — `research_candidates`·`add_web_materials`·`upload_material` 를 교체한다.

```python
_MATERIAL_STEPS = [
    ("extract", "텍스트 추출"),
    ("chunk", "청킹"),
    ("embed", "임베딩"),
    ("slot", "슬롯 요약"),
]
_RESEARCH_STEPS = [("queries", "검색어 생성"), ("serp", "웹 검색")]
# chunk·embed·slot 은 _index_and_summarize 가 쓰는 키와 반드시 같아야 한다
# (Pipeline 이 선언에 없는 키를 KeyError 로 막는다).
_WEB_STEPS = [
    ("crawl", "본문 수집"),
    ("store", "자료 저장"),
    ("chunk", "청킹"),
    ("embed", "임베딩"),
    ("slot", "슬롯 요약"),
]


def _index_and_summarize(pid: str, created: list, pipe: Pipeline) -> Iterator[Event]:
    """증분 인덱싱 + 건드린 슬롯 재요약을 단계 이벤트로 감싼다.

    pipeline.add_materials_incremental 과 같은 일을 하되, 청크 수를 미리 세어
    화면에 보여줄 수 있게 임베딩 앞뒤로 단계를 나눈다. 실패 흡수 동작은 동일하다.
    """
    from ..briefing.pipeline import chunks_with_angle

    n_chunks = sum(len(chunks_with_angle([m])) for m in created)
    yield pipe.start("chunk")
    yield pipe.done("chunk", chunks=n_chunks)

    yield pipe.start("embed")
    failed = 0
    for m in created:
        try:
            briefing_pipeline.index_material(pid, m)
        except Exception as e:  # noqa: BLE001 — 임베딩 일시 장애가 수집을 죽이지 않게
            failed += 1
            log.warning("증분 인덱싱 실패, 다음 refresh 로 미룸 (project=%s, material=%s): %s",
                        pid, getattr(m, "id", "?"), e)
    if failed and failed == len(created):
        yield pipe.skip("embed", reason="인덱싱 실패 — 다음 refresh 가 따라잡는다")
    else:
        yield pipe.done("embed", chunks=n_chunks, model=get_settings().embed_model,
                        failed=failed)

    angles = sorted({m.angle for m in created})
    yield pipe.start("slot")
    for angle in angles:
        briefing_pipeline.refresh_slot(pid, angle)
    yield pipe.done("slot", angles=angles)


def run_material(pid: str, filename: str, raw: bytes, angle: str) -> Iterator[Event]:
    """수동 업로드 → materials 풀에 저장 → RAG 증분 인덱싱·슬롯 재요약."""
    pipe = Pipeline(_MATERIAL_STEPS)
    yield pipe.declare()

    yield pipe.start("extract")
    try:
        text = extract_text(filename, raw)
    except MaterialError as e:
        yield pipe.fail("extract", str(e), status_code=400)
        return
    if not text.strip():
        yield pipe.fail("extract", "자료에서 텍스트를 추출하지 못했습니다(스캔 PDF 등).",
                        status_code=400)
        return
    yield pipe.done("extract", chars=len(text))

    m = store.create_material(Material(
        project_id=pid, source="upload", angle=angle,
        title=filename or "업로드", text=text,
    ))
    yield from _index_and_summarize(pid, [m], pipe)
    yield {"result": {"project_id": pid, "chars": len(text), "angle": angle}}


def _check_angle(angle: str) -> None:
    """스트림 시작 전 검증 — 두 엔드포인트가 공유한다."""
    if angle not in ("현상", "원인", "활용"):
        raise HTTPException(400, "슬롯(angle)은 현상·원인·활용 중 하나여야 합니다.")


@router.post("/{pid}/material")
async def upload_material(pid: str, file: UploadFile, angle: str = Form(...)) -> dict:
    """수동 업로드 → materials 풀에 저장(유저가 슬롯 지정). RAG 재인덱싱·요약."""
    _require(pid)
    _check_angle(angle)
    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(400, "파일이 너무 큽니다(최대 10MB).")
    return drain(run_material(pid, file.filename or "", raw, angle))


@router.post("/{pid}/material/stream")
async def upload_material_stream(pid: str, file: UploadFile, angle: str = Form(...)) -> StreamingResponse:
    """수동 업로드 — 진행 화면용 SSE. 파일은 스트림 시작 전에 전부 읽는다."""
    _require(pid)
    _check_angle(angle)
    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(400, "파일이 너무 큽니다(최대 10MB).")
    return StreamingResponse(sse(run_material(pid, file.filename or "", raw, angle)),
                             media_type="text/event-stream", headers=SSE_HEADERS)


def run_research(p: Project) -> Iterator[Event]:
    """웹 리서치 — 브리프로 검색어 생성 → SERP 후보 반환(크롤 전·미저장)."""
    pipe = Pipeline(_RESEARCH_STEPS)
    yield pipe.declare()

    yield pipe.start("queries")
    slot_queries = research.research_queries(p.topic, p.target, p.motivation, p.utilization)
    yield pipe.done("queries", queries=sum(len(v) for v in slot_queries.values()))

    yield pipe.start("serp")
    try:
        cands = research.search(slot_queries)
    except research.ResearchError as e:
        yield pipe.fail("serp", f"웹 검색에 실패했습니다: {e}", status_code=502)
        return
    yield pipe.done("serp", candidates=len(cands))

    yield {"result": {"candidates": [
        {"angle": c.angle, "title": c.title, "url": c.url, "snippet": c.snippet}
        for c in cands
    ]}}


@router.post("/{pid}/research")
def research_candidates(pid: str) -> dict:
    return drain(run_research(_require(pid)))


@router.post("/{pid}/research/stream")
def research_candidates_stream(pid: str) -> StreamingResponse:
    p = _require(pid)
    return StreamingResponse(sse(run_research(p)),
                             media_type="text/event-stream", headers=SSE_HEADERS)


def _pick_web_candidates(pid: str, body: WebSelectIn) -> tuple[list, list[str]]:
    """중복 URL(요청 내·기존 풀) 제거. 스트림 시작 전에 400 을 판정한다."""
    if not body.selected:
        raise HTTPException(400, "선택된 자료가 없습니다.")
    existing = {m.url for m in store.list_materials(pid) if m.url}
    picked: list = []
    seen: set[str] = set()
    skipped: list[str] = []
    for c in body.selected:
        if not c.url:
            continue
        if c.url in existing or c.url in seen:
            skipped.append(c.url)
            continue
        seen.add(c.url)
        picked.append(c)
    return picked, skipped


def run_web_materials(pid: str, picked: list, skipped: list[str]) -> Iterator[Event]:
    """선택 후보 크롤 → materials 저장 → 증분 인덱싱·요약."""
    pipe = Pipeline(_WEB_STEPS)
    yield pipe.declare()

    if not picked:                                    # 전부 중복/무효
        for key in ("crawl", "store", "chunk", "embed", "slot"):
            yield pipe.skip(key, reason="새로 받을 자료 없음")
        yield {"result": {"stored": 0, "failed": [], "skipped": skipped}}
        return

    yield pipe.start("crawl")
    try:
        bodies = research.crawl([c.url for c in picked])
    except research.ResearchError as e:
        yield pipe.fail("crawl", f"본문 수집에 실패했습니다: {e}", status_code=502)
        return
    yield pipe.done("crawl", fetched=sum(1 for v in bodies.values() if (v or "").strip()),
                    requested=len(picked))

    yield pipe.start("store")
    created: list = []
    failed: list[str] = []
    for c in picked:
        text = (bodies.get(c.url) or "").strip()
        if not text:
            failed.append(c.url)                      # 크롤 실패분(같은 루프에서 판정)
            continue
        created.append(store.create_material(Material(
            project_id=pid, source="web", angle=c.angle,
            url=c.url, title=c.title or c.url, text=text,
        )))
    yield pipe.done("store", stored=len(created), failed=len(failed))

    if created:                                        # 저장분 있을 때만 후처리
        yield from _index_and_summarize(pid, created, pipe)
    else:
        for key in ("chunk", "embed", "slot"):
            yield pipe.skip(key, reason="저장된 자료 없음")

    yield {"result": {"stored": len(created), "failed": failed, "skipped": skipped}}


@router.post("/{pid}/materials/web")
def add_web_materials(pid: str, body: WebSelectIn) -> dict:
    _require(pid)
    picked, skipped = _pick_web_candidates(pid, body)
    return drain(run_web_materials(pid, picked, skipped))


@router.post("/{pid}/materials/web/stream")
def add_web_materials_stream(pid: str, body: WebSelectIn) -> StreamingResponse:
    _require(pid)
    picked, skipped = _pick_web_candidates(pid, body)
    return StreamingResponse(sse(run_web_materials(pid, picked, skipped)),
                             media_type="text/event-stream", headers=SSE_HEADERS)
```

> **불변식:** `_index_and_summarize` 가 내보내는 키(`chunk`·`embed`·`slot`)는 그 함수를 부르는 모든 파이프라인의 선언에 들어 있어야 한다. `Pipeline._check` 가 선언에 없는 키를 `KeyError` 로 막으므로, 빠지면 테스트가 아니라 실행이 먼저 터진다.

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_pipeline_streams.py -q`
Expected: PASS (전체)

- [ ] **Step 5: 자료·리서치 기존 테스트 회귀 확인**

Run: `./.venv/Scripts/python.exe -m pytest api/tests -q -k "material or research or web"`
Expected: 전부 통과

- [ ] **Step 6: 전체 스위트**

Run: `./.venv/Scripts/python.exe -m pytest api/tests -q`
Expected: 전부 통과 (기존 276건 + 신규)

- [ ] **Step 7: 커밋**

```bash
git add api/routers/projects.py api/tests/test_pipeline_streams.py
git commit -m "자료 업로드·웹 리서치에도 진행 이벤트 스트림을 연다"
```

---

## Task 5: `design.md` 에 진행 화면 절을 추가한다 (프론트 구현 전)

**Files:**
- Modify: `design.md` (§5 "상태 화면" 절 바로 뒤)

**왜 코드보다 먼저인가:** AGENTS.md §2 — "코드 전에 디자인 시스템 정본(`design.md`)을 먼저 못박고 구현은 이걸 근거로만". 현재 §5는 로딩을 "스켈레톤 시머(텍스트 없음)"로만 규정해서 단계 이름이 보이는 화면은 시스템에 없는 범주다.

- [ ] **Step 1: 절을 추가한다**

`design.md` 의 `### 상태 화면 …` 절 바로 아래에 삽입:

```markdown
### 작업 진행(파이프라인) 화면 — 의뢰자

수 초~수 분 걸리는 서버 작업(가이드 생성·인사이트 생성·자료 수집)이 도는 동안 띄우는 전체 화면.
**스켈레톤과 섞지 않는다** — 1초 미만 예상이면 스켈레톤, 그 이상이면 이 화면이다.

- **배치:** 콘텐츠 영역 전체. 사이드바·콘텐츠 헤더바는 유지(길을 잃지 않게).
- **구성:** 제목(무엇을 하는 중인지) → mono 경과 타이머 → 단계 리스트 → 하단 요약 바(n/N 단계 · 토큰 · 백그라운드로 두기).
- **단계 아이콘** (전부 `lucide-react`, **이모지 금지**):
  `check`=완료 · `loader-2`(회전)=진행 · `circle`=대기 · `minus`=건너뜀 · `alert-triangle`=실패.
- **색:** 진행 중 `red`(NPU가 일하는 중) · 완료 `go` · 대기·건너뜀 `ink-faint` · 실패 `maroon`
  (brand red 와 절대 안 섞음 — §1 시맨틱).
- **수치 = 텔레메트리 mono.** 소요 시간·토큰·건수는 **서버 실측만** 쓴다. 클라이언트가 추정하지
  않는다. 값이 없으면 `—`(벤치마크 §5 와 같은 규칙). 모델명도 서버가 보낸 값을 쓴다.
- **모션:** `loader-2` 회전만. `prefers-reduced-motion` 은 globals.css 전역 규칙이 처리한다.
- **중단 버튼 문구는 "백그라운드로 두기".** 이미 떠난 NPU 호출을 죽일 수 없으므로 "취소"는 거짓말이다.
```

- [ ] **Step 2: 커밋**

```bash
git add design.md
git commit -m "design.md 에 작업 진행 화면 규약을 못박는다"
```

---

## Task 6: SSE 파서 (`web/lib/sse.ts`)

**Files:**
- Create: `web/lib/sse.ts`
- Modify: `web/lib/api.ts` (`apiUrl` export 추가)

**Interfaces:**
- Consumes: 없음
- Produces:
  - `parseSseBuffer(buffer: string): { payloads: string[]; rest: string }`
  - `streamSse<T>(url: string, init: RequestInit, onEvent: (e: T) => void, signal?: AbortSignal): Promise<void>`
  - `web/lib/api.ts` 에 `export const apiUrl = (path: string) => \`${BASE}${path}\`;`

> **테스트 참고:** 웹에는 JS 테스트 러너가 없다(`web/package.json` 에 jest/vitest 없음). 러너를 새로 들이는 것은 이 계획의 범위 밖이다. 대신 파서를 **순수 함수로 분리**해 나중에 테스트 가능하게 두고, 검증은 `npm run typecheck` + `npm run build` + **로컬 API 상대 실동작 확인**(Task 12)으로 한다.

- [ ] **Step 1: `apiUrl` 을 export 한다**

`web/lib/api.ts` 의 `const BASE = …` 바로 아래:

```ts
/** 절대 API URL — fetch 를 직접 쓰는 곳(SSE·multipart)에서 BASE 를 다시 짜지 않게. */
export const apiUrl = (path: string) => `${BASE}${path}`;
```

- [ ] **Step 2: 파서를 쓴다**

`web/lib/sse.ts`:

```ts
// SSE 파서 — fetch + ReadableStream. EventSource 는 POST 를 못 보내서 쓸 수 없다.
// 서버 포맷은 api/services/progress.py 의 sse(): `data: {json}\n\n`.

/** 버퍼에서 완성된 프레임의 data 페이로드만 뽑고, 남은 꼬리를 돌려준다(순수 함수). */
export function parseSseBuffer(buffer: string): { payloads: string[]; rest: string } {
  const frames = buffer.split("\n\n");
  const rest = frames.pop() ?? "";
  const payloads: string[] = [];
  for (const frame of frames) {
    for (const line of frame.split("\n")) {
      if (line.startsWith("data:")) payloads.push(line.slice(5).trim());
    }
  }
  return { payloads, rest };
}

/** SSE 를 끝까지 읽으며 이벤트마다 onEvent 를 부른다. 중단은 signal 로. */
export async function streamSse<T>(
  url: string,
  init: RequestInit,
  onEvent: (event: T) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(url, { ...init, signal, cache: "no-store" });
  if (!res.ok || !res.body) {
    throw new Error(`${init.method ?? "GET"} ${url} → ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { payloads, rest } = parseSseBuffer(buffer);
    buffer = rest;
    for (const p of payloads) {
      if (!p) continue;
      onEvent(JSON.parse(p) as T);
    }
  }
}
```

- [ ] **Step 3: 타입 검사**

Run: `cd web && npm run typecheck`
Expected: 에러 없음

- [ ] **Step 4: 커밋**

```bash
git add web/lib/sse.ts web/lib/api.ts
git commit -m "SSE 파서를 추가한다 — EventSource 대신 fetch 스트림"
```

---

## Task 7: 파이프라인 훅 (`web/lib/pipeline.ts`)

**Files:**
- Create: `web/lib/pipeline.ts`

**Interfaces:**
- Consumes: `streamSse` (Task 6), `apiUrl` (Task 6)
- Produces:
  - `type StepStatus = "wait" | "run" | "done" | "skip" | "error"`
  - `type StepView = { key: string; label: string; status: StepStatus; ms?: number; detail?: Record<string, unknown> }`
  - `type PipelineState = { running: boolean; steps: StepView[]; elapsedMs: number; tokens: number; error: string | null }`
  - `usePipeline<T>(): { state: PipelineState; run: (path: string, init: RequestInit) => Promise<T | null>; detach: () => void }`

- [ ] **Step 1: 훅을 쓴다**

`web/lib/pipeline.ts`:

```ts
"use client";

// 진행 이벤트 소비 훅 — 서버(api/services/progress.py)가 보내는 4종 이벤트를 화면 상태로 접는다.
// 수치는 전부 서버 실측을 그대로 쓴다. 경과 타이머만 클라이언트 벽시계다(추정이 아니다).
import { useCallback, useEffect, useRef, useState } from "react";

import { apiUrl } from "./api";
import { streamSse } from "./sse";

export type StepStatus = "wait" | "run" | "done" | "skip" | "error";

export type StepView = {
  key: string;
  label: string;
  status: StepStatus;
  ms?: number;
  detail?: Record<string, unknown>;
};

type ServerEvent =
  | { steps: { key: string; label: string }[] }
  | { step: string; status: "start" | "done" | "skip" | "error"; ms?: number; error?: string;
      detail?: Record<string, unknown> }
  | { result: unknown }
  | { error: string };

export type PipelineState = {
  running: boolean;
  steps: StepView[];
  elapsedMs: number;
  tokens: number;
  error: string | null;
};

const IDLE: PipelineState = { running: false, steps: [], elapsedMs: 0, tokens: 0, error: null };

export function usePipeline<T>() {
  const [state, setState] = useState<PipelineState>(IDLE);
  const abortRef = useRef<AbortController | null>(null);
  const startRef = useRef(0);

  // 경과 타이머 — 진행 중에만 돈다.
  useEffect(() => {
    if (!state.running) return;
    const id = window.setInterval(
      () => setState((s) => ({ ...s, elapsedMs: Date.now() - startRef.current })),
      100,
    );
    return () => window.clearInterval(id);
  }, [state.running]);

  const detach = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setState(IDLE);
  }, []);

  const run = useCallback(async (path: string, init: RequestInit): Promise<T | null> => {
    const ac = new AbortController();
    abortRef.current = ac;
    startRef.current = Date.now();
    setState({ ...IDLE, running: true });

    let result: T | null = null;
    try {
      await streamSse<ServerEvent>(apiUrl(path), { method: "POST", ...init }, (ev) => {
        if ("steps" in ev) {
          setState((s) => ({
            ...s,
            steps: ev.steps.map((d) => ({ key: d.key, label: d.label, status: "wait" as const })),
          }));
          return;
        }
        if ("result" in ev) {
          result = ev.result as T;
          return;
        }
        if ("error" in ev && !("step" in ev)) {
          setState((s) => ({ ...s, error: ev.error }));
          return;
        }
        if (!("step" in ev)) return;

        const next: StepStatus =
          ev.status === "start" ? "run" : ev.status === "done" ? "done"
          : ev.status === "skip" ? "skip" : "error";
        const tokenDelta = Number(ev.detail?.tokens ?? 0);
        setState((s) => ({
          ...s,
          tokens: s.tokens + (ev.status === "done" ? tokenDelta : 0),
          error: ev.status === "error" ? (ev.error ?? "작업에 실패했어요.") : s.error,
          steps: s.steps.map((st) =>
            st.key === ev.step
              ? { ...st, status: next, ms: ev.ms ?? st.ms, detail: ev.detail ?? st.detail }
              : st,
          ),
        }));
      }, ac.signal);
    } catch (e) {
      // 사용자가 백그라운드로 두면 abort 가 뜬다 — 실패가 아니다.
      if ((e as Error)?.name !== "AbortError") {
        setState((s) => ({ ...s, error: "작업 중 연결이 끊겼어요." }));
      }
      setState((s) => ({ ...s, running: false }));
      return null;
    }
    setState((s) => ({ ...s, running: false }));
    return result;
  }, []);

  return { state, run, detach };
}
```

- [ ] **Step 2: 타입 검사**

Run: `cd web && npm run typecheck`
Expected: 에러 없음

- [ ] **Step 3: 커밋**

```bash
git add web/lib/pipeline.ts
git commit -m "진행 이벤트를 화면 상태로 접는 usePipeline 훅을 추가한다"
```

---

## Task 8: 진행 뷰 컴포넌트 (`pipeline-progress.tsx`)

**Files:**
- Create: `web/components/shared/pipeline-progress.tsx`
- Modify: `web/components/shared/index.ts`

**Interfaces:**
- Consumes: `PipelineState`, `StepView` (Task 7)
- Produces: `<PipelineProgress title state onDetach onRetry />` — 프레젠테이션 전용(fetch 안 함)

- [ ] **Step 1: 컴포넌트를 쓴다**

`web/components/shared/pipeline-progress.tsx`:

```tsx
"use client";

// 작업 진행 화면 — design.md §5 "작업 진행(파이프라인) 화면".
// 프레젠테이션 전용이다: 스스로 fetch 하지 않고 usePipeline 이 접어 준 상태만 그린다.
// 수치는 서버 실측만 쓴다. 값이 없으면 "—"(추정치를 실측처럼 보여주지 않는다).
import { AlertTriangle, Check, Circle, Loader2, Minus, RotateCw } from "lucide-react";

import { Button } from "./button";
import { cn } from "@/lib/utils";
import type { PipelineState, StepView } from "@/lib/pipeline";

function clock(ms: number): string {
  const total = Math.floor(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function StepIcon({ status }: { status: StepView["status"] }) {
  const base = "h-4 w-4 shrink-0";
  if (status === "done") return <Check className={cn(base, "text-go")} aria-hidden="true" />;
  if (status === "run")
    return <Loader2 className={cn(base, "animate-spin text-red")} aria-hidden="true" />;
  if (status === "skip") return <Minus className={cn(base, "text-ink-faint")} aria-hidden="true" />;
  if (status === "error")
    return <AlertTriangle className={cn(base, "text-maroon")} aria-hidden="true" />;
  return <Circle className={cn(base, "text-ink-faint/50")} aria-hidden="true" />;
}

/** 단계가 실제로 무엇을 했는지 — 서버가 보낸 detail 만 쓴다. */
function StepDetail({ step }: { step: StepView }) {
  const d = step.detail ?? {};
  const samples = Array.isArray(d.samples) ? (d.samples as { text: string; source: string }[]) : [];
  const model = typeof d.model === "string" ? d.model : "";
  const reason = typeof d.reason === "string" ? d.reason : "";
  const done = typeof d.done === "number" ? d.done : null;
  const total = typeof d.total === "number" ? d.total : null;

  return (
    <>
      {done !== null && total !== null && (
        <p className="mt-0.5 font-mono text-2xs text-ink-faint">
          {done}/{total}
        </p>
      )}
      {model && (
        <p className="mt-0.5 font-mono text-2xs text-ink-faint">└ RNGD · {model}</p>
      )}
      {reason && <p className="mt-0.5 text-2xs text-ink-faint">└ {reason}</p>}
      {samples.map((s, i) => (
        <p key={i} className="mt-0.5 text-2xs text-ink-soft">
          &ldquo;{s.text}&rdquo;{s.source ? ` — ${s.source}` : ""}
        </p>
      ))}
    </>
  );
}

export interface PipelineProgressProps {
  title: string;
  state: PipelineState;
  onDetach: () => void;
  onRetry?: () => void;
}

export function PipelineProgress({ title, state, onDetach, onRetry }: PipelineProgressProps) {
  const finished = state.steps.filter((s) => s.status !== "wait" && s.status !== "run").length;

  return (
    <div className="flex flex-col items-center px-6 py-16">
      <h2 className="text-title text-ink">{title}</h2>
      <p className="mt-1 font-mono text-lead text-ink-faint" aria-live="polite">
        {clock(state.elapsedMs)}
      </p>

      <ul className="mt-8 w-full max-w-md space-y-3">
        {state.steps.map((step) => (
          <li key={step.key} className="flex items-start gap-3">
            <span className="mt-0.5">
              <StepIcon status={step.status} />
            </span>
            <div className="min-w-0 flex-1">
              <p
                className={cn(
                  "text-base",
                  step.status === "wait" ? "text-ink-faint" : "text-ink",
                  step.status === "error" && "text-maroon",
                )}
              >
                {step.label}
              </p>
              <StepDetail step={step} />
            </div>
            <span className="shrink-0 font-mono text-2xs text-ink-faint">
              {step.status === "done" && step.ms !== undefined
                ? `${(step.ms / 1000).toFixed(1)}s`
                : "—"}
            </span>
          </li>
        ))}
      </ul>

      <div className="mt-8 w-full max-w-md border-t border-line pt-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="font-mono text-2xs text-ink-faint">
            {finished}/{state.steps.length} 단계
            {state.tokens > 0 ? ` · 토큰 ${state.tokens.toLocaleString()}` : ""}
          </p>
          {state.running && (
            <Button size="sm" variant="ghost" onClick={onDetach}>
              백그라운드로 두기
            </Button>
          )}
        </div>
        {state.error && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <p className="text-meta text-maroon">{state.error}</p>
            {onRetry && (
              <Button size="sm" variant="secondary" onClick={onRetry} className="gap-1.5">
                <RotateCw className="h-4 w-4" aria-hidden="true" />
                다시 시도
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 배럴에 추가한다**

`web/components/shared/index.ts` 에 한 줄 추가:

```ts
export { PipelineProgress, type PipelineProgressProps } from "./pipeline-progress";
```

- [ ] **Step 3: 타입·린트 검사**

Run: `cd web && npm run typecheck && npm run lint`
Expected: 에러 없음

- [ ] **Step 4: 커밋**

```bash
git add web/components/shared/pipeline-progress.tsx web/components/shared/index.ts
git commit -m "작업 진행 화면 컴포넌트를 추가한다"
```

---

## Task 9: 가이드 패널 연결

**Files:**
- Modify: `web/app/projects/[id]/guide-panel.tsx:103-117` (`generate`) 및 렌더 분기

**Interfaces:**
- Consumes: `usePipeline` (Task 7), `PipelineProgress` (Task 8)
- Produces: 없음

- [ ] **Step 1: 훅을 붙인다**

`guide-panel.tsx` import 에 추가:

```tsx
import { PipelineProgress } from "@/components/shared";
import { usePipeline } from "@/lib/pipeline";
```

컴포넌트 상단 상태 선언부(51-58행 근처)에 추가:

```tsx
  const gen = usePipeline<InterviewGuide>();
```

`generate()`(103-117행)를 교체:

```tsx
  async function generate() {
    setError(null);
    setMessage(null);
    const g = await gen.run(`/api/projects/${projectId}/guide/stream`, {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic: project.topic, target: project.target }),
    });
    if (!g) return;   // 실패·중단 — 에러는 진행 화면이 이미 보여준다
    setGuide(g);
    setDirty(false);
    setMessage("가이드를 새로 만들었어요. 확인하고 필요하면 고쳐 주세요.");
    gen.detach();
  }
```

- [ ] **Step 2: 진행 중이면 진행 화면으로 갈아끼운다**

`if (loading) { … }` 블록(377-384행) **바로 앞**에 삽입:

```tsx
  // 진행 중이면 화면 전체를 진행 뷰로 바꾼다 — 트리거 버튼이 언마운트되므로
  // 더블클릭 방지가 비활성화가 아니라 화면 전환으로 이뤄진다.
  if (gen.state.running || gen.state.error) {
    return (
      <PipelineProgress
        title="가이드를 만들고 있어요"
        state={gen.state}
        onDetach={gen.detach}
        onRetry={generate}
      />
    );
  }
```

- [ ] **Step 3: 이제 안 쓰는 `busy === "generate"` 라벨을 정리한다**

394행: `{busy === "generate" ? "만드는 중…" : "가이드 생성하기"}` → `가이드 생성하기`
424행: `{busy === "generate" ? "생성 중…" : "AI로 다시 생성"}` → `AI로 다시 생성`
두 버튼의 `disabled={busy === "generate"}` 도 제거한다(진행 중엔 화면 자체가 바뀐다).
`busy` 상태의 `"generate"` 유니온 멤버(53행)도 뺀다: `useState<null | "save" | "deploy">(null)`.

- [ ] **Step 4: 타입·린트·빌드**

Run: `cd web && npm run typecheck && npm run lint && npm run build`
Expected: 전부 통과

- [ ] **Step 5: 커밋**

```bash
git add web/app/projects/[id]/guide-panel.tsx
git commit -m "가이드 생성에 진행 화면을 붙인다"
```

---

## Task 10: 결과 패널(인사이트) 연결

**Files:**
- Modify: `web/app/projects/[id]/results-panel.tsx` (`refreshInsight`, 렌더 분기, 300-303행 버튼)

**Interfaces:**
- Consumes: `usePipeline` (Task 7), `PipelineProgress` (Task 8)

- [ ] **Step 1: 훅을 붙이고 호출을 바꾼다**

import 에 추가:

```tsx
import { PipelineProgress } from "@/components/shared";
import { usePipeline } from "@/lib/pipeline";
```

상태 선언부에 추가:

```tsx
  const ins = usePipeline<Insight>();
```

`refreshInsight` 를 교체(기존 `regenerateInsight(pid)` 호출부):

```tsx
  async function refreshInsight() {
    const result = await ins.run(`/api/projects/${projectId}/insight/stream`, {
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    if (!result) return;   // 실패·중단 — 진행 화면이 에러를 보여준다
    setInsight(result);
    ins.detach();
    await load();          // 대시보드 다른 카드도 갱신
  }
```

> `projectId` 변수명이 이 파일에서 다르면(`pid` 등) 그 이름을 쓴다. 파일 상단의 props 선언을 확인할 것.

- [ ] **Step 2: 진행 중이면 진행 화면으로 갈아끼운다**

`if (error && !data) { … }` 분기(282행) **바로 앞**에 삽입:

```tsx
  if (ins.state.running || ins.state.error) {
    return (
      <PipelineProgress
        title="응답을 분석하고 있어요"
        state={ins.state}
        onDetach={ins.detach}
        onRetry={refreshInsight}
      />
    );
  }
```

- [ ] **Step 3: 버튼 라벨을 정리한다**

301-302행: `{insightBusy ? "분석 중…" : insight ? "다시 분석" : "인사이트 생성"}`
→ `{insight ? "다시 분석" : "인사이트 생성"}`, `disabled={insightBusy}` 제거.
`insightBusy` 상태가 다른 곳에서 안 쓰이면 선언째 지운다.

- [ ] **Step 4: 타입·린트·빌드**

Run: `cd web && npm run typecheck && npm run lint && npm run build`
Expected: 전부 통과

- [ ] **Step 5: 커밋**

```bash
git add web/app/projects/[id]/results-panel.tsx
git commit -m "인사이트 생성에 진행 화면을 붙인다"
```

---

## Task 11: 자료 업로드 연결

**Files:**
- Modify: `web/app/projects/new/new-project-form.tsx:33-57` (`submit`), 렌더 분기
- Modify: `web/lib/api.ts` (`uploadMaterialStream` 추가)

**Interfaces:**
- Consumes: `usePipeline` (Task 7), `PipelineProgress` (Task 8), Task 0 의 `MaterialAngle`

- [ ] **Step 1: 스트림 업로드 헬퍼를 만든다**

`web/lib/api.ts` 의 `uploadMaterial` 아래에 추가:

```ts
/** 진행 화면용 업로드 경로·폼 — usePipeline 이 fetch 를 맡으므로 여기선 재료만 만든다. */
export function materialStreamInit(file: File, angle: MaterialAngle = "현상"): RequestInit {
  const form = new FormData();
  form.append("file", file);
  form.append("angle", angle);
  return { body: form };   // Content-Type 은 브라우저가 boundary 와 함께 붙인다
}
```

- [ ] **Step 2: 폼 제출을 바꾼다**

`new-project-form.tsx` import 에 추가:

```tsx
import { PipelineProgress } from "@/components/shared";
import { usePipeline } from "@/lib/pipeline";
import { createProject, materialStreamInit } from "@/lib/api";
```

(`uploadMaterial` import 는 제거 — 이 화면에서는 스트림 경로만 쓴다)

상태 선언부에 추가:

```tsx
  const mat = usePipeline<{ project_id: string; chars: number; angle: string }>();
```

`submit()` 을 교체:

```tsx
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || creating) return;
    setCreating(true);
    setFormError(null);
    let created;
    try {
      created = await createProject({
        topic: purpose.trim(),
        target: target.trim(),
        motivation: motivation.trim(),
        utilization: utilization.trim(),
      });
    } catch {
      setFormError("프로젝트를 만들지 못했어요. 잠시 후 다시 시도해 주세요.");
      setCreating(false);
      return;
    }
    if (file) {
      // 자료가 있으면 인덱싱이 끝날 때까지 진행 화면을 띄운다(임베딩이 오래 걸린다).
      const ok = await mat.run(
        `/api/projects/${created.id}/material/stream`,
        materialStreamInit(file),
      );
      if (!ok) {
        // 프로젝트는 이미 만들어졌다 — 자료만 실패. 상세로 보내 이어가게 한다.
        setFormError("프로젝트는 만들었지만 자료 처리에 실패했어요. 상세에서 다시 올려 주세요.");
      }
    }
    router.push(`/projects/${created.id}`);
  }
```

- [ ] **Step 3: 진행 중이면 진행 화면을 띄운다**

`return (` 바로 앞에 삽입:

```tsx
  if (mat.state.running || mat.state.error) {
    return (
      <main className="py-10 md:py-16">
        <Container className="max-w-2xl">
          <PipelineProgress
            title="자료를 읽고 있어요"
            state={mat.state}
            onDetach={mat.detach}
          />
        </Container>
      </main>
    );
  }
```

- [ ] **Step 4: 타입·린트·빌드**

Run: `cd web && npm run typecheck && npm run lint && npm run build`
Expected: 전부 통과

- [ ] **Step 5: 커밋**

```bash
git add web/lib/api.ts web/app/projects/new/new-project-form.tsx
git commit -m "자료 업로드에 진행 화면을 붙인다"
```

---

## Task 12: 실동작 검증 (목이 아니라 실제 실행)

**Files:** 없음 (검증만)

**왜 필요한가:** AGENTS.md §5 — `coded`(green)를 `live`로 부풀리지 않는다. 목킹된 pytest 가 통과했다고 SSE 가 브라우저에서 실제로 흐른다는 뜻은 아니다.

- [ ] **Step 1: API 와 웹을 띄운다**

```bash
./.venv/Scripts/python.exe -m uvicorn api.main:app --port 8099 --reload
cd web && NEXT_PUBLIC_API_BASE=http://localhost:8099 npm run dev
```

- [ ] **Step 2: 스트림이 조각조각 오는지 확인한다 (버퍼링 점검)**

```bash
curl -N -X POST http://localhost:8099/api/projects/PID/guide/stream \
  -H "Content-Type: application/json" -d '{}'
```

Expected: `data: {"steps": …}` 가 **즉시** 뜨고 나머지가 시간차를 두고 이어진다. 전부가 마지막에 한꺼번에 오면 버퍼링이다 — `SSE_HEADERS` 적용을 확인한다.

- [ ] **Step 3: 브라우저에서 세 경로를 직접 돌린다**

1. 새 프로젝트 + 자료 파일 업로드 → "자료를 읽고 있어요" 단계 4개가 순서대로 채워지는지
2. 프로젝트 상세 → 가이드 생성 → 단계 6개 · 근거 스니펫 · 모델명 · 토큰 수
3. 응답이 있는 프로젝트 → 인사이트 생성 → `세션 요약 i/N` 이 실제로 올라가는지

- [ ] **Step 4: 이탈 복원을 확인한다**

가이드 생성 중 새로고침 → 다시 들어갔을 때 **가이드가 저장돼 있어야 한다**(저장을 품질 점검 앞으로 옮긴 이유).

- [ ] **Step 5: UI 스크린샷을 남긴다**

세 진행 화면 각각. AGENTS.md §3 Verify — "UI 스크린샷".

- [ ] **Step 6: CI 4종 전부 통과 확인**

```bash
./.venv/Scripts/python.exe -m pytest api/tests -q
cd web && npm run typecheck && npm run build && npm run lint
```

Expected: 4종 전부 통과

- [ ] **Step 7: PR 초안 작성 (머지·배포는 하지 않는다)**

```bash
git push -u origin HEAD
gh pr create --draft --title "무거운 작업의 실시간 진행 화면" --body "…"
```

> **하드게이트:** `main` 머지 = Cloud Run 자동 롤아웃(`deploy.yml`). **머지·배포 실행은 사람 승인 없이 하지 않는다** (AGENTS.md §1).

---

## Self-Review

**1. 스펙 커버리지**

| 스펙 절 | 담당 태스크 |
|---|---|
| §3 이벤트 계약 | Task 1 (`Pipeline`·`sse`·`drain`), Task 7 (클라이언트 타입) |
| §4 두 겹 노출 | Task 2·3·4 (`drain` 동치 테스트 포함) |
| §5.1 가이드 6단계 | Task 2 |
| §5.2 인사이트 5단계 | Task 3 |
| §5.3 자료 4단계 | Task 4 |
| §5.4 웹 리서치 | Task 4 |
| §6 프론트 | Task 6·7·8·9·10·11 |
| §7 design.md 델타 | Task 5 (프론트보다 먼저) |
| §8.1 저장 시점 | Task 2 Step 3 (`store.save_guide` 를 품질 점검 앞으로) |
| §8.2 중단 | Task 7 (`detach`), Task 8 ("백그라운드로 두기") |
| §8.3 실패 | Task 8 (`maroon` + `alert-triangle` + 재시도) |
| §8.4 멱등성 | Task 9·10·11 (진행 중 트리거 버튼 언마운트) |
| §9 테스트 | Task 1·2·3·4 (pytest), Task 12 (실동작) |

**2. 스펙에 없던 추가 발견:** Task 0 — `uploadMaterial` 의 `angle` 누락으로 자료 업로드가 422 로 죽고 있었다. 자료 진행 화면의 선행 조건이라 계획에 넣었다.

**3. 타입 일관성:** `Pipeline` 메서드명(`declare`/`start`/`progress`/`done`/`skip`/`fail`)은 Task 1 정의와 Task 2·3·4 사용처가 일치한다. `StepStatus` 는 서버가 `start|done|skip|error`, 클라이언트가 `wait|run|done|skip|error` 로 다르며 Task 7 에서 명시적으로 매핑한다(대기 상태는 서버가 보내지 않으므로 클라이언트에만 있다).

**4. 알려진 미해결:** 웹에 JS 테스트 러너가 없어 `parseSseBuffer` 는 자동 테스트 없이 나간다(Task 6 참고). 러너 도입은 별건.
