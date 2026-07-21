"""프롬프트 v3 단위테스트 — 행동별 생성 지시·첫턴 1문항·모순 컨텍스트가 문자열에 실리는지."""
from __future__ import annotations

from api.interview.prompts import (
    ListenOut,
    analysis_user,
    farewell_user,
    generate_user,
    opening_user,
)
from api.interview.state import init_ledger

GUIDE = {"goal": "배달앱 전환 요인", "questions": [
    {"id": "q1", "text": "어떤 앱을 쓰세요?", "goal": "현재 앱"},
    {"id": "q2", "text": "갈아탄 계기는?", "goal": "트리거"},
]}


def test_listen_out_has_seven_actions_no_message():
    assert set(ListenOut.model_fields["action"].annotation.__args__) == {
        "probe", "clarify", "challenge", "advance", "revisit", "redirect", "close"}
    assert "message" not in ListenOut.model_fields          # 생성은 generate 의 일


def test_opening_exposes_only_first_question():
    prompt, qid = opening_user(GUIDE)
    assert qid == "q1"
    assert "어떤 앱을 쓰세요?" in prompt and "갈아탄 계기는?" not in prompt  # 첫턴 1문항
    assert "하나만" in prompt


def test_analysis_user_carries_ledger_and_contradiction_instruction():
    led = init_ledger(GUIDE)
    led["q1"]["status"] = "touched"
    led["q1"]["hooks"] = ["배민클럽 언급"]
    u = analysis_user(GUIDE, [], "그냥 싸서요", 3, 1, led)
    assert "배민클럽 언급" in u                              # 원장 컨텍스트
    assert "모순" in u and "contradiction" in u              # challenge 재료 지시
    assert "구체화" in u and "심화" in u                     # 래더링 (팀원 개선)


def test_generate_user_varies_by_action():
    led = init_ledger(GUIDE)
    led["q2"]["facts"] = ["쿠폰 때문"]
    base = dict(question_id="q2", probe_type="", contradiction="", guide=GUIDE, messages=[], ledger=led)
    g_ch = generate_user("challenge", **{**base, "contradiction": "가격 안 본다더니 최저가만 찾음"})
    assert "가격 안 본다더니" in g_ch and "확인" in g_ch
    g_rv = generate_user("revisit", **base)
    assert "갈아탄 계기는?" in g_rv and "쿠폰 때문" in g_rv   # 재방문 문항 + 기존 수확
    g_pr = generate_user("probe", **{**base, "probe_type": "심화"})
    assert "심화" in g_pr
    g_rd = generate_user("redirect", **base)
    assert "부드럽게" in g_rd


def test_farewell_user_mentions_thanks():
    assert "감사" in farewell_user([])
