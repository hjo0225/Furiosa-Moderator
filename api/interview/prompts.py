"""그래프 전용 프롬프트·스키마 — T2 부터 그래프는 구엔진 프롬프트와 독립 진화한다.

시스템 프롬프트는 기존 것을 재사용(Qwen3 톤 튜닝 보존), 원장 컨텍스트와
facts/hooks/coverage 보고 지시는 user 프롬프트에 싣는다(구엔진과 같은 패턴).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..prompts.interview_moderator import interview_moderator_system  # 재수출 — 노드는 여기서만 가져간다

__all__ = ["ListenOut", "listen_user", "interview_moderator_system"]


class ListenOut(BaseModel):
    message: str
    done: bool = False
    question_id: str = ""
    is_probe: bool = False
    # 직전 문항의 취재 상태 판정: touched(더 나올 수 있음) / satisfied(goal 충족) / saturated(더 캐도 안 나옴)
    coverage: Literal["touched", "satisfied", "saturated"] = "touched"
    facts: list[str] = Field(default_factory=list)   # 직전 답변에서 알아낸 사실 (짧게)
    hooks: list[str] = Field(default_factory=list)   # 파고들 만한데 아직 안 판 떡밥


def _convo(messages: list, utterance: str) -> str:
    lines = [f"{'진행자' if m.type == 'ai' else '응답자'}: {m.content}" for m in messages]
    if utterance:
        lines.append(f"응답자: {utterance}")
    return "\n".join(lines)


def listen_user(
    guide: dict, messages: list, utterance: str, asked: int, probe_streak: int,
    ledger: dict, lang: str = "ko",
) -> str:
    goal = guide.get("goal", "")
    questions = {q["id"]: q for q in guide.get("questions", []) if q.get("id")}
    pending = [q for qid, q in questions.items() if ledger.get(qid, {}).get("status") == "pending"]
    thin = [q for qid, q in questions.items() if ledger.get(qid, {}).get("status") == "touched"]

    pending_block = "\n".join(f"- {q['id']}: {q['text']} (알아낼 것: {q.get('goal', '')})" for q in pending)
    thin_block = "\n".join(
        f"- {q['id']}: {q['text']} (지금까지 알아낸 것 {len(ledger[q['id']]['facts'])}건"
        + (f", 안 판 떡밥: {' / '.join(ledger[q['id']]['hooks'][:2])}" if ledger[q["id"]]["hooks"] else "")
        + ")"
        for q in thin
    )

    if not messages and not utterance:
        return (
            f"[조사 목표]\n{goal or '(목표 미기재)'}\n\n"
            f"[첫 문항]\n{pending_block}\n\n"
            "인터뷰의 첫 턴입니다. 따뜻하게 인사하고 위 첫 문항으로 가볍게 시작하세요. "
            "question_id 에 그 문항 id 를, is_probe=false, done=false 로 하세요. "
            "facts/hooks 는 빈 배열로 두세요."
        )

    return (
        f"[조사 목표]\n{goal or '(목표 미기재)'}\n\n"
        f"[지금까지 대화] (진행자 질문 {asked}회)\n{_convo(messages, utterance)}\n\n"
        f"[응답자의 직전 답변]\n{utterance or '(없음)'}\n\n"
        "먼저 직전 답변을 취재 수첩에 정리하세요:\n"
        "- facts: 직전 답변에서 실제로 알아낸 사실을 짧은 문장으로 (없으면 빈 배열)\n"
        "- hooks: 걸려 있는데 아직 안 판 떡밥 (없으면 빈 배열)\n"
        "- coverage: 지금 문항의 상태 — 아직 더 나올 수 있으면 touched, "
        "'알아낼 것'을 충분히 채웠으면 satisfied, 더 캐도 안 나올 것 같으면 saturated\n\n"
        "그 다음 행동하세요.\n"
        "직전 답변에 구체적 사례·감정·이유가 걸려 있는데 아직 캐묻지 않았다면 "
        "**꼬리질문이 기본값입니다**(is_probe=true, question_id 는 지금 문항 유지). "
        f"(지금 이 문항에서 연속 {probe_streak}회 파고들었습니다. 2회를 넘겼거나 "
        "답이 짧고 더 나올 게 없으면 다음 문항으로 — is_probe=false.)\n\n"
        f"[아직 다루지 않은 문항]\n{pending_block or '(전부 다룸)'}\n"
        f"[답이 얕은 문항 — 나중에 되짚을 후보]\n{thin_block or '(없음)'}\n\n"
        "남은 문항이 없고 충분히 들었으면 done=true, message 는 감사 인사 한 마디."
    )
