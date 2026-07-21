"""도구 4종 중 결정론 3종 단위테스트 — LLM·DB 없이."""
from __future__ import annotations

from api.interview.state import init_ledger
from api.interview.tools.ledger_report import ledger_report
from api.interview.tools.pace import pace
from api.interview.tools.playbook import playbook

GUIDE = {"goal": "전환 요인", "questions": [
    {"id": "q1", "text": "어떤 앱?", "goal": "현재 앱"},
    {"id": "q2", "text": "계기는?", "goal": "트리거"},
    {"id": "q3", "text": "만족도는?", "goal": "만족 요인"},
]}


def test_playbook_maps_action_to_technique():
    assert "5 Why" in playbook("probe", "심화") or "래더링" in playbook("probe", "심화")
    assert "CIT" in playbook("probe", "구체화") or "사례" in playbook("probe", "구체화")
    assert "모순" in playbook("challenge")
    assert playbook("advance") == ""                     # 기법이 필요 없는 행동은 빈 문자열


def test_ledger_report_summarizes():
    led = init_ledger(GUIDE)
    led["q1"].update(status="touched", facts=["배민 사용"], hooks=["배민클럽 안 팜"])
    led["q2"]["status"] = "satisfied"
    r = ledger_report(GUIDE, led)
    assert "q3" in r                                      # 남은 goal
    assert "q1" in r and "배민클럽 안 팜" in r             # 빈약 문항 + 미회수 떡밥
    detail = ledger_report(GUIDE, led, qid="q1")
    assert "배민 사용" in detail                          # 문항 상세엔 facts 전체


def test_pace_warns_when_budget_tight():
    assert "여유" not in pace(10, 12, 3) and "서둘" in pace(10, 12, 3)   # 남은 2턴 < 남은 3문항
    assert "서둘" not in pace(2, 12, 3)                                   # 초반은 경고 없음
