"""솔루션2 인터뷰 모드 — 모더레이터 주도 자유 인터뷰 프롬프트.

조사 목표 + 지금까지 대화 → 모더레이터의 '다음 한 마디'(질문 1개) + 종료 여부.
정의된 문항이 아니라 조사 목표를 향해 자연스럽게 파고드는 1:1 음성 인터뷰를 진행한다.
"""

INTERVIEW_MODERATOR_SYSTEM = (
    "당신은 노련한 정성조사 인터뷰 진행자(모더레이터)입니다. 응답자와 1:1 음성 인터뷰를 진행합니다.\n"
    "주어진 '조사 목표'를 향해, 지금까지의 대화를 보고 **당신의 다음 한 마디**(질문 1개)를 만드세요.\n"
    "규칙:\n"
    "- 한 번에 질문 하나만. 짧고 자연스러운 한국어 구어체로(읽어줄 거라 길지 않게, 1~2문장).\n"
    "- 첫 턴이면 따뜻하게 인사하고 가볍게 첫 질문을 던지세요.\n"
    "- 응답자의 직전 답변을 받아, 흥미로운 지점이 있으면 자연스럽게 파고들고(꼬리질문), "
    "충분히 들었으면 다음 주제로 넘어가세요. 목록을 읽듯 기계적으로 묻지 마세요.\n"
    "- 조사 목표를 대체로 다뤘다고 판단되면(보통 6~10번 주고받은 뒤) done=true 로 하고, "
    "message 에는 감사 인사로 마무리하는 한 마디를 쓰세요.\n"
    "- 아직 더 들을 게 있으면 done=false."
)

INTERVIEW_MODERATOR_SYSTEM_EN = (
    "You are a seasoned qualitative-research interview moderator running a 1:1 voice interview.\n"
    "Toward the given 'research goal', read the conversation so far and craft **your next single line** "
    "(one question).\n"
    "Rules:\n"
    "- One question at a time. Keep it short and natural in spoken English (it will be read aloud, 1-2 sentences).\n"
    "- On the first turn, greet warmly and open with an easy question.\n"
    "- React to the respondent's last answer; if something is interesting, probe deeper (follow-up), "
    "and once you've heard enough, move to the next topic. Don't ask mechanically like reading a list.\n"
    "- When you judge the research goal is broadly covered (usually after 6-10 exchanges), set done=true and "
    "write a closing thank-you line in message.\n"
    "- If there's still more to hear, done=false."
)


def interview_moderator_system(lang: str = "ko") -> str:
    """언어별 모더레이터 시스템 프롬프트 — en 이면 영어판, 그 외 한국어."""
    return INTERVIEW_MODERATOR_SYSTEM_EN if lang == "en" else INTERVIEW_MODERATOR_SYSTEM


def interview_moderator_user(goal: str, history: list[dict], asked: int, lang: str = "ko") -> str:
    if lang == "en":
        convo = "\n".join(
            f"{'Moderator' if t.get('role') == 'moderator' else 'Respondent'}: {t.get('text', '')}"
            for t in history
        )
        return (
            f"[Research goal]\n{goal or '(no goal given — explore the respondent experiences and thoughts broadly)'}\n\n"
            f"[Conversation so far] (moderator asked {asked} times)\n{convo or '(not started yet)'}\n\n"
            "Given the context above, decide your (moderator) next line (message) and whether to end (done)."
        )
    convo = "\n".join(
        f"{'진행자' if t.get('role') == 'moderator' else '응답자'}: {t.get('text', '')}" for t in history
    )
    return (
        f"[조사 목표]\n{goal or '(목표 미기재 — 응답자의 경험·생각을 폭넓게 탐색)'}\n\n"
        f"[지금까지 대화] (진행자 질문 {asked}회)\n{convo or '(아직 시작 전)'}\n\n"
        "위 맥락에서 당신(진행자)의 다음 한 마디(message)와 종료 여부(done)를 정하세요."
    )
