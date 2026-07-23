"""strategize — 결정론 확정: 턴 예산 하드 가드 + 정직한 종료 + revisit 근거 검증 (T3).

LLM(분석 콜)의 행동 '제안'을 데이터가 검열한다 — 판단은 LLM, 집행은 결정론.

턴 예산은 가이드에서 나온다(스펙 `docs/specs/2026-07-24-guide-topics-turn-budget.md`):
**주제당 = 그 주제의 질문수 + 1**, 전체는 그 합. 고정 상수(구 `MAX_ASKED = 12`)는 없앴다 —
가이드가 크면 인터뷰가 길어지고, 그 사실을 의뢰자가 가이드 화면의 `최대 N턴` 으로 본다.
"""
from __future__ import annotations

from ..state import InterviewState

PROBE_STREAK_CAP = 3  # probe/clarify 연속 상한 — 넘으면 다음 pending 으로 결정론 전환 (보강 A)

_DIGGING = ("probe", "clarify", "challenge", "redirect")   # 앞으로 안 나가는 행동들


def topic_budget(topic: dict) -> int:
    """주제 하나가 쓸 수 있는 턴 = 질문수 + 1.

    `+1` 은 꼬리질문 몫이다. 질문마다 최소 1턴을 써야 그 질문의 버킷이 채워지므로
    질문 수만큼은 반드시 확보하고, 남는 1턴만 파고들기에 쓴다.
    """
    return len(topic.get("questions") or []) + 1


def max_turns(guide: dict) -> int:
    """가이드 전체 예산 = 주제별 예산의 합. 주제가 없으면 0(=제한 없음)."""
    return sum(topic_budget(t) for t in (guide.get("topics") or []))


def _topic_of(guide: dict, qid: str) -> dict | None:
    for t in guide.get("topics") or []:
        if any(q.get("id") == qid for q in (t.get("questions") or [])):
            return t
    return None


def strategize(state: InterviewState) -> dict:
    guide = state.get("guide", {}) or {}
    ledger = state.get("ledger", {})

    # 결정론 하드 가드 — LLM 이 close 를 안 내도 예산을 넘기지 않는다.
    # 별도 상한 상수가 아니라 주제별 예산의 합이라, 가이드를 바꾸면 같이 움직인다.
    budget = max_turns(guide)
    if budget and state.get("asked", 0) + 1 >= budget:
        return {"action": "close", "end_reason": "max_turns"}

    # 강제 advance — 주제 안에서 '남은 질문 수 >= 남은 턴 수' 면 파고들기를 막는다.
    # 없으면 진행자가 앞 질문에서 꼬리질문을 다 써버려 뒤 질문의 버킷이 영영 빈 채로 남는다.
    if state.get("action") in _DIGGING:
        topic = _topic_of(guide, state.get("question_id", ""))
        if topic:
            qids = [q.get("id") for q in (topic.get("questions") or []) if q.get("id")]
            left_turns = topic_budget(topic) - state.get("t_streak", 0)
            pending_here = [q for q in qids if ledger.get(q, {}).get("status") == "pending"]
            if len(pending_here) >= left_turns:
                if pending_here:
                    return {"action": "advance", "question_id": pending_here[0],
                            "is_probe": False, "probe_type": ""}
                # 이 주제는 다 물었고 예산도 없다 — 다음 주제의 pending 으로 넘긴다
                nxt = [qid for qid, e in ledger.items()
                       if e["status"] == "pending" and qid not in qids]
                if nxt:
                    return {"action": "advance", "question_id": nxt[0],
                            "is_probe": False, "probe_type": ""}
    # 정직한 종료 — "문항을 다 입에 올림"이 아니라 원장이 전부 satisfied/saturated 일 때
    if ledger and all(e["status"] in ("satisfied", "saturated") for e in ledger.values()):
        return {"action": "close", "end_reason": "honest_close"}
    # 모순을 적어놓고도 probe/clarify 로 라벨된 턴 → challenge 로 승격 (보강 D)
    # analyst 가 사유엔 모순을 정확히 적으면서 action 은 probe 로 뭉개는 편향 교정 — 모순이 생성에 실린다.
    if state.get("analysis", {}).get("contradiction", "").strip() and state.get("action") in ("probe", "clarify"):
        return {"action": "challenge", "is_probe": False, "probe_type": ""}
    # revisit 근거 검증 — 원장에 빈약(touched) 문항이 없으면 강등, 대상이 틀리면 보정
    if state.get("action") == "revisit":
        thin = [qid for qid, e in ledger.items() if e["status"] == "touched"]
        if not thin:
            return {"action": "advance"}
        if state.get("question_id") not in thin:
            return {"question_id": thin[0]}
    # 꼬리질문 폭주 차단 — probe/clarify 가 상한만큼 연속되면 다음 pending 문항으로 강제 전환 (보강 A)
    if state.get("action") in ("probe", "clarify") and state.get("probe_streak", 0) >= PROBE_STREAK_CAP:
        pending = [qid for qid, e in ledger.items() if e["status"] == "pending"]
        if pending:
            return {"action": "advance", "question_id": pending[0], "is_probe": False, "probe_type": ""}
    # 피로 감지 — 응답자가 지쳤는데 또 캐물으려 하면 강등한다 (F5.1). 남은 pending 이 있으면
    # 거기로 넘어가고, 없으면 억지로 끌지 말고 정직하게 종료한다.
    if state.get("fatigue") and state.get("action") in ("probe", "clarify"):
        pending = [qid for qid, e in ledger.items() if e["status"] == "pending"]
        if pending:
            return {"action": "advance", "question_id": pending[0], "is_probe": False, "probe_type": ""}
        return {"action": "close", "end_reason": "fatigue"}
    # 문항 고착 방지는 위의 '강제 advance'(주제 예산)가 대신한다 — 구 Q_STREAK_CAP=4 폐기.
    # 고정 상한 대신 남은 질문 수와 남은 턴 수를 비교하므로, 질문이 많은 주제일수록
    # 파고들기를 더 일찍 접는다(= 모든 질문의 버킷이 채워진다).
    return {}
