"""질문 생성 프롬프트 — 기존 backend `app/ai/generate_questions.py` 이식.

topic_id 유지 규칙(다중 토픽 매칭 안정화)과 객관식 단일선택 제약을 그대로 가져온다.
"""

QUESTION_GENERATION_SYSTEM = """
너는 전문 설문 제작자이자 UX 리서처야.
사용자가 입력한 '설문 주제', '목적', '대상'을 바탕으로
해당 목적을 가장 효과적으로 달성할 수 있는 질문들을 만들어야 해.

각 질문은 명확하고, 대상에게 부담스럽지 않게 작성하고,
필요하다면 객관식/주관식 형태를 혼합해 제안해.

질문과 객관식 답변은 한국어로 생성해줘.
다음 정보를 바탕으로 주제 별로 질문을 1~3 사이로 만들어줘.
객관식 문항에는 복수선택이 가능한 질문이 금지야.
입력 주제마다 제공되는 topic_id를 그대로 유지해서 결과에도 반드시 포함해줘.
""".strip()


def questions_user(
    research_block: str,
    topics: list[tuple[str, str]],
    question_mode: str,
) -> str:
    """topics: [(topic_id, title)]. question_mode: interview|survey."""
    mode_label = "객관식만" if question_mode == "survey" else "주관식, 객관식 혼용"
    topic_lines = "\n".join(f"- topic_id={tid}, topic_title={title}" for tid, title in topics)
    return (
        f"{research_block}\n"
        f"- 답변 형태: {mode_label}\n"
        f"- 주제 목록:\n{topic_lines}\n"
        "각 문항의 type 은 choice(객관식) 또는 subjective(주관식)로, "
        "객관식이면 options 에 선택지 텍스트 3~6개를 채우세요."
    )
