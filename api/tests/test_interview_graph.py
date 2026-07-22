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
from api.interview.prompts import CoverageUpdate, ListenOut, ReflectOut
from api.interview.state import init_ledger
from api.schemas.models import GuideQuestion, InterviewGuide, Project, Turn

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
        self.blocklist: list[str] = []   # generate 노드가 읽는 지식팩 금칙어(F1.5)

    def list_turns(self, pid, sid):
        return list(self.turns)

    def add_turn(self, pid, sid, turn):
        self.turns.append(turn)
        return turn

    def update_session(self, pid, sid, patch):
        self.session_patches.append(patch)

    def get_project(self, pid):
        # generate 노드가 금칙어를 읽는다 — DB 없이 프로젝트 대역을 돌려준다
        return Project(id=pid, topic="t", blocklist=list(self.blocklist))


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
    # generate 는 지식팩 금칙어(F1.5)를 store.get_project 로 읽는다 — DB 없이 대역으로
    monkeypatch.setattr(gen_mod, "store", fs)
    # guard 는 LLM 없이 동작하도록 고정 (재작성 경로는 가드레일 자체 테스트가 커버)
    monkeypatch.setattr(
        guard_mod.guardrail, "ensure_neutral",
        lambda q, **kw: (q, False, "") if "당연히" not in q else ("중립 질문으로 재작성", True, "당연시"),
    )

    def set_llm(outs=(), texts=()):
        llm = FakeLLM(outs, texts)
        from api.interview.nodes import reflect as ref_mod
        for m in (listen_mod, gen_mod, fw_mod, ref_mod):
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
              ReflectOut(),                                   # 턴1 슬로우패스 원장 정리
              ListenOut(action="close"),
              ReflectOut()],                                  # 종료 턴에도 reflect 가 돈다 (BUG-1)
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
    set_llm(outs=[ListenOut(action="probe", question_id="q1"), ReflectOut()],
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
    monkeypatch.setenv("DATABASE_URL", "postgresql+pg8000://localhost:5432/mindlens")
    assert checkpoint.conn_string() == "postgresql://localhost:5432/mindlens"


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
    set_llm(outs=[ListenOut(action="probe", question_id="q1"), ReflectOut()],
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
    set_llm(outs=[ListenOut(action="probe", question_id="q1"),
                  ReflectOut(updates=[CoverageUpdate(
                      question_id="q1", coverage="touched", facts=["배민 사용"], hooks=["배민클럽"])])],
            texts=["오프닝?", "꼬리?"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    g.invoke(Command(resume="배민 써요, 배민클럽 때문에"), config)
    v = g.get_state(config).values
    assert v["ledger"]["q1"]["facts"] == ["배민 사용"]       # reflect 가 갱신했다
    assert v["ledger"]["q1"]["hooks"] == ["배민클럽"]
    assert v["probe_streak"] == 1
    assert v["analysis"]["reason"] == ""                     # 분석 스냅숏 저장 확인


def test_honest_close_when_all_satisfied(fakes):
    fs, set_llm = fakes
    led = init_ledger(GUIDE.model_dump())
    for q in led:
        led[q]["status"] = "satisfied"
    set_llm(outs=[ListenOut(action="probe", question_id="q2"), ReflectOut()],
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
              ReflectOut(),
              ListenOut(action="redirect"),
              ReflectOut()],
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
    set_llm(outs=[ListenOut(action="revisit", question_id="q2"), ReflectOut()],
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
    set_llm(outs=[ListenOut(action="revisit", question_id="q2"), ReflectOut()],   # 잘못된 대상
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
    set_llm(outs=[ListenOut(action="close"), ReflectOut()], texts=["오프닝?", "마무리 인사"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    g.invoke(Command(resume="네"), config)
    assert calls == ["오프닝?"]                               # 오프닝만 검수, 인사는 미경유


# --- T4: 슬로우패스 (reflect) ----------------------------------------------------

def test_reflect_runs_before_next_interrupt(fakes):
    fs, set_llm = fakes
    set_llm(outs=[ListenOut(action="probe", question_id="q1"),
                  ReflectOut(updates=[CoverageUpdate(question_id="q1", facts=["사실1"])])],
            texts=["오프닝?", "꼬리?"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    r = g.invoke(Command(resume="답변"), config)
    assert "__interrupt__" in r                              # 다음 interrupt 에서 잠들었고
    assert g.get_state(config).values["ledger"]["q1"]["facts"] == ["사실1"]  # 원장은 이미 갱신됨


def test_opening_turn_skips_reflect(fakes):
    fs, set_llm = fakes
    llm = set_llm(texts=["오프닝?"])                          # structured 큐가 비어 있다
    g = build_graph(InMemorySaver())
    _start(g, {"configurable": {"thread_id": "s1"}})
    assert llm.outs == [] and llm.structured_prompts == []    # 오프닝은 분석·reflect 콜 없음


def test_reflect_emotion_patches_turn(fakes, monkeypatch):
    from api.interview.nodes import reflect as ref_mod
    fs, set_llm = fakes
    patched = {}
    fs.update_turn = lambda pid, sid, tid, patch: patched.update({tid: patch})
    monkeypatch.setattr(ref_mod, "store", fs)
    monkeypatch.setattr(ref_mod, "tag_emotion", lambda t: ("불만", 0.7))
    set_llm(outs=[ListenOut(action="probe", question_id="q1"), ReflectOut()],
            texts=["오프닝?", "꼬리?"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    g.invoke(Command(resume={"text": "배달비 비싸요", "turn_id": "t_9"}), config)
    assert patched == {"t_9": {"emotion": "불만", "emotion_confidence": 0.7, "question_id": "q1"}}


def test_close_turn_still_reflects_last_answer(fakes, monkeypatch):
    # BUG-1 회귀: 종료 턴에도 슬로우패스가 돌아 마지막 문답이 원장·감정에 남아야 한다
    from api.interview.nodes import reflect as ref_mod
    fs, set_llm = fakes
    patched = {}
    fs.update_turn = lambda pid, sid, tid, patch: patched.update({tid: patch})
    monkeypatch.setattr(ref_mod, "store", fs)
    monkeypatch.setattr(ref_mod, "tag_emotion", lambda t: ("만족", 0.8))
    set_llm(outs=[ListenOut(action="close"),
                  ReflectOut(updates=[CoverageUpdate(
                      question_id="q1", coverage="satisfied", facts=["총정리 사실"])])],
            texts=["오프닝?", "마무리 인사"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    r = g.invoke(Command(resume={"text": "정리하면 배달비가 제일 컸어요", "turn_id": "t_last"}), config)
    assert r["done"] is True and "__interrupt__" not in r
    v = g.get_state(config).values
    assert v["ledger"]["q1"]["facts"] == ["총정리 사실"]           # 마지막 답변이 원장에 남았다
    assert patched == {"t_last": {"emotion": "만족", "emotion_confidence": 0.8, "question_id": "q1"}}
    assert g.get_state(config).next == ()                          # reflect 뒤 END — 재잠들지 않는다


def test_listen_accepts_plain_string_resume(fakes):
    # 구 체크포인트(문자열 resume) 재개 방어
    fs, set_llm = fakes
    set_llm(outs=[ListenOut(action="probe", question_id="q1"), ReflectOut()],
            texts=["오프닝?", "꼬리?"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    r = g.invoke(Command(resume="그냥 문자열"), config)
    assert "__interrupt__" in r                              # 정상 진행


# --- T4: SSE 스트리밍 ------------------------------------------------------------

def test_speak_emits_tokens_via_custom_stream(fakes):
    fs, set_llm = fakes
    set_llm(texts=["안녕하세요! 어떤 배달앱을 쓰세요?"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    chunks = []
    for mode, payload in g.stream(
        {"project_id": "p1", "session_id": "s1", "lang": "ko",
         "guide": GUIDE.model_dump(), "covered": [], "asked": 0,
         "messages": [], "ledger": init_ledger(GUIDE.model_dump()), "probe_streak": 0},
        config, stream_mode=["custom", "values"],
    ):
        if mode == "custom":
            chunks.append(payload["token"])
    assert "".join(chunks) == "안녕하세요! 어떤 배달앱을 쓰세요?"   # 토큰 합 = 최종 발화


def test_unknown_terms_trigger_brief_lookup(fakes, monkeypatch):
    from api.interview.nodes import generate as gen_mod
    looked = {}

    def fake_lookup(pid, terms, k=2):
        looked["terms"] = list(terms)
        return [{"text": "배민클럽=구독제", "source": "자료", "score": 0.9}]

    monkeypatch.setattr(gen_mod.brief, "lookup", fake_lookup)
    fs, set_llm = fakes
    llm = set_llm(outs=[ListenOut(action="probe", question_id="q1", unknown_terms=["배민클럽"]),
                        ReflectOut()],
                  texts=["오프닝?", "브리핑 반영 질문?"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    g.invoke(Command(resume="배민클럽 때문에 갈아탔어요"), config)
    assert looked["terms"] == ["배민클럽"]                   # 구조화 출력이 brief 를 지정했다
    assert "배민클럽=구독제" in llm.text_prompts[-1]         # 검색 결과가 생성 프롬프트에 주입


def test_no_unknown_terms_no_lookup(fakes, monkeypatch):
    from api.interview.nodes import generate as gen_mod
    called = []
    monkeypatch.setattr(gen_mod.brief, "lookup", lambda *a, **k: called.append(1) or [])
    fs, set_llm = fakes
    set_llm(outs=[ListenOut(action="probe", question_id="q1"), ReflectOut()],
            texts=["오프닝?", "질문?"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    g.invoke(Command(resume="그냥 편해서요"), config)
    assert called == []                                      # 지정 없으면 검색도 없다


def test_engine_stream_turn_yields_tokens_then_meta(fakes, monkeypatch):
    from api.interview import engine as eng
    fs, set_llm = fakes
    set_llm(texts=["오프닝 질문?"])
    g = build_graph(InMemorySaver())
    monkeypatch.setattr(eng, "get_graph", lambda: g)
    monkeypatch.setattr(eng, "store", fs)

    from api.schemas.models import Session
    events = list(eng.stream_turn("p1", Session(id="s1", project_id="p1"), GUIDE, ""))
    assert events and all("token" in e for e in events[:-1])  # 토큰 이벤트들이 먼저
    meta = events[-1]["meta"]
    assert meta["message"] == "오프닝 질문?" and meta["done"] is False and meta["asked"] == 1


# --- T3: 비답변 단락 (엔진) ------------------------------------------------------

def test_non_answer_short_circuits_without_waking_graph(monkeypatch):
    from api.interview import engine as eng
    fs = FakeStore()
    fs.turns = [Turn(role="moderator", text="안녕하세요! 어떤 앱을 쓰세요?", question_id="q1")]
    monkeypatch.setattr(eng, "store", fs)
    monkeypatch.setattr(eng, "get_graph", lambda: (_ for _ in ()).throw(AssertionError("그래프를 깨우면 안 된다")))

    from api.schemas.models import Session
    msg, done, resp, mod = eng.next_turn("p1", Session(id="s1", project_id="p1"), GUIDE, "음, 그래. 그래.")
    assert "다시 여쭤볼게요" in msg and "어떤 앱을 쓰세요?" in msg
    assert done is False and resp is None
    assert len(fs.turns) == 1                                 # 아무것도 저장 안 됨


def test_real_answer_does_not_short_circuit(monkeypatch):
    # '글쎄요'는 실제 답변(모르겠다는 의사) — 레거시 _FILLERS 설계 의도대로 단락되면 안 된다
    from api.interview import engine as eng
    fs = FakeStore()
    fs.turns = [Turn(role="moderator", text="질문?", question_id="q1")]
    monkeypatch.setattr(eng, "store", fs)
    assert eng._non_answer_reply("p1", "s1", "글쎄요, 잘 모르겠어요") is None


# --- 보강 A: probe/clarify 연속 상한 (꼬리질문 폭주 차단) ------------------------

def _thin_ledger():
    """q1 touched(빈약)·q2 pending — honest_close 미발동이면서 전환할 pending 이 있는 상태."""
    led = init_ledger(GUIDE.model_dump())
    led["q1"]["status"] = "touched"
    return led


def test_probe_streak_cap_forces_advance_to_pending():
    from api.interview.nodes.strategize import strategize
    patch = strategize({"asked": 4, "action": "probe", "question_id": "q1",
                        "probe_streak": 3, "ledger": _thin_ledger()})
    assert patch["action"] == "advance"          # 3연속 파고들었으면 결정론으로 전환
    assert patch["question_id"] == "q2"          # 다음 pending 문항으로
    assert patch["is_probe"] is False            # 전환이므로 probe 플래그 해제


def test_clarify_streak_also_capped():
    from api.interview.nodes.strategize import strategize
    patch = strategize({"asked": 4, "action": "clarify", "question_id": "q1",
                        "probe_streak": 3, "ledger": _thin_ledger()})
    assert patch["action"] == "advance" and patch["question_id"] == "q2"


def test_streak_under_cap_not_forced():
    from api.interview.nodes.strategize import strategize
    patch = strategize({"asked": 4, "action": "probe", "question_id": "q1",
                        "probe_streak": 2, "ledger": _thin_ledger()})
    assert "action" not in patch                 # 2연속까지는 그대로 둔다


def test_cap_without_pending_target_leaves_action():
    from api.interview.nodes.strategize import strategize
    led = init_ledger(GUIDE.model_dump())
    led["q1"]["status"] = "touched"
    led["q2"]["status"] = "touched"              # pending 없음(전부 satisfied 도 아님)
    patch = strategize({"asked": 4, "action": "probe", "question_id": "q1",
                        "probe_streak": 5, "ledger": led})
    assert "action" not in patch                 # 전환 대상이 없으면 강제하지 않는다


def test_clarify_counts_toward_probe_streak(fakes):
    fs, set_llm = fakes
    set_llm(outs=[ListenOut(action="clarify", question_id="q1"), ReflectOut()],
            texts=["오프닝?", "무슨 뜻인지 좀 더 말씀해 주실래요?"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    g.invoke(Command(resume="음 그냥 그래요"), config)
    assert g.get_state(config).values["probe_streak"] == 1   # clarify 도 꼬리질문 — 리셋 아님


# --- 보강 B: 한 답변이 건드린 여러 문항에 나눠 귀속 -----------------------------

def test_reflect_attributes_across_questions(fakes):
    fs, set_llm = fakes
    set_llm(
        outs=[ListenOut(action="probe", question_id="q1"),
              ReflectOut(updates=[
                  CoverageUpdate(question_id="q1", coverage="satisfied", facts=["시간이 없어서"]),
                  CoverageUpdate(question_id="q2", coverage="touched", facts=["대용식 사본 적 있음"])])],
        texts=["오프닝?", "꼬리?"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    g.invoke(Command(resume="시간이 없어서요. 예전에 대용식 사봤는데 비쌌어요"), config)
    led = g.get_state(config).values["ledger"]
    assert led["q1"]["facts"] == ["시간이 없어서"] and led["q1"]["status"] == "satisfied"
    assert led["q2"]["facts"] == ["대용식 사본 적 있음"]     # 안 물은 문항인데 곁다리 답이 귀속됨
    assert led["q2"]["status"] == "touched"                  # pending → touched


def test_reflect_ignores_unknown_question_id(fakes):
    fs, set_llm = fakes
    set_llm(
        outs=[ListenOut(action="probe", question_id="q1"),
              ReflectOut(updates=[
                  CoverageUpdate(question_id="q1", facts=["진짜 사실"]),
                  CoverageUpdate(question_id="q99", facts=["환각"])])],   # q99 는 가이드에 없음
        texts=["오프닝?", "꼬리?"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)
    g.invoke(Command(resume="답변"), config)
    led = g.get_state(config).values["ledger"]
    assert led["q1"]["facts"] == ["진짜 사실"]
    assert "q99" not in led                                  # 없는 문항은 조용히 무시
