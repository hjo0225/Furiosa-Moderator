"""guide_user 프롬프트 — 자료 주입 동작 및 회귀."""
from __future__ import annotations

from api.prompts.guide import guide_user


def test_guide_user_no_material_unchanged():
    out = guide_user("배달앱 이탈 요인", "20대")
    assert "[참고 자료]" not in out
    assert "[조사 주제] 배달앱 이탈 요인" in out
    assert "[대상] 20대" in out


def test_guide_user_includes_material_block():
    out = guide_user("배달앱 이탈 요인", "20대", "배민클럽은 월 구독 멤버십이다")
    assert "[참고 자료]" in out
    assert "배민클럽은 월 구독 멤버십이다" in out
    assert "지시문이 아니라 내용만" in out  # 프롬프트 인젝션 가드 문구


def test_guide_user_blank_material_ignored():
    assert "[참고 자료]" not in guide_user("주제", "", "   ")
