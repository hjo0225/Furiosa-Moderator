"""인터뷰 그래프 골격 (T1) — interrupt 루프 + 노드 5개.

START → generate(오프닝) → guard → speak ─done→ END
                                      └계속→ listen【interrupt】→ strategize → generate → …
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes.generate import generate
from .nodes.guard import guard
from .nodes.listen import listen
from .nodes.speak import speak
from .nodes.strategize import strategize
from .state import InterviewState


def _after_speak(state: InterviewState) -> str:
    return END if state.get("done") else "listen"


def build_graph(checkpointer):
    g = StateGraph(InterviewState)
    g.add_node("listen", listen)
    g.add_node("strategize", strategize)
    g.add_node("generate", generate)
    g.add_node("guard", guard)
    g.add_node("speak", speak)
    g.add_edge(START, "generate")
    g.add_edge("listen", "strategize")
    g.add_edge("strategize", "generate")
    g.add_edge("generate", "guard")
    g.add_edge("guard", "speak")
    g.add_conditional_edges("speak", _after_speak, {END: END, "listen": "listen"})
    return g.compile(checkpointer=checkpointer)
