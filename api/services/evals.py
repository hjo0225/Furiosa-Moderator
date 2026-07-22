"""품질 Evals (F8) — 결정론적·오프라인 가이드 품질 측정.

CI 는 NPU LLM 을 호출할 수 없다. 그래서 이 모듈은 **LLM 없이** 순수 규칙으로만
가이드 생성 품질(유도신문·버킷 MECE)과 지식 누출(knowledge-leak) 정도를 점수/플래그로
낸다. 목적은 pytest 로 회귀를 막고, generate_guide 가 매 생성마다 비차단으로 자기평가를
남기게 하는 것이다(라우터의 log.warning).

설계 판단 — 보수적 휴리스틱:
  오탐(false positive)이 가이드 생성을 막지도, 응답자 인터뷰를 바꾸지도 않는다(로그 전용).
  그래서 여기 규칙은 '명백한' 신호만 잡도록 보수적으로 짠다 — 애매한 판정은 라이브 LLM
  하니스(아래)의 몫이지 저장·생성 경로에 넣을 게 아니다.

범위 밖(별도 오프라인 하니스로 이관):
  실제 전사(transcript)에 대한 분류 일치도(κ)·실측 누출률, 골드셋 대비 유도신문 재현율 등
  '라이브 LLM 평가'는 NPU 를 실제로 태워야 하므로 CI(이 모듈)가 아니라 별도 하니스에서 돈다.
  이 파일은 그 하니스가 재사용할 수 있는 순수 측정 함수만 제공한다.
"""
from __future__ import annotations

import re
import string
from typing import Any

# --- 토큰화 (한국어 친화, 결정론) -------------------------------------------
# 한국어는 형태소 분석 없이도 공백 토큰 + 양끝 구두점 제거만으로 n-gram 겹침 측정에
# 충분히 쓸 만하다. 외부 사전·모델을 붙이지 않는 게 CI 오프라인 제약과도 맞는다.
_STRIP = string.punctuation + "…·「」『』（）【】《》，。！？、；：〈〉“”‘’―–—•ㆍ"


def _tokenize(text: str) -> list[str]:
    """공백으로 나누고 양끝 구두점을 벗겨 소문자화한 토큰 목록."""
    if not text:
        return []
    out: list[str] = []
    for raw in str(text).split():
        tok = raw.strip(_STRIP)
        if tok:
            out.append(tok.lower())
    return out


def _ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    if n <= 0 or len(tokens) < n:
        return []
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _get(obj: Any, key: str, default: Any = "") -> Any:
    """pydantic 모델과 dict 를 함께 받기 위한 얇은 접근자."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


# --- F2.3.6 유도신문 검출 ---------------------------------------------------
# 세 갈래를 잡는다(전부 '명백'한 것만):
#   1) 감정 전제: '얼마나 <감정어>' — 감정을 질문이 이미 단정하고 그 '정도'만 묻는 형태.
#      ("얼마나 불편/좋/힘드/만족스러우셨나요")
#   2) 확인 유도 어미: '…죠?', '…잖아요?', '…않나요?' 류 — 동의를 끌어내는 부가/종결.
#   3) 다중질문(double-barreled): '그리고/또는/또'로 두 질문을 묶거나 물음표가 2개 이상.
# PRD 중립 예('그때 어떠셨나요?', '배송 과정은 어떠셨나요?')는 걸리지 않아야 하고,
# 나쁜 예('배송이 느려서 불편하셨죠?')는 걸려야 한다 → 어미는 '않나요'처럼 '않'을 요구해
# 중립형 '…나요?'/'…세요?'와 구분한다.
_VALENCE = (
    r"(?:불편|불만|힘드|힘들|괴로|싫|나쁘|짜증|실망|후회|아쉽|아쉬|"
    r"좋|만족|편리|편(?=하)|행복|즐거|뿌듯|감동|훌륭)"
)
_VALENCE_DEGREE = re.compile(r"얼마나\s*(?:나\s*|이나\s*)?" + _VALENCE)

# '않'을 동반한 확인 유도만 잡아 중립 종결어미('나요?','세요?')를 오탐하지 않는다.
_TAG_CLOSE = re.compile(
    r"(?:죠|지요|잖아요|잖아|않나요|않으세요|않으신가요|않습니까|"
    r"아니(?:세요|신가요|에요|야)|맞죠|맞지요|맞잖아)\s*[?？]"
)

# 두 질문을 접속사로 묶은 형태. '또'는 '또한/또렷/또는' 오탐을 피해 한글 경계를 요구한다
# (단 '또는'은 별도 분기로 잡는다).
_DOUBLE_CONJ = re.compile(r"그리고|또는|(?<![가-힣])또(?![가-힣])")


def is_leading_question(text: str) -> tuple[bool, str]:
    """유도·편향 질문 플래그 (F2.3.6).

    반환: (유도인가, 사유). 유도가 아니면 (False, "").
    로그·리포트 전용이라 오탐이 생성을 막지 않는다 — 명백한 신호만 보수적으로 잡는다.
    """
    q = (text or "").strip()
    if not q:
        return False, ""

    # double-barreled: 물음표 2개 이상은 '문항당 물음표 1개' 규칙 위반이자 두 질문 결합 신호.
    if q.count("?") + q.count("？") >= 2:
        return True, "다중 질문(물음표 2개 이상)"
    if _DOUBLE_CONJ.search(q):
        return True, "다중 질문(접속사로 두 질문 결합)"

    # 감정 전제: 정도를 묻는 유도.
    if _VALENCE_DEGREE.search(q):
        return True, "감정 전제(정도를 묻는 유도)"

    # 확인 유도 어미.
    if _TAG_CLOSE.search(q):
        return True, "확인 유도 어미"

    return False, ""


# --- F2.3.1 버킷 MECE 겹침 경고 ---------------------------------------------
def _norm_label(s: str) -> str:
    """라벨 정규화 — 공백 제거 + 소문자화. '배송 지연'과 '배송지연'을 같게 본다."""
    return "".join(str(s).split()).lower()


def bucket_overlap_warnings(buckets: list) -> list[str]:
    """MECE(상호배타·포괄) 위반 의심 쌍을 사람이 읽을 경고 문자열로 (F2.3.1).

    - 캐치올('기타')은 원래 겹치는 개념이므로 겹침 판정에서 제외한다.
    - 두 버킷의 라벨이 정규화 후 동일하거나, (라벨+정의) 토큰집합의 Jaccard 가 0.6 이상이면
      겹침으로 본다.
    ResponseBucket 객체와 dict 를 모두 받는다. 빈 리스트면 깨끗하다는 뜻.
    """
    items: list[tuple[str, set]] = []
    for b in buckets or []:
        if _get(b, "is_catchall", False):
            continue
        label = str(_get(b, "label", "") or "").strip()
        if not label:
            continue
        definition = str(_get(b, "definition", "") or "")
        tokens = set(_tokenize(label + " " + definition))
        items.append((label, tokens))

    warnings: list[str] = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (la, ta), (lb, tb) = items[i], items[j]
            if _norm_label(la) and _norm_label(la) == _norm_label(lb):
                warnings.append(
                    f"버킷 '{la}' 와(과) '{lb}' 의 라벨이 사실상 동일합니다 (MECE 위반 의심)."
                )
                continue
            jac = _jaccard(ta, tb)
            if jac >= 0.6:
                warnings.append(
                    f"버킷 '{la}' 와(과) '{lb}' 의 의미가 크게 겹칩니다 "
                    f"(Jaccard={jac:.2f}, MECE 위반 의심)."
                )
    return warnings


# --- F1.5.9 지식 누출 측정 ---------------------------------------------------
def leak_overlap(utterance: str, sources: list[str]) -> float:
    """발화가 출처(지식팩) 표현을 얼마나 그대로 옮겼는지 0..1 로 (F1.5.9).

    발화의 content n-gram(3-gram, 짧으면 2/1-gram 폴백) 중 출처의 같은 n-gram 집합에도
    나타나는 비율. 발화나 출처가 비면 0.0. '진행자가 팩 문장을 통째로 읊는' 누출을 잡되,
    단어 한둘 우연히 겹치는 것은 3-gram 이라 걸러진다.
    """
    utt_tokens = _tokenize(utterance)
    src_tokens = _tokenize(" ".join(s for s in (sources or []) if s))
    if not utt_tokens or not src_tokens:
        return 0.0

    # 짧은 발화는 3-gram 이 안 나오므로 2→1 로 폴백한다(그래도 못 만들면 0).
    n = 3 if len(utt_tokens) >= 3 else (2 if len(utt_tokens) >= 2 else 1)
    utt_grams = _ngrams(utt_tokens, n)
    if not utt_grams:
        return 0.0
    src_grams = set(_ngrams(src_tokens, n))
    hits = sum(1 for g in utt_grams if g in src_grams)
    return hits / len(utt_grams)


# --- 리포트 집계 ------------------------------------------------------------
def guide_quality_report(guide) -> dict:
    """InterviewGuide(또는 dict) 전체에 위 검사를 돌려 요약 dict 를 낸다.

    반환:
      leading:         유도로 플래그된 질문 id 목록
      bucket_warnings: {질문 id: [경고, …]} (겹침 있는 질문만)
      n_questions / n_leading: 개수
      mece_ok:         버킷 겹침 경고가 하나도 없으면 True
    pydantic 모델과 dict 형태 가이드를 모두 받는다.
    """
    questions = _get(guide, "questions", []) or []
    leading: list[str] = []
    bucket_warnings: dict[str, list[str]] = {}
    for q in questions:
        qid = str(_get(q, "id", "") or "")
        is_lead, _reason = is_leading_question(str(_get(q, "text", "") or ""))
        if is_lead:
            leading.append(qid)
        warns = bucket_overlap_warnings(_get(q, "response_buckets", []) or [])
        if warns:
            bucket_warnings[qid] = warns
    return {
        "leading": leading,
        "bucket_warnings": bucket_warnings,
        "n_questions": len(questions),
        "n_leading": len(leading),
        "mece_ok": not bucket_warnings,
    }
