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
    from api.schemas.models import GuideQuestion, InterviewGuide, Session, Turn

    legacy.tag_emotion = lambda t: ("중립", 0.0)  # 동일 조건

    guide = InterviewGuide(project_id="p", goal="배달앱 전환 요인", questions=[
        GuideQuestion(id="q1", text="어떤 배달앱을 쓰세요?", goal="현재 앱"),
        GuideQuestion(id="q2", text="갈아탄 계기는?", goal="전환 트리거"),
        GuideQuestion(id="q3", text="지금 만족도는?", goal="만족도"),
    ])

    # --- 구엔진 ---
    fake_stores([legacy])
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
    turns_g = fake_stores([listen_mod, speak_mod])
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
        # 운영에선 engine.next_turn 이 하는 응답자 턴 저장 — 동일 조건을 위해 재현
        turns_g.append(Turn(role="respondent", text=text))
        t0 = time.perf_counter()
        r = g.invoke(Command(resume=text), config)
        t_graph.append(time.perf_counter() - t0)
        print(f"  graph  {t_graph[-1]:.2f}s  {r.get('message', '')[:36]}")

    print(f"\nlegacy mean {sum(t_legacy)/len(t_legacy):.2f}s | graph mean {sum(t_graph)/len(t_graph):.2f}s "
          f"| 오버헤드 {sum(t_graph)/len(t_graph) - sum(t_legacy)/len(t_legacy):+.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
