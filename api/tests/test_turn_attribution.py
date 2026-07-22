"""응답자 턴 문항 귀속 — reflect_emotion 이 answered_qid 를 턴에 붙인다 (버킷 분포·문항별 요약 전제)."""
from __future__ import annotations

from api.interview.nodes import reflect as reflect_mod


class _CapStore:
    def __init__(self):
        self.patches = []

    def update_turn(self, pid, sid, tid, patch):
        self.patches.append((tid, patch))


def test_reflect_emotion_attributes_question_id(monkeypatch):
    cap = _CapStore()
    monkeypatch.setattr(reflect_mod, "store", cap)
    monkeypatch.setattr(reflect_mod, "tag_emotion", lambda u: ("중립", 0.0))
    state = {
        "project_id": "p1", "session_id": "s1", "resp_turn_id": "t1",
        "utterance": "야근이라 배달로 시켰어요", "answered_qid": "q1",
    }
    reflect_mod.reflect_emotion(state)
    assert cap.patches, "update_turn 이 호출돼야 한다"
    tid, patch = cap.patches[0]
    assert tid == "t1"
    assert patch["question_id"] == "q1"   # ← 응답자 턴이 방금 답한 문항으로 귀속됨
    assert "emotion" in patch


def test_reflect_emotion_noop_without_turn(monkeypatch):
    cap = _CapStore()
    monkeypatch.setattr(reflect_mod, "store", cap)
    monkeypatch.setattr(reflect_mod, "tag_emotion", lambda u: ("중립", 0.0))
    reflect_mod.reflect_emotion({"project_id": "p1", "session_id": "s1", "utterance": "x"})
    assert cap.patches == []   # resp_turn_id 없으면 아무것도 안 함
