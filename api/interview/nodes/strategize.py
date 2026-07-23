"""strategize — 결정론 확정: 12턴 하드 가드 + 정직한 종료 + revisit 근거 검증 (T3).

LLM(분석 콜)의 행동 '제안'을 데이터가 검열한다 — 판단은 LLM, 집행은 결정론.
"""
from __future__ import annotations

from ..state import InterviewState

MAX_ASKED = 12  # moderator._MAX_ASKED 와 동일 값 — 구엔진 제거 시 여기가 단일 출처
PROBE_STREAK_CAP = 3  # probe/clarify 연속 상한 — 넘으면 다음 pending 으로 결정론 전환 (보강 A)
Q_STREAK_CAP = 4  # 같은 문항에 머문 총 턴 상한 — probe_streak 이 비-probe 턴에 리셋되는 구멍을 메운다(문항 고착 방지)


def strategize(state: InterviewState) -> dict:
    # 결정론 하드 가드 — LLM 이 close 를 안 내도 12번째 질문에서 끝낸다
    if state.get("asked", 0) + 1 >= MAX_ASKED:
        return {"action": "close", "end_reason": "max_turns"}
    # 정직한 종료 — "문항을 다 입에 올림"이 아니라 원장이 전부 satisfied/saturated 일 때
    ledger = state.get("ledger", {})
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
    # 문항 고착 방지 — 같은 문항에 Q_STREAK_CAP 턴 이상 머물면(probe 여부 무관, 리셋 안 되는 카운터)
    # 다음 pending 으로 강제 전환. probe_streak 이 비-probe 턴에 리셋돼 못 잡던 고착을 메운다.
    if state.get("q_streak", 0) >= Q_STREAK_CAP and state.get("action") in ("probe", "clarify", "challenge", "redirect"):
        pending = [qid for qid, e in ledger.items() if e["status"] == "pending"]
        if pending:
            return {"action": "advance", "question_id": pending[0], "is_probe": False, "probe_type": ""}
    return {}
