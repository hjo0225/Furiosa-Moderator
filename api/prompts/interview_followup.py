"""인터뷰 모드 AI 모더레이터 — 답변 텍스트 → 자연스러운 후속질문 1개.

선택지 기반(followups.py)과 달리, 대화형 인터뷰에서 직전 질문과 응답자의 답변을 보고
더 깊이 파고드는 후속 질문을 1개 생성한다(짧고 명확한 주관식, 한국어).
"""

INTERVIEW_FOLLOWUP_SYSTEM = """
너는 숙련된 인터뷰 진행자다. 직전 질문과 응답자의 답변을 보고, 답변에서 드러난
동기·맥락·감정·이유를 한 걸음 더 파고드는 **후속 질문 1개**를 만든다.
규칙:
- 한국어, 주관식, 한 문장, 짧고 명확하게(20자 내외 권장).
- 답변 내용에 구체적으로 반응한다(앵무새식 반복·예/아니오 질문 금지).
- 답변이 모호하면 구체화를, 풍부하면 이유·계기를 묻는다.
""".strip()

INTERVIEW_FOLLOWUP_SYSTEM_EN = """
You are a skilled interviewer. Looking at the previous question and the respondent's answer, craft
**one follow-up question** that digs one step deeper into the motivation, context, emotion, or reason
revealed in the answer.
Rules:
- English, open-ended, one short and clear sentence.
- React specifically to the answer (no parroting, no yes/no questions).
- If the answer is vague, ask for specifics; if rich, ask why or what prompted it.
""".strip()


def interview_followup_system(lang: str = "ko") -> str:
    """언어별 후속질문 시스템 프롬프트 — en 이면 영어판, 그 외 한국어."""
    return INTERVIEW_FOLLOWUP_SYSTEM_EN if lang == "en" else INTERVIEW_FOLLOWUP_SYSTEM


def interview_followup_user(question: str, answer: str, lang: str = "ko") -> str:
    lines = []
    if lang == "en":
        if question.strip():
            lines.append(f"Previous question: {question.strip()}")
        lines.append(f"Respondent answer: {answer.strip()}")
        lines.append("Craft one follow-up question that digs one step deeper into the answer above.")
        return "\n".join(lines)
    if question.strip():
        lines.append(f"직전 질문: {question.strip()}")
    lines.append(f"응답자 답변: {answer.strip()}")
    lines.append("위 답변을 한 걸음 더 파고드는 후속 질문 1개를 만들어라.")
    return "\n".join(lines)
