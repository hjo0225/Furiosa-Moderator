# Discord 알림 프로젝트별 웹훅 라우팅 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 각 프로젝트가 자기 Discord 웹훅을 가질 수 있게 하고(비면 기본 채널), 알림을 프로젝트 웹훅으로 라우팅한다.

**Architecture:** `projects.discord_webhook_url` 컬럼을 추가하고(Alembic 0002), `notify.emit_session_completed` 가 `project.discord_webhook_url or settings.discord_webhook_url` 로 전송한다. 둘 다 비면 skip. 프로젝트 웹훅은 생성 시(`ProjectCreateIn`) 또는 `PUT /api/projects/{pid}/webhook` 로 설정한다.

**Tech Stack:** Python 3.11 · FastAPI · SQLAlchemy + Alembic(0001 baseline 도입 완료) · httpx · pytest(monkeypatch, no DB/net)

## Global Constraints

- 모든 파이썬 모듈 최상단에 `from __future__ import annotations`.
- **알림은 본류(인터뷰)를 절대 막지 않는다** — `emit_session_completed` 는 모든 예외를 자체 흡수(log.warning), 예외를 밖으로 던지지 않는다.
- webhook URL 은 시크릿 — 로그에 값 노출 금지(기존 `type(e).__name__` + status 만 로깅 유지).
- 기존 함수 시그니처 유지: `store.get_project(pid)->Project|None`, `store.update_project(pid, patch)->None`, `store.create_project(Project)->Project`, `store._project(row, sessions=0, completed=0)->Project`, `notify._build_payload(pid, sid, settings)->dict|None`, `notify._post(url, payload)->None`.
- **Alembic adoption 규칙**: 기존 DB(테이블 O, `alembic_version` X)는 `stamp "0001"`(baseline) 후 **항상** `upgrade head`. `stamp head` 로 두면 0002 도입 시 기존 prod 를 0002 로 잘못 stamp 한다 — 이 플랜에서 고친다.
- 테스트: 네트워크·DB 없이 `monkeypatch`. 실행기 `./.venv/Scripts/python.exe -m pytest`.
- 마이그레이션·`init_schema` 는 실제 DB 없이 단위테스트 불가 → Task 2 는 로컬 Postgres 수동 검증(레시피 포함).
- 커밋 메시지: 한국어 현재형 서술 + trailer 2줄:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_017wmqbeh5UTFZUSvfGV7zNa
  ```

---

### Task 1: 데이터 필드 — Project.discord_webhook_url

**Files:**
- Modify: `api/schemas/models.py` (Project · ProjectCreateIn · 신규 WebhookSetIn)
- Modify: `api/services/db.py` (ProjectRow 컬럼)
- Modify: `api/services/store.py` (_project · create_project)
- Test: `api/tests/test_schema_project.py` (확장)

**Interfaces:**
- Consumes: 기존 `Project`, `ProjectCreateIn`, `ProjectRow`, `store._project`, `store.create_project`.
- Produces: `Project.discord_webhook_url: str = ""`, `ProjectCreateIn.discord_webhook_url: str = ""`, `WebhookSetIn(discord_webhook_url: str = "")`, `ProjectRow.discord_webhook_url` 컬럼. `store._project`/`create_project` 가 이 필드를 왕복한다.

- [ ] **Step 1: Write the failing test**

`api/tests/test_schema_project.py` 에 추가하고, **기존** `test_store_project_maps_material_text` 의 SimpleNamespace 에도 `discord_webhook_url` 을 넣는다(안 넣으면 _project 가 AttributeError):

```python
def test_project_has_discord_webhook_url_default():
    from api.schemas.models import Project
    assert Project(topic="t").discord_webhook_url == ""
    assert Project(topic="t", discord_webhook_url="https://x").discord_webhook_url == "https://x"


def test_store_project_maps_discord_webhook_url():
    from api.services import store
    row = SimpleNamespace(
        id="p_1", owner="anonymous", title="t", topic="주제", target="",
        material_text="", discord_webhook_url="https://x", status="draft",
        created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    p = store._project(row, 0, 0)
    assert p.discord_webhook_url == "https://x"
```

기존 `test_store_project_maps_material_text` 의 `row = SimpleNamespace(...)` 에 `discord_webhook_url="",` 를 `material_text="자료",` 다음에 추가한다.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_schema_project.py -v`
Expected: FAIL — `test_project_has_discord_webhook_url_default` 에서 `AttributeError: 'Project' object has no attribute 'discord_webhook_url'`

- [ ] **Step 3: Write minimal implementation**

`api/schemas/models.py` `Project` 에서 `material_text` 아래에 추가:
```python
    material_text: str = ""      # 조사 참고 자료 원문 (협업자 기능)
    discord_webhook_url: str = ""  # 프로젝트별 알림 채널 override (비면 기본)
    status: ProjectStatus = "draft"
```

`api/schemas/models.py` `ProjectCreateIn` 에 추가:
```python
class ProjectCreateIn(BaseModel):
    topic: str
    title: str = ""
    target: str = ""
    discord_webhook_url: str = ""
```

`api/schemas/models.py` 의 `ProjectCreateIn` 클래스 **바로 아래** 에 신규 모델을 추가:
```python
class WebhookSetIn(BaseModel):
    """프로젝트별 Discord 웹훅 설정/해제(빈 문자열이면 기본 채널로 폴백)."""
    discord_webhook_url: str = ""
```

`api/services/db.py` `ProjectRow` 에서 `material_text` 아래에 추가:
```python
    material_text: Mapped[str] = mapped_column(Text, default="")
    discord_webhook_url: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
```

`api/services/store.py` `_project` 의 `Project(...)` 에 `material_text` 다음으로 추가:
```python
    return Project(
        id=r.id, owner=r.owner, title=r.title, topic=r.topic, target=r.target,
        material_text=r.material_text, discord_webhook_url=r.discord_webhook_url,
        status=r.status, created_at=r.created_at,
        session_count=sessions, completed_count=completed,
    )
```

`api/services/store.py` `create_project` 의 `ProjectRow(...)` 에 추가:
```python
        s.add(ProjectRow(
            id=p.id, owner=p.owner, title=p.title, topic=p.topic,
            target=p.target, material_text=p.material_text,
            discord_webhook_url=p.discord_webhook_url,
            status=p.status, created_at=p.created_at,
        ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_schema_project.py -v`
Expected: PASS (4개)

- [ ] **Step 5: Commit**

```bash
git add api/schemas/models.py api/services/db.py api/services/store.py api/tests/test_schema_project.py
git commit -F - <<'EOF'
프로젝트에 discord_webhook_url 필드를 추가한다

프로젝트별 알림 채널 override. 모델·row·store 왕복 + WebhookSetIn 스키마.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017wmqbeh5UTFZUSvfGV7zNa
EOF
```

---

### Task 2: Alembic 0002 마이그레이션 + adoption 로직 수정

**Files:**
- Create: `api/alembic/versions/0002_add_project_discord_webhook.py`
- Modify: `api/services/db.py` (`init_schema` adoption 분기)

**Interfaces:**
- Consumes: Task 1 의 `ProjectRow.discord_webhook_url`; 기존 baseline `0001`.
- Produces: revision `0002`(down_revision `0001`) — `projects.discord_webhook_url TEXT NOT NULL DEFAULT ''`. `init_schema` 가 기존 DB 를 `stamp "0001"` 후 `upgrade head` 로 0002 를 적용.

> 이 태스크는 실제 DB 가 있어야 검증된다. 단위테스트가 아니라 **로컬 Postgres 수동 검증**(Step 3)으로 대신한다.

- [ ] **Step 1: 마이그레이션 파일 작성**

`api/alembic/versions/0002_add_project_discord_webhook.py`:
```python
"""add projects.discord_webhook_url — 프로젝트별 알림 채널 override

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("discord_webhook_url", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("projects", "discord_webhook_url")
```

- [ ] **Step 2: init_schema adoption 분기 수정**

`api/services/db.py` `init_schema` 의 마지막 분기를 아래로 교체한다(현재 `if ... stamp head else upgrade head` → `stamp 0001` 후 항상 `upgrade head`):
```python
    if has_core and not has_version:
        command.stamp(cfg, "0001")   # 기존 스키마를 baseline(0001)으로 채택
    command.upgrade(cfg, "head")     # baseline 이후 마이그레이션(0002…)을 적용
```
(주석 `# 기존 스키마를 baseline 으로 채택` / `else:` 줄은 사라진다.)

- [ ] **Step 3: 로컬 Postgres 수동 검증**

```bash
# 일회용 컨테이너 (5432/5433 점유 회피용 5544)
docker rm -f mw-verify >/dev/null 2>&1
docker run -d --name mw-verify -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=postgres -p 5544:5432 postgres:16-alpine
docker exec mw-verify sh -c 'until pg_isready -U postgres; do :; done' 2>/dev/null || true
docker exec mw-verify psql -U postgres -c "CREATE DATABASE existing"
```

시나리오 A(신규) — 빈 DB 는 0001+0002 를 모두 만든다:
```bash
./.venv/Scripts/python.exe - <<'PY'
import os, time
os.environ["INSTANCE_CONNECTION_NAME"]=""
os.environ["DATABASE_URL"]="postgresql+pg8000://postgres:pw@localhost:5544/postgres"
import sqlalchemy as sa
for _ in range(45):
    try:
        with sa.create_engine(os.environ["DATABASE_URL"]).connect() as c: c.execute(sa.text("select 1")); break
    except Exception: time.sleep(1)
from api.services.db import init_schema
init_schema()
e=sa.create_engine(os.environ["DATABASE_URL"]); insp=sa.inspect(e)
cols=[c["name"] for c in insp.get_columns("projects")]
with e.connect() as c: v=[r[0] for r in c.execute(sa.text("select version_num from alembic_version"))]
print("discord_webhook_url in projects:", "discord_webhook_url" in cols, "| version:", v)
PY
```
Expected: `discord_webhook_url in projects: True | version: ['0002']`

시나리오 B(기존 prod 모사) — 테이블만 있고 version 없음 → stamp 0001 후 upgrade 가 0002 를 적용:
```bash
./.venv/Scripts/python.exe - <<'PY'
import os
os.environ["INSTANCE_CONNECTION_NAME"]=""
os.environ["DATABASE_URL"]="postgresql+pg8000://postgres:pw@localhost:5544/existing"
import sqlalchemy as sa
from api.services.db import Base, _engine, init_schema
# 기존 prod 모사: 0001 상태(테이블 O, discord_webhook_url 없음, alembic_version 없음)
Base.metadata.create_all(_engine())
with _engine().begin() as c:
    c.execute(sa.text("ALTER TABLE projects DROP COLUMN discord_webhook_url"))  # 0001 시점으로 되돌림
print("before:", "discord_webhook_url" in [c["name"] for c in sa.inspect(_engine()).get_columns("projects")])
init_schema()   # stamp 0001 → upgrade head(0002)
e=sa.create_engine(os.environ["DATABASE_URL"])
with e.connect() as c: v=[r[0] for r in c.execute(sa.text("select version_num from alembic_version"))]
print("after :", "discord_webhook_url" in [c["name"] for c in sa.inspect(e).get_columns("projects")], "| version:", v)
PY
docker rm -f mw-verify >/dev/null 2>&1
```
Expected: `before: False` → `after : True | version: ['0002']` (기존 DB 를 안 깨고 0002 만 적용)

- [ ] **Step 4: 전체 스위트 회귀 (마이그레이션은 import 시 안 돎)**

Run: `./.venv/Scripts/python.exe -m pytest api/tests -q`
Expected: 전부 PASS (init_schema 는 테스트에서 호출되지 않는다)

- [ ] **Step 5: Commit**

```bash
git add api/alembic/versions/0002_add_project_discord_webhook.py api/services/db.py
git commit -F - <<'EOF'
projects.discord_webhook_url 마이그레이션(0002)을 추가한다

기존 DB adoption 을 stamp head 에서 stamp 0001 후 upgrade head 로 고쳐
baseline 이후 마이그레이션이 기존 prod 에도 정확히 적용되게 한다.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017wmqbeh5UTFZUSvfGV7zNa
EOF
```

---

### Task 3: notify 라우팅 — 프로젝트 웹훅 우선

**Files:**
- Modify: `api/services/notify.py` (`emit_session_completed`)
- Test: `api/tests/test_notify.py` (라우팅 테스트 추가 + 기존 emit 테스트에 get_project 목 추가)

**Interfaces:**
- Consumes: Task 1 의 `Project.discord_webhook_url`; 기존 `store.get_project`, `notify._build_payload`, `notify._post`, `settings.discord_webhook_url`.
- Produces: `emit_session_completed(pid, sid)` 가 `project.discord_webhook_url or settings.discord_webhook_url` 로 전송(둘 다 비면 skip). 시그니처 불변.

- [ ] **Step 1: Write the failing test**

`api/tests/test_notify.py` 에 라우팅 테스트를 추가한다:
```python
def _capture_post(monkeypatch):
    from api.services import notify
    captured = {}

    class _R:
        def raise_for_status(self): pass
    def _post(url, json, timeout):
        captured["url"] = url
        return _R()
    monkeypatch.setattr(notify.httpx, "post", _post)
    monkeypatch.setattr(notify, "_build_payload",
                        lambda pid, sid, settings: {"content": "x", "embeds": []})
    return captured


def test_emit_routes_to_project_webhook_when_set(monkeypatch):
    from api.services import notify
    from api.config import Settings
    from api.schemas.models import Project

    monkeypatch.setattr(notify, "get_settings", lambda: Settings(discord_webhook_url="https://default"))
    monkeypatch.setattr(notify.store, "get_project",
                        lambda pid: Project(id="p_1", topic="t", discord_webhook_url="https://project"))
    captured = _capture_post(monkeypatch)

    notify.emit_session_completed("p_1", "s_1")
    assert captured["url"] == "https://project"   # 프로젝트 웹훅 우선


def test_emit_falls_back_to_default_webhook(monkeypatch):
    from api.services import notify
    from api.config import Settings
    from api.schemas.models import Project

    monkeypatch.setattr(notify, "get_settings", lambda: Settings(discord_webhook_url="https://default"))
    monkeypatch.setattr(notify.store, "get_project",
                        lambda pid: Project(id="p_1", topic="t"))   # discord_webhook_url 비어있음
    captured = _capture_post(monkeypatch)

    notify.emit_session_completed("p_1", "s_1")
    assert captured["url"] == "https://default"


def test_emit_skips_when_no_webhook_anywhere(monkeypatch):
    from api.services import notify
    from api.config import Settings
    from api.schemas.models import Project

    monkeypatch.setattr(notify, "get_settings", lambda: Settings(discord_webhook_url=""))
    monkeypatch.setattr(notify.store, "get_project", lambda pid: Project(id="p_1", topic="t"))
    calls = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **k: calls.append(1))

    notify.emit_session_completed("p_1", "s_1")
    assert calls == []
```

같은 파일의 **기존** emit 테스트 4개는 이제 `emit` 이 `store.get_project` 를 호출하므로 목을 추가한다. 아래 각 테스트 함수의 `monkeypatch.setattr(notify, "get_settings", ...)` **바로 다음 줄** 에 삽입:
```python
    monkeypatch.setattr(notify.store, "get_project", lambda pid: None)
```
대상: `test_emit_skips_when_url_unset`, `test_emit_posts_payload`, `test_emit_swallows_post_errors`, `test_emit_does_not_log_webhook_url_on_http_error`.
(project 가 None 이면 웹훅은 `settings.discord_webhook_url` 로 폴백 → 기존 기대값 유지.)

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_notify.py -k "routes or falls_back or no_webhook" -v`
Expected: FAIL — `test_emit_routes_to_project_webhook_when_set` 가 `https://default` 로 가서 assert 실패(아직 라우팅 없음)

- [ ] **Step 3: Write minimal implementation**

`api/services/notify.py` 의 `emit_session_completed` 를 아래로 교체한다:
```python
def emit_session_completed(pid: str, sid: str) -> None:
    """제출 완료 알림 진입점. 백그라운드에서 호출된다.

    전송 대상은 프로젝트 웹훅(있으면) → 없으면 기본 웹훅. 둘 다 비면 skip.
    어떤 예외도 밖으로 던지지 않는다 — 알림 실패가 인터뷰를 깨선 안 된다.
    """
    settings = get_settings()
    project = store.get_project(pid)
    webhook = (project.discord_webhook_url if project else "") or settings.discord_webhook_url
    if not webhook:
        log.debug("웹훅 미설정 — 알림 skip (project=%s session=%s)", pid, sid)
        return
    try:
        payload = _build_payload(pid, sid, settings)
        if payload is None:
            log.warning("알림 payload 없음 — 세션 미발견 (project=%s session=%s)", pid, sid)
            return
        _post(webhook, payload)
        log.info("Discord 알림 전송 (project=%s session=%s)", pid, sid)
    except Exception as e:   # noqa: BLE001 — 알림은 본류를 막지 않는다
        # 예외 문자열에 webhook URL 이 섞일 수 있어 타입·상태코드만 남긴다(시크릿 노출 금지).
        status = getattr(getattr(e, "response", None), "status_code", "")
        log.warning("Discord 알림 실패 (project=%s session=%s): %s %s", pid, sid, type(e).__name__, status)
```
(`_build_payload` 가 내부에서 `get_project` 를 한 번 더 부르는 이중 조회는 감수한다 — DB 한 번 더, 테스트는 목킹돼 무해.)

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_notify.py -v`
Expected: PASS (전체 — 신규 3 + 기존 emit 4 포함)

- [ ] **Step 5: Commit**

```bash
git add api/services/notify.py api/tests/test_notify.py
git commit -F - <<'EOF'
알림을 프로젝트 웹훅으로 라우팅한다

emit 이 project.discord_webhook_url 우선, 없으면 기본 웹훅으로 보낸다.
둘 다 비면 skip.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017wmqbeh5UTFZUSvfGV7zNa
EOF
```

---

### Task 4: 엔드포인트 — 생성 시 설정 + PUT webhook

**Files:**
- Modify: `api/routers/projects.py` (import · create_project · 신규 set_webhook)
- Test: `api/tests/test_notify.py` (또는 test_schema_project.py) — 라우트 등록 + 동작

**Interfaces:**
- Consumes: Task 1 의 `ProjectCreateIn.discord_webhook_url`, `WebhookSetIn`; 기존 `store.create_project`, `store.update_project`, `store.get_project`, `_require`.
- Produces: `create_project` 가 웹훅을 넘긴다; `PUT /api/projects/{pid}/webhook` (`set_webhook(pid, body: WebhookSetIn)->Project`).

- [ ] **Step 1: Write the failing test**

`api/tests/test_schema_project.py` 에 추가:
```python
def test_webhook_route_registered():
    import api.main as m
    paths = {r.path for r in m.app.routes if hasattr(r, "path")}
    assert "/api/projects/{pid}/webhook" in paths


def test_set_webhook_updates_via_store(monkeypatch):
    from api.routers import projects
    from api.schemas.models import Project, WebhookSetIn

    updates = {}
    monkeypatch.setattr(projects.store, "get_project", lambda pid: Project(id="p_1", topic="t"))
    monkeypatch.setattr(projects.store, "update_project", lambda pid, patch: updates.update(patch))

    projects.set_webhook("p_1", WebhookSetIn(discord_webhook_url="https://x"))
    assert updates == {"discord_webhook_url": "https://x"}


def test_create_project_passes_webhook(monkeypatch):
    from api.routers import projects
    from api.schemas.models import ProjectCreateIn

    captured = {}
    monkeypatch.setattr(projects.store, "create_project",
                        lambda p: captured.update(url=p.discord_webhook_url) or p)

    projects.create_project(ProjectCreateIn(topic="주제", discord_webhook_url="https://x"))
    assert captured["url"] == "https://x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest api/tests/test_schema_project.py -k "webhook" -v`
Expected: FAIL — `test_webhook_route_registered` 에서 라우트 없음 / `set_webhook` 미정의

- [ ] **Step 3: Write minimal implementation**

`api/routers/projects.py` 의 import 에 `WebhookSetIn` 을 추가한다(기존 `from ..schemas.models import (...)` 목록에):
```python
from ..schemas.models import (
    GuideGenerateIn,
    Insight,
    InterviewGuide,
    Project,
    ProjectCreateIn,
    WebhookSetIn,
)
```

`create_project` 의 `Project(...)` 에 웹훅을 넘긴다:
```python
    return store.create_project(
        Project(topic=body.topic.strip(), title=body.title.strip() or body.topic.strip()[:40],
                target=body.target.strip(), discord_webhook_url=body.discord_webhook_url.strip())
    )
```

`create_project` 함수 **바로 아래** 에 엔드포인트를 추가한다:
```python
@router.put("/{pid}/webhook", response_model=Project)
def set_webhook(pid: str, body: WebhookSetIn) -> Project:
    """프로젝트별 Discord 웹훅 override 설정. 빈 문자열이면 기본 채널로 폴백."""
    _require(pid)
    store.update_project(pid, {"discord_webhook_url": body.discord_webhook_url.strip()})
    return _require(pid)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest api/tests -q`
Expected: 전부 PASS

- [ ] **Step 5: Commit**

```bash
git add api/routers/projects.py api/tests/test_schema_project.py
git commit -F - <<'EOF'
프로젝트 웹훅 설정 경로를 추가한다

생성 시(ProjectCreateIn) 전달 + PUT /api/projects/{pid}/webhook 로 사후 설정.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_017wmqbeh5UTFZUSvfGV7zNa
EOF
```

---

## 배포 노트 (플랜 밖)

- 이 기능은 **Alembic 0002** 를 포함하므로, 배포되면 prod startup 에서 `stamp 0001 → upgrade head` 로 `discord_webhook_url` 컬럼이 자동 추가된다(Task 2 Step 3 시나리오 B 로 검증).
- 프로젝트별 채널을 쓰려면: Discord 에서 채널·웹훅을 만들고 `PUT /api/projects/{pid}/webhook` 로 그 프로젝트에 지정. 지정 안 한 프로젝트는 기본 `DISCORD_WEBHOOK_URL` 채널로 간다.

## Self-Review (작성자 확인 완료)

- **스펙 커버리지**: 필드(Task1) · 마이그레이션+adoption 수정(Task2) · 라우팅(Task3) · 설정 경로 생성/PUT(Task4) → 설계안 A 전 항목 대응.
- **플레이스홀더**: 없음(모든 코드·명령 구체값). Task2 는 DB 필요라 수동 검증 레시피로 명시.
- **타입 일관성**: `discord_webhook_url`(str), `WebhookSetIn`, `set_webhook(pid, body: WebhookSetIn)->Project`, `emit_session_completed(pid, sid)` 가 태스크 전반에서 동일. 기존 emit 테스트의 get_project 목 누락 위험을 Task3 Step1 에 명시.
- **회귀 주의**: Task1 이 `store._project` 에 `r.discord_webhook_url` 참조를 추가하므로, 기존 `test_store_project_maps_material_text` 의 stub 갱신을 Task1 Step1 에 포함.
