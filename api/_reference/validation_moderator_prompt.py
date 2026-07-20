"""솔루션 1 — 모더레이터 / 라운드 의제 v2 (PRD §8-4).

의제 v2 — 발견 내러티브 3챕터(§01 예상치 못한 발견 · §02 뉘앙스 · §03 소수 의견)에 원료를
직접 공급하도록 설계. 인테이크 변수(price_range·value_prop·feared_question)를 라운드별로 주입한다.
"""

# 6라운드 의제 v3 — 아이디어 검증(문제·가치·해결책) 중심. R2~R4 는 agenda_for 가 인테이크 변수로 합성한다.
# (정량 가격민감도·구매점수 라운드는 제거 — 검증 초점을 문제·가치·해결책으로.)
ROUND_AGENDAS: dict[int, dict[str, str]] = {
    1: {
        "topic": "첫 인상 · 이해도",
        # 사용 장면 — §01 원료
        "agenda": (
            "이 제품/서비스를 처음 들었을 때 첫 인상과 이해도를 말씀해 주세요. "
            "그리고 이걸 누가, 어떤 장면(상황)에서 쓸 것 같은지 구체적으로 상상해 말해 주세요."
        ),
    },
    2: {
        # 문제 공감 — agenda_for 가 problem 을 주입(자신도 겪나·빈도·심각도). §02 원료
        "topic": "문제 공감",
        "agenda": (
            "이 아이디어가 풀려는 문제를 당신도 실제로 겪나요? 얼마나 자주, 얼마나 불편한지(심각도)와 "
            "그 문제를 가장 아프게 느낀 구체적 상황을 말씀해 주세요."
        ),
    },
    3: {
        # 가치·해결책 적합성 — agenda_for 가 value+solution 을 주입(가정 직접 검증). §01 원료
        "topic": "가치 · 해결책 적합성",
        "agenda": (
            "이 해결책이 그 문제를 의미있게 풀어준다고 느끼시나요? 당신에게 진짜 가치인지, "
            "아니면 부족하거나 빗나간 부분이 있는지 솔직히 말씀해 주세요."
        ),
    },
    4: {
        # 현재 대처법 대비 — agenda_for 가 alternative 를 주입.
        "topic": "현재 대처법 대비",
        "agenda": "지금 그 문제를 견디는 방식(기존 대처법) 대비, 이 해결책이 더 낫다고 느끼는 점과 아쉬운 점은?",
    },
    5: {"topic": "가장 큰 의구심", "agenda": "이 아이디어가 안 통할 것 같은 가장 큰 의구심은 무엇입니까?"},
    6: {
        "topic": "재고 · 개선 제안",
        # 재고(Reflection) — §03 flip 증거 직접 생산
        "agenda": (
            "먼저, 토론을 거치며 처음 입장에서 바뀐 것이 있다면 누구의 어떤 말이 바꿨는지 말해 주세요. "
            "그 다음, 이 아이디어가 당신에게 더 의미있어지려면 무엇이 어떻게 바뀌면 좋을지 제안해 주세요."
        ),
    },
}


def all_round_agendas(
    feared_question: str | None = None,
    *,
    problem: str | None = None,
    value: str | None = None,
    solution: str | None = None,
    alternative: str | None = None,
) -> list[dict]:
    """6라운드 의제 전체 — SSE 'agenda' 이벤트용(프론트가 미래 라운드 라벨에 사용).

    프론트가 의제 사본(ROUNDS 폴백)을 들고 있다가 드리프트 나던 문제의 근본 수정 —
    백엔드가 SSOT 그대로 흘려보내고, 프론트 폴백 의존을 제거한다(검증 수칙 6).
    """
    return [
        {
            "no": rno,
            **agenda_for(
                rno, feared_question,
                problem=problem, value=value, solution=solution, alternative=alternative,
            ),
        }
        for rno in sorted(ROUND_AGENDAS)
    ]


def agenda_for(
    round_no: int,
    feared_question: str | None = None,
    *,
    problem: str | None = None,
    value: str | None = None,
    solution: str | None = None,
    alternative: str | None = None,
) -> dict[str, str]:
    """라운드 의제 합성(v3 — 아이디어 검증 중심).

    · R2: problem 이 있으면 그 문제를 직접 제시하고 공감/심각도/빈도를 캐묻는다(§02 원료).
    · R3: value+solution 이 있으면 창업자의 가치·해결책 가정을 직접 검증한다(§01 원료).
    · R4: alternative 가 있으면 기존 대처법을 명시해 비교를 구체화한다.
    · R5: 창업자의 '두려운 질문'을 강제 주입(기존 유지).
    """
    base = ROUND_AGENDAS[round_no]
    agenda = base["agenda"]
    if round_no == 2 and (problem or "").strip():
        agenda = (
            f"이 아이디어가 풀려는 문제는 '{problem.strip()}' 입니다 — 당신도 실제로 겪나요? "
            "얼마나 자주·심각하게 겪는지와, 그 문제를 가장 아프게 느낀 구체적 상황을 말씀해 주세요."
        )
    elif round_no == 3 and ((value or "").strip() or (solution or "").strip()):
        bits = []
        if (solution or "").strip():
            bits.append(f"해결책은 '{solution.strip()}'")
        if (value or "").strip():
            bits.append(f"창업자가 믿는 핵심 가치는 '{value.strip()}'")
        lead = ", ".join(bits)
        agenda = (
            f"{lead} 입니다 — 이 해결책이 그 문제를 의미있게 풀어준다고 느끼시나요? "
            "당신에게 진짜 가치인지, 부족하거나 빗나간 부분은 없는지 솔직히 말씀해 주세요."
        )
    elif round_no == 4 and (alternative or "").strip():
        agenda = (
            f"지금 그 문제를 견디는 방식은 '{alternative.strip()}' 입니다 — "
            "그 대비 이 해결책이 더 낫다고 느끼는 점과 아쉬운 점을 구체적으로 말씀해 주세요."
        )
    elif round_no == 5 and feared_question:
        agenda = f"{agenda} 특히 창업자가 가장 피하고 싶어 한 질문을 직접 다뤄 주세요 — “{feared_question}”"
    return {"topic": base["topic"], "agenda": agenda}


MODERATOR_INTRO = (
    "당신은 가상 포커스그룹(FGI) 모더레이터입니다. 라운드 의제를 명확히 던지고, "
    "패널의 솔직한 반응을 이끌어냅니다. 당신은 '원하는 답을 끌어내는 인터뷰어'가 아니라 "
    "'토론을 설계·운영하는 진행자'입니다 — 답을 유도하지 말고, 의견이 부딪치게 만들고, 깊게 파세요."
)

# 라운드별 모더레이터 역할(#10) — 단계적 진전. 라운드마다 목표가 다르다.
ROUND_MODERATOR_ROLE = {
    1: "문제 이해 — 패널의 경험·첫인상을 끌어내라. 아직 해결책·전문 수치(AUC·MAPE 등)로 들어가지 말고 "
       "'이게 뭔지 이해됐는지', '그 문제를 실제로 겪어봤는지'를 캐라.",
    2: "문제 검증 — 추상론 말고 '실제 사례'를 깊게. 누가 언제 그 문제를 겪었는지, 얼마나 자주·심각한지 구체적으로 파라.",
    3: "해결책 검증 — 찬반을 의도적으로 충돌시켜라. 한 사람이 긍정하면 곧장 반대 성향·다른 직무 패널에게 반론을 물어라.",
    4: "대안 비교 — 지금 그 문제를 견디는 방식(기존 대처법·경쟁 대안) 대비 이 해결책이 더 나은 점과 "
       "아쉬운 점을 구체적으로 캐라. '돈'이 아니라 '정말 더 나은가·충분한가'를 파라.",
    5: "가장 큰 의구심 — 이 아이디어가 안 통할 것 같은 의구심을 직접 다루되, 답을 유도하지 말고 열어두라.",
    6: "재고·개선 공동 도출 — 토론 중 처음 입장에서 바뀐 지점을 짚게 하고, 이 아이디어가 더 의미있어지려면 "
       "무엇이 어떻게 바뀌면 좋을지 패널끼리 함께 제안하게 하라.",
}


def founder_followup_frame(text: str, target_name: str | None = None) -> str:
    """HITL — 사용자(창업자/관찰자) 발언을 모더레이터가 패널에게 전달하는 멘트로 감싼다."""
    who = f"{target_name}님" if target_name else "패널 여러분"
    return f"창업자가 직접 질문을 남겼습니다 — {who}, 답해 주세요: “{text}”"


def moderator_decide_system(panel: list[dict], round_no: int | None = None) -> str:
    """라운드 발언 검토 후 후속질문/종료 결정 (ModeratorAction 강제).

    message 에는 패널을 '이름'으로 호명(내부 id 금지), next_speaker 에만 해당 id 를 넣는다.
    round_no 가 있으면 그 라운드의 모더레이터 역할(ROUND_MODERATOR_ROLE)을 주입한다(#10).
    """
    roster = ", ".join(f"{p.get('name') or p['id']}(id:{p['id']})" for p in panel)
    role = ROUND_MODERATOR_ROLE.get(round_no or 0, "")
    role_line = f"[이번 라운드 역할] {role}\n" if role else ""
    return (
        f"{MODERATOR_INTRO}\n\n"
        f"{role_line}"
        "방금 이 라운드의 발언들을 검토하고 다음 행동을 결정하세요(의제 변경 금지). "
        "후속질문은 여러 턴 이어질 수 있으니, 매번 가장 파고들 가치가 큰 지점을 새로 고르세요.\n"
        "- 더 파고들 가치가 있으면: action='ask', next_speaker 에 패널 id 하나, message 에 그 패널을 "
        "**이름으로 호명**하며 던지는 후속질문 1개.\n"
        "  [① 유도 금지 — 가장 중요] 답을 정해놓고 끌어내지 마세요. '정말 …할 수 있다고 확신하세요?', "
        "'…를 줄일 수 있다고 보시죠?' 처럼 전제·방향을 깐 질문은 금지. 대신 열어두세요 — "
        "'그 부분 어떻게 보세요?', '실제로는 어떤 결과가 나올 것 같나요?' 처럼.\n"
        "  [② 반론 만들기 — 같은 사람만 계속 묻지 마라] 한 사람이 말하면 **다른 패널**에게 넘겨 충돌을 만드세요. "
        "직전이 긍정이면 우려·반대 성향에게, 부정이면 찬성 성향에게, 또는 다른 직무에게 "
        "'OOO님 의견에 동의하세요?' / 'OO 입장에서는 어떠세요?' 로 물어 의견이 갈리게 하세요.\n"
        "  [③ 깊게 파기(5 Why)] 패널이 이유를 대면 거기서 멈추지 말고 '왜 그렇죠?'를 1~2단계 더 파세요 "
        "(예: '어렵다' → '왜 어렵죠?' → '동의를 안 해서' → '왜 동의를 안 할까요?'). 표면 답에서 끝내지 마세요.\n"
        "- 의제가 충분히 다뤄졌거나 답변이 반복·수렴하면: action='end' (message 비움) — 라운드를 조기 종료.\n"
        f"패널 명단: {roster}\n"
        "next_speaker 는 반드시 위 id 중 하나. **message 에는 절대 id(예: c_… / gx…)를 쓰지 말고 이름만** 사용하세요. "
        "위 명단에 없는 사람 이름을 지어내지 마세요."
    )


def intervention_guide_system(panel: list[dict]) -> str:
    """라운드 경계 개입 가이드 — 방금 끝난 라운드를 모더레이터 관점에서 해석해 파볼 포인트 제안."""
    roster = ", ".join(f"{p.get('name') or p['id']}(id:{p['id']})" for p in panel)
    return (
        f"{MODERATOR_INTRO}\n\n"
        "방금 끝난 라운드의 발언들을 모더레이터 관점에서 해석해, 창업자(관찰자)가 지금 개입한다면 "
        "어떤 포인트를 다시 물어보면 좋을지 2~3개 제안하세요. 각 포인트는:\n"
        "- point: 이 라운드에 남은 긴장·공백·애매함 한 줄(예: '가격 우려가 구체적 근거 없이 반복됨').\n"
        "- question: 창업자가 그대로 보낼 수 있는 짧은 개입 질문 1문장(존댓말).\n"
        "- target_id: 그 질문을 받기에 가장 적합한 패널의 id(전체에게 묻는 게 나으면 비움).\n"
        "summary 에는 이 라운드 흐름을 한 줄로 요약하세요(누가 어디서 갈렸는지).\n"
        f"패널 명단: {roster}\n"
        "point·question·summary 본문에는 절대 id 를 쓰지 말고 이름만 사용하세요. "
        "반드시 제공된 JSON 스키마로만 응답하세요."
    )


def intervention_guide_user(agenda: str, round_utts: list[dict], name_by_id: dict[str, str] | None = None) -> str:
    nm = name_by_id or {}
    lines = "\n".join(
        f"- {nm.get(u.get('speaker_id'), u.get('speaker_name') or u.get('speaker_id', '?'))}: "
        f"{str(u.get('content', ''))[:200]}"
        for u in round_utts
    )
    return (
        f"[의제]\n{agenda}\n\n[이번 라운드 발언]\n{lines}\n\n"
        "창업자가 개입하면 좋을 포인트 2~3개와 추천 질문을 만드세요."
    )


def moderator_decide_user(agenda: str, round_utts: list[dict], name_by_id: dict[str, str] | None = None) -> str:
    nm = name_by_id or {}
    lines = "\n".join(
        f"- {nm.get(u.get('speaker_id'), u.get('speaker_id', '?'))}: {str(u.get('content', ''))[:160]}"
        for u in round_utts
    )
    return f"[의제]\n{agenda}\n\n[이번 라운드 발언]\n{lines}\n\n다음 행동(ask/end)을 결정하세요."
