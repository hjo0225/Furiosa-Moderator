# TICKET-1 — 인터뷰 그래프 골격 구현 계획 (필수①②)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 인터뷰 한 판을 살아있는 실행 하나로(스레드화 + interrupt 루프), 만능 1콜을 노드 5개 골격으로 분해한다 — LLM 콜 수·대화 품질은 현행과 동일하게 유지.

**Architecture:** `api/interview/` 신설 — 노드 5개(listen·strategize·generate·guard·speak)를 StateGraph로 엮고 `PostgresSaver`(psycopg3, 같은 Cloud SQL)로 체크포인트한다. **T1 과도기 결정: LLM 생성 콜은 기존 모더레이터 프롬프트 그대로 1콜**(일반 턴은 listen에서, 오프닝은 generate에서) — 콜 수·품질 회귀 0. strategize는 결정론 정책(12턴 하드 가드)만. 라우터는 `INTERVIEW_ENGINE` 플래그로 구엔진(moderator.py)과 병행하고, 체크포인터 연결 실패 시 구엔진 자동 폴백.

**Tech Stack:** langgraph 1.2.9 (StateGraph·interrupt·Command·InMemorySaver) · langgraph-checkpoint-postgres 3.1.0 (PostgresSaver) · psycopg3 + psycopg_pool · 기존 FastAPI/store/guardrail 재사용

**작업 위치:** 워크트리 `C:\Users\david\project\furiosa-moderator\.worktrees\langgraph` · 브랜치 `feat/langgraph-ticket-1` (ticket-0 위에서 생성됨)

## Global Constraints (전역 불변식 중 T1 해당분)

- **PII는 그래프 진입 전 마스킹** — `Command(resume=마스킹된 발화)`만. 원문은 체크포인트에 박제되므로 금지.
- **interrupt 재개 시 노드는 처음부터 재실행** → `interrupt()`는 listen의 **첫 문장**(앞에 부수효과 없음 = 멱등).
- **저장은 speak에서 완료 후 잠듦** — 진행자 턴 저장·세션 갱신은 speak, 그 다음에야 listen의 interrupt.
- **12턴 하드 가드 = 결정론 엣지** (strategize에서 LLM 출력과 무관하게 close 강제).
- 가드레일 문안·정규식·재귀 금지 그대로 — guard 노드는 `guardrail.ensure_neutral` 재사용.
- "숫자는 DB가 센다" — turns/sessions 테이블 유지. T1은 대화 이력 원본이 여전히 DB(T2에서 State로 이사).
- `llm_client` 기존 메서드 불변. 구엔진은 플래그 병행(`INTERVIEW_ENGINE`, 기본 `legacy`).
- **커밋은 코드만** — 계획 문서·docs는 스테이징하지 않는다 (사용자 선호).
- **T1 파리티 원칙**: 프롬프트·콜 수·응답 계약(TurnOut) 불변. 알려진 구엔진 특성(12턴 가드 시 모델의 질문 문장이 마지막 멘트로 나가는 것 포함)도 그대로 보존 — 품질 변경은 T3의 일.

**라이브 검증 전제:** 지연 실측(Task 5)은 `LLM_API_KEY` 필요. PostgresSaver `setup()` 라이브 확인은 DB env 필요 — 없으면 T0의 pgvector처럼 배포 환경 몫으로 기록.

---

### Task 1: State + 노드 5개 + 그래프 배선 (InMemorySaver로 TDD)

**Files:**
- Create: `api/interview/__init__.py` (빈 파일), `api/interview/state.py`, `api/interview/graph.py`
- Create: `api/interview/nodes/__init__.py` (빈 파일), `nodes/listen.py`, `nodes/strategize.py`, `nodes/generate.py`, `nodes/guard.py`, `nodes/speak.py`
- Test: `api/tests/test_interview_graph.py` (신규)

**Interfaces:**
- Consumes: `moderator._ModeratorOut`·`moderator._moderator_user`(과도기 재사용 — 구엔진 제거 시 이사), `store.list_turns/add_turn/update_session`, `guardrail.ensure_neutral`, `get_llm().structured`
- Produces (Task 3 engine이 사용):
  - `InterviewState(TypedDict, total=False)` — 아래 필드
  - `build_graph(checkpointer) -> CompiledStateGraph` — 어떤 checkpointer든 주입 가능 (테스트=InMemorySaver, 운영=PostgresSaver)
  - 그래프 흐름: `START → generate(오프닝) → guard → speak ─done→ END / ─계속→ listen【interrupt】→ strategize → generate → …`
  - 결과 state 키: `message`(최종 발화)·`done`·`is_probe`·`question_id`·`rewritten`·`covered`·`asked`

- [ ] **Step 1: 실패하는 테스트** — `api/tests/test_interview_graph.py`:

```python
"""인터뷰 그래프 골격(T1) 단위테스트 — 네트워크·DB 없이 InMemorySaver 로.

검증 대상: interrupt 루프(잠들기→재개), 노드 5개 배선, 12턴 결정론 가드,
guard 적용 조건, speak 의 저장·세션 갱신. LLM 과 store 는 가짜로 대체한다.
"""
from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from api.interview.graph import build_graph
from api.schemas.models import InterviewGuide, Question, Turn
from api.services.moderator import _ModeratorOut

GUIDE = InterviewGuide(
    project_id="p1", goal="배달앱 전환 요인",
    questions=[Question(id="q1", text="어떤 앱을 쓰세요?", goal="현재 사용 앱"),
               Question(id="q2", text="갈아탄 계기는?", goal="전환 트리거")],
)


class FakeStore:
    """turns 만 기억하는 인메모리 store 대역."""
    def __init__(self):
        self.turns: list[Turn] = []
        self.session_patches: list[dict] = []

    def list_turns(self, pid, sid):
        return list(self.turns)

    def add_turn(self, pid, sid, turn):
        self.turns.append(turn)
        return turn

    def update_session(self, pid, sid, patch):
        self.session_patches.append(patch)


class FakeLLM:
    """structured() 호출마다 큐에서 하나씩 꺼내 준다."""
    def __init__(self, outs):
        self.outs = list(outs)
        self.calls = 0

    def structured(self, system, user, schema, **kw):
        self.calls += 1
        return self.outs.pop(0), None


@pytest.fixture
def fakes(monkeypatch):
    from api.interview.nodes import generate as gen_mod
    from api.interview.nodes import guard as guard_mod
    from api.interview.nodes import listen as listen_mod
    from api.interview.nodes import speak as speak_mod

    fs = FakeStore()
    for mod in (listen_mod, speak_mod):
        monkeypatch.setattr(mod, "store", fs)
    # guard 는 LLM 없이 정규식 사전검사만 쓰도록 고정 (재작성 경로는 가드레일 자체 테스트가 커버)
    monkeypatch.setattr(
        guard_mod.guardrail, "ensure_neutral",
        lambda q, **kw: (q, False, "") if "당연히" not in q else ("중립 질문으로 재작성", True, "당연시"),
    )

    def set_llm(outs):
        llm = FakeLLM(outs)
        monkeypatch.setattr(listen_mod, "get_llm", lambda: llm)
        monkeypatch.setattr(gen_mod, "get_llm", lambda: llm)
        return llm

    return fs, set_llm


def _start(g, config):
    return g.invoke(
        {"project_id": "p1", "session_id": "s1", "lang": "ko",
         "guide": GUIDE.model_dump(), "covered": [], "asked": 0},
        config,
    )


def test_opening_then_sleeps_at_interrupt(fakes):
    fs, set_llm = fakes
    set_llm([_ModeratorOut(message="안녕하세요! 어떤 배달앱을 쓰세요?", question_id="q1")])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    result = _start(g, config)

    assert result["message"] == "안녕하세요! 어떤 배달앱을 쓰세요?"
    assert result["asked"] == 1 and result["covered"] == ["q1"]
    assert fs.turns[-1].role == "moderator"          # speak 가 저장했다
    assert "__interrupt__" in result                  # listen 에서 잠들었다
    assert g.get_state(config).next == ("listen",)


def test_resume_probe_then_close_ends(fakes):
    fs, set_llm = fakes
    set_llm([
        _ModeratorOut(message="오프닝 질문입니다?", question_id="q1"),
        _ModeratorOut(message="어느 정도일 때 부담되세요?", question_id="q1", is_probe=True),
        _ModeratorOut(message="감사합니다. 마치겠습니다.", done=True),
    ])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)

    r2 = g.invoke(Command(resume="배달비가 부담돼요"), config)
    assert r2["is_probe"] is True and r2["done"] is False
    assert r2["asked"] == 2
    assert "__interrupt__" in r2

    r3 = g.invoke(Command(resume="그 정도예요"), config)
    assert r3["done"] is True
    assert "__interrupt__" not in r3                  # END 도달
    assert g.get_state(config).next == ()             # 더 깰 것이 없다
    assert fs.session_patches[-1]["status"] == "completed"


def test_12turn_hard_guard_forces_close(fakes):
    fs, set_llm = fakes
    # 이미 진행자 질문 11개가 저장돼 있다 → 이번이 12번째 = 강제 종료
    fs.turns = [Turn(role="moderator", text=f"질문{i}") for i in range(11)]
    set_llm([
        _ModeratorOut(message="오프닝?", question_id="q1"),
        _ModeratorOut(message="더 파고들 질문?", question_id="q2", is_probe=True),  # LLM 은 계속하려 한다
    ])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    r = g.invoke(Command(resume="네"), config)
    assert r["done"] is True                          # 결정론 엣지가 이겼다


def test_guard_rewrites_leading_question(fakes):
    fs, set_llm = fakes
    set_llm([_ModeratorOut(message="당연히 편하셨죠?", question_id="q1")])
    g = build_graph(InMemorySaver())
    r = _start(g, {"configurable": {"thread_id": "s1"}})
    assert r["message"] == "중립 질문으로 재작성"
    assert r["rewritten"] is True
    assert fs.turns[-1].guardrail_rewritten is True
```

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest api/tests/test_interview_graph.py -v` (워크트리에서)
Expected: FAIL — `ModuleNotFoundError: api.interview`

- [ ] **Step 3: 구현** — 파일 8개:

`api/interview/state.py`:
```python
"""인터뷰 그래프 상태 — T1 은 턴 스크래치 + 최소 세션 컨텍스트만.

T2 에서 messages·ledger 가 들어오며 '그래프가 상태를 소유'가 완성된다.
지금은 대화 이력·커버리지의 원본이 여전히 DB(store)다.
"""
from __future__ import annotations

from typing import TypedDict


class InterviewState(TypedDict, total=False):
    # 세션 컨텍스트 — 그래프 시작 시 1회 주입, 체크포인트로 유지
    project_id: str
    session_id: str
    lang: str
    guide: dict                # InterviewGuide.model_dump()
    covered: list[str]
    asked: int                 # 진행자 질문 수 (speak 가 +1)

    # 턴 스크래치 — 매 턴 덮어씀
    utterance: str             # 마스킹된 응답자 발화 (listen 의 interrupt 반환값)
    draft: str                 # 질문 초안 (T1: 만능 콜 출력)
    action: str                # probe | advance | close
    question_id: str
    is_probe: bool
    message: str               # guard 를 통과한 최종 발화
    rewritten: bool
    done: bool
```

`api/interview/nodes/listen.py`:
```python
"""listen — 발화 대기(interrupt)와 분석·행동·초안의 만능 1콜 (T1 과도기).

interrupt() 가 노드 첫 문장인 것이 규약이다: 재개 시 노드가 처음부터 재실행돼도
interrupt 앞에 부수효과가 없어 멱등이다(전역 불변식).

T1 은 기존 모더레이터 프롬프트를 그대로 써서 분석+행동선택+질문초안을 1콜로 받는다
(콜 수·대화 품질 불변). T3 에서 분석(listen)/생성(generate) 콜로 분리된다.
"""
from __future__ import annotations

from langgraph.types import interrupt

from ...prompts.interview_moderator import interview_moderator_system
from ...schemas.models import InterviewGuide
from ...services import store
from ...services.llm_client import get_llm
from ...services.moderator import _ModeratorOut, _moderator_user
from ..state import InterviewState


def listen(state: InterviewState) -> dict:
    utterance = interrupt({"waiting": "respondent"})  # 여기서 잠든다 — 재개값 = 마스킹된 발화

    history = store.list_turns(state["project_id"], state["session_id"])
    asked = sum(1 for t in history if t.role == "moderator")
    guide = InterviewGuide.model_validate(state["guide"])
    out, _ = get_llm().structured(
        interview_moderator_system(state.get("lang", "ko")),
        _moderator_user(guide, history, asked, list(state.get("covered", []))),
        _ModeratorOut,
        max_tokens=500,
    )
    return {
        "utterance": utterance or "",
        "draft": (out.message or "").strip(),
        "action": "close" if out.done else ("probe" if out.is_probe else "advance"),
        "question_id": out.question_id or "",
        "is_probe": bool(out.is_probe),
        "asked": asked,
    }
```

`api/interview/nodes/strategize.py`:
```python
"""strategize — T1 은 결정론 정책만: 12턴 하드 가드. 행동 7종 선택은 T3 에서."""
from __future__ import annotations

from ..state import InterviewState

MAX_ASKED = 12  # moderator._MAX_ASKED 와 동일 값 — 구엔진 제거 시 여기가 단일 출처


def strategize(state: InterviewState) -> dict:
    # 결정론 하드 가드 — LLM 이 close 를 안 내도 12번째 질문에서 끝낸다
    if state.get("asked", 0) + 1 >= MAX_ASKED:
        return {"action": "close"}
    return {}
```

`api/interview/nodes/generate.py`:
```python
"""generate — T1 은 오프닝 생성 + close 시 마무리 확정만.

일반 턴의 생성 콜은 T1 에선 listen 의 만능 콜에 있다(콜 수 불변).
T3~T5 에서 행동별 생성·도구 호출이 이 노드로 들어온다.
"""
from __future__ import annotations

from ...prompts.interview_moderator import interview_moderator_system
from ...schemas.models import InterviewGuide
from ...services.llm_client import get_llm
from ...services.moderator import _ModeratorOut, _moderator_user
from ..state import InterviewState

_FAREWELL_FALLBACK = "오늘 말씀 정말 감사합니다. 여기서 인터뷰를 마치겠습니다."


def generate(state: InterviewState) -> dict:
    if state.get("action") == "close":
        # 구엔진 파리티: 모델이 준 문장이 있으면 그대로(12턴 가드로 잘린 경우 질문일 수도
        # 있다 — 알려진 구엔진 특성 보존), 없으면 기본 인사.
        return {"draft": state.get("draft") or _FAREWELL_FALLBACK, "done": True}

    if not state.get("draft"):
        # 오프닝 턴 — 그래프 진입 직후 (이력 없음)
        guide = InterviewGuide.model_validate(state["guide"])
        out, _ = get_llm().structured(
            interview_moderator_system(state.get("lang", "ko")),
            _moderator_user(guide, [], 0, []),
            _ModeratorOut,
            max_tokens=500,
        )
        return {
            "draft": (out.message or "").strip(),
            "question_id": out.question_id or "",
            "is_probe": False,
            "action": "advance",
        }
    return {}
```

`api/interview/nodes/guard.py`:
```python
"""guard — 중립성 검수. 마무리 멘트(done)는 질문이 아니므로 검사하지 않는다(기존 동일)."""
from __future__ import annotations

from ...services import guardrail
from ..state import InterviewState


def guard(state: InterviewState) -> dict:
    draft = state.get("draft", "")
    if state.get("done") or not draft:
        return {"message": draft, "rewritten": False}
    message, rewritten, _reason = guardrail.ensure_neutral(draft)
    return {"message": message, "rewritten": rewritten}
```

`api/interview/nodes/speak.py`:
```python
"""speak — 진행자 턴 저장 + 세션 갱신. '저장은 speak 에서 완료 후 잠듦'(전역 불변식).

SSE 스트리밍 연결은 T4. T1 은 동기 반환이다.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ...schemas.models import Turn
from ...services import store
from ..state import InterviewState


def speak(state: InterviewState) -> dict:
    pid, sid = state["project_id"], state["session_id"]
    store.add_turn(pid, sid, Turn(
        role="moderator",
        text=state.get("message", ""),
        is_probe=bool(state.get("is_probe")),
        question_id=state.get("question_id", ""),
        guardrail_rewritten=bool(state.get("rewritten")),
    ))
    covered = list(state.get("covered", []))
    qid = state.get("question_id", "")
    if qid and qid not in covered:
        covered.append(qid)
    asked = state.get("asked", 0) + 1
    patch: dict = {"asked": asked, "covered": covered, "status": "active"}
    if state.get("done"):
        patch["status"] = "completed"
        patch["ended_at"] = datetime.now(timezone.utc)
    store.update_session(pid, sid, patch)
    # 턴 스크래치 초기화 — 다음 턴의 오프닝 오인 방지
    return {"covered": covered, "asked": asked, "draft": "", "utterance": ""}
```

`api/interview/graph.py`:
```python
"""인터뷰 그래프 골격 (T1) — interrupt 루프 + 노드 5개.

START → generate(오프닝) → guard → speak ─done→ END
                                      └계속→ listen【interrupt】→ strategize → generate → …
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes.generate import generate
from .nodes.guard import guard
from .nodes.listen import listen
from .nodes.speak import speak
from .nodes.strategize import strategize
from .state import InterviewState


def _after_speak(state: InterviewState) -> str:
    return END if state.get("done") else "listen"


def build_graph(checkpointer):
    g = StateGraph(InterviewState)
    g.add_node("listen", listen)
    g.add_node("strategize", strategize)
    g.add_node("generate", generate)
    g.add_node("guard", guard)
    g.add_node("speak", speak)
    g.add_edge(START, "generate")
    g.add_edge("listen", "strategize")
    g.add_edge("strategize", "generate")
    g.add_edge("generate", "guard")
    g.add_edge("guard", "speak")
    g.add_conditional_edges("speak", _after_speak, {END: END, "listen": "listen"})
    return g.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: 통과 확인**

Run: `python -m pytest api/tests/test_interview_graph.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 전체 회귀**

Run: `python -m pytest api/tests -q`
Expected: 23 passed (기존 19 + 신규 4)

- [ ] **Step 6: Commit (코드만)**

```bash
git add api/interview/ api/tests/test_interview_graph.py
git commit -m "feat(graph): 인터뷰 그래프 골격 — 노드 5개 + interrupt 루프 (TICKET-1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: PostgresSaver 배선 (checkpoint.py)

**Files:**
- Create: `api/interview/checkpoint.py`
- Test: `api/tests/test_interview_graph.py` (conn_string 테스트 2개 추가)

**Interfaces:**
- Produces: `conn_string() -> str` (env 해석·정규화), `get_checkpointer() -> PostgresSaver` (lru_cache 싱글톤, `setup()` 포함 — 실패는 예외로 호출부 전파)

- [ ] **Step 1: 실패하는 테스트 추가** — `test_interview_graph.py` 끝에:

```python
# --- checkpoint conn_string ----------------------------------------------------

def test_conn_string_normalizes_pg8000_url(monkeypatch):
    from api.interview import checkpoint
    monkeypatch.delenv("INSTANCE_CONNECTION_NAME", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+pg8000://u:p@localhost:5432/mindlens")
    assert checkpoint.conn_string() == "postgresql://u:p@localhost:5432/mindlens"


def test_conn_string_uses_cloudsql_socket(monkeypatch):
    from api.interview import checkpoint
    monkeypatch.setenv("INSTANCE_CONNECTION_NAME", "proj:asia-northeast3:db")
    monkeypatch.setenv("DB_USER", "postgres")
    monkeypatch.setenv("DB_PASSWORD", "pw")
    monkeypatch.setenv("DB_NAME", "mindlens")
    s = checkpoint.conn_string()
    assert "host=/cloudsql/proj:asia-northeast3:db" in s and "dbname=mindlens" in s
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest api/tests/test_interview_graph.py -v -k conn_string` → FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현** — `api/interview/checkpoint.py`:

```python
"""체크포인터 배선 — PostgresSaver(psycopg3) 를 도메인 DB 와 같은 Postgres 에 붙인다.

접속 경로가 도메인 DB(pg8000+커넥터)와 다른 이유: Cloud SQL Python Connector 는
psycopg3 드라이버를 지원하지 않는다. 그래서
- 로컬:      DATABASE_URL (postgresql+pg8000:// 접두어는 psycopg 용으로 정규화)
- Cloud Run: --add-cloudsql-instances 유닉스 소켓 (host=/cloudsql/<ICN>) — 배포 플래그 필요
"""
from __future__ import annotations

import os
from functools import lru_cache


def conn_string() -> str:
    icn = os.environ.get("INSTANCE_CONNECTION_NAME", "")
    if icn:
        user = os.environ.get("DB_USER", "postgres")
        pw = os.environ.get("DB_PASSWORD", "")
        db = os.environ.get("DB_NAME", "mindlens")
        return f"host=/cloudsql/{icn} dbname={db} user={user} password={pw}"
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("체크포인터: INSTANCE_CONNECTION_NAME 또는 DATABASE_URL 이 필요합니다.")
    for prefix in ("postgresql+pg8000://", "postgres+pg8000://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


@lru_cache
def get_checkpointer():
    """PostgresSaver 싱글톤 — 커넥션 풀 + setup(멱등). 실패는 호출부(engine.ready)가 처리."""
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(
        conn_string(),
        min_size=0,
        max_size=4,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    saver = PostgresSaver(pool)
    saver.setup()  # 체크포인트 테이블 생성(멱등)
    return saver
```

- [ ] **Step 4: 통과 + 회귀** — Run: `python -m pytest api/tests -q` → 25 passed

- [ ] **Step 5: Commit**

```bash
git add api/interview/checkpoint.py api/tests/test_interview_graph.py
git commit -m "feat(graph): PostgresSaver 배선 — Cloud SQL 소켓/DATABASE_URL 이원 경로 (TICKET-1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: 엔진 파사드 + INTERVIEW_ENGINE 플래그 + 라우터 분기

**Files:**
- Create: `api/interview/engine.py`
- Modify: `api/config.py` (설정 1개), `api/routers/public.py` (turn 분기), `api/main.py` (startup 웜업)
- Test: `api/tests/test_interview_graph.py` (라우팅 테스트 2개 추가)

**Interfaces:**
- Consumes: Task 1 `build_graph`, Task 2 `get_checkpointer`, `moderator.tag_emotion`, `pii.mask_pii/scan_pii`, `store.add_turn`
- Produces: `engine.next_turn(project_id, session, guide, respondent_text, lang) -> tuple[str, bool, Turn | None, Turn]` — **moderator.next_turn 과 동일 계약** (라우터 분기가 3줄로 끝나는 이유). `engine.ready() -> bool` (체크포인터 실패 시 False → 구엔진 폴백).

- [ ] **Step 1: 실패하는 테스트 추가**:

```python
# --- 엔진 플래그 라우팅 ---------------------------------------------------------

def _stub_router_deps(monkeypatch, pub):
    from api.schemas.models import Session

    monkeypatch.setattr(pub.store, "get_session", lambda p, s: Session(id="s1", project_id="p1"))
    monkeypatch.setattr(pub.store, "get_guide", lambda p: GUIDE)


def _spy_engine(called, name):
    def fake_next_turn(*a, **k):
        called["engine"] = name
        return "m", False, None, Turn(role="moderator", text="m")
    return fake_next_turn


def test_turn_uses_legacy_engine_by_default(monkeypatch):
    import api.routers.public as pub
    from api.config import get_settings
    from api.schemas.models import TurnIn

    monkeypatch.delenv("INTERVIEW_ENGINE", raising=False)
    get_settings.cache_clear()
    called = {}
    monkeypatch.setattr(pub.moderator, "next_turn", _spy_engine(called, "legacy"))
    _stub_router_deps(monkeypatch, pub)

    pub.turn("p1", "s1", TurnIn(text=""))
    assert called["engine"] == "legacy"
    get_settings.cache_clear()


def test_turn_uses_graph_engine_when_flag_set(monkeypatch):
    import api.routers.public as pub
    from api.config import get_settings
    from api.schemas.models import TurnIn

    monkeypatch.setenv("INTERVIEW_ENGINE", "graph")
    get_settings.cache_clear()
    called = {}
    monkeypatch.setattr(pub.graph_engine, "ready", lambda: True)
    monkeypatch.setattr(pub.graph_engine, "next_turn", _spy_engine(called, "graph"))
    _stub_router_deps(monkeypatch, pub)

    pub.turn("p1", "s1", TurnIn(text=""))
    assert called["engine"] == "graph"
    get_settings.cache_clear()
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest api/tests/test_interview_graph.py -v -k engine` → FAIL (`AttributeError: graph_engine`)

- [ ] **Step 3: 구현.**

`api/config.py` — `Settings`에 추가 (`# --- 앱 ---` 섹션):
```python
    # 인터뷰 엔진: legacy(구엔진 moderator.py) | graph(LangGraph, TICKET-1+)
    interview_engine: str = "legacy"
```
`get_settings()`에 추가:
```python
        interview_engine=env.get("INTERVIEW_ENGINE", "legacy"),
```

`api/interview/engine.py`:
```python
"""그래프 엔진 파사드 — moderator.next_turn 과 동일한 계약.

라우터는 INTERVIEW_ENGINE 플래그로 이 모듈과 구엔진 중 하나를 고른다.
PII 마스킹·응답자 턴 저장·감정 태깅은 그래프 진입 전(여기)에서 — 전역 불변식.
Command(resume=…) 에는 마스킹된 발화만 들어간다(체크포인트에 박제되므로).
"""
from __future__ import annotations

import logging
from functools import lru_cache

from langgraph.types import Command

from ..schemas.models import InterviewGuide, Session, Turn
from ..services import store
from ..services.moderator import tag_emotion
from ..services.pii import mask_pii, scan_pii
from .checkpoint import get_checkpointer
from .graph import build_graph

log = logging.getLogger(__name__)


@lru_cache
def get_graph():
    return build_graph(get_checkpointer())


def ready() -> bool:
    """그래프 엔진 가용성 — 체크포인터 연결 실패 시 False (라우터가 구엔진 폴백)."""
    try:
        get_graph()
        return True
    except Exception as e:
        log.warning("그래프 엔진 비활성 (체크포인터 실패): %s", e)
        return False


def next_turn(
    project_id: str, session: Session, guide: InterviewGuide, respondent_text: str, lang: str = "ko"
) -> tuple[str, bool, Turn | None, Turn]:
    """moderator.next_turn 과 동일 반환: (발화, 종료, 응답자턴|None, 진행자턴)."""
    g = get_graph()
    sid = session.id
    config = {"configurable": {"thread_id": sid}}

    respondent_turn: Turn | None = None
    masked = ""
    text = (respondent_text or "").strip()
    if text:
        pii_types = scan_pii(text)
        masked = mask_pii(text)
        emotion, conf = tag_emotion(masked)
        respondent_turn = store.add_turn(project_id, sid, Turn(
            role="respondent", text=masked, emotion=emotion,
            emotion_confidence=conf, pii_types=pii_types,
        ))

    if g.get_state(config).next:          # interrupt 에서 잠들어 있다 → 재개
        result = g.invoke(Command(resume=masked), config)
    else:                                 # 첫 호출 → 그래프 시작(오프닝)
        result = g.invoke(
            {"project_id": project_id, "session_id": sid, "lang": lang,
             "guide": guide.model_dump(), "covered": list(session.covered),
             "asked": session.asked},
            config,
        )

    message = result.get("message", "")
    done = bool(result.get("done"))
    session.covered = list(result.get("covered", session.covered))
    session.asked = int(result.get("asked", session.asked))
    moderator_turn = Turn(
        role="moderator", text=message,
        is_probe=bool(result.get("is_probe")),
        question_id=result.get("question_id", ""),
        guardrail_rewritten=bool(result.get("rewritten")),
    )
    return message, done, respondent_turn, moderator_turn
```

`api/routers/public.py` — import에 추가:
```python
from ..config import get_settings
from ..interview import engine as graph_engine
```
`turn()` 안의 호출부 교체 (기존 `moderator.next_turn(...)` 한 줄 →):
```python
    use_graph = get_settings().interview_engine == "graph" and graph_engine.ready()
    run = graph_engine.next_turn if use_graph else moderator.next_turn
    try:
        message, done, _, mod_turn = run(pid, session, guide, body.text, body.lang)
```

`api/main.py` — `_startup()` 끝에 추가:
```python
        if get_settings().interview_engine == "graph":
            from .interview import engine as graph_engine

            log.info("그래프 엔진: %s", "준비 완료" if graph_engine.ready() else "실패 → 구엔진 폴백")
```
(주의: 이 두 줄은 init_schema 와 같은 try 블록 안 — 실패해도 앱은 뜬다.)

- [ ] **Step 4: 통과 + 회귀** — Run: `python -m pytest api/tests -q` → 27 passed

- [ ] **Step 5: Commit**

```bash
git add api/interview/engine.py api/config.py api/routers/public.py api/main.py api/tests/test_interview_graph.py
git commit -m "feat(graph): 엔진 파사드 + INTERVIEW_ENGINE 플래그 — 구엔진 병행 (TICKET-1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: 턴 지연 실측 스크립트 + 실측

**Files:**
- Create: `scripts/exp_turn_latency.py`

**Interfaces:**
- Consumes: `build_graph(InMemorySaver())`, `moderator.next_turn` — 같은 가짜 store·감정태깅 무력화로 공정 비교, LLM 만 실물.

- [ ] **Step 1: 스크립트 작성** — `scripts/exp_turn_latency.py`:

```python
"""TICKET-1 검증 — 구엔진 vs 그래프 엔진 턴 지연 비교 (LLM 실물, store 가짜).

같은 대본(오프닝 + 응답 3개)을 두 엔진에 태워 턴별 지연을 잰다.
감정 태깅은 양쪽에서 무력화(동일 조건) — 그래프 오버헤드만 본다.

사용:  python scripts/exp_turn_latency.py
전제:  LLM_API_KEY
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ANSWERS = ["주로 배민 쓰는데 요즘 쿠팡이츠로 갈아탔어요", "배달비가 부담돼서요", "무료배달 쿠폰이 결정적이었어요"]


def fake_stores(monkey_targets):
    from api.schemas.models import Turn

    turns: list[Turn] = []

    class FS:
        @staticmethod
        def list_turns(pid, sid):
            return list(turns)

        @staticmethod
        def add_turn(pid, sid, t):
            turns.append(t)
            return t

        @staticmethod
        def update_session(pid, sid, patch):
            pass

    for mod in monkey_targets:
        mod.store = FS
    return turns


def main() -> int:
    if not os.environ.get("LLM_API_KEY"):
        print("LLM_API_KEY 필요")
        return 2
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command

    import api.interview.nodes.listen as listen_mod
    import api.interview.nodes.speak as speak_mod
    import api.services.moderator as legacy
    from api.interview.graph import build_graph
    from api.schemas.models import InterviewGuide, Question, Session

    legacy.tag_emotion = lambda t: ("중립", 0.0)  # 동일 조건

    guide = InterviewGuide(project_id="p", goal="배달앱 전환 요인", questions=[
        Question(id="q1", text="어떤 배달앱을 쓰세요?", goal="현재 앱"),
        Question(id="q2", text="갈아탄 계기는?", goal="전환 트리거"),
        Question(id="q3", text="지금 만족도는?", goal="만족도"),
    ])

    # --- 구엔진 ---
    turns = fake_stores([legacy])
    legacy_session = Session(id="L", project_id="p")
    t_legacy = []
    for text in ["", *ANSWERS]:
        t0 = time.perf_counter()
        msg, done, _, _ = legacy.next_turn("p", legacy_session, guide, text)
        t_legacy.append(time.perf_counter() - t0)
        print(f"  legacy {t_legacy[-1]:.2f}s  {msg[:36]}")
        if done:
            break

    # --- 그래프 ---
    turns = fake_stores([listen_mod, speak_mod])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "G"}}
    t_graph = []
    t0 = time.perf_counter()
    r = g.invoke({"project_id": "p", "session_id": "G", "lang": "ko",
                  "guide": guide.model_dump(), "covered": [], "asked": 0}, config)
    t_graph.append(time.perf_counter() - t0)
    print(f"  graph  {t_graph[-1]:.2f}s  {r.get('message', '')[:36]}")
    for text in ANSWERS:
        if r.get("done"):
            break
        t0 = time.perf_counter()
        r = g.invoke(Command(resume=text), config)
        t_graph.append(time.perf_counter() - t0)
        print(f"  graph  {t_graph[-1]:.2f}s  {r.get('message', '')[:36]}")

    print(f"\nlegacy mean {sum(t_legacy)/len(t_legacy):.2f}s | graph mean {sum(t_graph)/len(t_graph):.2f}s "
          f"| 오버헤드 {sum(t_graph)/len(t_graph) - sum(t_legacy)/len(t_legacy):+.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 문법 확인** — Run: `python -c "import ast; ast.parse(open('scripts/exp_turn_latency.py', encoding='utf-8').read()); print('ok')"` → `ok`

- [ ] **Step 3: 실측 (LLM_API_KEY 필요)** — Run: `LLM_API_KEY=<키> python scripts/exp_turn_latency.py`
Expected: 두 엔진 모두 4턴 완주, 그래프 오버헤드 **±0.3s 이내** (동일 프롬프트·동일 콜 수이므로 차이는 그래프 프레임워크 비용뿐이어야 함). 결과 수치는 TICKETS.md 검증란에 손으로 기록(커밋 안 함).

- [ ] **Step 4: Commit (스크립트만)**

```bash
git add scripts/exp_turn_latency.py
git commit -m "test(exp): 구엔진 vs 그래프 턴 지연 비교 스크립트 (TICKET-1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## 검증 (전체)

1. **단위**: `python -m pytest api/tests -q` — 27 passed (기존 19 + 그래프 4 + conn_string 2 + 라우팅 2).
2. **interrupt 왕복**: test_resume_probe_then_close_ends 가 잠들기→재개→종료 전 과정을 InMemorySaver 로 검증.
3. **12턴 결정론 가드**: test_12turn_hard_guard_forces_close.
4. **지연 실측**: exp_turn_latency.py — 그래프 오버헤드 ±0.3s 이내 확인, 수치 기록.
5. **PostgresSaver 라이브**: DB env 있는 환경에서 `INTERVIEW_ENGINE=graph`로 앱 기동 → 로그 "그래프 엔진: 준비 완료" + `checkpoints` 테이블 생성 확인. (env 없으면 T0 pgvector처럼 배포 환경 몫으로 기록.)
5-1. **_GUARDED**: 신규 라우트 없음 — turn 경로는 기존 `/api/public/` 프리픽스로 이미 레이트리밋 커버 (기존 test_interview_routes_registered 가 경로 존재를 검증). 티켓의 "_GUARDED 확장" 항목은 "확장 불필요 확인"으로 종결.
6. **TICKETS.md** TICKET-1 체크박스 갱신 — **커밋하지 않는다** (코드만 커밋).

## 범위 밖

- messages·원장을 State로 (T2) · 행동 7종 (T3) · reflect/SSE (T4) · 도구 (T5)
- 구엔진 제거 — 플래그 병행 유지, 제거는 마이그레이션 마지막
- 프롬프트 개선·마무리 멘트 품질(12턴 가드 파리티 특성 포함) — T3
