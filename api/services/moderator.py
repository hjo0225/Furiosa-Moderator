"""모더레이터 오케스트레이터 — 한 턴의 전 과정을 조율한다.

아키텍처 §5.2 의 흐름을 그대로 구현한다:
  응답자 발화 → PII 마스킹 → 감정 태깅 → 가이드 커버리지 판정 →
  LLM 다음 질문 생성 → 중립성 가드레일 검증 → 저장 → 반환

M-1(가이드 준수)은 '커버한 문항 id' 를 세션에 누적하는 방식으로 구현했다. 모델에게
남은 문항을 매 턴 보여주고 어떤 문항을 다뤘는지 함께 답하게 한다. 프롬프트로만
'가이드를 지켜라'라고 하는 것과 달리, 커버리지가 데이터로 남아 종료 판정과 대시보드에 쓰인다.
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import re

from pydantic import BaseModel

from ..prompts.insight import EMOTION_SYSTEM, emotion_user
from ..prompts.interview_moderator import interview_moderator_system
from ..schemas.models import InterviewGuide, Session, Turn
from . import guardrail, store
from .llm_client import LLMError, get_llm
from .pii import mask_pii, scan_pii

log = logging.getLogger(__name__)

# 진행자 질문이 이 수를 넘으면 강제 종료한다. 모델이 done 을 안 내는 경우의 안전장치로,
# 응답자를 무한 인터뷰에 가두지 않기 위한 것이다.
#
# 고정 상수(구 12)를 버리고 가이드에서 계산한다 — 주제당 질문수+1 의 합
# (스펙 docs/specs/2026-07-24-guide-topics-turn-budget.md). 그래프 엔진의
# strategize.max_turns 와 같은 정의이며, 구엔진은 폴백 경로라 값만 맞춘다.
_FALLBACK_MAX_ASKED = 12   # 가이드가 없을 때만 쓰는 최후 안전장치


def _max_asked(guide) -> int:
    return getattr(guide, "max_turns", 0) or _FALLBACK_MAX_ASKED

# 그 자체로는 아무 내용도 없는 발화들. 되묻기 판정에만 쓴다.
# 의도적으로 **좁게** 잡았다 — 오탐(진짜 답변을 잡음으로 버림)이 미탐(잡음에 되물음)보다
# 훨씬 나쁘기 때문이다. 버린 답변은 복구할 방법이 없고, 한 번 더 되묻는 건 성가실 뿐이다.
# 그래서 '글쎄요'(= 모르겠다는 실제 답)나 '별로요' 같은 건 넣지 않았다.
_FILLERS = {
    "음", "으음", "어", "어어", "아", "아아", "에", "엄", "흠", "허", "하",
    "그", "그래", "그래요", "그러네", "그러네요", "그렇죠", "그쵸", "그니까", "그러니까",
    "네", "넵", "네네", "예", "응", "웅", "옹",
    "뭐", "저기", "이제", "약간",
    "uh", "um", "umm", "hmm", "ah", "oh", "yeah", "yes", "ok", "okay",
}


def is_non_answer(text: str) -> bool:
    """실질적 내용이 없는 발화인가.

    "음, 그래. 그래." 처럼 추임새만 있는 발화가 정상 답변으로 처리되던 걸 막는다. 실측에서
    이런 발화가 감정 태깅 LLM 호출을 낭비하고, 턴으로 저장되고, 턴 예산을 깎고,
    모델이 직전 질문을 사과 한마디 없이 거의 그대로 반복하게 만들었다.

    마이크가 TTS 재생음이나 주변음을 주워담으면 이런 게 들어온다.
    """
    tokens = [t for t in re.split(r"[\s,.!?…·~\-]+", text.strip()) if t]
    if not tokens:
        return True
    # "어어어", "음음" 같은 늘임은 한 글자로 접어서 본다.
    return all(re.sub(r"(.)\1+", r"\1", t.lower()) in _FILLERS or t.lower() in _FILLERS
               for t in tokens)


def _question_part(text: str) -> str:
    """진행자 발화에서 질문 문장만 뽑는다.

    되물을 때 "안녕하세요! ..." 인사까지 되풀이하면 더 어색해진다. 마지막 물음표 문장,
    없으면 마지막 문장만 쓴다.
    """
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]
    if not parts:
        return text.strip()
    return next((p for p in reversed(parts) if p.endswith("?")), parts[-1])


class _ModeratorOut(BaseModel):
    message: str
    done: bool = False
    question_id: str = ""   # 이번 발화가 다루는 가이드 문항
    is_probe: bool = False  # 꼬리질문이면 True
    # 꼬리질문의 종류 — 표면 사례를 끌어내면 '구체화', 이유·동기·감정으로 내려가면 '심화'.
    # 아직 저장하지 않는다(turns 에 컬럼이 없다). 모델이 스스로 분류하게 해 래더링을 유도하고,
    # 로그로만 관찰한다. 대시보드 지표로 쓰려면 그때 컬럼을 붙인다.
    probe_type: str = ""


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
        # 첫 턴에는 **문항 하나만** 보여준다. 목록 전체를 넘겼더니 모델이 앞의 3개를 한
        # 발화로 합쳐 던졌다(실측: "어떤 목적으로? / 어떤 앱을? / 왜 그 앱을?" = q1+q2+q3).
        # 시스템 프롬프트의 '한 번에 질문 하나만' 은 눈앞의 목록을 이기지 못한다.
        first = remaining[0] if remaining else None
        first_block = (
            f"- {first.id}: {first.text} (알아낼 것: {first.goal})" if first else "(문항 없음)"
        )
        return (
            f"[조사 목표]\n{guide.goal or '(목표 미기재)'}\n\n"
            f"[첫 문항]\n{first_block}\n\n"
            "인터뷰의 첫 턴입니다. 따뜻하게 인사하고 **위 문항 하나만** 물어보세요. "
            "나머지 문항은 다음 턴들에서 다루니 여러 개를 묶어 던지지 마세요. "
            "question_id 에 그 문항 id 를, is_probe=false, done=false 로 하세요."
        )

    return (
        f"[조사 목표]\n{guide.goal or '(목표 미기재)'}\n\n"
        f"[지금까지 대화] (진행자 질문 {asked}회)\n{convo}\n\n"
        f"[응답자의 직전 답변]\n{last_answer or '(없음)'}\n\n"
        "먼저 직전 답변을 판단하세요.\n"
        "직전 답변에 구체적 사례·감정·이유가 걸려 있는데 아직 캐묻지 않았다면 "
        "**꼬리질문을 하는 것이 기본값입니다**(is_probe=true, question_id 는 지금 문항 유지).\n"
        f"- 지금 이 문항에서 연속 {probe_streak}회 파고들었습니다. 아직 표면(무엇을·어떤)에 "
        "머물러 있으면 구체적 사례를 끌어내고(probe_type=구체화), 구체적 사례가 이미 나왔으면 "
        "그 밑의 이유·동기·감정으로 한 단계 더 내려가세요(probe_type=심화). '배달비가 부담된다'에는 "
        "'어느 정도일 때 부담스럽게 느껴지세요?' → '그럴 때는 어떻게 하세요?'처럼 답 안으로 들어갑니다.\n"
        "- 단, 동기·감정·가치까지 내려가 더 캘 게 없거나, 2회를 넘겼거나, 답이 짧아 나올 게 "
        "없어 보이면 다음 문항으로 넘어가세요(is_probe=false).\n"
        "- 다음 문항으로 넘어갈 때, 앞선 답변과 자연스럽게 연결되는 지점이 있으면 그걸 실마리로 "
        "이으세요(콜백: '아까 …라고 하셨는데'). 단 **응답자가 실제로 한 말만** 가져오고, "
        "없으면 억지로 만들지 마세요.\n\n"
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

    text = (respondent_text or "").strip()

    # 0) 무의미 발화는 턴으로 치지 않는다 — 저장 전에 판정한다.
    #    아무것도 저장하지 않고 되묻기만 한다: 잡음이 전사에 남지 않고, asked 예산도 안 깎이고,
    #    커버리지도 그대로다. 대화 상태를 건드리지 않으니 그냥 '한 번 더 물은' 셈이 된다.
    #    text 가 비어 있는 건 오프닝 요청 신호(public.turn 첫 호출)라 여기서 걸러선 안 된다.
    if text and is_non_answer(text):
        prev = next(
            (t for t in reversed(store.list_turns(project_id, sid)) if t.role == "moderator"),
            None,
        )
        if prev and prev.text:
            log.info("무의미 발화 — 되묻는다 (session=%s): %r", sid, text[:40])
            message = f"앗, 잘 못 들었어요. 다시 여쭤볼게요. {_question_part(prev.text)}"
            # 저장하지 않는 임시 턴이다. 호출자는 플래그만 읽는다.
            return message, False, None, Turn(
                role="moderator", text=message, question_id=prev.question_id
            )
        # 되물을 직전 질문이 없으면(첫 턴 등) 평소 경로로 흘려보낸다.

    # 1) 응답자 발화 — 저장 전에 마스킹한다(PRD 9절). 마스킹된 텍스트로 이후 전부 진행.
    #    감정 태깅은 질문 생성과 병렬로 돌린다 — 생성 프롬프트는 감정 라벨을 쓰지 않고
    #    (텍스트만 쓴다), 라벨은 저장·응답에만 필요하다. 직렬이던 시절 태깅(~0.5s)이
    #    턴 지연에 그대로 더해졌다(2026-07-23 RNGD 실측: 턴 p50 4.5s 중 0.4~0.6s).
    executor: cf.ThreadPoolExecutor | None = None
    emotion_future: cf.Future | None = None
    masked = ""
    pii_types: list[str] = []
    if text:
        pii_types = scan_pii(text)
        masked = mask_pii(text)
        executor = cf.ThreadPoolExecutor(max_workers=1)
        emotion_future = executor.submit(tag_emotion, masked)

    def _save_respondent() -> Turn | None:
        """감정 태깅 완료를 기다렸다가 응답자 턴을 저장한다. 생성 성공/실패 양쪽에서 쓴다."""
        if not text:
            return None
        emotion, conf = emotion_future.result()   # tag_emotion 은 실패를 내부에서 흡수한다("중립", 0.0)
        return store.add_turn(
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

    # 2) 대화이력 — 아직 저장 전이므로 방금 발화를 메모리에서 이어붙인다.
    #    (프롬프트는 role·text·is_probe 만 읽는다. asked 는 진행자 턴 수라 응답자 턴과 무관.)
    history = store.list_turns(project_id, sid)
    if text:
        history = history + [Turn(role="respondent", text=masked, pii_types=pii_types)]
    asked = sum(1 for t in history if t.role == "moderator")

    # 3) 다음 발화 생성 — 감정 태깅과 동시에 진행된다.
    try:
        out, _ = get_llm().structured(
            interview_moderator_system(lang),
            _moderator_user(guide, history, asked, session.covered),
            _ModeratorOut,
            max_tokens=500,
        )
    except LLMError as e:
        log.exception("모더레이터 생성 실패: %s", e)
        _save_respondent()   # 구버전과 동일하게, 생성이 실패해도 응답자 발화는 전사에 남긴다
        raise
    finally:
        if executor:
            executor.shutdown(wait=False)

    respondent_turn = _save_respondent()

    message = (out.message or "").strip()
    done = bool(out.done)

    # 프로빙 종류는 아직 저장하지 않는다(컬럼 없음) — 로그로만 관찰한다. 래더링이 실제로
    # '심화'까지 내려가는지, 아니면 '구체화'에서만 맴도는지 여기서 드러난다.
    if out.is_probe and out.probe_type:
        log.info("프로빙 (session=%s, 종류=%s)", sid, out.probe_type)

    # 안전장치 — 모델이 종료를 안 내도 무한 인터뷰는 막는다.
    if asked + 1 >= _max_asked(guide):
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
        # 진행자가 마무리했다고 '응답 1건'이 되는 게 아니다. 응답자가 제출해야 completed 로
        # 넘어간다(public.submit). ended_at 도 그때 찍는다 — 여기서 찍으면 제출 안 한 세션에
        # 종료시각이 남아 완료된 것처럼 보인다.
        patch["status"] = "pending"
    store.update_session(project_id, sid, patch)
    session.covered = covered
    session.asked = asked + 1

    return message, done, respondent_turn, moderator_turn
