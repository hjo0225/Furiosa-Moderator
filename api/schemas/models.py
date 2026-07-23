"""도메인 스키마 — 아키텍처 §7 데이터 모델.

Project / InterviewGuide / Session / Turn / Insight / Respondent.
응답자는 익명 ID 로만 관리하고 PII 는 저장 전에 마스킹한다(PRD 9절).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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

Angle = Literal["현상", "원인", "활용"]


class Material(BaseModel):
    id: str = ""
    project_id: str = ""
    source: Literal["upload", "web"]
    angle: Angle
    url: str = ""            # web 만
    title: str = ""          # web=페이지 제목, upload=파일명
    text: str = ""           # 본문 verbatim
    created_at: datetime = Field(default_factory=_now)


class WebCandidate(BaseModel):
    angle: Angle
    title: str = ""
    url: str


class WebSelectIn(BaseModel):
    selected: list[WebCandidate] = Field(default_factory=list)


class ResponseBucket(BaseModel):
    """질문별 응답 분류 카테고리(코드북)이자 프로빙 목표 (PRD F2.3).

    id/분포 카운트는 서버가 채운다 — LLM 은 label/definition 만 만든다(계약 1).
    """
    id: str = ""
    label: str
    definition: str = ""              # 1문장 정의. 생성 스키마에서 필수로 승격됨(F2.3.2)
    is_catchall: bool = False         # '기타' 버킷 (F2.3.3)
    is_negative_case: bool = False    # '불편 없음' 류 (F2.3.4)


class Stimulus(BaseModel):
    """질문에 붙는 제시 자료(시안·광고·컨셉) — 이미지/영상 (PRD v2.0 자극물).

    url 이 빈 자극물은 '없음'과 같다 — 의뢰자가 캡션만 남기고 URL 을 비운 채 저장한 경우
    응답자에게 빈 액자를 띄우지 않도록 라우터가 걸러 내려보내지 않는다(public._question_stimulus).
    가이드 문항에 얹히므로 별도 테이블·마이그레이션 없이 guides.questions(JSONB)에 함께 저장된다.
    """
    type: Literal["image", "video"] = "image"
    url: str = ""
    caption: str = ""


class GuideQuestion(BaseModel):
    id: str
    text: str
    goal: str = ""          # 이 문항으로 알아내려는 것 (M-1 커버리지 판정에 쓰인다)
    order: int = 0
    response_buckets: list[ResponseBucket] = Field(default_factory=list)
    # 이 문항을 다룰 때 응답자 화면에 함께 띄울 제시 자료(선택). 없으면 None — 기본 단일 컬럼.
    stimulus: Stimulus | None = None


class GuideTopic(BaseModel):
    """주제 — 질문 여러 개를 묶는 단위 (스펙 `docs/specs/2026-07-24-guide-topics-turn-budget.md`).

    **턴 예산이 이 단위로 잡힌다: 주제당 질문수 + 1.** `+1` 은 꼬리질문 몫이다 —
    질문마다 최소 1턴을 써야 그 질문의 버킷이 채워지므로 질문 수만큼은 반드시 확보하고
    남는 1턴을 진행자가 주제 안 어디에든 쓴다.

    버킷은 주제가 아니라 **질문**에 붙는다. 코드북·프로빙 목표가 질문 단위로 동작하고
    분류 결과가 `turns.bucket_id` 에 질문 기준으로 쌓이기 때문이다(reflect_bucket).
    """
    id: str = ""
    title: str = ""
    goal: str = ""          # 이 주제로 알아내려는 것
    order: int = 0
    questions: list[GuideQuestion] = Field(default_factory=list)


class InterviewGuide(BaseModel):
    """가이드 — 주제 > 질문 2단.

    `topics` 가 정본이고 `questions` 는 **거기서 파생된 평면 뷰**다. 진행자·인사이트·알림이
    전부 평면 뷰를 읽고 있어서 그대로 남겼다 — 소비처를 한꺼번에 뜯지 않기 위한 의도적 이중화다.
    둘의 동기화는 `_sync_topics_questions` 가 책임진다(직접 대입하지 말 것).

    **구형 가이드 호환:** `questions` 만 주고 `topics` 를 비우면 주제 1개("전체")로 감싼다.
    운영 DB 에 이미 평면으로 저장된 가이드들이 이 경로로 그대로 동작한다.
    """
    project_id: str = ""
    goal: str = ""          # 조사 전체 목표
    topics: list[GuideTopic] = Field(default_factory=list)
    questions: list[GuideQuestion] = Field(default_factory=list)
    # STT 어휘 힌트. 이 조사에서 나올 법한 고유명사·전문용어를 담는다.
    # 조사 주제를 아는 건 우리뿐이고 STT 는 모른다 — 실측으로 '배달팁'이 '배달 TV'로
    # 나오던 게 이 힌트만으로 정확히 잡혔다(WER 46% → 8%).
    vocabulary: list[str] = Field(default_factory=list)
    version: int = 1
    updated_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def _sync_topics_questions(self) -> InterviewGuide:
        """topics ↔ questions 를 한 방향으로 맞춘다 — topics 가 정본."""
        if self.topics:
            self.questions = [q for t in self.topics for q in t.questions]
        elif self.questions:
            # 구형(평면) 가이드 — 주제 1개로 감싼다. 운영 DB 마이그레이션 없이 읽기로만 처리.
            self.topics = [GuideTopic(id="t1", title="전체", goal=self.goal,
                                      order=0, questions=self.questions)]
        return self

    @property
    def max_turns(self) -> int:
        """이 가이드로 인터뷰가 쓸 수 있는 최대 턴 — 주제별 예산의 합.

        전체 상한이라는 별도 상수는 두지 않는다(구 `MAX_ASKED = 12` 폐기). 총량은 주제 구성의
        결과로 자연히 결정되고, 의뢰자는 가이드 화면에서 이 수를 실시간으로 본다.
        """
        return sum(len(t.questions) + 1 for t in self.topics)


class ScreenerQuestion(BaseModel):
    """참가 조건 문항 (F4.3) — 의뢰자가 정의하는 단일선택 자격 질문.

    pass_options 는 '통과(적격)'로 치는 선택지들이다. 응답자에게 내려줄 때는
    반드시 벗겨낸다(public.py) — 어느 답이 통과인지 알면 스크리너가 무력화된다.
    """
    id: str = ""
    text: str
    options: list[str] = Field(default_factory=list)
    pass_options: list[str] = Field(default_factory=list)


class Project(BaseModel):
    id: str = ""
    owner: str = "anonymous"     # MVP 무인증 — 링크 소유 기반
    title: str = ""
    topic: str                   # 조사 목적 (UI 라벨: 조사 목적)
    target: str = ""             # 타깃 대상
    motivation: str = ""         # 조사 동기
    utilization: str = ""        # 활용 방안
    material_text: str = ""      # 의뢰자 업로드 자료 (가이드 생성 프롬프트 주입용)
    discord_webhook_url: str = Field(default="", exclude=True)  # 응답 노출 금지(시크릿). 저장·라우팅엔 사용.
    # 참가 조건 스크리너 (F4.3) — 동의 후·인터뷰 전 자격 판정. 비면 게이트 없음.
    screener: list[ScreenerQuestion] = Field(default_factory=list)
    # 지식팩 금칙어 (F1.5) — 진행자가 절대 먼저 꺼내면 안 되는 주제·표현. 비면 제약 없음.
    # 팩은 '읽기 전용·발화 금지'라, 이건 팩이 말해선 안 되는 것을 명시하는 두 번째 방어선이다.
    blocklist: list[str] = Field(default_factory=list)
    status: ProjectStatus = "draft"
    created_at: datetime = Field(default_factory=_now)
    session_count: int = 0
    completed_count: int = 0


class ProjectCreateIn(BaseModel):
    topic: str                   # 조사 목적
    title: str = ""
    target: str = ""             # 타깃 대상
    motivation: str = ""         # 조사 동기
    utilization: str = ""        # 활용 방안
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


class ScreenerSetIn(BaseModel):
    """참가 조건 스크리너 설정/해제 (F4.3). 빈 리스트면 게이트를 없앤다."""
    screener: list[ScreenerQuestion] = Field(default_factory=list)


class BlocklistSetIn(BaseModel):
    """지식팩 금칙어 설정/해제 (F1.5). 빈 리스트면 금칙어 제약을 없앤다."""
    blocklist: list[str] = Field(default_factory=list)


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


class ScreenIn(BaseModel):
    """스크리너 응답 (F4.3) — {문항 id: 선택한 옵션}. 판정은 서버가 pass_options 로 한다."""
    answers: dict[str, str] = Field(default_factory=dict)


class Turn(BaseModel):
    id: str = ""
    session_id: str = ""
    role: Literal["moderator", "respondent"]
    text: str                    # 저장 시점에 이미 마스킹된 텍스트
    emotion: str = ""            # M-3 톤·감정 라벨
    emotion_confidence: float = 0.0
    is_probe: bool = False       # 꼬리질문 여부
    question_id: str = ""        # 대응하는 guide question
    # F6.1 응답 버킷 분류 — 이 답변을 문항 코드북(response_buckets) 중 하나에 귀속.
    # LLM 은 '어느 버킷'만 고른다. 버킷별 N(분포)은 DB 실측이 센다(계약 1) — store.bucket_distribution.
    bucket_id: str = ""
    bucket_confidence: float = 0.0
    bucket_evidence: str = ""    # 그 분류의 근거가 된 답변 속 짧은 인용(원문)
    pii_types: list[str] = Field(default_factory=list)  # 무엇이 마스킹됐는지(원문 아님)
    guardrail_rewritten: bool = False
    created_at: datetime = Field(default_factory=_now)


class BucketAssignment(BaseModel):
    """응답 버킷 분류 결과 (F6.1) — LLM 구조화 출력.

    분류만 한다: 어느 버킷(bucket_id)인지 + 확신도 + 근거 인용. '개수 세기'는 하지 않는다.
    """
    bucket_id: str
    confidence: float = 0.0
    evidence: str = ""


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
    # 이번 진행자 발화가 다루는 문항의 제시 자료(있으면). url 이 빈 것은 서버가 None 으로 거른다.
    stimulus: Stimulus | None = None


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


class QuestionSummary(BaseModel):
    """문항별 AI 요약(F6.3) — 응답자 발언 기반 headline(핵심 발견) + 짧은 summary.

    버킷 분포(bucket_distribution, 계약 1: DB 실측)와 달리 이건 LLM '해석' 출력이다 —
    theme 요약과 같은 계열이라 세지 않고 지어내지 않으며 응답자 발언에만 근거한다.
    """
    question_id: str
    headline: str = ""
    summary: str = ""


class Insight(BaseModel):
    project_id: str = ""
    overall: str = ""
    themes: list[ThemeInsight] = Field(default_factory=list)
    sentiment: dict[str, int] = Field(default_factory=dict)
    # 문항별 응답 버킷 분포(F6.4) — {question_id: {bucket_id: N}}. sentiment 와 똑같이
    # LLM 이 아니라 DB 실측으로 채운다(계약 1). LLM 은 개별 답변을 버킷으로 '분류'만 한다.
    bucket_distribution: dict = Field(default_factory=dict)
    # 문항별 AI 요약(F6.3) — 문항마다 headline+summary. 버킷 분포가 '분류·개수'라면
    # 이건 '무엇을 말했나'의 서술 요약이다. theme 요약처럼 LLM 해석 출력(세지 않는다).
    question_summaries: list[QuestionSummary] = Field(default_factory=list)
    session_count: int = 0
    generated_at: datetime = Field(default_factory=_now)
