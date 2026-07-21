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
    "ListenOut", "ANALYST_SYSTEM", "analysis_user", "opening_user",
    "generate_user", "farewell_user", "interview_moderator_system",
]

ACTIONS = ("probe", "clarify", "challenge", "advance", "revisit", "redirect", "close")


class ListenOut(BaseModel):
    # --- 분석 (취재 수첩) ---
    facts: list[str] = Field(default_factory=list)   # 직전 답변에서 알아낸 사실
    hooks: list[str] = Field(default_factory=list)   # 파고들 만한데 안 판 떡밥
    coverage: Literal["touched", "satisfied", "saturated"] = "touched"
    contradiction: str = ""    # 앞선 발언과 모순이면 그 내용 한 줄 (없으면 "")
    # --- 전략 (행동 7종) ---
    action: Literal["probe", "clarify", "challenge", "advance", "revisit", "redirect", "close"] = "advance"
    question_id: str = ""      # advance/revisit 의 대상 문항 (그 외 행동은 현 문항 유지)
    probe_type: Literal["", "구체화", "심화"] = ""   # action=probe 일 때 래더링 단계
    reason: str = ""           # 선택 이유 한 줄 — 타임트래블 디버깅 재료


ANALYST_SYSTEM = (
    "당신은 정성조사 인터뷰의 전략 분석가입니다. 응답자의 직전 답변을 분석하고, "
    "진행자가 취할 다음 행동 하나를 고릅니다. **질문 문장은 만들지 않습니다** — 분석과 행동 선택만.\n"
    "행동 7종:\n"
    "- probe: 직전 답변 안으로 파고든다. 표면(무엇·어떤)에 머물면 probe_type=구체화(구체적 사례를 끌어냄), "
    "구체적 사례가 이미 나왔으면 probe_type=심화(그 밑의 이유·동기·감정으로 내려감).\n"
    "- clarify: 답이 모호하거나 뭉개져서 무슨 뜻인지 확인이 필요할 때.\n"
    "- challenge: 앞선 발언과 모순될 때 — contradiction 에 모순 내용을 적고 부드럽게 확인.\n"
    "- advance: 지금 문항을 충분히 들었을 때 다음 문항으로 (question_id 에 다음 문항).\n"
    "- revisit: [답이 얕은 문항]이 있고 지금 문항이 소진됐을 때 되짚기 (question_id 에 그 문항).\n"
    "- redirect: 응답자가 주제를 벗어났을 때 복귀.\n"
    "- close: 남은 문항이 없고 충분히 들었을 때 마무리.\n"
    "구체적 사례·감정·이유가 걸려 있는데 아직 캐묻지 않았다면 probe 가 기본값입니다."
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


def analysis_user(
    guide: dict, messages: list, utterance: str, asked: int, probe_streak: int, ledger: dict
) -> str:
    pending_block, thin_block = _ledger_blocks(guide, ledger)
    return (
        f"[조사 목표]\n{guide.get('goal', '') or '(목표 미기재)'}\n\n"
        f"[지금까지 대화] (진행자 질문 {asked}회)\n{_convo(messages, utterance)}\n\n"
        f"[응답자의 직전 답변]\n{utterance or '(없음)'}\n\n"
        "직전 답변을 취재 수첩에 정리하세요 — facts(알아낸 사실)·hooks(안 판 떡밥)·"
        "coverage(touched/satisfied/saturated).\n"
        "앞선 발언들과 대조해 모순이 있으면 contradiction 에 한 줄로 적으세요(없으면 빈 문자열).\n"
        f"(지금 문항에서 연속 {probe_streak}회 파고들었습니다. 2회를 넘겼으면 다른 행동을 고려하세요. "
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


def generate_user(
    action: str, question_id: str, probe_type: str, contradiction: str,
    guide: dict, messages: list, ledger: dict,
) -> str:
    qs = _qmap(guide)
    parts = [
        f"[조사 목표]\n{guide.get('goal', '') or '(목표 미기재)'}",
        f"[지금까지 대화]\n{_convo(messages, '') or '(시작 전)'}",
        f"[당신이 방금 정한 행동] {action} — {_GEN_DIRECTIVES.get(action, _GEN_DIRECTIVES['advance'])}",
    ]
    if action == "probe" and probe_type:
        parts.append(f"[래더링 단계] {probe_type} — "
                     + ("구체적 사례·상황을 끌어내세요." if probe_type == "구체화"
                        else "이유·동기·감정으로 한 단계 내려가세요."))
    if action == "challenge" and contradiction:
        parts.append(f"[확인할 모순]\n{contradiction}")
    if action in ("advance", "revisit") and question_id in qs:
        q = qs[question_id]
        parts.append(f"[대상 문항]\n{q['text']} (알아낼 것: {q.get('goal', '')})")
        if action == "revisit" and ledger.get(question_id, {}).get("facts"):
            parts.append("[이 문항에서 이미 들은 것]\n- " + "\n- ".join(ledger[question_id]["facts"]))
    parts.append("진행자의 다음 한 마디(질문 1~2문장, 한국어 존댓말)만 출력하세요.")
    return "\n\n".join(parts)


def farewell_user(messages: list) -> str:
    return (
        f"[지금까지 대화]\n{_convo(messages, '') or '(대화 없음)'}\n\n"
        "인터뷰를 마무리합니다. 응답자가 말해준 내용을 한 가지 짚으며 "
        "진심 어린 감사 인사로 마치세요. 1~2문장, 새 질문 금지."
    )
