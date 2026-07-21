"""원장(ledger) 자료구조 단위테스트 — 순수 함수, 그래프 없이."""
from __future__ import annotations

from api.interview.ledger import update_ledger
from api.interview.state import init_ledger

GUIDE = {"questions": [{"id": "q1", "text": "앱?", "goal": "현재 앱"},
                       {"id": "q2", "text": "계기?", "goal": "트리거"}]}


def test_init_ledger_all_pending():
    led = init_ledger(GUIDE)
    assert set(led) == {"q1", "q2"}
    assert all(e == {"status": "pending", "facts": [], "hooks": []} for e in led.values())


def test_update_accumulates_facts_without_dup():
    led = init_ledger(GUIDE)
    led2 = update_ledger(led, "q1", "touched", ["배민 사용"], ["배민클럽 언급"])
    led3 = update_ledger(led2, "q1", "touched", ["배민 사용", "주 3회 주문"], [])
    assert led3["q1"]["facts"] == ["배민 사용", "주 3회 주문"]
    assert led3["q1"]["hooks"] == ["배민클럽 언급"]
    assert led3["q1"]["status"] == "touched"
    assert led["q1"]["facts"] == []              # 원본 불변


def test_status_never_regresses():
    led = init_ledger(GUIDE)
    led = update_ledger(led, "q1", "satisfied", ["fact"], [])
    led = update_ledger(led, "q1", "touched", [], [])   # 후퇴 시도
    assert led["q1"]["status"] == "satisfied"
    led = update_ledger(led, "q1", "saturated", [], [])  # 전진은 허용
    assert led["q1"]["status"] == "saturated"


def test_unknown_qid_is_noop_copy():
    led = init_ledger(GUIDE)
    led2 = update_ledger(led, "없는문항", "touched", ["x"], [])
    assert led2 == led and led2 is not led
