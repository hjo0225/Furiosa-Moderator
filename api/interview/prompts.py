"""그래프 전용 프롬프트·스키마 v3 — 분석(listen)과 생성(generate)의 콜 분리 (T3).

분석 콜(ANALYST_SYSTEM + analysis_user → ListenOut)은 질문 문장을 만들지 않는다.
생성 콜은 기존 interview_moderator_system(질문 1개 만들기)을 재사용하고,
행동별 지시는 generate_user 가 싣는다. 래더링(probe_type)·첫턴 1문항·모순 확인은
원격 병합으로 들어온 구엔진 개선을 그래프에 이식한 것.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..prompts.interview_moderator import interview_moderator_system  # 생성 콜 시스템 (재수출)

__all__ = [
    "ListenOut", "ReflectOut", "CoverageUpdate", "ANALYST_SYSTEM", "REFLECT_SYSTEM",
    "analysis_user", "reflect_user", "opening_user",
    "generate_user", "farewell_user", "interview_moderator_system",
]


class ListenOut(BaseModel):
    # 슬림 분석 (T4) — 취재 수첩 정리(facts/hooks/coverage)는 슬로우패스 ReflectOut 으로 이사
    contradiction: str = ""    # 앞선 발언과 모순이면 그 내용 한 줄 (없으면 "")
    # 모르는 용어 나열 — brief(RAG) 의 트리거 (T0 폴백: 자율 tool choice 대신 명시적 분류)
    unknown_terms: list[str] = Field(default_factory=list)
    # --- 전략 (행동 7종) ---
    action: Literal["probe", "clarify", "challenge", "advance", "revisit", "redirect", "close"] = "advance"
    question_id: str = ""      # advance/revisit 의 대상 문항 (그 외 행동은 현 문항 유지)
    # action=probe 일 때 프로빙 유형 5종 (F5.1). "" 는 미지정.
    probe_type: Literal["", "구체화", "심화", "예시요청", "대비", "결과추적", "감정원인"] = ""
    # 응답자 피로 신호 감지 — true 면 strategize 가 더 캐묻지 않고 advance/close 로 강등 (F5.1)
    fatigue: bool = False
    reason: str = ""           # 선택 이유 한 줄 — 타임트래블 디버깅 재료


ANALYST_SYSTEM = (
    "당신은 정성조사 인터뷰의 전략 분석가입니다. 응답자의 직전 답변을 분석하고, "
    "진행자가 취할 다음 행동 하나를 고릅니다. **질문 문장은 만들지 않습니다** — 분석과 행동 선택만.\n"
    "행동 7종:\n"
    "- probe: 직전 답변 안으로 파고든다. probe_type 으로 프로빙 유형을 고른다(아래 [프로빙 유형] 참고).\n"
    "- clarify: 답이 모호하거나 뭉개져서 무슨 뜻인지 확인이 필요할 때.\n"
    "- challenge: 앞선 발언과 모순될 때 — contradiction 에 모순 내용을 적고 부드럽게 확인.\n"
    "- advance: 지금 문항을 충분히 들었을 때 다음 문항으로 (question_id 에 다음 문항).\n"
    "- revisit: [답이 얕은 문항]이 있고 지금 문항이 소진됐을 때 되짚기 (question_id 에 그 문항).\n"
    "- redirect: 응답자가 주제를 벗어났을 때 복귀.\n"
    "- close: 남은 문항이 없고 충분히 들었을 때 마무리.\n"
    "구체적 사례·감정·이유가 걸려 있는데 아직 캐묻지 않았다면 probe 가 기본값입니다.\n"
    "\n[프로빙 유형] (action=probe 일 때 probe_type 에 하나):\n"
    "- 구체화: 표면(무엇·어떤)에 머물 때 구체적 사례를 끌어냄.\n"
    "- 심화: 사례가 나왔을 때 그 밑의 이유·동기·감정으로 한 단계 내려감.\n"
    "- 예시요청: 일반론으로 말할 때 가장 최근의 실제 사례 하나를 청함.\n"
    "- 대비: 대안·다른 선택지와 비교하게 함(왜 이것이고 저것이 아닌가).\n"
    "- 결과추적: 그 상황에서 그래서 어떻게 했는지·무슨 일이 벌어졌는지 뒤를 좇음.\n"
    "- 감정원인: 감정 표현이 나왔을 때 그 감정의 원인을 캐물음.\n"
    "\n[버킷 적합도] 직전 답변이 지금 문항의 응답 버킷 중 하나에 명확히 들어가지 않으면"
    "(경계에 걸치거나 어디에도 안 맞으면) 그것이 곧 probe 신호다. "
    "버킷은 분류 라벨이자 프로빙 목표다 — 답을 특정 버킷으로 몰아가지 말고, 어느 버킷인지 "
    "또렷해지도록 파고든다.\n"
    "\n[피로 감지] 응답자 피로 신호(답변이 직전보다 급격히 짧아짐, '몰라요/글쎄요/그냥' 반복, "
    "성의 없음)를 감지하면 fatigue=true 로 표시한다. 피로가 감지되면 더 캐묻지 말고 "
    "advance 또는 close 를 고른다."
)


def _convo(messages: list, utterance: str) -> str:
    lines = [f"{'진행자' if m.type == 'ai' else '응답자'}: {m.content}" for m in messages]
    if utterance:
        lines.append(f"응답자: {utterance}")
    return "\n".join(lines)


def _qmap(guide: dict) -> dict:
    return {q["id"]: q for q in guide.get("questions", []) if q.get("id")}


def _ledger_blocks(guide: dict, ledger: dict) -> tuple[str, str]:
    qs = _qmap(guide)
    pending = [q for qid, q in qs.items() if ledger.get(qid, {}).get("status") == "pending"]
    thin = [q for qid, q in qs.items() if ledger.get(qid, {}).get("status") == "touched"]
    pending_block = "\n".join(f"- {q['id']}: {q['text']} (알아낼 것: {q.get('goal', '')})" for q in pending)
    thin_block = "\n".join(
        f"- {q['id']}: {q['text']} (알아낸 것 {len(ledger[q['id']]['facts'])}건"
        + (f", 안 판 떡밥: {' / '.join(ledger[q['id']]['hooks'][:2])}" if ledger[q["id"]]["hooks"] else "")
        + ")"
        for q in thin
    )
    return pending_block, thin_block


def _bucket_block(guide: dict, current_qid: str) -> str:
    """지금 문항의 응답 버킷을 label+정의로 나열 — 분석가가 버킷 적합도를 판단하는 재료.

    버킷이 없거나 문항을 못 찾으면 빈 문자열(호출부가 블록을 생략)."""
    if not current_qid:
        return ""
    q = _qmap(guide).get(current_qid)
    if not q:
        return ""
    buckets = q.get("response_buckets") or []
    if not buckets:
        return ""
    lines = []
    for b in buckets:
        label = b.get("label", "")
        definition = b.get("definition", "")
        lines.append(f"- {label}" + (f": {definition}" if definition else ""))
    return "\n".join(lines)


def analysis_user(
    guide: dict, messages: list, utterance: str, asked: int, probe_streak: int, ledger: dict,
    pace_line: str = "", current_qid: str = "",
) -> str:
    pending_block, thin_block = _ledger_blocks(guide, ledger)
    bucket_block = _bucket_block(guide, current_qid)
    return (
        f"[조사 목표]\n{guide.get('goal', '') or '(목표 미기재)'}\n\n"
        f"[지금까지 대화] (진행자 질문 {asked}회)\n{_convo(messages, utterance)}\n\n"
        f"[응답자의 직전 답변]\n{utterance or '(없음)'}\n\n"
        + (f"[지금 문항의 응답 버킷] (직전 답변이 어느 버킷에도 또렷이 안 들어가면 그 자체가 probe 신호)\n"
           f"{bucket_block}\n\n" if bucket_block else "")
        + "직전 답변을 앞선 발언들과 대조해 모순이 있으면 contradiction 에 한 줄로 적으세요(없으면 빈 문자열).\n"
        "직전 답변에 당신이 모르는 용어·브랜드·고유명사가 있으면 unknown_terms 에 그대로 나열하세요"
        "(아는 척 금지 — 없으면 빈 배열).\n"
        + (f"{pace_line}\n" if pace_line else "")
        + f"(지금 문항에서 연속 {probe_streak}회 파고들었습니다. 2회를 넘겼으면 다른 행동을 고려하세요. "
        "표면에 머물면 구체화, 사례가 나왔으면 심화 — probe_type 에 기록.)\n\n"
        f"[아직 다루지 않은 문항]\n{pending_block or '(전부 다룸)'}\n"
        f"[답이 얕은 문항 — revisit 후보]\n{thin_block or '(없음)'}\n\n"
        "이제 행동 하나(action)와 그 이유(reason)를 정하세요."
    )


def opening_user(guide: dict) -> tuple[str, str]:
    """오프닝 프롬프트 — 첫 문항 **하나만** 노출(문항 여러 개를 묶어 던지는 실측 사고 방지)."""
    qs = list(_qmap(guide).values())
    first = qs[0] if qs else None
    block = f"- {first['text']} (알아낼 것: {first.get('goal', '')})" if first else "(문항 없음)"
    prompt = (
        f"[조사 목표]\n{guide.get('goal', '') or '(목표 미기재)'}\n\n"
        f"[첫 문항]\n{block}\n\n"
        "인터뷰의 첫 턴입니다. 따뜻하게 인사하고 위 문항 하나만 물어보세요. "
        "나머지 문항은 다음 턴들에서 다루니 여러 개를 묶어 던지지 마세요. 1~2문장."
    )
    return prompt, (first["id"] if first else "")


_GEN_DIRECTIVES = {
    "probe": "직전 답변 안으로 한 단계 더 들어가는 꼬리질문을 하세요.",
    "clarify": "방금 답변이 모호했습니다. 무슨 뜻이었는지 부드럽게 되묻으세요.",
    "challenge": "앞선 발언과 모순이 있습니다. 비난하지 말고 호기심으로, 두 발언을 함께 들어 확인하세요.",
    "advance": "지금 문항은 충분히 들었습니다. 아래 다음 문항으로 자연스럽게 넘어가세요.",
    "revisit": "앞서 얕게 지나간 문항으로 되돌아갑니다. 이미 들은 내용을 언급하며 더 깊이 물으세요.",
    "redirect": "응답자가 주제를 벗어났습니다. 답변을 존중하면서 부드럽게 원래 주제로 돌아오세요.",
}

# 프로빙 유형 5종(+구체화·심화 합쳐 6) 각각의 한 줄 지시 — ANALYST_SYSTEM 의 뜻과 일치 (F5.1)
_PROBE_DIRECTIVES = {
    "구체화": "구체적 사례·상황을 끌어내세요.",
    "심화": "이유·동기·감정으로 한 단계 내려가세요.",
    "예시요청": "가장 최근의 실제 사례 하나를 들어달라고 청하세요.",
    "대비": "대안·다른 선택지와 비교해 왜 이것이었는지 물으세요.",
    "결과추적": "그래서 그다음 어떻게 했는지·무슨 일이 벌어졌는지 뒤를 좇으세요.",
    "감정원인": "방금 드러난 감정의 원인이 무엇인지 물으세요.",
}


def generate_user(
    action: str, question_id: str, probe_type: str, contradiction: str,
    guide: dict, messages: list, ledger: dict,
    brief_notes: list | tuple = (), technique: str = "",
) -> str:
    from .tools.ledger_report import ledger_report

    qs = _qmap(guide)
    parts = [
        f"[조사 목표]\n{guide.get('goal', '') or '(목표 미기재)'}",
        f"[지금까지 대화]\n{_convo(messages, '') or '(시작 전)'}",
        f"[당신이 방금 정한 행동] {action} — {_GEN_DIRECTIVES.get(action, _GEN_DIRECTIVES['advance'])}",
    ]
    if action == "probe" and probe_type in _PROBE_DIRECTIVES:
        parts.append(f"[프로빙 유형] {probe_type} — {_PROBE_DIRECTIVES[probe_type]}")
    if action == "challenge" and contradiction:
        parts.append(f"[확인할 모순]\n{contradiction}")
    if action in ("advance", "revisit") and question_id in qs:
        q = qs[question_id]
        parts.append(f"[대상 문항]\n{q['text']} (알아낼 것: {q.get('goal', '')})")
        if action == "revisit":
            parts.append(ledger_report(guide, ledger, qid=question_id))   # 도구: 원장 상세
    if brief_notes:
        notes = "\n".join(f"- {n['text']} (출처: {n['source']})" for n in brief_notes)
        parts.append("[의뢰자 브리핑 발췌 — 용어·사실 참고용]\n" + notes +
                     "\n위 내용은 이해를 돕는 배경입니다. 특정 답을 유도하는 데 쓰지 마세요.")
    if technique:
        parts.append(technique)
    parts.append("진행자의 다음 한 마디(질문 1~2문장, 한국어 존댓말)만 출력하세요.")
    return "\n\n".join(parts)


def farewell_user(messages: list) -> str:
    return (
        f"[지금까지 대화]\n{_convo(messages, '') or '(대화 없음)'}\n\n"
        "인터뷰를 마무리합니다. 응답자가 말해준 내용을 한 가지 짚으며 "
        "진심 어린 감사 인사로 마치세요. 1~2문장, 새 질문 금지."
    )


# --- 슬로우패스 (reflect) — 취재 수첩 정리, 응답자가 말하는 시간에 돈다 (T4) ------

class CoverageUpdate(BaseModel):
    """한 답변이 건드린 한 문항의 취재 결과 — 지금 물은 문항일 수도, 곁다리로 답한 문항일 수도 (보강 B)."""
    question_id: str
    coverage: Literal["touched", "satisfied", "saturated"] = "touched"
    facts: list[str] = Field(default_factory=list)
    hooks: list[str] = Field(default_factory=list)


class ReflectOut(BaseModel):
    updates: list[CoverageUpdate] = Field(default_factory=list)


REFLECT_SYSTEM = (
    "당신은 정성조사 인터뷰의 기록 담당입니다. 방금 나온 응답자 답변을 취재 수첩에 정리합니다.\n"
    "답변이 실제로 건드린 문항마다 updates 항목을 하나씩 만드세요:\n"
    "- question_id: 해당 문항 id (아래 목록에 있는 것만)\n"
    "- facts: 그 문항에 대해 알아낸 사실 (짧은 문장)\n"
    "- hooks: 걸려 있는데 아직 안 판 떡밥\n"
    "- coverage: 그 문항 상태 — 더 나올 수 있으면 touched, '알아낼 것'을 채웠으면 satisfied, "
    "더 캐도 안 나올 것 같으면 saturated\n"
    "지금 물은 문항이 주로 채워지지만, 답변이 다른 문항까지 답했다면 그 문항도 넣으세요. "
    "안 건드린 문항은 넣지 마세요."
)


def reflect_user(guide: dict, current_qid: str, utterance: str) -> str:
    lines = "\n".join(
        f"- {q['id']}: {q['text']} (알아낼 것: {q.get('goal', '')})"
        + ("  ← 지금 물은 문항" if q["id"] == current_qid else "")
        for q in guide.get("questions", []) if q.get("id")
    )
    return (
        f"[가이드 문항 전체]\n{lines}\n\n"
        f"[응답자의 답변]\n{utterance}\n\n"
        "이 답변이 건드린 문항을 각각 updates 에 정리하세요."
    )
