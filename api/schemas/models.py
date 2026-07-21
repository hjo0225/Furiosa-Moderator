"""도메인 스키마 — 아키텍처 §7 데이터 모델.

Project / InterviewGuide / Session / Turn / Insight / Respondent.
응답자는 익명 ID 로만 관리하고 PII 는 저장 전에 마스킹한다(PRD 9절).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _now() -> datetime:
    return datetime.now(timezone.utc)


_DISCORD_WEBHOOK_PREFIXES = (
    "https://discord.com/api/webhooks/",
    "https://discordapp.com/api/webhooks/",
)


def _validate_webhook_url(v: str) -> str:
    """빈 문자열(해제) 또는 Discord 웹훅 URL 만 허용한다 (SSRF 차단)."""
    v = (v or "").strip()
    if v and not v.startswith(_DISCORD_WEBHOOK_PREFIXES):
        raise ValueError("Discord 웹훅 URL 이어야 합니다 (https://discord.com/api/webhooks/...).")
    return v


# --- 의뢰자 -----------------------------------------------------------------

ProjectStatus = Literal["draft", "deployed", "closed"]


class GuideQuestion(BaseModel):
    id: str
    text: str
    goal: str = ""          # 이 문항으로 알아내려는 것 (M-1 커버리지 판정에 쓰인다)
    order: int = 0


class InterviewGuide(BaseModel):
    project_id: str = ""
    goal: str = ""          # 조사 전체 목표
    questions: list[GuideQuestion] = Field(default_factory=list)
    # STT 어휘 힌트. 이 조사에서 나올 법한 고유명사·전문용어를 담는다.
    # 조사 주제를 아는 건 우리뿐이고 STT 는 모른다 — 실측으로 '배달팁'이 '배달 TV'로
    # 나오던 게 이 힌트만으로 정확히 잡혔다(WER 46% → 8%).
    vocabulary: list[str] = Field(default_factory=list)
    version: int = 1
    updated_at: datetime = Field(default_factory=_now)


class Project(BaseModel):
    id: str = ""
    owner: str = "anonymous"     # MVP 무인증 — 링크 소유 기반
    title: str = ""
    topic: str
    target: str = ""             # 대상 조건
    material_text: str = ""      # 조사 참고 자료 원문 (협업자 기능)
    discord_webhook_url: str = Field(default="", exclude=True)  # 응답 노출 금지(시크릿). 저장·라우팅엔 사용.
    status: ProjectStatus = "draft"
    created_at: datetime = Field(default_factory=_now)
    session_count: int = 0
    completed_count: int = 0


class ProjectCreateIn(BaseModel):
    topic: str
    title: str = ""
    target: str = ""
    discord_webhook_url: str = ""

    @field_validator("discord_webhook_url")
    @classmethod
    def _v_webhook(cls, v: str) -> str:
        return _validate_webhook_url(v)


class WebhookSetIn(BaseModel):
    """프로젝트별 Discord 웹훅 설정/해제(빈 문자열이면 기본 채널로 폴백)."""
    discord_webhook_url: str = ""

    @field_validator("discord_webhook_url")
    @classmethod
    def _v_webhook(cls, v: str) -> str:
        return _validate_webhook_url(v)


class GuideGenerateIn(BaseModel):
    """가이드 재생성 요청 — 비우면 프로젝트의 주제·대상을 그대로 쓴다."""
    topic: str = ""
    target: str = ""


# --- 응답자 -----------------------------------------------------------------

# 세션 수명주기:
#   consented — 동의만 누르고 아직 한 마디도 안 함
#   active    — 대화 중
#   pending   — 진행자가 마무리했고 응답자의 '제출'을 기다리는 중
#   completed — 제출 완료. **이것만 '응답 1건'으로 센다**
#   abandoned — 이탈. 오래 방치된 미제출 세션을 스윕해서 떨군다
#
# completed 를 제출 시점으로 미룬 이유: 진행자가 done 을 냈다고 응답자가 끝낸 게 아니다.
# 예전엔 동의 클릭만으로도 '응답 1건'이 잡혀서 대시보드 숫자가 인사이트 모수와 어긋났다.
SessionStatus = Literal["consented", "active", "pending", "completed", "abandoned"]


class ConsentLog(BaseModel):
    """동의 로그 (R-1) — 개인식별정보는 담지 않는다."""
    agreed: bool
    purpose_version: str = "v1"
    at: datetime = Field(default_factory=_now)
    user_agent_hash: str = ""    # 원문 UA 가 아니라 해시만


class Session(BaseModel):
    id: str = ""
    project_id: str
    respondent_id: str = ""      # 익명 ID
    status: SessionStatus = "consented"
    started_at: datetime = Field(default_factory=_now)
    ended_at: datetime | None = None
    asked: int = 0               # 진행자 질문 수
    summary: str = ""
    covered: list[str] = Field(default_factory=list)  # 커버한 guide question id


class SessionStartIn(BaseModel):
    # project_id 는 경로에서 온다. 본문에 있으면 받아만 두고 경로 값을 신뢰한다.
    project_id: str = ""
    agreed: bool = False
    user_agent: str = ""


class Turn(BaseModel):
    id: str = ""
    session_id: str = ""
    role: Literal["moderator", "respondent"]
    text: str                    # 저장 시점에 이미 마스킹된 텍스트
    emotion: str = ""            # M-3 톤·감정 라벨
    emotion_confidence: float = 0.0
    is_probe: bool = False       # 꼬리질문 여부
    question_id: str = ""        # 대응하는 guide question
    pii_types: list[str] = Field(default_factory=list)  # 무엇이 마스킹됐는지(원문 아님)
    guardrail_rewritten: bool = False
    created_at: datetime = Field(default_factory=_now)


class TurnIn(BaseModel):
    """응답자 발화 → 다음 진행자 발화 요청."""
    # session_id 는 경로에서 온다. 본문 값은 신뢰하지 않는다.
    session_id: str = ""
    text: str = ""               # 텍스트 입력 또는 STT 결과
    lang: str = "ko"


class TurnOut(BaseModel):
    message: str                 # 진행자의 다음 한 마디
    done: bool = False
    asked: int = 0
    is_probe: bool = False
    guardrail_rewritten: bool = False
    emotion: str = ""


# --- 집계 -------------------------------------------------------------------

class ThemeInsight(BaseModel):
    theme: str
    summary: str
    quotes: list[str] = Field(default_factory=list)
    # 이 주제를 가리키는 짧은 검색어들. LLM 이 '어휘'를 주고 '세는 일'은 DB 가 한다.
    # theme 명 자체로 전사를 검색하면 서술형이라("배달비 및 할인 제도에 대한 불만족")
    # 절대 매칭되지 않아 카운트가 전부 0 이 된다.
    keywords: list[str] = Field(default_factory=list)
    mention_count: int = 0


class Insight(BaseModel):
    project_id: str = ""
    overall: str = ""
    themes: list[ThemeInsight] = Field(default_factory=list)
    sentiment: dict[str, int] = Field(default_factory=dict)
    session_count: int = 0
    generated_at: datetime = Field(default_factory=_now)
