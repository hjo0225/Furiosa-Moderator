"""모더레이터 오케스트레이터 — 한 턴의 전 과정을 조율한다.

아키텍처 §5.2 의 흐름을 그대로 구현한다:
  응답자 발화 → PII 마스킹 → 감정 태깅 → 가이드 커버리지 판정 →
  LLM 다음 질문 생성 → 중립성 가드레일 검증 → 저장 → 반환

M-1(가이드 준수)은 '커버한 문항 id' 를 세션에 누적하는 방식으로 구현했다. 모델에게
남은 문항을 매 턴 보여주고 어떤 문항을 다뤘는지 함께 답하게 한다. 프롬프트로만
'가이드를 지켜라'라고 하는 것과 달리, 커버리지가 데이터로 남아 종료 판정과 대시보드에 쓰인다.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel

from ..prompts.insight import EMOTION_SYSTEM, emotion_user
from ..prompts.interview_moderator import interview_moderator_system
from ..schemas.models import InterviewGuide, Session, Turn
from . import guardrail, store
from .llm_client import LLMError, get_llm
from .pii import mask_pii, scan_pii

log = logging.getLogger(__name__)

# 진행자 질문이 이 수를 넘으면 강제 종료한다. 모델이 done 을 안 내는 경우의 안전장치로,
# 응답자를 무한 인터뷰에 가두지 않기 위한 것이다(원본 프롬프트 기준 6~10턴).
_MAX_ASKED = 12


class _ModeratorOut(BaseModel):
    message: str
    done: bool = False
    question_id: str = ""   # 이번 발화가 다루는 가이드 문항
    is_probe: bool = False  # 꼬리질문이면 True


class _Emotion(BaseModel):
    label: str = "중립"
    confidence: float = 0.0


def _moderator_user(guide: InterviewGuide, history: list[Turn], asked: int, covered: list[str]) -> str:
    """모더레이터 user 프롬프트 — 가이드 커버리지를 명시적으로 실어보낸다.

    구성 순서가 중요하다. 초안에서는 '남은 문항' 목록을 앞에 크게 실었더니 모델이
    매 턴 목록에서 다음 항목을 집어들기만 하고 직전 답변을 무시했다(실측: 7턴 내내
    is_probe=false, 응답자가 '배달비가 부담된다'고 해도 다음 대본 질문으로 직행).
    직전 답변을 먼저 보게 하고, 문항 목록은 '넘어갈 때 참고'로 뒤에 두면 probing 이 산다.
    """
    convo = "\n".join(
        f"{'진행자' if t.role == 'moderator' else '응답자'}: {t.text}" for t in history
    )
    last_answer = next(
        (t.text for t in reversed(history) if t.role == "respondent"), ""
    )
    # 직전 문항에서 몇 번 연속 파고들었는지 — 한 주제에 갇히지 않게 하는 근거
    probe_streak = 0
    for t in reversed(history):
        if t.role != "moderator":
            continue
        if t.is_probe:
            probe_streak += 1
        else:
            break

    remaining = [q for q in guide.questions if q.id not in covered]
    remaining_block = "\n".join(f"- {q.id}: {q.text} (알아낼 것: {q.goal})" for q in remaining)
    covered_block = ", ".join(covered) or "(없음)"

    if not history:
        return (
            f"[조사 목표]\n{guide.goal or '(목표 미기재)'}\n\n"
            f"[첫 문항]\n{remaining_block}\n\n"
            "인터뷰의 첫 턴입니다. 따뜻하게 인사하고 위 첫 문항으로 가볍게 시작하세요. "
            "question_id 에 그 문항 id 를, is_probe=false, done=false 로 하세요."
        )

    return (
        f"[조사 목표]\n{guide.goal or '(목표 미기재)'}\n\n"
        f"[지금까지 대화] (진행자 질문 {asked}회)\n{convo}\n\n"
        f"[응답자의 직전 답변]\n{last_answer or '(없음)'}\n\n"
        "먼저 직전 답변을 판단하세요.\n"
        f"직전 답변에 구체적 사례·감정·이유가 걸려 있는데 아직 캐묻지 않았다면 "
        f"**꼬리질문을 하는 것이 기본값입니다**(is_probe=true, question_id 는 지금 문항 유지). "
        "'배달비가 부담된다' 같은 답에는 '어느 정도일 때 부담스럽게 느껴지세요?', "
        "'그럴 때는 어떻게 하세요?' 처럼 그 답 안으로 한 단계 더 들어가세요. "
        "답을 못 들은 채 다음 문항으로 넘어가지 마세요.\n"
        f"(지금 이 문항에서 연속 {probe_streak}회 파고들었습니다. 2회를 넘겼거나 "
        "답이 짧고 더 나올 게 없어 보이면 다음 문항으로 넘어가세요 — is_probe=false.)\n\n"
        f"[아직 다루지 않은 문항] (넘어갈 때만 참고)\n{remaining_block or '(전부 다룸)'}\n"
        f"[이미 다룬 문항] {covered_block}\n\n"
        "남은 문항이 없고 충분히 들었으면 done=true, message 에는 감사 인사로 마무리하는 한 마디를 쓰세요."
    )


def tag_emotion(text: str) -> tuple[str, float]:
    """발화 감정 태깅 (M-3). 실패하면 중립/0.0 — 인터뷰를 막지 않는다."""
    if not text or len(text.strip()) < 2:
        return "중립", 0.0
    try:
        e, _ = get_llm().structured(EMOTION_SYSTEM, emotion_user(text), _Emotion, max_tokens=150)
    except LLMError as e:
        log.warning("감정 태깅 실패: %s", e)
        return "중립", 0.0
    return e.label or "중립", max(0.0, min(1.0, e.confidence))


def next_turn(
    project_id: str, session: Session, guide: InterviewGuide, respondent_text: str, lang: str = "ko"
) -> tuple[str, bool, Turn | None, Turn]:
    """한 턴 진행. 반환 (진행자 발화, 종료여부, 저장된 응답자 턴|None, 저장된 진행자 턴)."""
    sid = session.id
    respondent_turn: Turn | None = None

    # 1) 응답자 발화 — 저장 전에 마스킹한다(PRD 9절). 마스킹된 텍스트로 이후 전부 진행.
    text = (respondent_text or "").strip()
    if text:
        pii_types = scan_pii(text)
        masked = mask_pii(text)
        emotion, conf = tag_emotion(masked)
        respondent_turn = store.add_turn(
            project_id,
            sid,
            Turn(
                role="respondent",
                text=masked,
                emotion=emotion,
                emotion_confidence=conf,
                pii_types=pii_types,
            ),
        )

    # 2) 대화이력 — 방금 저장한 턴까지 포함해 다시 읽는다.
    history = store.list_turns(project_id, sid)
    asked = sum(1 for t in history if t.role == "moderator")

    # 3) 다음 발화 생성
    try:
        out, _ = get_llm().structured(
            interview_moderator_system(lang),
            _moderator_user(guide, history, asked, session.covered),
            _ModeratorOut,
            max_tokens=500,
        )
    except LLMError as e:
        log.exception("모더레이터 생성 실패: %s", e)
        raise

    message = (out.message or "").strip()
    done = bool(out.done)

    # 안전장치 — 모델이 종료를 안 내도 무한 인터뷰는 막는다.
    if asked + 1 >= _MAX_ASKED:
        done = True
        if not message:
            message = "오늘 말씀 정말 감사합니다. 여기서 인터뷰를 마치겠습니다."

    # 4) 중립성 가드레일 (M-2) — 마무리 멘트는 질문이 아니므로 검사하지 않는다.
    rewritten = False
    if not done and message:
        message, rewritten, reason = guardrail.ensure_neutral(message)
        if rewritten:
            log.info("가드레일 재작성 (session=%s, 사유=%s)", sid, reason)

    # 5) 진행자 턴 저장
    moderator_turn = store.add_turn(
        project_id,
        sid,
        Turn(
            role="moderator",
            text=message,
            is_probe=bool(out.is_probe),
            question_id=out.question_id or "",
            guardrail_rewritten=rewritten,
        ),
    )

    # 6) 세션 갱신 — 커버리지 누적
    covered = list(session.covered)
    if out.question_id and out.question_id not in covered:
        covered.append(out.question_id)
    patch: dict = {"asked": asked + 1, "covered": covered, "status": "active"}
    if done:
        from datetime import datetime, timezone

        patch["status"] = "completed"
        patch["ended_at"] = datetime.now(timezone.utc)
    store.update_session(project_id, sid, patch)
    session.covered = covered
    session.asked = asked + 1

    return message, done, respondent_turn, moderator_turn
