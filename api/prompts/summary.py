"""문항별 AI 요약 프롬프트 — 기존 backend `views/surveys/summary.py` 의
question/answer 프롬프트 빌더 이식. SSE 스트리밍 대신 단일 요청/응답으로 단순화.
"""

QUESTION_SUMMARY_SYSTEM = """
너는 설문 응답 분석 전문가다. 한 문항에 대한 응답 목록을 받아,
사용자의 요약 요청에 따라 핵심 경향과 시사점을 한국어로 정리한다.

원칙:
- 제공된 응답에 없는 내용은 만들어내지 않는다.
- 빈도/경향 등 정량적 표현은 응답 목록에서 직접 확인 가능한 범위로만 서술한다.
- markdown 으로 작성하고, 강조할 부분은 bold 처리한다.
- 요약 → 주요 패턴 → 시사점 순으로 간결하게 구성한다.
""".strip()

DEFAULT_SUMMARY_PROMPT = "이 문항의 응답을 요약하고 시사점을 정리해주세요."


def question_block(title: str, type_: str) -> str:
    type_label = "객관식" if type_ == "choice" else "주관식"
    return f"다음은 문항의 내용 입니다.\n제목 : {title}\n응답 방법 : {type_label}"


def answers_block(answers: list[str]) -> str:
    lines = ["다음은 답변의 목록입니다."]
    for index, answer in enumerate(answers, 1):
        lines.append(f"{index}. {answer}")
    if len(answers) == 0:
        lines.append("(아직 응답이 없습니다)")
    return "\n".join(lines)


def summary_user(
    title: str,
    type_: str,
    answers: list[str],
    request_prompt: str,
    respondents: int | None = None,
    allow_multiple: bool = False,
) -> str:
    """복수응답이면 **응답자 수와 선택 건수를 숫자로 주입**한다(T-MULTI-CONSISTENCY).

    안 넣으면 LLM 이 "나열된 4개 = 4명"으로 오추정한다(실제로는 3명이 4개를 고른 것).
    일반 지침으로 추론시키지 않고 grounding 한다.
    """
    counts = ""
    if allow_multiple and respondents is not None:
        counts = (
            f"\n\n이 문항은 **복수응답**이 가능합니다. 응답자 수: {respondents}명, "
            f"총 선택 건수: {len(answers)}건 (한 응답자가 여러 개를 고를 수 있습니다). "
            "비율은 응답자 수를 분모로 삼으세요 — 합계가 100%를 넘을 수 있습니다."
        )
    return (
        f"{question_block(title, type_)}{counts}\n\n"
        f"{answers_block(answers)}\n\n"
        f"요약 요청: {request_prompt or DEFAULT_SUMMARY_PROMPT}"
    )
