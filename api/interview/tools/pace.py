"""pace — 남은 턴 예산·페이스 경고 (결정론)."""
from __future__ import annotations


def pace(asked: int, max_asked: int, pending_count: int) -> str:
    left = max(0, max_asked - asked)
    line = f"[페이스] 질문 {asked}/{max_asked}회 사용, 남은 예산 {left}턴, 남은 문항 {pending_count}개."
    if left <= pending_count and asked >= max_asked // 3:
        return line + " 예산이 빠듯합니다 — 서둘러 남은 문항을 커버하고 파고들기는 아껴 쓰세요."
    return line
