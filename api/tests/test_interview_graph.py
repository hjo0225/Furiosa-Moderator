"""인터뷰 그래프 단위테스트 — 네트워크·DB 없이 InMemorySaver 로.

검증 대상: interrupt 루프, 노드 배선(T3: 행동 조건 엣지 + farewell), 결정론
(12턴·정직종료·revisit 검증), guard 적용 조건, speak 의 저장·세션 갱신.
LLM(분석 structured / 생성 text)과 store 는 가짜로 대체한다.
"""
from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from api.interview.graph import build_graph
from api.interview.prompts import ListenOut
from api.interview.state import init_ledger
from api.schemas.models import GuideQuestion, InterviewGuide, Turn

GUIDE = InterviewGuide(
    project_id="p1", goal="배달앱 전환 요인",
    questions=[GuideQuestion(id="q1", text="어떤 앱을 쓰세요?", goal="현재 사용 앱"),
               GuideQuestion(id="q2", text="갈아탄 계기는?", goal="전환 트리거")],
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
    """structured()/text() 호출마다 각자 큐에서 하나씩 꺼내 준다. 프롬프트를 캡처한다."""
    def __init__(self, outs=(), texts=()):
        self.outs = list(outs)
        self.texts = list(texts)
        self.structured_prompts: list[str] = []
        self.text_prompts: list[str] = []

    def structured(self, system, user, schema, **kw):
        self.structured_prompts.append(user)
        return self.outs.pop(0), None

    def text(self, system, user, **kw):
        self.text_prompts.append(user)
        return self.texts.pop(0), None


@pytest.fixture
def fakes(monkeypatch):
    from api.interview.nodes import farewell as fw_mod
    from api.interview.nodes import generate as gen_mod
    from api.interview.nodes import guard as guard_mod
    from api.interview.nodes import listen as listen_mod
    from api.interview.nodes import speak as speak_mod

    fs = FakeStore()
    # T2 부터 listen 은 store 를 안 읽는다(상태 소유) — speak 만 기록용으로 쓴다
    monkeypatch.setattr(speak_mod, "store", fs)
    # guard 는 LLM 없이 동작하도록 고정 (재작성 경로는 가드레일 자체 테스트가 커버)
    monkeypatch.setattr(
        guard_mod.guardrail, "ensure_neutral",
        lambda q, **kw: (q, False, "") if "당연히" not in q else ("중립 질문으로 재작성", True, "당연시"),
    )

    def set_llm(outs=(), texts=()):
        llm = FakeLLM(outs, texts)
        for m in (listen_mod, gen_mod, fw_mod):
            monkeypatch.setattr(m, "get_llm", lambda llm=llm: llm)
        return llm

    return fs, set_llm


def _start(g, config):
    return g.invoke(
        {"project_id": "p1", "session_id": "s1", "lang": "ko",
         "guide": GUIDE.model_dump(), "covered": [], "asked": 0,
         "messages": [], "ledger": init_ledger(GUIDE.model_dump()), "probe_streak": 0},
        config,
    )


# --- 골격: interrupt 루프 -------------------------------------------------------

def test_opening_then_sleeps_at_interrupt(fakes):
    fs, set_llm = fakes
    set_llm(texts=["안녕하세요! 어떤 배달앱을 쓰세요?"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    result = _start(g, config)
    assert result["message"] == "안녕하세요! 어떤 배달앱을 쓰세요?"
    assert result["asked"] == 1 and result["covered"] == ["q1"]   # 오프닝 qid 는 코드가 확정
    assert fs.turns[-1].role == "moderator"
    assert "__interrupt__" in result
    assert g.get_state(config).next == ("listen",)


def test_resume_probe_then_close_ends(fakes):
    fs, set_llm = fakes
    set_llm(
        outs=[ListenOut(action="probe", question_id="q1", probe_type="심화"),
              ListenOut(action="close")],
        texts=["오프닝?", "어느 정도일 때 부담되세요?", "말씀 감사했습니다. 여기서 마칠게요."],
    )
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)

    r2 = g.invoke(Command(resume="배달비가 부담돼요"), config)
    assert r2["is_probe"] is True and not r2.get("done")
    assert r2["asked"] == 2 and "__interrupt__" in r2

    r3 = g.invoke(Command(resume="그 정도예요"), config)
    assert r3["done"] is True and r3["message"] == "말씀 감사했습니다. 여기서 마칠게요."
    assert r3["end_reason"] == "model_done"
    assert "__interrupt__" not in r3 and g.get_state(config).next == ()
    assert fs.session_patches[-1]["status"] == "pending"  # 제출(R-4) 전까지는 completed 아님


def test_12turn_hard_guard_forces_close(fakes):
    fs, set_llm = fakes
    set_llm(outs=[ListenOut(action="probe", question_id="q1")],
            texts=["오프닝?", "마무리 인사"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    # asked 는 State 소유 — 이미 11회 물은 세션으로 시작 (이어하기 시나리오)
    g.invoke({"project_id": "p1", "session_id": "s1", "lang": "ko",
              "guide": GUIDE.model_dump(), "covered": [], "asked": 11,
              "messages": [], "ledger": init_ledger(GUIDE.model_dump()), "probe_streak": 0},
             config)
    r = g.invoke(Command(resume="네"), config)
    assert r["done"] is True and r["end_reason"] == "max_turns"
    assert r["message"] == "마무리 인사"                      # quirk 해소: 질문이 아니라 인사


def test_guard_rewrites_leading_question(fakes):
    fs, set_llm = fakes
    set_llm(texts=["당연히 편하셨죠?"])
    g = build_graph(InMemorySaver())
    r = _start(g, {"configurable": {"thread_id": "s1"}})
    assert r["message"] == "중립 질문으로 재작성"
    assert r["rewritten"] is True and fs.turns[-1].guardrail_rewritten is True


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


# --- T2: 상태 소유 + 원장 ------------------------------------------------------

def test_messages_accumulate_in_state(fakes):
    fs, set_llm = fakes
    set_llm(outs=[ListenOut(action="probe", question_id="q1")],
            texts=["오프닝?", "꼬리?"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    g.invoke(Command(resume="배민 써요"), config)
    msgs = g.get_state(config).values["messages"]
    assert [m.type for m in msgs] == ["ai", "human", "ai"]
    assert msgs[1].content == "배민 써요"


def test_listen_updates_ledger_and_probe_streak(fakes):
    fs, set_llm = fakes
    set_llm(outs=[ListenOut(action="probe", question_id="q1",
                            coverage="touched", facts=["배민 사용"], hooks=["배민클럽"])],
            texts=["오프닝?", "꼬리?"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    g.invoke(Command(resume="배민 써요, 배민클럽 때문에"), config)
    v = g.get_state(config).values
    assert v["ledger"]["q1"]["facts"] == ["배민 사용"]
    assert v["ledger"]["q1"]["hooks"] == ["배민클럽"]
    assert v["probe_streak"] == 1
    assert v["analysis"]["reason"] == ""                     # 분석 스냅숏 저장 확인


def test_honest_close_when_all_satisfied(fakes):
    fs, set_llm = fakes
    led = init_ledger(GUIDE.model_dump())
    for q in led:
        led[q]["status"] = "satisfied"
    set_llm(outs=[ListenOut(action="probe", question_id="q2", coverage="satisfied")],
            texts=["오프닝?", "마무리 인사"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s2"}}
    g.invoke({"project_id": "p1", "session_id": "s2", "lang": "ko",
              "guide": GUIDE.model_dump(), "covered": [], "asked": 0,
              "messages": [], "ledger": led, "probe_streak": 0}, config)
    r = g.invoke(Command(resume="네 뭐든요"), config)
    assert r["done"] is True and r["end_reason"] == "honest_close"


# --- T3: 행동 7종 ---------------------------------------------------------------

def test_new_actions_reach_generate_with_directives(fakes):
    fs, set_llm = fakes
    llm = set_llm(
        outs=[ListenOut(action="challenge", contradiction="가격 안 본다더니 최저가만 찾음"),
              ListenOut(action="redirect")],
        texts=["오프닝?", "챌린지 질문?", "복귀 질문?"],
    )
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    r = g.invoke(Command(resume="무조건 최저가요"), config)
    assert r["message"] == "챌린지 질문?"
    assert "가격 안 본다더니" in llm.text_prompts[-1]        # 모순이 생성 프롬프트에 실림
    r = g.invoke(Command(resume="근데 어제 축구 봤는데요"), config)
    assert "부드럽게 원래 주제로" in llm.text_prompts[-1]     # redirect 지시


def test_revisit_demoted_without_thin_question(fakes):
    fs, set_llm = fakes
    # q1 은 이미 satisfied(후퇴 금지로 오프닝 touched 마킹에도 유지), q2 는 pending
    # → 원장에 touched(빈약) 문항이 하나도 없다 = revisit 근거 없음
    led = init_ledger(GUIDE.model_dump())
    led["q1"]["status"] = "satisfied"
    set_llm(outs=[ListenOut(action="revisit", question_id="q2")],
            texts=["오프닝?", "질문?"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    g.invoke({"project_id": "p1", "session_id": "s1", "lang": "ko",
              "guide": GUIDE.model_dump(), "covered": [], "asked": 0,
              "messages": [], "ledger": led, "probe_streak": 0}, config)
    g.invoke(Command(resume="네"), config)
    assert g.get_state(config).values["action"] == "advance"  # 근거 없음 → 강등


def test_revisit_target_corrected_to_thin(fakes):
    fs, set_llm = fakes
    led = init_ledger(GUIDE.model_dump())
    led["q1"]["status"] = "touched"                           # 빈약 문항은 q1 뿐
    set_llm(outs=[ListenOut(action="revisit", question_id="q2")],   # 잘못된 대상
            texts=["오프닝?", "재방문 질문?"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    g.invoke({"project_id": "p1", "session_id": "s1", "lang": "ko",
              "guide": GUIDE.model_dump(), "covered": [], "asked": 0,
              "messages": [], "ledger": led, "probe_streak": 0}, config)
    g.invoke(Command(resume="네"), config)
    v = g.get_state(config).values
    assert v["action"] == "revisit" and v["question_id"] == "q1"   # 대상 보정


def test_farewell_skips_guard(fakes, monkeypatch):
    from api.interview.nodes import guard as guard_mod
    calls = []
    monkeypatch.setattr(guard_mod.guardrail, "ensure_neutral",
                        lambda q, **kw: (calls.append(q) or (q, False, "")))
    fs, set_llm = fakes
    set_llm(outs=[ListenOut(action="close")], texts=["오프닝?", "마무리 인사"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    g.invoke(Command(resume="네"), config)
    assert calls == ["오프닝?"]                               # 오프닝만 검수, 인사는 미경유
