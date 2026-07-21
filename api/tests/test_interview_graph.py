"""인터뷰 그래프 골격(T1) 단위테스트 — 네트워크·DB 없이 InMemorySaver 로.

검증 대상: interrupt 루프(잠들기→재개), 노드 5개 배선, 12턴 결정론 가드,
guard 적용 조건, speak 의 저장·세션 갱신. LLM 과 store 는 가짜로 대체한다.
"""
from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from api.interview.graph import build_graph
from api.schemas.models import GuideQuestion, InterviewGuide, Turn
from api.services.moderator import _ModeratorOut

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
    # guard 는 LLM 없이 동작하도록 고정 (재작성 경로는 가드레일 자체 테스트가 커버)
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
    assert r2["is_probe"] is True and not r2.get("done")  # done 계약: 키 없음 = False
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
