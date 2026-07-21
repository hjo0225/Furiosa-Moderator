"""브리핑 인덱싱 — 청킹(순수)과 라우트 등록. 임베딩·DB 경로는 라이브 검증 몫."""
from __future__ import annotations

from api.briefing.pipeline import chunk_text


def test_chunk_splits_paragraphs_and_respects_size():
    text = "첫 문단입니다.\n\n" + "가" * 1200 + "\n\n마지막 문단."
    chunks = chunk_text(text, size=500, overlap=80)
    assert chunks[0] == "첫 문단입니다."
    assert all(len(c) <= 500 for c in chunks)
    assert chunks[-1] == "마지막 문단."
    long_parts = [c for c in chunks if "가" in c]
    assert len(long_parts) >= 3                            # 1200자 → 500/80 오버랩 분할
    assert long_parts[1][:80] == long_parts[0][-80:]       # 오버랩 확인


def test_chunk_drops_blank():
    assert chunk_text("  \n\n  \n") == []


def test_briefing_index_route_registered():
    import api.main as m
    paths = {r.path for r in m.app.routes if hasattr(r, "path")}
    assert "/api/projects/{pid}/briefing/index" in paths
