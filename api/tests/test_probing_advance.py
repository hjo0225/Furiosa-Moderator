"""주제 예산 기반 강제 advance — 남은 질문 수 >= 남은 턴 수면 파고들기를 막는다.

구 `Q_STREAK_CAP = 4`(문항당 고정 상한)를 대체한다. 고정 상한은 질문이 많은 주제에서
앞 질문이 예산을 다 먹어도 못 막았고, 그러면 **뒤 질문의 버킷이 영영 빈 채로 남았다.**
스펙: docs/specs/2026-07-24-guide-topics-turn-budget.md
"""
from __future__ import annotations

from api.interview.nodes import speak as speak_mod
from api.interview.nodes.strategize import max_turns, strategize, topic_budget


def _ledger(**status):
    return {qid: {"status": s, "facts": [], "hooks": []} for qid, s in status.items()}


def _guide(*topics):
    """_guide(("t1", ["q1","q2"]), ("t2", ["q3"])) → 그래프 상태에 실리는 guide dict."""
    return {"topics": [{"id": tid, "questions": [{"id": q} for q in qs]} for tid, qs in topics]}


def test_topic_budget_is_questions_plus_one():
    assert topic_budget({"questions": [{"id": "q1"}, {"id": "q2"}]}) == 3
    assert topic_budget({"questions": []}) == 1


def test_max_turns_is_sum_of_topic_budgets():
    # 주제 2개 × 질문 2개 → (2+1) + (2+1) = 6턴
    assert max_turns(_guide(("t1", ["q1", "q2"]), ("t2", ["q3", "q4"]))) == 6
    assert max_turns({}) == 0        # 주제 없음 = 예산 산출 불가


def test_forces_advance_when_questions_outnumber_remaining_turns():
    # 주제 예산 4(질문 3 + 1). 이미 2턴 썼으니 남은 턴 2, 아직 안 물은 질문 2개 → 파고들기 금지
    st = {"action": "probe", "question_id": "q1", "asked": 1, "t_streak": 2,
          "guide": _guide(("t1", ["q1", "q2", "q3"])),
          "ledger": _ledger(q1="touched", q2="pending", q3="pending")}
    out = strategize(st)
    assert out.get("action") == "advance"
    assert out.get("question_id") == "q2"
    assert out.get("is_probe") is False


def test_allows_probe_while_budget_has_slack():
    # 같은 주제, 1턴만 씀 → 남은 턴 3 > 남은 질문 2 → 애널리스트 판단(probe) 유지
    st = {"action": "probe", "question_id": "q1", "asked": 1, "t_streak": 1,
          "guide": _guide(("t1", ["q1", "q2", "q3"])),
          "ledger": _ledger(q1="touched", q2="pending", q3="pending")}
    assert strategize(st) == {}


def test_moves_to_next_topic_when_current_is_exhausted():
    # t1 은 다 물었고 예산도 소진 → 다음 주제의 pending 으로 넘어간다
    st = {"action": "probe", "question_id": "q1", "asked": 3, "t_streak": 4,
          "guide": _guide(("t1", ["q1", "q2", "q3"]), ("t2", ["q4"])),
          "ledger": _ledger(q1="touched", q2="touched", q3="touched", q4="pending")}
    out = strategize(st)
    assert out.get("action") == "advance"
    assert out.get("question_id") == "q4"


def test_not_applied_when_already_advancing():
    st = {"action": "advance", "question_id": "q2", "asked": 1, "t_streak": 3,
          "guide": _guide(("t1", ["q1", "q2"])),
          "ledger": _ledger(q1="satisfied", q2="pending")}
    assert strategize(st) == {}


def test_closes_when_guide_budget_is_spent():
    # 주제 1개 × 질문 2개 → 예산 3. 3번째 질문을 내려는 순간 종료한다.
    st = {"action": "probe", "question_id": "q1", "asked": 2, "t_streak": 2,
          "guide": _guide(("t1", ["q1", "q2"])),
          "ledger": _ledger(q1="touched", q2="pending")}
    out = strategize(st)
    assert out.get("action") == "close"
    assert out.get("end_reason") == "max_turns"


class _StubStore:
    def add_turn(self, *a, **k):
        pass

    def update_session(self, *a, **k):
        pass


def test_speak_tracks_topic_streak(monkeypatch):
    monkeypatch.setattr(speak_mod, "store", _StubStore())
    guide = _guide(("t1", ["q1", "q2"]), ("t2", ["q3"]))
    base = {"project_id": "p", "session_id": "s", "message": "질문?", "guide": guide}

    # 같은 주제 안에서 질문이 q1→q2 로 바뀌어도 주제 예산은 계속 깎인다
    same_topic = speak_mod.speak({**base, "question_id": "q2", "t_streak": 2, "t_streak_tid": "t1"})
    assert same_topic["t_streak"] == 3 and same_topic["t_streak_tid"] == "t1"
    # 주제가 바뀌면 1로 리셋
    new_topic = speak_mod.speak({**base, "question_id": "q3", "t_streak": 3, "t_streak_tid": "t1"})
    assert new_topic["t_streak"] == 1 and new_topic["t_streak_tid"] == "t2"


def test_speak_qstreak_increments_then_resets(monkeypatch):
    monkeypatch.setattr(speak_mod, "store", _StubStore())
    same = speak_mod.speak({"project_id": "p", "session_id": "s", "message": "질문?",
                            "question_id": "q1", "q_streak": 2, "q_streak_qid": "q1"})
    assert same["q_streak"] == 3 and same["q_streak_qid"] == "q1"     # 같은 문항 → 누적
    changed = speak_mod.speak({"project_id": "p", "session_id": "s", "message": "질문?",
                               "question_id": "q2", "q_streak": 3, "q_streak_qid": "q1"})
    assert changed["q_streak"] == 1 and changed["q_streak_qid"] == "q2"  # 문항 바뀜 → 1 리셋
