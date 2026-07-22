"""문항 고착 방지 — q_streak 상한 초과 시 다음 pending 으로 강제 advance (probe_streak 리셋 구멍 보완)."""
from __future__ import annotations

from api.interview.nodes import speak as speak_mod
from api.interview.nodes.strategize import Q_STREAK_CAP, strategize


def _ledger(**status):
    return {qid: {"status": s, "facts": [], "hooks": []} for qid, s in status.items()}


def test_qstreak_cap_forces_advance_to_pending():
    st = {"action": "probe", "q_streak": Q_STREAK_CAP, "probe_streak": 0,
          "question_id": "q1", "asked": 3,
          "ledger": _ledger(q1="touched", q2="pending", q3="pending")}
    out = strategize(st)
    assert out.get("action") == "advance"
    assert out.get("question_id") == "q2"      # 첫 pending 으로
    assert out.get("is_probe") is False


def test_qstreak_below_cap_no_override():
    st = {"action": "probe", "q_streak": Q_STREAK_CAP - 1, "probe_streak": 0,
          "question_id": "q1", "asked": 3, "ledger": _ledger(q1="touched", q2="pending")}
    assert strategize(st) == {}                 # 상한 미만 → 애널리스트 판단 유지


def test_qstreak_cap_no_pending_no_override():
    st = {"action": "probe", "q_streak": Q_STREAK_CAP, "probe_streak": 0,
          "question_id": "q1", "asked": 3, "ledger": _ledger(q1="touched", q2="touched")}
    assert strategize(st) == {}                 # 넘길 pending 이 없으면 그대로 둔다


def test_qstreak_cap_ignored_when_advancing():
    st = {"action": "advance", "q_streak": Q_STREAK_CAP, "probe_streak": 0,
          "question_id": "q2", "asked": 3,
          "ledger": _ledger(q1="satisfied", q2="pending")}
    assert strategize(st) == {}                 # 이미 advance 중이면 개입 안 함


class _StubStore:
    def add_turn(self, *a, **k):
        pass

    def update_session(self, *a, **k):
        pass


def test_speak_qstreak_increments_then_resets(monkeypatch):
    monkeypatch.setattr(speak_mod, "store", _StubStore())
    same = speak_mod.speak({"project_id": "p", "session_id": "s", "message": "질문?",
                            "question_id": "q1", "q_streak": 2, "q_streak_qid": "q1"})
    assert same["q_streak"] == 3 and same["q_streak_qid"] == "q1"     # 같은 문항 → 누적
    changed = speak_mod.speak({"project_id": "p", "session_id": "s", "message": "질문?",
                               "question_id": "q2", "q_streak": 3, "q_streak_qid": "q1"})
    assert changed["q_streak"] == 1 and changed["q_streak_qid"] == "q2"  # 문항 바뀜 → 1 리셋
