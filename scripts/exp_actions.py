"""TICKET-3 검증 — 행동 7종이 실전에서 발동하는지 관찰 (LLM 실물, 수동 평가 재료).

대본에 함정을 심는다: 모순 발언(challenge 유도), 주제 이탈(redirect 유도),
모호한 답(clarify 유도). 각 턴의 [행동/사유]와 최종 원장을 출력한다.

사용:  python scripts/exp_actions.py   ·  전제: LLM_API_KEY
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ANSWERS = [
    "가격은 잘 안 봐요. 그냥 편한 앱 쓰는 편이에요",
    "아 근데 어제 축구 보셨어요? 국대 경기 있었잖아요",
    "무조건 최저가만 골라서 시켜요. 십원 단위까지 비교해요",   # ← 1번 답변과 모순
    "그게... 뭐랄까 그런 느낌이죠",                            # ← 모호 (clarify 유도)
    "배달비 무료 쿠폰 주길래 갈아탔어요",
    "지금은 만족해요. 가게 수가 좀 아쉽긴 한데",
]


def main() -> int:
    if not os.environ.get("LLM_API_KEY"):
        print("LLM_API_KEY 필요")
        return 2
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command

    import api.interview.nodes.speak as speak_mod
    from api.interview.graph import build_graph
    from api.interview.state import init_ledger
    from api.schemas.models import GuideQuestion, InterviewGuide, Turn

    turns = []

    class FS:
        @staticmethod
        def add_turn(pid, sid, t):
            turns.append(t)
            return t

        @staticmethod
        def update_session(pid, sid, patch):
            pass

    speak_mod.store = FS

    guide = InterviewGuide(project_id="p", goal="배달앱 선택 기준과 전환 요인", questions=[
        GuideQuestion(id="q1", text="배달앱 고를 때 뭘 보세요?", goal="선택 기준"),
        GuideQuestion(id="q2", text="다른 앱으로 갈아탄 적 있나요?", goal="전환 경험"),
        GuideQuestion(id="q3", text="지금 앱 만족도는?", goal="만족/불만 요인"),
    ])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "A"}}
    r = g.invoke({"project_id": "p", "session_id": "A", "lang": "ko",
                  "guide": guide.model_dump(), "covered": [], "asked": 0,
                  "messages": [], "ledger": init_ledger(guide.model_dump()),
                  "probe_streak": 0}, config)
    print(f"[오프닝] {r.get('message', '')}")
    for text in ANSWERS:
        if r.get("done"):
            break
        turns.append(Turn(role="respondent", text=text))
        r = g.invoke(Command(resume=text), config)
        v = g.get_state(config).values
        a = v.get("analysis", {})
        print(f"\n응답자: {text}")
        print(f"[{v.get('action', '?'):9s}] {r.get('message', '')}")
        print(f"   사유: {a.get('reason', '')}"
              + (f" · 모순: {a.get('contradiction')}" if a.get("contradiction") else "")
              + (f" · 래더링: {v.get('probe_type')}" if v.get("probe_type") else ""))
    print(f"\n종료: done={r.get('done')} · end_reason={r.get('end_reason', '-')}")
    print("\n[최종 원장]")
    print(json.dumps(g.get_state(config).values.get("ledger", {}), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
