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

    import api.interview.nodes.speak as speak_mod
    import api.services.moderator as legacy
    from api.interview.graph import build_graph
    from api.interview.state import init_ledger
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
        print(f"  legacy  {'[probe]' if turns_l[-1].is_probe else '       '} {msg[:40]}")
        if done:
            break
    p, n = probe_rate(turns_l)
    print(f"legacy: probe {p}/{n} = {p / n:.0%}\n")

    # --- 그래프 ---
    turns_g = fake_stores([speak_mod])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "G"}}
    r = g.invoke({"project_id": "p", "session_id": "G", "lang": "ko",
                  "guide": guide.model_dump(), "covered": [], "asked": 0,
                  "messages": [], "ledger": init_ledger(guide.model_dump()),
                  "probe_streak": 0}, config)
    print(f"  graph   {'[probe]' if turns_g[-1].is_probe else '       '} {r.get('message', '')[:40]}")
    for text in ANSWERS:
        if r.get("done"):
            break
        turns_g.append(Turn(role="respondent", text=text))
        r = g.invoke(Command(resume=text), config)
        print(f"  graph   {'[probe]' if turns_g[-1].is_probe else '       '} {r.get('message', '')[:40]}")
    p, n = probe_rate(turns_g)
    print(f"graph:  probe {p}/{n} = {p / n:.0%}")
    if r.get("done"):
        print(f"종료 근거: {r.get('end_reason', '(없음)')}")

    led = g.get_state(config).values.get("ledger", {})
    print("\n[최종 원장]")
    print(json.dumps(led, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
