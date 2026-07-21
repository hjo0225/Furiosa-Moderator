# 인터뷰 응답 실시간 Discord 알림 (n8n 경유) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 응답자가 인터뷰를 제출할 때마다 그 세션의 요약·감정·커버리지·전사 합본을 n8n 웹훅으로 emit 하고, n8n 이 Discord 에 게시한다.

**Architecture:** FastAPI `submit` 핸들러가 세션을 `completed` 로 바꾼 뒤 `BackgroundTasks` 로 `notify.emit_session_completed(pid, sid)` 를 비동기 호출한다. notify 는 payload(마스킹 데이터만)를 만들어 n8n Webhook URL 로 POST 한다. 포맷·전송은 n8n 이 담당. 알림은 인터뷰 본류를 절대 막지 않는다.

**Tech Stack:** Python 3.11 · FastAPI · httpx(동기) · SQLAlchemy(기존 store 계층) · pytest(monkeypatch, 네트워크·DB 없이) · n8n(Webhook→Code→HTTP Request)

## Global Constraints

- 모든 파이썬 모듈 최상단에 `from __future__ import annotations`.
- **알림은 본류(인터뷰)를 절대 막지 않는다** — `emit_session_completed` 는 모든 예외를 자체 흡수하고 `log.warning` 만 남긴다. 예외를 호출부로 던지지 않는다.
- 전사는 **마스킹된 `turns.text` 만** 쓴다. 원문 오디오·비마스킹 PII 금지.
- 원 식별자(`respondent_id`)는 payload 에 직접 넣지 않고 **짧은 해시**(`respondent_ref`)로만.
- `N8N_WEBHOOK_URL` 은 시크릿 — 코드·로그에 값 노출 금지. Cloud Run 은 Secret Manager 로 주입. 미설정이면 알림 자동 비활성.
- 기존 패턴 준수: 동기 함수, `store` 계층 경유, 기존 함수 시그니처 변경 금지.
- 테스트는 네트워크·DB 없이 돈다 — `monkeypatch` 로 `store`·`get_llm`·`httpx.post` 를 대체.
- 커밋 메시지는 한국어 현재형 서술 + 아래 trailer 2줄:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_017wmqbeh5UTFZUSvfGV7zNa
  ```
- 테스트 실행기: `./.venv/Scripts/python.exe -m pytest`.

---

### Task 1: 설정·의존성 — `N8N_WEBHOOK_URL` / `PUBLIC_WEB_BASE`

**Files:**
- Modify: `api/config.py` (Settings 필드 + get_settings 매핑)
- Modify: `.env.example` (N8N_WEBHOOK_URL 항목)
- Modify: `api/requirements.txt` (httpx 명시)
- Test: `api/tests/test_notify.py` (신규)

**Interfaces:**
- Consumes: 없음(기존 `Settings`, `get_settings`)
- Produces: `Settings.n8n_webhook_url: str`, `Settings.public_web_base: str`; env `N8N_WEBHOOK_URL`, `PUBLIC_WEB_BASE` 로 채워짐. `get_settings()` 는 `functools.lru_cache` 라 테스트에서 `get_settings.cache_clear()` 필요.

- [ ] **Step 1: Write the failing test**

`api/tests/test_notify.py` 를 새로 만든다:

```python
"""n8n 경유 Discord 알림 단위테스트 (네트워크·DB 없이 monkeypatch)."""
from __future__ import annotations


def test_settings_reads_n8n_webhook_url(monkeypatch):
    from api.config import get_settings

    monkeypatch.setenv("N8N_WEBHOOK_URL", "https://n8n.example/webhook/xyz")
    monkeypatch.setenv("PUBLIC_WEB_BASE", "https://web.example")
    get_settings.cache_clear()
    s = get_settings()
    assert s.n8n_webhook_url == "https://n8n.example/webhook/xyz"
    assert s.public_web_base == "https://web.example"
    get_settings.cache_clear()   # 다른 테스트에 캐시가 새지 않게
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_notify.py::test_settings_reads_n8n_webhook_url -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'n8n_webhook_url'`

- [ ] **Step 3: Write minimal implementation**

`api/config.py` 의 `Settings` 클래스에서 `cors_origins`/`max_audio_bytes` 아래에 필드를 추가한다:

```python
    # --- 알림 (n8n → Discord) ------------------------------------------------
    n8n_webhook_url: str = ""     # 비면 알림 비활성
    public_web_base: str = ""     # 대시보드 링크 베이스
```

같은 파일 `get_settings()` 의 `return Settings(...)` 안, `cors_origins=...` 아래에 매핑을 추가한다:

```python
        n8n_webhook_url=env.get("N8N_WEBHOOK_URL", ""),
        public_web_base=env.get("PUBLIC_WEB_BASE", ""),
```

`.env.example` 의 `# --- 배포 연결 ---` 블록 아래에 추가한다:

```
# --- 알림 (n8n → Discord) ---
# n8n Webhook 노드의 Production URL. 실값은 Secret Manager. 비우면 알림 비활성.
N8N_WEBHOOK_URL=
```

`api/requirements.txt` 마지막 줄에 추가한다(openai 가 이미 전이적으로 끌어오지만 notify 가 직접 import 하므로 명시):

```
httpx==0.28.1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_notify.py::test_settings_reads_n8n_webhook_url -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/config.py .env.example api/requirements.txt api/tests/test_notify.py
git commit -m "$(cat <<'EOF'
알림 설정(N8N_WEBHOOK_URL·PUBLIC_WEB_BASE)을 추가한다

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017wmqbeh5UTFZUSvfGV7zNa
EOF
)"
```

---

### Task 2: 알림 payload 빌더 — `api/services/notify.py`

**Files:**
- Create: `api/services/notify.py`
- Test: `api/tests/test_notify.py` (확장)

**Interfaces:**
- Consumes: `store.get_session(pid,sid)->Session|None`, `store.get_project(pid)->Project|None`, `store.get_guide(pid)->InterviewGuide|None`, `store.list_turns(pid,sid)->list[Turn]`, `store.update_session(pid,sid,dict)->None`; `get_llm().text(system, user, *, max_tokens=512)->tuple[str, Usage]`; `LLMError(RuntimeError)`; `SESSION_SUMMARY_SYSTEM`, `session_summary_user(goal, transcript)`; `Settings.public_web_base`.
- Produces: `notify._build_payload(pid: str, sid: str, settings: Settings) -> dict | None`. 헬퍼 `_respondent_ref`, `_transcript`, `_emotion_counts`, `_generate_summary`, `_duration_sec`.

- [ ] **Step 1: Write the failing test**

`api/tests/test_notify.py` 에 헬퍼와 테스트를 추가한다:

```python
def _fake_turns():
    from api.schemas.models import Turn
    return [
        Turn(role="moderator", text="배달앱을 주로 어떤 목적으로 쓰세요?", question_id="q1"),
        Turn(role="respondent", text="야근할 때 시켜요", emotion="긍정"),
        Turn(role="moderator", text="어떤 앱을 쓰세요?", question_id="q2"),
        Turn(role="respondent", text="배민이요", emotion="중립"),
    ]


def _patch_store(monkeypatch, sess, proj, guide, turns):
    from api.services import notify
    monkeypatch.setattr(notify.store, "get_session", lambda pid, sid: sess)
    monkeypatch.setattr(notify.store, "get_project", lambda pid: proj)
    monkeypatch.setattr(notify.store, "get_guide", lambda pid: guide)
    monkeypatch.setattr(notify.store, "list_turns", lambda pid, sid: turns)
    monkeypatch.setattr(notify.store, "update_session", lambda pid, sid, patch: None)


def test_build_payload_shape(monkeypatch):
    from api.services import notify
    from api.config import Settings
    from api.schemas.models import Session, Project, InterviewGuide, GuideQuestion

    sess = Session(id="s_1", project_id="p_1", respondent_id="r_abc",
                   status="completed", asked=2, covered=["q1", "q2"])
    proj = Project(id="p_1", title="배달앱 조사", topic="배달앱 사용 경험")
    guide = InterviewGuide(goal="배달앱 사용 경험 파악", questions=[
        GuideQuestion(id="q1", text="a"), GuideQuestion(id="q2", text="b"),
        GuideQuestion(id="q3", text="c")])
    _patch_store(monkeypatch, sess, proj, guide, _fake_turns())

    class _FakeLLM:
        def text(self, system, user, **kw):
            return "이 응답자는 야근 시 배달앱을 쓴다.", {}
    monkeypatch.setattr(notify, "get_llm", lambda: _FakeLLM())

    payload = notify._build_payload("p_1", "s_1", Settings(public_web_base="https://web.example"))

    assert payload["event"] == "session.completed"
    assert payload["project"] == {"id": "p_1", "title": "배달앱 조사", "topic": "배달앱 사용 경험"}
    assert payload["session"]["asked"] == 2
    assert payload["session"]["respondent_ref"] and payload["session"]["respondent_ref"] != "r_abc"
    assert payload["metrics"]["coverage"] == {"covered": ["q1", "q2"], "total": 3}
    assert payload["metrics"]["emotion"] == {"긍정": 1, "중립": 1}
    assert payload["summary"] == "이 응답자는 야근 시 배달앱을 쓴다."
    assert "응답자: 야근할 때 시켜요" in payload["transcript"]
    assert "진행자: 어떤 앱을 쓰세요?" in payload["transcript"]
    assert payload["dashboard_url"] == "https://web.example/projects/p_1"


def test_build_payload_summary_fallback_on_llm_error(monkeypatch):
    from api.services import notify
    from api.services.llm_client import LLMError
    from api.config import Settings
    from api.schemas.models import Session, Project, InterviewGuide

    sess = Session(id="s_1", project_id="p_1", respondent_id="r_x", status="completed")
    _patch_store(monkeypatch, sess, Project(id="p_1", topic="주제"),
                 InterviewGuide(goal="목표"), _fake_turns())

    class _BoomLLM:
        def text(self, system, user, **kw):
            raise LLMError("boom")
    monkeypatch.setattr(notify, "get_llm", lambda: _BoomLLM())

    payload = notify._build_payload("p_1", "s_1", Settings())
    assert payload["summary"] is None
    assert payload["transcript"]   # 전사는 그대로


def test_build_payload_none_when_session_missing(monkeypatch):
    from api.services import notify
    from api.config import Settings
    monkeypatch.setattr(notify.store, "get_session", lambda pid, sid: None)
    assert notify._build_payload("p_1", "s_x", Settings()) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_notify.py -k build_payload -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.services.notify'`

- [ ] **Step 3: Write minimal implementation**

`api/services/notify.py` 를 만든다:

```python
"""n8n 경유 아웃바운드 알림.

응답자가 인터뷰를 제출(completed)할 때 세션의 요약·감정·커버리지·전사 합본을
n8n 웹훅으로 emit 한다. n8n 이 Discord embed 로 게시한다.

원칙: 알림은 본류(인터뷰)를 절대 막지 않는다. 전사는 이미 마스킹된 turns.text 만 쓴다.
"""
from __future__ import annotations

import hashlib
import logging

from ..config import Settings
from ..prompts.insight import SESSION_SUMMARY_SYSTEM, session_summary_user
from ..schemas.models import Session, Turn
from ..services import store
from ..services.llm_client import LLMError, get_llm

log = logging.getLogger(__name__)


def _respondent_ref(respondent_id: str) -> str:
    """원 식별자 대신 짧은 해시. 원 식별자·PII 미노출."""
    if not respondent_id:
        return ""
    return hashlib.sha256(respondent_id.encode("utf-8")).hexdigest()[:12]


def _transcript(turns: list[Turn]) -> str:
    """마스킹된 문답 합본. build_insight 과 같은 표기."""
    return "\n".join(
        f"{'진행자' if t.role == 'moderator' else '응답자'}: {t.text}" for t in turns
    )


def _emotion_counts(turns: list[Turn]) -> dict[str, int]:
    """이 세션 응답자 턴의 감정 라벨 카운트(빈 라벨 제외)."""
    out: dict[str, int] = {}
    for t in turns:
        if t.role == "respondent" and t.emotion:
            out[t.emotion] = out.get(t.emotion, 0) + 1
    return out


def _duration_sec(session: Session) -> int | None:
    if not session.ended_at:
        return None
    return int((session.ended_at - session.started_at).total_seconds())


def _generate_summary(goal: str, transcript: str) -> str | None:
    """세션 요약 1회 생성. 실패하면 None (best-effort)."""
    if not transcript.strip():
        return None
    try:
        summary, _ = get_llm().text(
            SESSION_SUMMARY_SYSTEM, session_summary_user(goal, transcript), max_tokens=500
        )
        return summary or None
    except LLMError as e:
        log.warning("세션 요약 생성 실패: %s", e)
        return None


def _build_payload(pid: str, sid: str, settings: Settings) -> dict | None:
    """이벤트 payload 구성. 세션이 없으면 None."""
    session = store.get_session(pid, sid)
    if not session:
        return None
    project = store.get_project(pid)
    guide = store.get_guide(pid)
    turns = store.list_turns(pid, sid)

    transcript = _transcript(turns)
    goal = (guide.goal if guide else "") or (project.topic if project else "")

    summary = _generate_summary(goal, transcript)
    if summary:
        store.update_session(pid, sid, {"summary": summary})   # 나중 insight 빌드도 재사용

    total_questions = len(guide.questions) if guide else 0
    web_base = (settings.public_web_base or "").rstrip("/")

    return {
        "event": "session.completed",
        "project": {
            "id": pid,
            "title": project.title if project else "",
            "topic": project.topic if project else "",
        },
        "session": {
            "id": sid,
            "respondent_ref": _respondent_ref(session.respondent_id),
            "asked": session.asked,
            "duration_sec": _duration_sec(session),
        },
        "metrics": {
            "emotion": _emotion_counts(turns),
            "coverage": {"covered": list(session.covered), "total": total_questions},
        },
        "summary": summary,
        "transcript": transcript,
        "dashboard_url": f"{web_base}/projects/{pid}" if web_base else f"/projects/{pid}",
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_notify.py -k build_payload -v`
Expected: PASS (3개)

- [ ] **Step 5: Commit**

```bash
git add api/services/notify.py api/tests/test_notify.py
git commit -m "$(cat <<'EOF'
알림 payload 빌더를 추가한다

세션 요약(실패 시 폴백)·감정 카운트·커버리지·마스킹 전사 합본을 구성한다.
respondent_id 는 해시로만 싣는다.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017wmqbeh5UTFZUSvfGV7zNa
EOF
)"
```

---

### Task 3: 전송 + 진입점 — `_post` / `emit_session_completed`

**Files:**
- Modify: `api/services/notify.py` (함수 추가)
- Test: `api/tests/test_notify.py` (확장)

**Interfaces:**
- Consumes: `_build_payload`(Task 2), `get_settings()->Settings`, `httpx.post`.
- Produces: `notify.emit_session_completed(pid: str, sid: str) -> None` (예외를 절대 던지지 않음), `notify._post(url: str, payload: dict) -> None` (최종 실패는 예외로 올림).

- [ ] **Step 1: Write the failing test**

`api/tests/test_notify.py` 에 추가한다:

```python
def test_emit_skips_when_url_unset(monkeypatch):
    from api.services import notify
    from api.config import Settings

    monkeypatch.setattr(notify, "get_settings", lambda: Settings(n8n_webhook_url=""))
    calls = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **k: calls.append((a, k)))

    notify.emit_session_completed("p_1", "s_1")
    assert calls == []   # URL 없으면 아무 것도 안 보냄


def test_emit_posts_payload(monkeypatch):
    from api.services import notify
    from api.config import Settings

    monkeypatch.setattr(notify, "get_settings",
                        lambda: Settings(n8n_webhook_url="https://n8n.example/webhook/xyz"))
    monkeypatch.setattr(notify, "_build_payload", lambda pid, sid, settings: {"event": "session.completed"})

    captured = {}

    class _Resp:
        def raise_for_status(self): pass
    def _fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _Resp()
    monkeypatch.setattr(notify.httpx, "post", _fake_post)

    notify.emit_session_completed("p_1", "s_1")
    assert captured["url"] == "https://n8n.example/webhook/xyz"
    assert captured["json"] == {"event": "session.completed"}


def test_emit_swallows_post_errors(monkeypatch):
    from api.services import notify
    from api.config import Settings

    monkeypatch.setattr(notify, "get_settings",
                        lambda: Settings(n8n_webhook_url="https://n8n.example/webhook/xyz"))
    monkeypatch.setattr(notify, "_build_payload", lambda pid, sid, settings: {"event": "x"})

    def _boom(url, json, timeout):
        raise RuntimeError("network down")
    monkeypatch.setattr(notify.httpx, "post", _boom)
    monkeypatch.setattr(notify.time, "sleep", lambda *_: None)   # 재시도 백오프 빨리감기

    # 예외가 밖으로 새지 않아야 한다 — 실패해도 조용히 반환
    notify.emit_session_completed("p_1", "s_1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_notify.py -k emit -v`
Expected: FAIL — `AttributeError: module 'api.services.notify' has no attribute 'httpx'` (또는 `emit_session_completed` 미정의)

- [ ] **Step 3: Write minimal implementation**

`api/services/notify.py` 상단 import 에 `time` 과 `httpx`, `get_settings` 를 추가한다. import 블록을 아래로 교체한다:

```python
import hashlib
import logging
import time

import httpx

from ..config import Settings, get_settings
from ..prompts.insight import SESSION_SUMMARY_SYSTEM, session_summary_user
from ..schemas.models import Session, Turn
from ..services import store
from ..services.llm_client import LLMError, get_llm
```

파일 맨 아래에 다음을 추가한다:

```python
_TIMEOUT = 5.0
_MAX_ATTEMPTS = 3   # 최초 1회 + 2회 재시도


def _post(url: str, payload: dict) -> None:
    """n8n 웹훅으로 POST. 타임아웃·재시도. 최종 실패는 예외로 올린다(호출부가 흡수)."""
    last: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            r = httpx.post(url, json=payload, timeout=_TIMEOUT)
            r.raise_for_status()
            return
        except Exception as e:   # noqa: BLE001 — 네트워크 오류 전부
            last = e
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(0.5 * (2 ** attempt))   # 0.5s, 1s 백오프
    raise last if last else RuntimeError("알림 전송 실패")


def emit_session_completed(pid: str, sid: str) -> None:
    """제출 완료 알림 진입점. 백그라운드에서 호출된다.

    URL 미설정이면 조용히 skip. 어떤 예외도 밖으로 던지지 않는다 —
    알림 실패가 인터뷰를 깨선 안 된다.
    """
    settings = get_settings()
    if not settings.n8n_webhook_url:
        log.debug("N8N_WEBHOOK_URL 미설정 — 알림 skip (project=%s session=%s)", pid, sid)
        return
    try:
        payload = _build_payload(pid, sid, settings)
        if payload is None:
            log.warning("알림 payload 없음 — 세션 미발견 (project=%s session=%s)", pid, sid)
            return
        _post(settings.n8n_webhook_url, payload)
        log.info("n8n 알림 전송 (project=%s session=%s)", pid, sid)
    except Exception as e:   # noqa: BLE001 — 알림은 본류를 막지 않는다
        log.warning("n8n 알림 실패 (project=%s session=%s): %s", pid, sid, e)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_notify.py -v`
Expected: PASS (전체)

- [ ] **Step 5: Commit**

```bash
git add api/services/notify.py api/tests/test_notify.py
git commit -m "$(cat <<'EOF'
n8n 전송과 알림 진입점을 추가한다

emit_session_completed 는 URL 미설정 시 skip 하고 모든 예외를 흡수한다.
_post 는 타임아웃·2회 재시도.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017wmqbeh5UTFZUSvfGV7zNa
EOF
)"
```

---

### Task 4: submit 훅 배선 — `api/routers/public.py`

**Files:**
- Modify: `api/routers/public.py` (import + submit 시그니처/본문)
- Test: `api/tests/test_notify.py` (확장)

**Interfaces:**
- Consumes: `notify.emit_session_completed`(Task 3), FastAPI `BackgroundTasks`.
- Produces: 변경된 `submit(pid, sid, background_tasks)` — completed 전환 직후 알림 태스크 등록. 멱등 재제출 시 등록 안 함.

- [ ] **Step 1: Write the failing test**

`api/tests/test_notify.py` 에 추가한다:

```python
def test_submit_schedules_notification(monkeypatch):
    from fastapi import BackgroundTasks
    from api.routers import public
    from api.schemas.models import Session

    sess = Session(id="s_1", project_id="p_1", status="active")
    monkeypatch.setattr(public.store, "get_session", lambda pid, sid: sess)
    monkeypatch.setattr(public.store, "update_session", lambda pid, sid, patch: None)

    bt = BackgroundTasks()
    public.submit("p_1", "s_1", bt)

    assert any(t.func is public.notify.emit_session_completed for t in bt.tasks)
    assert any(t.args == ("p_1", "s_1") for t in bt.tasks)


def test_submit_idempotent_no_duplicate_notification(monkeypatch):
    from fastapi import BackgroundTasks
    from api.routers import public
    from api.schemas.models import Session

    done = Session(id="s_1", project_id="p_1", status="completed")
    monkeypatch.setattr(public.store, "get_session", lambda pid, sid: done)

    bt = BackgroundTasks()
    public.submit("p_1", "s_1", bt)
    assert bt.tasks == []   # 이미 completed — 알림 재발사 금지
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_notify.py -k submit -v`
Expected: FAIL — `TypeError: submit() takes 2 positional arguments but 3 were given` (또는 `public.notify` 미존재)

- [ ] **Step 3: Write minimal implementation**

`api/routers/public.py` 의 import 두 줄을 교체한다:

```python
from fastapi import APIRouter, BackgroundTasks, HTTPException
```
```python
from ..services import moderator, notify, store
```

`submit` 함수 시그니처를 바꾸고, `completed` 로 업데이트한 **직후**에 알림 태스크를 등록한다. 함수 전체를 아래로 교체한다:

```python
@router.post("/{pid}/sessions/{sid}/submit", response_model=Session)
def submit(pid: str, sid: str, background_tasks: BackgroundTasks) -> Session:
    """R-4 제출 — 이 시점에야 '응답 1건'이 된다.

    진행자가 done 을 냈다고 세션이 완료된 게 아니다. 응답자가 직접 제출해야 completed 로
    넘어가고 집계·인사이트 모수에 들어간다. 중간에 그만두고 제출하는 것도 허용한다(active).
    """
    session = store.get_session(pid, sid)
    if not session:
        raise HTTPException(404, "세션을 찾을 수 없습니다.")
    if session.status == "completed":
        return session   # 멱등 — 재전송·중복 클릭으로 실패시키지 않는다(알림도 재발사 안 함)
    if session.status not in ("active", "pending"):
        # consented(한 마디도 안 함) / abandoned — 제출할 답변이 없다.
        raise HTTPException(400, "제출할 답변이 없습니다.")

    from datetime import datetime, timezone

    store.update_session(
        pid, sid, {"status": "completed", "ended_at": datetime.now(timezone.utc)}
    )
    log.info("세션 제출 완료 (project=%s session=%s)", pid, sid)
    # 알림은 백그라운드로 — 응답자 응답을 막지 않는다. 실패해도 제출은 성공이다.
    background_tasks.add_task(notify.emit_session_completed, pid, sid)
    return store.get_session(pid, sid) or session
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_notify.py -v`
Expected: PASS (전체)

- [ ] **Step 5: Run the full suite (회귀 확인)**

Run: `./.venv/Scripts/python.exe -m pytest api/tests -q`
Expected: 전부 PASS (기존 21 + 신규)

- [ ] **Step 6: Commit**

```bash
git add api/routers/public.py api/tests/test_notify.py
git commit -m "$(cat <<'EOF'
제출 시 인터뷰 알림을 백그라운드로 발사한다

completed 전환 직후 emit_session_completed 를 BackgroundTasks 로 등록한다.
멱등 재제출에서는 재발사하지 않는다. 알림 실패는 제출을 막지 않는다.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017wmqbeh5UTFZUSvfGV7zNa
EOF
)"
```

---

### Task 5: n8n 워크플로우 산출물 — `n8n/`

**Files:**
- Create: `n8n/interview-notify.workflow.json` (import 가능한 워크플로우)
- Create: `n8n/README.md` (import·연결 설명)

**Interfaces:**
- Consumes: Task 2 의 payload 계약(`event`, `project`, `session`, `metrics`, `summary`, `transcript`, `dashboard_url`).
- Produces: 없음(mindlens 코드가 의존하지 않는 별도 산출물).

- [ ] **Step 1: 워크플로우 JSON 작성**

`n8n/interview-notify.workflow.json` 을 만든다 (Webhook → Code(embed 매핑) → HTTP Request(Discord webhook POST)):

```json
{
  "name": "mindlens interview → Discord",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "mindlens-interview",
        "responseMode": "onReceived",
        "options": {}
      },
      "id": "webhook-in",
      "name": "Webhook",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 1,
      "position": [260, 300]
    },
    {
      "parameters": {
        "jsBlock": "const p = $json.body || $json;\nconst m = p.metrics || {};\nconst emo = Object.entries(m.emotion || {}).map(([k,v]) => `${k} ${v}`).join(' · ') || '없음';\nconst cov = m.coverage ? `${(m.coverage.covered||[]).length}/${m.coverage.total}` : '-';\nlet transcript = p.transcript || '';\nif (transcript.length > 1500) transcript = transcript.slice(0, 1500) + '…';\nconst embed = {\n  title: `새 인터뷰 응답 · ${p.project?.title || p.project?.id || ''}`,\n  description: p.summary || '(요약 없음)',\n  url: p.dashboard_url || undefined,\n  fields: [\n    { name: '감정', value: emo, inline: true },\n    { name: '커버리지', value: cov, inline: true },\n    { name: '진행자 질문', value: String(p.session?.asked ?? '-'), inline: true },\n    { name: '전사', value: '```\\n' + (transcript || '(없음)') + '\\n```' }\n  ]\n};\nreturn [{ json: { content: null, embeds: [embed] } }];"
      },
      "id": "format-embed",
      "name": "Format embed",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [520, 300]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "={{ $env.DISCORD_WEBHOOK_URL }}",
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify($json) }}",
        "options": {}
      },
      "id": "discord-post",
      "name": "Discord webhook",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4,
      "position": [780, 300]
    }
  ],
  "connections": {
    "Webhook": { "main": [[{ "node": "Format embed", "type": "main", "index": 0 }]] },
    "Format embed": { "main": [[{ "node": "Discord webhook", "type": "main", "index": 0 }]] }
  },
  "settings": {},
  "active": false
}
```

- [ ] **Step 2: JSON 유효성 검증**

Run: `./.venv/Scripts/python.exe -c "import json; json.load(open('n8n/interview-notify.workflow.json', encoding='utf-8')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: README 작성**

`n8n/README.md` 를 만든다:

````markdown
# n8n — 인터뷰 응답 Discord 알림

`interview-notify.workflow.json` 을 n8n 에 import 하면 아래 흐름이 생긴다.

```
Webhook(POST /mindlens-interview) → Format embed(Code) → Discord webhook(HTTP Request)
```

## 설정

1. n8n → **Import from File** 로 `interview-notify.workflow.json` 을 불러온다.
2. **Webhook** 노드의 **Production URL** 을 복사한다. 이 값을 mindlens api 의
   `N8N_WEBHOOK_URL`(Secret Manager)에 넣는다.
3. Discord 채널 → 채널 설정 → 연동 → **웹후크** 생성 후 URL 복사.
4. n8n 인스턴스 환경변수 `DISCORD_WEBHOOK_URL` 에 그 값을 넣는다
   (또는 **Discord webhook** 노드의 `url` 을 직접 채운다).
5. 워크플로우를 **Activate**.

## mindlens → n8n payload 계약

`api/services/notify.py::_build_payload` 가 보내는 JSON:

| 필드 | 설명 |
|---|---|
| `event` | 항상 `session.completed` |
| `project` | `id` · `title` · `topic` |
| `session` | `id` · `respondent_ref`(해시) · `asked` · `duration_sec` |
| `metrics.emotion` | `{라벨: 수}` |
| `metrics.coverage` | `{covered: [문항id], total: n}` |
| `summary` | 세션 요약(생성 실패 시 `null`) |
| `transcript` | 마스킹된 문답 합본 |
| `dashboard_url` | 대시보드 링크 |

원문 오디오·비마스킹 PII 는 담기지 않는다.

## 보안(현 상태)

HMAC 서명은 생략됐다. Webhook Production URL 자체를 시크릿으로 취급한다.
향후: Webhook 뒤에 정적 토큰/서명 검증 노드를 추가할 수 있다.
````

- [ ] **Step 4: Commit**

```bash
git add n8n/interview-notify.workflow.json n8n/README.md
git commit -m "$(cat <<'EOF'
n8n Discord 알림 워크플로우와 설명을 추가한다

Webhook → Code(embed 매핑) → HTTP Request(Discord webhook). payload 계약 문서 포함.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017wmqbeh5UTFZUSvfGV7zNa
EOF
)"
```

---

## 배포 노트 (플랜 밖, 실행 후)

- `N8N_WEBHOOK_URL` 을 Secret Manager 에 등록하고 Cloud Run **api** 서비스에 주입한다.
- **Cloud Run**: 응답 후 BackgroundTask(요약 LLM 호출)가 CPU 스로틀로 지연·중단될 수 있으므로
  api 서비스에 **"CPU always allocated"** 를 켠다(스펙 참고). 더 견고히 하려면 Cloud Tasks 로 이관.
- 미설정 환경(로컬·CI)에서는 알림이 자동 비활성 → 안전.

## Self-Review (작성자 확인 완료)

- **스펙 커버리지**: 트리거(submit·Task4) · 요약 생성+폴백(Task2) · 감정/커버리지/전사(Task2) ·
  respondent 해시(Task2) · n8n POST+재시도(Task3) · URL 미설정 skip(Task3) · 본류 비차단(Task3/4) ·
  설정·시크릿(Task1) · n8n 워크플로우+문서(Task5) · 배포 노트 → 스펙 각 절에 대응 태스크 존재.
- **플레이스홀더**: 없음(모든 코드·명령 구체값).
- **타입 일관성**: `emit_session_completed(pid, sid)` · `_build_payload(pid, sid, settings)` · `_post(url, payload)` ·
  `settings.n8n_webhook_url`/`settings.public_web_base` 가 Task 전반에서 동일.
