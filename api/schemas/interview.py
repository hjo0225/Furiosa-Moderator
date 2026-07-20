"""인터뷰 모드 스키마.

발췌 출처: mindlens_solution/apps/api/schemas/survey.py
  - TranscriptTurn         L397-399
  - InterviewFollowupIn/Out L663-675
  - InterviewTurnIn/Out     L677-690
원본은 700줄 넘는 설문 스키마 파일이라 인터뷰 관련 4개만 떼어냄. 로직 변경 없음.
"""

from pydantic import BaseModel, Field


class TranscriptTurn(BaseModel):
    role: str  # moderator | respondent
    text: str


class InterviewFollowupIn(BaseModel):
    """인터뷰 모드 — 직전 질문 + 응답자 답변으로 후속질문 1개 생성 입력."""

    question: str = ""
    answer: str
    lang: str = "ko"  # 응답 언어(ko|en) — en 이면 AI 후속질문도 영어로


class InterviewFollowupOut(BaseModel):
    """생성된 후속질문(주관식·짧게)."""

    followup: str


class InterviewTurnIn(BaseModel):
    """인터뷰 모드(모더레이터 주도) — 조사 목표 + 대화이력 → 다음 진행자 발화."""

    goal: str = ""
    history: list[TranscriptTurn] = Field(default_factory=list)
    asked: int = 0  # 지금까지 진행자가 던진 질문 수(종료 판단 보조)
    lang: str = "ko"  # 응답 언어(ko|en) — en 이면 진행자 발화도 영어로


class InterviewTurnOut(BaseModel):
    """진행자의 다음 한 마디 + 인터뷰 종료 여부."""

    message: str
    done: bool = False
