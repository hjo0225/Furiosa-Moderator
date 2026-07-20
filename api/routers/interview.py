"""인터뷰 엔드포인트 2개.

발췌 출처: mindlens_solution/apps/api/routers/survey.py L2080-2134
원본은 3198줄짜리 거대 라우터. 인터뷰 함수 2개만 떼어내고 아래 2가지만 손댐:

  1. `Depends(get_current_user)` (Firebase 인증) 제거 — 새 프로젝트는 링크 접속형 무인증.
     ※ 무인증이면 LLM 호출이 그대로 외부에 열린다. 배포 전 rate limit / 세션 토큰 필수.
  2. `get_settings().panel_model` → `settings.model` 로 이름만 변경 (Furiosa 서빙 모델명).

프롬프트/구조화출력 호출부 로직은 원본 그대로 유지했다.
"""

from fastapi import APIRouter, HTTPException

from ..prompts.interview_followup import (
    interview_followup_system,
    interview_followup_user,
)
from ..prompts.interview_moderator import (
    interview_moderator_system,
    interview_moderator_user,
)
from ..schemas.interview import (
    InterviewFollowupIn,
    InterviewFollowupOut,
    InterviewTurnIn,
    InterviewTurnOut,
)
from ..services.llm_client import get_llm

router = APIRouter(prefix="/interview", tags=["interview"])


@router.post("/turn", response_model=InterviewTurnOut)
def interview_turn(body: InterviewTurnIn) -> InterviewTurnOut:
    """조사 목표 + 대화이력으로 진행자의 다음 한 마디 + 종료 여부."""
    history = [t.model_dump() for t in body.history]
    try:
        res, _ = get_llm().structured(
            interview_moderator_system(body.lang),
            interview_moderator_user(body.goal, history, body.asked, body.lang),
            InterviewTurnOut,
            max_tokens=300,
        )
        return res
    except Exception as exc:  # noqa: BLE001 — LLM 실패는 503
        raise HTTPException(status_code=503, detail="인터뷰 진행에 실패했어요.") from exc


@router.post("/followup", response_model=InterviewFollowupOut)
def interview_followup(body: InterviewFollowupIn) -> InterviewFollowupOut:
    """직전 질문+답변으로 후속질문 1개."""
    try:
        res, _ = get_llm().structured(
            interview_followup_system(body.lang),
            interview_followup_user(body.question, body.answer, body.lang),
            InterviewFollowupOut,
            max_tokens=300,
        )
        return res
    except Exception as exc:  # noqa: BLE001 — LLM 실패는 503 으로 표준화
        raise HTTPException(status_code=503, detail="후속질문 생성에 실패했어요.") from exc
