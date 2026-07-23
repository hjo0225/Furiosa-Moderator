"""인터뷰 그래프 (T3) — interrupt 루프 + 노드 6개 + 행동 조건 엣지.

START → generate(오프닝) → guard → speak ─문답 있음→ reflect(Send 병렬) ─done→ END
                                       │                          └계속→ listen【interrupt】
                                       └오프닝→ listen【interrupt】→ strategize ─close→ farewell → speak
                                                                         └6종→ generate → guard → speak

END 판단은 reflect 뒤 — 종료 턴에도 마지막 문답의 원장·감정 정리는 하고 끝낸다(BUG-1).
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .nodes.farewell import farewell
from .nodes.generate import generate
from .nodes.guard import guard
from .nodes.listen import listen
from .nodes.reflect import reflect_emotion, reflect_ledger
from .nodes.speak import speak
from .nodes.strategize import strategize
from .state import InterviewState

# 인터뷰 중 실시간 버킷 분류(reflect_bucket)는 뺐다(스펙 C). 코드북은 측정 전에 없고,
# 분류는 인사이트 생성 시 전사 전체를 놓고 일괄로 한다 — 인터뷰는 이야기만 좇는다.


def _after_speak(state: InterviewState):
    if state.get("utterance") and state.get("answered_qid"):
        sends = [Send("reflect_ledger", state)]      # 슬로우패스 — 사람의 시간에 숨는다
        if state.get("resp_turn_id"):
            sends.append(Send("reflect_emotion", state))
        return sends                                  # done 이어도 정리는 하고 끝낸다
    return END if state.get("done") else "listen"     # 오프닝 턴 — 정리할 문답이 없다


def _after_reflect(state: InterviewState):
    return END if state.get("done") else "listen"


def _route_action(state: InterviewState) -> str:
    return "farewell" if state.get("action") == "close" else "generate"


def build_graph(checkpointer):
    g = StateGraph(InterviewState)
    g.add_node("listen", listen)
    g.add_node("strategize", strategize)
    g.add_node("generate", generate)
    g.add_node("guard", guard)
    g.add_node("speak", speak)
    g.add_node("farewell", farewell)
    g.add_node("reflect_ledger", reflect_ledger)
    g.add_node("reflect_emotion", reflect_emotion)
    g.add_edge(START, "generate")
    g.add_edge("listen", "strategize")
    g.add_conditional_edges("strategize", _route_action, {"farewell": "farewell", "generate": "generate"})
    g.add_edge("generate", "guard")
    g.add_edge("guard", "speak")
    g.add_edge("farewell", "speak")
    g.add_conditional_edges("speak", _after_speak)
    g.add_conditional_edges("reflect_ledger", _after_reflect)
    g.add_conditional_edges("reflect_emotion", _after_reflect)
    return g.compile(checkpointer=checkpointer)
