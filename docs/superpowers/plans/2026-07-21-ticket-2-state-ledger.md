# TICKET-2 — 상태 이동 + 커버리지 원장 구현 계획 (필수③)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대화(messages)·커버리지(원장)·페이스(asked·probe_streak)를 그래프 State로 옮겨 체크포인트가 저장할 대상을 만들고, 출석부(covered)를 취재 수첩(원장)으로 바꾼다.

**Architecture:** State에 `messages(add_messages 리듀서)`·`ledger`·`probe_streak`가 들어오고 **listen이 store를 더 이상 읽지 않는다**(매 턴 기억 재조립 해소 — 한계② 해결). 그래프는 이제 자기 프롬프트·스키마(`api/interview/prompts.py`의 `ListenOut`)를 가진다 — 만능 콜이 facts·hooks·coverage 판정을 함께 반환하고, listen이 노드 내에서 원장을 갱신한다(슬로우패스 이사는 T4). strategize에 **정직한 종료**(모든 문항 satisfied/saturated → 결정론 close) 추가. 구엔진(moderator.py)은 문자 그대로 불변 — 그래프가 사설 심볼(`_ModeratorOut`·`_moderator_user`) 재사용하던 것도 이번에 끊는다.

**Tech Stack:** langgraph `add_messages` + langchain-core 1.5.0 메시지(HumanMessage=응답자, AIMessage=진행자 — 체크포인트 serde 기본 지원) · 기존 T1 그래프 골격

**작업 위치:** 워크트리 `.worktrees/langgraph` · 브랜치 `feat/langgraph-ticket-1` 이어서 (T1 위에 T2 커밋 — 브랜치는 사용자 결정대로 유지)

## Global Constraints

- 구엔진 `moderator.py` **불변** (플래그 병행 중 — 파리티 기준선 유지).
- 대시보드용 도메인 테이블 유지: `sessions.covered`·`turns`는 speak/engine이 계속 기록 (이원화 의도된 설계). ledger는 T2에선 체크포인트에만 산다.
- interrupt 멱등 규약: `interrupt()`는 여전히 listen 첫 문장.
- 12턴 하드 가드 유지 + 정직한 종료 추가 (둘 다 strategize의 결정론).
- 원장 status는 **후퇴 금지**: pending→touched→satisfied→saturated 순방향만.
- 커밋은 코드만 (docs 스테이징 금지).
- T2 검증 = **probe율 비교** (프롬프트가 원장 컨텍스트로 확장되므로 품질 변화를 측정하는 것이 목적 — 파리티가 아니라 개선 확인).

---

### Task 1: State 확장 + 원장 자료구조 (순수 단위 테스트)

**Files:**
- Modify: `api/interview/state.py` (CoverageEntry·messages·ledger·probe_streak·init_ledger)
- Create: `api/interview/ledger.py` (update_ledger — 순수 함수)
- Test: `api/tests/test_interview_ledger.py` (신규)

**Interfaces:**
- Produces:
  - `CoverageEntry(TypedDict)`: `status: str`("pending|touched|satisfied|saturated") · `facts: list[str]` · `hooks: list[str]`
  - `init_ledger(guide: dict) -> dict[str, CoverageEntry]` — guide.questions 전부 pending으로
  - `update_ledger(ledger, qid: str, coverage: str, facts: list[str], hooks: list[str]) -> dict` — **원본 불변**(새 dict 반환), facts/hooks 중복 없이 누적, status 후퇴 금지. qid가 없거나 원장에 없으면 복사본 그대로.
  - `InterviewState` 추가 필드: `messages: Annotated[list, add_messages]` · `ledger: dict[str, CoverageEntry]` · `probe_streak: int`

- [ ] **Step 1: 실패하는 테스트** — `api/tests/test_interview_ledger.py`:

```python
"""원장(ledger) 자료구조 단위테스트 — 순수 함수, 그래프 없이."""
from __future__ import annotations

from api.interview.ledger import update_ledger
from api.interview.state import init_ledger

GUIDE = {"questions": [{"id": "q1", "text": "앱?", "goal": "현재 앱"},
                       {"id": "q2", "text": "계기?", "goal": "트리거"}]}


def test_init_ledger_all_pending():
    led = init_ledger(GUIDE)
    assert set(led) == {"q1", "q2"}
    assert all(e == {"status": "pending", "facts": [], "hooks": []} for e in led.values())


def test_update_accumulates_facts_without_dup():
    led = init_ledger(GUIDE)
    led2 = update_ledger(led, "q1", "touched", ["배민 사용"], ["배민클럽 언급"])
    led3 = update_ledger(led2, "q1", "touched", ["배민 사용", "주 3회 주문"], [])
    assert led3["q1"]["facts"] == ["배민 사용", "주 3회 주문"]
    assert led3["q1"]["hooks"] == ["배민클럽 언급"]
    assert led3["q1"]["status"] == "touched"
    assert led["q1"]["facts"] == []              # 원본 불변


def test_status_never_regresses():
    led = init_ledger(GUIDE)
    led = update_ledger(led, "q1", "satisfied", ["fact"], [])
    led = update_ledger(led, "q1", "touched", [], [])   # 후퇴 시도
    assert led["q1"]["status"] == "satisfied"
    led = update_ledger(led, "q1", "saturated", [], [])  # 전진은 허용
    assert led["q1"]["status"] == "saturated"


def test_unknown_qid_is_noop_copy():
    led = init_ledger(GUIDE)
    led2 = update_ledger(led, "없는문항", "touched", ["x"], [])
    assert led2 == led and led2 is not led
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest api/tests/test_interview_ledger.py -q` → FAIL (`ModuleNotFoundError: api.interview.ledger`)

- [ ] **Step 3: 구현.**

`api/interview/state.py` 전체 교체:
```python
"""인터뷰 그래프 상태 — T2: 그래프가 대화·커버리지·페이스를 소유한다.

messages 가 대화의 원본이다(add_messages 리듀서, 12턴 캡이라 통째 보관).
DB(turns/sessions)는 대시보드용 기록 — 이원화가 의도된 설계.
원장(ledger)은 출석부가 아니라 취재 수첩: 문항별 상태·알아낸 사실·안 판 떡밥.
"""
from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class CoverageEntry(TypedDict):
    status: str            # pending | touched | satisfied | saturated
    facts: list[str]       # 이 문항에서 실제로 알아낸 것
    hooks: list[str]       # 파고들 만했는데 안 판 떡밥


def init_ledger(guide: dict) -> dict[str, CoverageEntry]:
    """가이드 문항 전부를 pending 원장으로."""
    return {
        q["id"]: CoverageEntry(status="pending", facts=[], hooks=[])
        for q in guide.get("questions", [])
        if q.get("id")
    }


class InterviewState(TypedDict, total=False):
    # 세션 컨텍스트 — 그래프 시작 시 1회 주입, 체크포인트로 유지
    project_id: str
    session_id: str
    lang: str
    guide: dict                # InterviewGuide.model_dump()

    # 그래프가 소유하는 상태 (T2, 필수③)
    messages: Annotated[list, add_messages]   # 응답자=Human, 진행자=AI
    ledger: dict[str, CoverageEntry]
    covered: list[str]         # 대시보드용 출석부 — sessions.covered 와 동기
    asked: int                 # 진행자 질문 수 (speak 가 +1)
    probe_streak: int          # 현 문항 연속 꼬리질문 수 (speak 가 갱신)

    # 턴 스크래치 — 매 턴 덮어씀
    utterance: str
    draft: str
    action: str                # probe | advance | close
    question_id: str
    is_probe: bool
    message: str
    rewritten: bool
    done: bool
    end_reason: str            # model_done | max_turns | honest_close — 종료 근거 기록
```

(티켓 명세의 `analysis`·`plan` 필드는 T3 콜 분리 때 들어온다 — T2에선 facts/hooks가 분석을, action이 plan 역할을 대신한다. 계획서에 이 결정을 명시.)

`api/interview/ledger.py`:
```python
"""원장 갱신 — 순수 함수. T2 는 listen 노드 내에서 호출, T4 에 슬로우패스로 이사."""
from __future__ import annotations

from .state import CoverageEntry

_ORDER = ["pending", "touched", "satisfied", "saturated"]


def update_ledger(
    ledger: dict[str, CoverageEntry], qid: str, coverage: str, facts: list[str], hooks: list[str]
) -> dict[str, CoverageEntry]:
    """직전 문항(qid)의 취재 결과를 반영한 새 원장을 돌려준다(원본 불변).

    - facts/hooks 는 중복 없이 누적
    - status 는 후퇴 금지 (satisfied 를 touched 로 강등하지 않는다)
    """
    new = {
        k: CoverageEntry(status=e["status"], facts=list(e["facts"]), hooks=list(e["hooks"]))
        for k, e in ledger.items()
    }
    if not qid or qid not in new:
        return new
    e = new[qid]
    e["facts"] += [f for f in facts if f and f not in e["facts"]]
    e["hooks"] += [h for h in hooks if h and h not in e["hooks"]]
    if coverage in _ORDER and _ORDER.index(coverage) > _ORDER.index(e["status"]):
        e["status"] = coverage
    return new
```

- [ ] **Step 4: 통과 + 회귀** — Run: `python -m pytest api/tests -q` → 31 passed (기존 27 + 신규 4)

- [ ] **Step 5: Commit**

```bash
git add api/interview/state.py api/interview/ledger.py api/tests/test_interview_ledger.py
git commit -m "feat(graph): State 확장 — messages·원장·probe_streak (TICKET-2)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: 그래프 전용 프롬프트(ListenOut) + 노드 개편

**Files:**
- Create: `api/interview/prompts.py`
- Modify: `api/interview/nodes/listen.py` (store 제거, messages·원장), `nodes/generate.py` (오프닝을 새 프롬프트로), `nodes/strategize.py` (정직한 종료), `nodes/speak.py` (AIMessage·probe_streak·touched 마킹)
- Test: `api/tests/test_interview_graph.py` (FakeLLM 출력 교체 + 신규 3개)

**Interfaces:**
- Consumes: Task 1의 `update_ledger`·`init_ledger`·State 필드
- Produces:
  - `ListenOut(BaseModel)`: `message: str` · `done: bool=False` · `question_id: str=""` · `is_probe: bool=False` · `coverage: Literal["touched","satisfied","saturated"]="touched"`(직전 문항 취재 상태) · `facts: list[str]=[]` · `hooks: list[str]=[]`
  - `listen_user(guide: dict, messages: list, utterance: str, asked: int, probe_streak: int, ledger: dict, lang: str="ko") -> str`
  - 노드 계약: listen이 `messages=[HumanMessage]`·`ledger` 갱신 반환, speak이 `messages=[AIMessage]`·`probe_streak`·`ledger`(touched 마킹) 반환

- [ ] **Step 1: 기존 테스트를 새 계약으로 갱신 + 신규 테스트 추가** — `test_interview_graph.py`:

import 변경: `from api.services.moderator import _ModeratorOut` → `from api.interview.prompts import ListenOut`. 파일 내 `_ModeratorOut(` 전부 `ListenOut(` 으로. `_start`의 초기 상태에 `"messages": [], "ledger": init_ledger(GUIDE.model_dump()), "probe_streak": 0` 추가 (`from api.interview.state import init_ledger`). fakes 픽스처의 listen store 패치는 유지(제거 후엔 no-op이어도 무해)하되 speak 패치는 유지.

파일 끝에 신규 테스트:
```python
# --- T2: 상태 소유 + 원장 ------------------------------------------------------

def test_messages_accumulate_in_state(fakes):
    fs, set_llm = fakes
    set_llm([
        ListenOut(message="오프닝?", question_id="q1"),
        ListenOut(message="꼬리?", question_id="q1", is_probe=True),
    ])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    g.invoke(Command(resume="배민 써요"), config)
    msgs = g.get_state(config).values["messages"]
    # AI(오프닝) → Human(답변) → AI(꼬리질문)
    assert [m.type for m in msgs] == ["ai", "human", "ai"]
    assert msgs[1].content == "배민 써요"


def test_listen_updates_ledger_and_probe_streak(fakes):
    fs, set_llm = fakes
    set_llm([
        ListenOut(message="오프닝?", question_id="q1"),
        ListenOut(message="꼬리?", question_id="q1", is_probe=True,
                  coverage="touched", facts=["배민 사용"], hooks=["배민클럽"]),
    ])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    g.invoke(Command(resume="배민 써요, 배민클럽 때문에"), config)
    v = g.get_state(config).values
    assert v["ledger"]["q1"]["facts"] == ["배민 사용"]
    assert v["ledger"]["q1"]["hooks"] == ["배민클럽"]
    assert v["ledger"]["q1"]["status"] == "touched"
    assert v["probe_streak"] == 1                     # 꼬리질문 1연속


def test_honest_close_when_all_satisfied(fakes):
    fs, set_llm = fakes
    # 원장을 전부 satisfied 로 채운 채 시작 — LLM 이 계속하자고 해도 결정론 close
    led = init_ledger(GUIDE.model_dump())
    for q in led:
        led[q]["status"] = "satisfied"
    set_llm([
        ListenOut(message="오프닝?", question_id="q1"),
        ListenOut(message="계속 묻고 싶은데요?", question_id="q2", coverage="satisfied"),
    ])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s2"}}
    g.invoke({"project_id": "p1", "session_id": "s2", "lang": "ko",
              "guide": GUIDE.model_dump(), "covered": [], "asked": 0,
              "messages": [], "ledger": led, "probe_streak": 0}, config)
    r = g.invoke(Command(resume="네 뭐든요"), config)
    assert r["done"] is True                           # 정직한 종료가 이겼다
    assert r["end_reason"] == "honest_close"           # 종료 근거가 기록된다
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest api/tests/test_interview_graph.py -q` → FAIL (ImportError: ListenOut)

- [ ] **Step 3: 구현.**

`api/interview/prompts.py`:
```python
"""그래프 전용 프롬프트·스키마 — T2 부터 그래프는 구엔진 프롬프트와 독립 진화한다.

시스템 프롬프트는 기존 것을 재사용(Qwen3 톤 튜닝 보존), 원장 컨텍스트와
facts/hooks/coverage 보고 지시는 user 프롬프트에 싣는다(구엔진과 같은 패턴).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..prompts.interview_moderator import interview_moderator_system  # 재수출 — 노드가 여기서만 가져가게

__all__ = ["ListenOut", "listen_user", "interview_moderator_system"]


class ListenOut(BaseModel):
    message: str
    done: bool = False
    question_id: str = ""
    is_probe: bool = False
    # 직전 문항의 취재 상태 판정: touched(더 나올 수 있음) / satisfied(goal 충족) / saturated(더 캐도 안 나옴)
    coverage: Literal["touched", "satisfied", "saturated"] = "touched"
    facts: list[str] = Field(default_factory=list)   # 직전 답변에서 알아낸 사실 (짧게)
    hooks: list[str] = Field(default_factory=list)   # 파고들 만한데 아직 안 판 떡밥


def _convo(messages: list, utterance: str) -> str:
    lines = [
        f"{'진행자' if m.type == 'ai' else '응답자'}: {m.content}" for m in messages
    ]
    if utterance:
        lines.append(f"응답자: {utterance}")
    return "\n".join(lines)


def listen_user(
    guide: dict, messages: list, utterance: str, asked: int, probe_streak: int,
    ledger: dict, lang: str = "ko",
) -> str:
    goal = guide.get("goal", "")
    questions = {q["id"]: q for q in guide.get("questions", []) if q.get("id")}
    pending = [q for qid, q in questions.items() if ledger.get(qid, {}).get("status") == "pending"]
    thin = [q for qid, q in questions.items() if ledger.get(qid, {}).get("status") == "touched"]

    pending_block = "\n".join(f"- {q['id']}: {q['text']} (알아낼 것: {q.get('goal', '')})" for q in pending)
    thin_block = "\n".join(
        f"- {q['id']}: {q['text']} (지금까지 알아낸 것 {len(ledger[q['id']]['facts'])}건"
        + (f", 안 판 떡밥: {' / '.join(ledger[q['id']]['hooks'][:2])}" if ledger[q["id"]]["hooks"] else "")
        + ")"
        for q in thin
    )

    if not messages and not utterance:
        return (
            f"[조사 목표]\n{goal or '(목표 미기재)'}\n\n"
            f"[첫 문항]\n{pending_block}\n\n"
            "인터뷰의 첫 턴입니다. 따뜻하게 인사하고 위 첫 문항으로 가볍게 시작하세요. "
            "question_id 에 그 문항 id 를, is_probe=false, done=false 로 하세요. "
            "facts/hooks 는 빈 배열로 두세요."
        )

    return (
        f"[조사 목표]\n{goal or '(목표 미기재)'}\n\n"
        f"[지금까지 대화] (진행자 질문 {asked}회)\n{_convo(messages, utterance)}\n\n"
        f"[응답자의 직전 답변]\n{utterance or '(없음)'}\n\n"
        "먼저 직전 답변을 취재 수첩에 정리하세요:\n"
        "- facts: 직전 답변에서 실제로 알아낸 사실을 짧은 문장으로 (없으면 빈 배열)\n"
        "- hooks: 걸려 있는데 아직 안 판 떡밥 (없으면 빈 배열)\n"
        "- coverage: 지금 문항의 상태 — 아직 더 나올 수 있으면 touched, "
        "'알아낼 것'을 충분히 채웠으면 satisfied, 더 캐도 안 나올 것 같으면 saturated\n\n"
        "그 다음 행동하세요.\n"
        "직전 답변에 구체적 사례·감정·이유가 걸려 있는데 아직 캐묻지 않았다면 "
        "**꼬리질문이 기본값입니다**(is_probe=true, question_id 는 지금 문항 유지). "
        f"(지금 이 문항에서 연속 {probe_streak}회 파고들었습니다. 2회를 넘겼거나 "
        "답이 짧고 더 나올 게 없으면 다음 문항으로 — is_probe=false.)\n\n"
        f"[아직 다루지 않은 문항]\n{pending_block or '(전부 다룸)'}\n"
        f"[답이 얕은 문항 — 나중에 되짚을 후보]\n{thin_block or '(없음)'}\n\n"
        "남은 문항이 없고 충분히 들었으면 done=true, message 는 감사 인사 한 마디."
    )
```

`api/interview/nodes/listen.py` 전체 교체:
```python
"""listen — 발화 대기(interrupt) + 만능 1콜 + 원장 갱신 (T2).

T2: store 를 더 이상 읽지 않는다 — 대화·커버리지·페이스 전부 State 소유(필수③).
원장 갱신은 v1 규칙대로 노드 내에서(슬로우패스 이사는 T4).
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from ...services.llm_client import get_llm
from ..ledger import update_ledger
from ..prompts import ListenOut, interview_moderator_system, listen_user
from ..state import InterviewState


def listen(state: InterviewState) -> dict:
    utterance = interrupt({"waiting": "respondent"})  # 여기서 잠든다 — 재개값 = 마스킹된 발화
    utterance = (utterance or "").strip()

    prev_qid = state.get("question_id", "")           # 응답자가 방금 답한 문항
    out, _ = get_llm().structured(
        interview_moderator_system(state.get("lang", "ko")),
        listen_user(
            state["guide"], state.get("messages", []), utterance,
            state.get("asked", 0), state.get("probe_streak", 0),
            state.get("ledger", {}), state.get("lang", "ko"),
        ),
        ListenOut,
        max_tokens=700,
    )
    return {
        "messages": [HumanMessage(content=utterance)],
        "utterance": utterance,
        "ledger": update_ledger(state.get("ledger", {}), prev_qid, out.coverage, out.facts, out.hooks),
        "draft": (out.message or "").strip(),
        "action": "close" if out.done else ("probe" if out.is_probe else "advance"),
        "question_id": out.question_id or prev_qid,
        "is_probe": bool(out.is_probe),
        **({"end_reason": "model_done"} if out.done else {}),
    }
```

`api/interview/nodes/strategize.py` 전체 교체:
```python
"""strategize — 결정론 정책: 12턴 하드 가드 + 정직한 종료 (T2). 행동 7종은 T3."""
from __future__ import annotations

from ..state import InterviewState

MAX_ASKED = 12  # moderator._MAX_ASKED 와 동일 값 — 구엔진 제거 시 여기가 단일 출처


def strategize(state: InterviewState) -> dict:
    # 결정론 하드 가드 — LLM 이 close 를 안 내도 12번째 질문에서 끝낸다
    if state.get("asked", 0) + 1 >= MAX_ASKED:
        return {"action": "close", "end_reason": "max_turns"}
    # 정직한 종료 — "문항을 다 입에 올림"이 아니라 원장이 전부 satisfied/saturated 일 때
    ledger = state.get("ledger", {})
    if ledger and all(e["status"] in ("satisfied", "saturated") for e in ledger.values()):
        return {"action": "close", "end_reason": "honest_close"}
    return {}
```

`api/interview/nodes/generate.py` — moderator 사설 import 제거, 오프닝을 새 프롬프트로:
```python
"""generate — T2: 오프닝 생성 + close 시 마무리 확정.

일반 턴의 생성 콜은 여전히 listen 의 만능 콜에 있다(콜 수 불변).
T3~T5 에서 행동별 생성·도구 호출이 이 노드로 들어온다.
"""
from __future__ import annotations

from ...services.llm_client import get_llm
from ..prompts import ListenOut, interview_moderator_system, listen_user
from ..state import InterviewState

_FAREWELL_FALLBACK = "오늘 말씀 정말 감사합니다. 여기서 인터뷰를 마치겠습니다."


def generate(state: InterviewState) -> dict:
    if state.get("action") == "close":
        # 구엔진 파리티: 모델이 준 문장이 있으면 그대로, 없으면 기본 인사.
        return {"draft": state.get("draft") or _FAREWELL_FALLBACK, "done": True}

    if not state.get("draft"):
        # 오프닝 턴 — 그래프 진입 직후 (대화 없음)
        out, _ = get_llm().structured(
            interview_moderator_system(state.get("lang", "ko")),
            listen_user(state["guide"], [], "", 0, 0, state.get("ledger", {}), state.get("lang", "ko")),
            ListenOut,
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

`api/interview/nodes/speak.py` 전체 교체 (AIMessage·probe_streak·touched 마킹 추가):
```python
"""speak — 진행자 턴 저장 + 세션 갱신 + 상태 마감. '저장 완료 후 잠듦'(전역 불변식).

T2: AIMessage 를 messages 에 쌓고, probe_streak 를 갱신하고, 이번에 입에 올린
문항을 원장에서 touched 로 마킹한다(pending 이었다면).
SSE 스트리밍 연결은 T4.
"""
from __future__ import annotations

from datetime import datetime, timezone

from langchain_core.messages import AIMessage

from ...schemas.models import Turn
from ...services import store
from ..ledger import update_ledger
from ..state import InterviewState


def speak(state: InterviewState) -> dict:
    pid, sid = state["project_id"], state["session_id"]
    message = state.get("message", "")
    store.add_turn(pid, sid, Turn(
        role="moderator",
        text=message,
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
    return {
        "messages": [AIMessage(content=message)],
        "ledger": update_ledger(state.get("ledger", {}), qid, "touched", [], []),
        "covered": covered,
        "asked": asked,
        "probe_streak": (state.get("probe_streak", 0) + 1) if state.get("is_probe") else 0,
        "draft": "",
        "utterance": "",
    }
```

- [ ] **Step 4: 통과 + 회귀** — Run: `python -m pytest api/tests -q` → 34 passed (31 + 신규 3)

- [ ] **Step 5: Commit**

```bash
git add api/interview/prompts.py api/interview/nodes/ api/tests/test_interview_graph.py
git commit -m "feat(graph): 그래프 전용 프롬프트 + 원장 갱신·정직한 종료 — store 재조립 제거 (TICKET-2)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: engine 초기 상태 + probe율·원장 실측

**Files:**
- Modify: `api/interview/engine.py` (`initial_state` 추출 + messages/ledger/probe_streak 주입)
- Create: `scripts/exp_probe_rate.py`
- Test: 기존 스위트 회귀 (engine 로직은 라우팅 테스트가 커버)

**Interfaces:**
- Produces: `initial_state(project_id, sid, lang, guide, session) -> dict` — 테스트·엔진 공용 초기 상태 빌더

- [ ] **Step 1: engine.py 수정** — `next_turn`의 초기 invoke 딕셔너리를 함수로 추출:

```python
def initial_state(project_id: str, sid: str, lang: str, guide: InterviewGuide, session: Session) -> dict:
    """그래프 시작 상태 — 테스트와 엔진이 같은 빌더를 쓴다."""
    gd = guide.model_dump()
    return {
        "project_id": project_id, "session_id": sid, "lang": lang, "guide": gd,
        "messages": [], "ledger": init_ledger(gd),
        "covered": list(session.covered), "asked": session.asked, "probe_streak": 0,
    }
```
(import 추가: `from .state import init_ledger`) — `next_turn`의 else 분기는 `result = g.invoke(initial_state(project_id, sid, lang, guide, session), config)` 로 교체.

- [ ] **Step 2: 실측 스크립트** — `scripts/exp_probe_rate.py`:

```python
"""TICKET-2 검증 — 구엔진 vs 그래프 probe율 비교 + 원장 스냅숏 (LLM 실물).

같은 대본을 두 엔진에 태워 진행자 질문 중 꼬리질문(is_probe) 비율을 비교하고,
그래프 쪽은 최종 원장을 덤프해 '취재 수첩'이 실제로 쌓이는지 눈으로 확인한다.

사용:  python scripts/exp_probe_rate.py
전제:  LLM_API_KEY
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ANSWERS = [
    "주로 배민 쓰다가 요즘 쿠팡이츠로 갈아탔어요",
    "배달비가 부담돼서요. 만원 넘으면 좀 아깝더라고요",
    "무료배달 쿠폰이 결정적이었어요. 배민클럽은 안 써봤고요",
    "만족해요. 근데 가게 수는 배민이 더 많은 것 같아요",
    "친구들도 다 옮기는 분위기예요",
]


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


def probe_rate(turns) -> tuple[int, int]:
    mod = [t for t in turns if t.role == "moderator"]
    return sum(1 for t in mod if t.is_probe), len(mod)


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
    from api.schemas.models import GuideQuestion, InterviewGuide, Session, Turn

    legacy.tag_emotion = lambda t: ("중립", 0.0)

    guide = InterviewGuide(project_id="p", goal="배달앱 전환 요인과 재전환 의향", questions=[
        GuideQuestion(id="q1", text="어떤 배달앱을 쓰세요?", goal="현재 앱과 사용 빈도"),
        GuideQuestion(id="q2", text="갈아탄 계기는?", goal="전환의 구체적 트리거"),
        GuideQuestion(id="q3", text="지금 만족도는?", goal="만족 요인과 아쉬운 점"),
    ])

    # --- 구엔진 ---
    turns_l = fake_stores([legacy])
    s = Session(id="L", project_id="p")
    for text in ["", *ANSWERS]:
        msg, done, _, _ = legacy.next_turn("p", s, guide, text)
        if done:
            break
    p, n = probe_rate(turns_l)
    print(f"legacy: probe {p}/{n} = {p / n:.0%}")

    # --- 그래프 ---
    turns_g = fake_stores([listen_mod, speak_mod])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "G"}}
    from api.interview.state import init_ledger

    r = g.invoke({"project_id": "p", "session_id": "G", "lang": "ko",
                  "guide": guide.model_dump(), "covered": [], "asked": 0,
                  "messages": [], "ledger": init_ledger(guide.model_dump()),
                  "probe_streak": 0}, config)
    for text in ANSWERS:
        if r.get("done"):
            break
        turns_g.append(Turn(role="respondent", text=text))
        r = g.invoke(Command(resume=text), config)
    p, n = probe_rate(turns_g)
    print(f"graph:  probe {p}/{n} = {p / n:.0%}")

    led = g.get_state(config).values.get("ledger", {})
    print("\n[최종 원장]")
    print(json.dumps(led, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 회귀 + 실측**

Run: `python -m pytest api/tests -q` → 34 passed
Run: `LLM_API_KEY=<키> python scripts/exp_probe_rate.py`
Expected: 두 엔진 완주, probe율 출력(그래프 ≥ 구엔진 기대 — 원장 컨텍스트가 파고들 근거를 제공), 원장에 facts/hooks 축적 확인. 수치는 TICKETS.md 검증란에 기록(커밋 안 함).

- [ ] **Step 4: Commit**

```bash
git add api/interview/engine.py scripts/exp_probe_rate.py
git commit -m "feat(graph): 엔진 초기 상태에 원장 주입 + probe율 실측 스크립트 (TICKET-2)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## 검증 (전체)

1. **단위**: 34 passed — 원장 순수 함수 4 + 그래프 신규 3 + 기존 27(계약 갱신).
2. **상태 소유**: listen 에서 `store` import 소멸 (`grep -n "store" api/interview/nodes/listen.py` → 0건) — "매 턴 기억 재조립" 해소의 증거.
3. **정직한 종료**: test_honest_close_when_all_satisfied.
4. **probe율 실측**: exp_probe_rate.py — 구엔진 대비 비교 수치 + 원장 스냅숏.
5. **TICKETS.md** T2 체크박스 갱신 (커밋 안 함).

## 범위 밖

- 원장 갱신의 슬로우패스 이사·감정 태깅 이사 (T4) · revisit **행동** (T3 — T2는 근거 데이터만) · 대시보드에 원장 노출 (범위 밖) · 구엔진 수정 (불변)
