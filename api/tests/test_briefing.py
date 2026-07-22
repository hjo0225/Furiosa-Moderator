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


def test_chunks_with_angle_tags_and_sequences():
    from api.briefing.pipeline import chunks_with_angle
    from api.schemas.models import Material

    mats = [
        Material(source="web", angle="현상", title="A", text="문단1.\n\n문단2."),
        Material(source="upload", angle="활용", title="B", text="문단3."),
    ]
    rows = chunks_with_angle(mats)
    assert [r[2] for r in rows] == ["현상", "현상", "활용"]   # angle 태깅
    assert [r[0] for r in rows] == [0, 1, 2]                  # seq 연속
    assert rows[0][3] == "A"                                  # source = title


def test_add_materials_incremental_indexes_each_and_refreshes_touched_slots(monkeypatch):
    from api.briefing import pipeline
    from api.schemas.models import Material

    indexed, refreshed = [], []
    monkeypatch.setattr(pipeline, "index_material", lambda pid, m: indexed.append(m.id) or 1)
    monkeypatch.setattr(pipeline, "refresh_slot", lambda pid, angle: refreshed.append(angle))
    mats = [
        Material(id="m1", source="web", angle="현상", text="a"),
        Material(id="m2", source="web", angle="현상", text="b"),
        Material(id="m3", source="upload", angle="활용", text="c"),
    ]
    pipeline.add_materials_incremental("p_1", mats)
    assert indexed == ["m1", "m2", "m3"]          # 자료마다 인덱싱
    assert set(refreshed) == {"현상", "활용"}       # 건드린 슬롯만(중복 제거)


def test_add_materials_incremental_survives_index_failure(monkeypatch):
    from api.briefing import pipeline
    from api.schemas.models import Material

    refreshed = []
    monkeypatch.setattr(pipeline, "index_material",
                        lambda pid, m: (_ for _ in ()).throw(RuntimeError("embed down")))
    monkeypatch.setattr(pipeline, "refresh_slot", lambda pid, angle: refreshed.append(angle))
    pipeline.add_materials_incremental("p_1", [Material(id="m1", source="web", angle="원인", text="x")])
    assert refreshed == ["원인"]                    # 인덱싱 실패해도 요약은 진행


def test_refresh_slot_summarizes_only_that_slot(monkeypatch):
    from api.briefing import pipeline
    from api.schemas.models import Material

    captured = {}
    monkeypatch.setattr("api.services.store.list_materials", lambda pid: [
        Material(id="m1", source="web", angle="현상", text="현상글"),
        Material(id="m2", source="web", angle="활용", text="활용글"),
    ])
    monkeypatch.setattr("api.services.material.summarize_slot",
                        lambda texts: "|".join(texts))
    monkeypatch.setattr("api.services.store.save_slot_summary",
                        lambda pid, angle, summary: captured.update({angle: summary}))
    pipeline.refresh_slot("p_1", "현상")
    assert captured == {"현상": "현상글"}             # 현상 자료만 요약, 활용 제외
