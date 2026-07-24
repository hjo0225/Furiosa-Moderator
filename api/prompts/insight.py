"""요약·집계 프롬프트 (M-4) + 감정 태깅 (M-3).

원본 prompts/summary.py 는 '문항별 답변 리스트'용이라 대화 전사에는 안 맞는다(PORTING.md).
여기는 대화 transcript 를 다룬다.

M-3 주의: 아키텍처 §4 는 감정을 '오디오 분류'로 잡는다고 돼 있지만, 우리는 텍스트에서
추정한다. 오디오 감정 분류기를 붙일 시간이 없어서다. 운율·톤이 아니라 어휘 기반이라
정확도가 낮다 — 라벨과 함께 confidence 를 받아 대시보드에서 낮은 건 흐리게 처리한다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..schemas.models import QuestionSummary

# --- 세션 요약 ---------------------------------------------------------------

SESSION_SUMMARY_SYSTEM = (
    "당신은 정성조사 분석가입니다. 1:1 인터뷰 전사를 읽고 요약합니다.\n"
    "규칙:\n"
    "- 응답자가 실제로 말한 것만 씁니다. 추측·일반화 금지.\n"
    "- 진행자의 질문이 아니라 응답자의 답에 집중하세요.\n"
    "- 3~5문장. 이 응답자만의 특징적인 지점이 드러나게."
)


def session_summary_user(goal: str, transcript: str) -> str:
    return (
        f"[조사 목표]\n{goal or '(미기재)'}\n\n"
        f"[인터뷰 전사]\n{transcript}\n\n"
        "위 인터뷰를 요약하세요."
    )


# --- 프로젝트 집계 ------------------------------------------------------------

INSIGHT_SYSTEM = (
    "당신은 정성조사 분석가입니다. 여러 응답자의 인터뷰 요약을 받아 주제별로 집계합니다.\n"
    "규칙:\n"
    "- overall 은 **반드시** 채우세요. 의뢰자가 가장 먼저 읽는 3~5문장 요약입니다. 비우지 마세요.\n"
    "- themes 는 3~6개. 여러 응답자에게서 반복되는 주제를 우선하세요.\n"
    "- theme 는 짧은 명사구로 (예: '배달비 부담', '리뷰 신뢰도'). 긴 서술문으로 쓰지 마세요.\n"
    "- 각 theme 의 keywords 에는 그 주제를 가리키는 **짧은 검색어 2~4개**를 넣으세요 "
    "(예: 배달비, 배송비, 수수료). 응답자가 실제로 쓸 법한 단어여야 합니다.\n"
    "- 각 theme 의 quotes 에는 응답자 발언을 **그대로** 1~3개 인용하세요. 지어내지 마세요.\n"
    "  · **같은 취지의 말을 여러 번 싣지 마세요.** 여러 응답자가 비슷하게 말했다면 가장 또렷한 "
    "한 마디만 남깁니다. 표현만 다르고 뜻이 같은 인용(예: '200원 이상 비싸면 망설인다'와 "
    "'200원 넘게 비싸면 구매를 망설임')은 중복입니다 — 몇 명이 그랬는지는 화면이 실측으로 셉니다.\n"
    "- mention_count 와 sentiment 는 서버가 실제 데이터로 계산합니다. 채우지 않아도 됩니다.\n"
    "- 근거 없는 수치·비율을 만들어내지 마세요."
)


def insight_user(topic: str, summaries: list[str]) -> str:
    block = "\n\n".join(f"[응답자 {i + 1}]\n{s}" for i, s in enumerate(summaries))
    return (
        f"[조사 주제] {topic}\n\n"
        f"[응답자별 요약] (총 {len(summaries)}명)\n{block}\n\n"
        "위 응답들을 주제별로 집계하세요."
    )


# --- 코드북 귀납 생성 (스펙 C) ------------------------------------------------

# 한 문항에 대한 여러 응답자의 실제 답변을 놓고, 거기서 **귀납적으로** 코드북(버킷)을 만든다.
# 가이드가 측정 전에 보기를 정하지 않는다 — 실제로 나온 답변의 결에 맞춰 카테고리를 세운다.
# 개수는 여기서 세지 않는다(계약 1): 버킷을 만든 뒤 분류·집계는 별도.
CODEBOOK_SYSTEM = (
    "당신은 정성조사 분석가입니다. 한 문항에 대한 여러 응답자의 실제 답변을 받아, "
    "그 답변들을 분류할 카테고리(코드북)를 **답변에서 귀납적으로** 도출합니다.\n"
    "규칙:\n"
    "- label(짧은 이름)과 definition(1문장 정의)을 가진 버킷을 **최대 6개까지만** 만드세요. "
    "3개 미만도, 6개 초과도 안 됩니다. **답변 하나마다 버킷을 만들지 마세요** — "
    "여러 답변을 아우르는 카테고리로 묶는 것이 목적입니다.\n"
    "- label 은 12자 이내, definition 은 한 문장(40자 이내)으로 짧게 쓰세요.\n"
    "- **실제 답변에 나타난 것만** 버킷으로 만드세요. 나오지 않은 카테고리를 미리 만들지 마세요.\n"
    "- 버킷은 상호배타적이고(MECE) 서로 결이 뚜렷이 달라야 합니다. 겹치면 합치세요.\n"
    "- 어디에도 잘 안 맞는 답변을 위해 is_catchall=true 인 '기타' 버킷 하나를 포함하세요.\n"
    "- id 는 비워 두세요(서버가 채웁니다). 개수·비율은 세지 마세요(서버가 셉니다)."
)

# 코드북 프롬프트에 넣을 답변 표본 상한. 응답이 늘어도 프롬프트가 같이 커지지 않게 한다.
_CODEBOOK_SAMPLE = 24
_CODEBOOK_ANSWER_CHARS = 200


def _codebook_sample(answers: list[str]) -> list[str]:
    """답변을 균등 간격으로 최대 _CODEBOOK_SAMPLE 개 뽑고 길이도 자른다(결정론).

    앞에서 N개를 자르면 먼저 응답한 사람들 쪽으로 코드북이 쏠린다 — 균등 간격으로
    훑어 전체 스펙트럼을 남긴다. 카테고리를 **귀납**하는 데엔 전수가 필요 없고,
    분류(bucket_classify)는 어차피 답변 하나하나를 개별로 다시 본다.
    """
    if len(answers) > _CODEBOOK_SAMPLE:
        step = len(answers) / _CODEBOOK_SAMPLE
        answers = [answers[int(i * step)] for i in range(_CODEBOOK_SAMPLE)]
    return [a[:_CODEBOOK_ANSWER_CHARS] for a in answers]


def codebook_user(question_text: str, goal: str, answers: list[str]) -> str:
    """코드북 생성 프롬프트. 답변은 표본·길이를 잘라 넣는다.

    전수를 그대로 넣었더니(라이브 34건) 모델이 답변마다 버킷을 하나씩 뽑아 출력이
    4096 토큰 상한에서도 잘렸다 — 재시도가 전체 재생성이라 문항 하나에 수 분이 걸리고
    q3 은 "Unterminated string" 으로 아예 실패했다. 입력을 줄이는 게 출력을 줄인다.
    """
    sample = _codebook_sample(answers)
    block = "\n".join(f"- {a}" for a in sample) or "(답변 없음)"
    scope = (f"(총 {len(answers)}개 중 {len(sample)}개 표본)"
             if len(sample) < len(answers) else f"(총 {len(answers)}개)")
    return (
        f"[문항]\n{question_text}\n\n"
        f"[이 문항으로 알아내려는 것]\n{goal or '(미기재)'}\n\n"
        f"[응답자들의 실제 답변] {scope}\n{block}\n\n"
        "위 답변들을 분류할 코드북을 만드세요. 버킷은 최대 6개, '기타' 포함."
    )


# --- 응답 버킷 분류 (F6.1) ----------------------------------------------------

# 개별 답변 하나를 그 문항의 코드북(response_buckets) 중 정확히 하나로 귀속시킨다.
# 여기서 '세지'는 않는다 — 버킷별 N(분포)은 DB 실측(store.bucket_distribution)이 센다(계약 1).
BUCKET_CLASSIFY_SYSTEM = (
    "당신은 정성조사 응답 분류기입니다. 응답자의 답변을 주어진 버킷(코드북) 중 "
    "하나만 고르세요 — 여러 개를 고르거나 새 버킷을 만들지 않습니다.\n"
    "규칙:\n"
    "- bucket_id 는 아래 제시된 버킷 id 중 하나여야 합니다. 목록에 없는 id 를 지어내지 마세요.\n"
    "- 어느 버킷에도 뚜렷이 맞지 않으면 '기타/캐치올' 버킷을 고르세요.\n"
    "- confidence 는 0.0~1.0. 근거가 약하거나 애매하면 낮게 주세요.\n"
    "- evidence 는 그렇게 분류한 근거가 되는 답변 속 짧은 인용입니다(원문 그대로). "
    "답변에 없는 말을 지어내지 마세요.\n"
    "- 당신은 '분류'만 합니다. 버킷별 개수는 서버가 셉니다(당신이 세지 않습니다)."
)


def bucket_classify_user(question_text: str, goal: str, buckets: list, answer: str) -> str:
    """분류 대상 문항·버킷 목록·답변을 제시. buckets 는 가이드의 response_buckets(dict 리스트)."""
    lines = []
    for b in buckets:
        bid = b.get("id", "")
        label = b.get("label", "")
        definition = b.get("definition", "")
        tags = []
        if b.get("is_catchall"):
            tags.append("기타/캐치올")
        if b.get("is_negative_case"):
            tags.append("부정형")
        tag = f" [{' · '.join(tags)}]" if tags else ""
        lines.append(f"- {bid}: {label}{tag}" + (f" — {definition}" if definition else ""))
    block = "\n".join(lines) or "(버킷 없음)"
    return (
        f"[문항]\n{question_text}\n\n"
        f"[이 문항으로 알아내려는 것]\n{goal or '(미기재)'}\n\n"
        f"[버킷 목록 — 이 중 하나의 id 를 고르세요]\n{block}\n\n"
        f"[응답자 답변]\n{answer}\n\n"
        "위 답변을 가장 잘 나타내는 버킷 하나의 id 를 bucket_id 에 넣고, "
        "confidence 와 근거 인용(evidence)을 채우세요."
    )


# --- 문항별 요약 (F6.3) -------------------------------------------------------

# 문항 하나에 여러 응답자가 답한 것을 모아, 그 문항에 대한 핵심 발견(headline)과 짧은
# 서술 요약(summary)을 만든다. 버킷 분포(F6.4)가 '분류·개수'라면 이건 '무엇을 말했나'다.
# theme 요약과 같은 계약: 세지 않고, 지어내지 않으며, 응답자 발언에만 근거한다.
QUESTION_SUMMARY_SYSTEM = (
    "당신은 정성조사 분석가입니다. 문항별로 여러 응답자의 답변을 받아 그 문항에 대한 "
    "핵심 발견을 요약합니다.\n"
    "규칙:\n"
    "- 각 문항마다 headline(핵심 발견 1문장)과 summary(2~4문장)를 만드세요.\n"
    "- 오직 실제 답변에 근거하세요. 답변에 없는 내용을 지어내지 마세요.\n"
    "- 근거 없는 수치·비율·인원수를 지어내지 마세요('70%가', '대부분' 같은 표현 주의). "
    "개수는 서버가 따로 셉니다.\n"
    "- 진행자의 질문이 아니라 응답자의 발언에 집중하세요 — 응답자 발언 중심으로 요약합니다.\n"
    "- question_id 는 입력에 주어진 값을 그대로 두세요. 새 문항을 만들지 마세요."
)


def question_summary_user(items: list[dict]) -> str:
    """문항별 요약 입력 — items 는 {question_id, question_text, answers:[str]} 리스트."""
    blocks = []
    for i, it in enumerate(items):
        qid = it.get("question_id", "")
        qtext = it.get("question_text", "")
        answers = it.get("answers") or []
        alist = "\n".join(f"- {a}" for a in answers) or "- (답변 없음)"
        blocks.append(
            f"[문항 {i + 1}] (question_id: {qid})\n{qtext}\n"
            f"[응답자 답변 {len(answers)}개]\n{alist}"
        )
    block = "\n\n".join(blocks)
    return (
        f"{block}\n\n"
        "각 문항마다 응답자 답변에 근거해 headline(1문장)과 summary(2~4문장)를 만드세요. "
        "question_id 는 그대로 두세요."
    )


class QuestionSummariesOut(BaseModel):
    """문항별 요약 배치 구조화 출력 — 문항 수만큼 QuestionSummary 를 담는다."""
    items: list[QuestionSummary] = Field(default_factory=list)


# --- 감정 태깅 (M-3) ----------------------------------------------------------

EMOTION_SYSTEM = (
    "응답자 발화의 감정을 분류합니다. label 은 긍정·중립·우려·불만·혼란 중 하나, "
    "confidence 는 0.0~1.0. 짧거나 단서가 없으면 중립에 낮은 confidence 를 주세요."
)


def emotion_user(text: str) -> str:
    return f"다음 발화의 감정을 분류하세요.\n\n발화: {text}"
