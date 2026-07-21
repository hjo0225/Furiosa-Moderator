"""TICKET-4 검증 — 체감 첫 토큰(TTFT) 실측. 목표 1.5~2.5s (T3 동기 4.36s 대비).

숨긴 슬로우패스 = 마지막 토큰 이후 스트림 종료까지 — reflect 가 토큰 뒤로 밀렸다는 증거.

사용:  python scripts/exp_stream_latency.py   ·  전제: LLM_API_KEY
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ANSWERS = ["주로 배민 쓰다가 쿠팡이츠로 갈아탔어요", "배달비가 부담돼서요", "무료배달 쿠폰이 결정적이었어요"]


def main() -> int:
    if not os.environ.get("LLM_API_KEY"):
        print("LLM_API_KEY 필요")
        return 2
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command

    import api.interview.nodes.reflect as ref_mod
    import api.interview.nodes.speak as speak_mod
    from api.interview.graph import build_graph
    from api.interview.state import init_ledger
    from api.schemas.models import GuideQuestion, InterviewGuide

    class FS:
        @staticmethod
        def add_turn(pid, sid, t):
            return t

        @staticmethod
        def update_session(pid, sid, patch):
            pass

        @staticmethod
        def update_turn(pid, sid, tid, patch):
            pass

    speak_mod.store = FS
    ref_mod.store = FS

    guide = InterviewGuide(project_id="p", goal="배달앱 전환 요인", questions=[
        GuideQuestion(id="q1", text="어떤 배달앱을 쓰세요?", goal="현재 앱"),
        GuideQuestion(id="q2", text="갈아탄 계기는?", goal="전환 트리거"),
        GuideQuestion(id="q3", text="지금 만족도는?", goal="만족도"),
    ])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "S"}}

    def run(payload, label):
        t0 = time.perf_counter()
        ttft = last_tok = None
        for chunk in g.stream(payload, config, stream_mode="custom"):
            now = time.perf_counter()
            if ttft is None:
                ttft = now - t0
            last_tok = now
        total = time.perf_counter() - t0
        hidden = total - (last_tok - t0) if last_tok else 0.0
        print(f"  {label:8s} TTFT {ttft:5.2f}s | 총 {total:5.2f}s | 숨긴 슬로우패스 {hidden:5.2f}s")
        return ttft

    ttfts = [run({"project_id": "p", "session_id": "S", "lang": "ko",
                  "guide": guide.model_dump(), "covered": [], "asked": 0,
                  "messages": [], "ledger": init_ledger(guide.model_dump()),
                  "probe_streak": 0}, "오프닝")]
    for i, text in enumerate(ANSWERS, 1):
        ttfts.append(run(Command(resume={"text": text, "turn_id": f"t{i}"}), f"턴{i}"))
    print(f"\n체감 첫 토큰 평균 {sum(ttfts) / len(ttfts):.2f}s (목표 1.5~2.5s · T3 동기 4.36s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
