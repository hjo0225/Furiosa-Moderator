"""토픽(연구 주제 후보) 생성 프롬프트 — 기존 backend `app/ai/generate_topic.py` 이식."""

TOPIC_GENERATION_SYSTEM = """
당신에게 연구 기획 초안을 만들기 위한 기본 정보를 제공합니다.
이 정보에는 조사 대상, 규모, 추가 조건, 관심 분야 등이 포함됩니다.
이 정보를 기반으로, 연구에 적합한 주제/토픽 후보를 5~10개 정도 topics 배열에 담아 생성하세요.

요구사항:
- 각 주제는 한 문장 또는 짧은 문구 형태
- 대상과 조건에 맞지 않는 주제는 제외
- 가능한 한 명확하고 실질적인 연구 주제로 작성
- 안내에 따라 제공되는 응답 스키마(json)에만 맞게 필드를 채울 것
""".strip()


def topics_user(
    background: str,
    purpose: str,
    motivation: str,
    utilization: str,
    target: str,
    size: str,
    additional_conditions: str,
) -> str:
    return (
        f"- 설문 배경: {background or '(비어 있음)'}\n"
        f"- 설문 목표: {purpose or '(비어 있음)'}\n"
        f"- 설문 동기: {motivation or '(비어 있음)'}\n"
        f"- 활용 방안: {utilization or '(비어 있음)'}\n"
        f"- 타겟 대상: {target or '(미지정)'}\n"
        f"- 규모: {size or '(미지정)'}\n"
        f"- 추가 조건: {additional_conditions or '(없음)'}"
    )
