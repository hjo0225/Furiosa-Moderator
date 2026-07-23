"""브리핑 인덱싱 — 청킹(순수)과 라우트 등록. 임베딩·DB 경로는 라이브 검증 몫."""
from __future__ import annotations

import pytest

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


# --- search_chunks: 2단 검색(코사인 → 리랭커) -------------------------------------
#
# DB(pgvector)·리랭커 네트워크 없이 함수 로직만 검증한다. db_session 은 넘긴
# (chunk, distance) 목록을 그대로(또는 angle 하드필터해) 돌려주는 가짜로,
# get_llm().rerank 는 지정한 재정렬(또는 LLMError)로 각각 monkeypatch 한다.

class _Chunk:
    """BriefingChunkRow 흉내 — search_chunks 가 읽는 필드만."""

    def __init__(self, text, source="src", angle=""):
        self.text, self.source, self.angle = text, source, angle


class _Row:
    """s.execute(...).all() 가 주는 Row 흉내 — r.BriefingChunkRow / r.d 접근."""

    def __init__(self, chunk, d):
        self.BriefingChunkRow = chunk
        self.d = d


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """db_session() 대체 — (chunk, distance) 목록을 코사인 순서 그대로 돌려준다.

    angle 하드필터가 실린 쿼리(WHERE angle=…)면 그 슬롯만 남긴다 — 실제 DB 의
    필터를 흉내 내, 리랭커에 넘어가는 후보가 슬롯으로 좁혀지는지 검증할 수 있게.
    """

    def __init__(self, pairs):
        self._pairs = pairs           # list[(_Chunk, float 거리)] — 이미 코사인 오름차순
        self.captured = None          # 마지막 실행 statement (angle 필터 검증용)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, stmt):
        self.captured = stmt
        want = stmt.compile().params.get("angle_1")   # angle 하드필터 값(없으면 None)
        pairs = [(c, d) for c, d in self._pairs if not want or c.angle == want]
        return _Result([_Row(c, d) for c, d in pairs])


class _FakeLLM:
    """get_llm() 대체 — rerank 만 가짜로. ranked 를 돌려주거나 LLMError 를 던진다."""

    def __init__(self, ranked=None, boom=False):
        self._ranked, self._boom = ranked, boom
        self.calls = []

    def rerank(self, query, documents, *, top_n):
        from api.services.llm_client import LLMError

        self.calls.append((query, list(documents), top_n))
        if self._boom:
            raise LLMError("rerank down")
        return self._ranked


def _wire(monkeypatch, pairs, fake_llm):
    """embed_texts·db_session·get_llm 를 한 번에 주입하고 세션 핸들을 돌려준다."""
    from api.briefing import pipeline

    sess = _FakeSession(pairs)
    monkeypatch.setattr(pipeline, "embed_texts", lambda texts: [[0.1, 0.2, 0.3]])
    monkeypatch.setattr(pipeline, "db_session", lambda: sess)
    # search_chunks 는 함수 안에서 로컬 임포트하므로 원본 모듈에서 patch 해야 먹는다.
    monkeypatch.setattr("api.services.llm_client.get_llm", lambda: fake_llm)
    return sess


def test_search_chunks_rerank_reorders(monkeypatch):
    from api.briefing import pipeline

    pairs = [                                        # 코사인 오름차순(=관련도 내림차순)
        (_Chunk("A", "sA", "현상"), 0.10),
        (_Chunk("B", "sB", "현상"), 0.20),
        (_Chunk("C", "sC", "현상"), 0.30),
        (_Chunk("D", "sD", "현상"), 0.40),
    ]
    fake = _FakeLLM(ranked=[(2, 0.99), (0, 0.80), (3, 0.55)])   # C, A, D 로 재정렬
    _wire(monkeypatch, pairs, fake)

    out = pipeline.search_chunks("p1", "q", k=3)

    assert [r["text"] for r in out] == ["C", "A", "D"]         # 리랭커 순서로 재정렬
    assert [r["source"] for r in out] == ["sC", "sA", "sD"]    # 나머지 필드 보존
    assert [r["score"] for r in out] == [0.99, 0.80, 0.55]     # 코사인 점수 → 리랭크 점수
    assert fake.calls[0][1] == ["A", "B", "C", "D"]            # 후보 4개 전부 리랭커에 전달
    assert fake.calls[0][2] == 3                               # top_n == k


def test_search_chunks_rerank_failure_falls_back_to_cosine(monkeypatch):
    from api.briefing import pipeline

    pairs = [
        (_Chunk("A", "sA"), 0.10),
        (_Chunk("B", "sB"), 0.20),
        (_Chunk("C", "sC"), 0.30),
        (_Chunk("D", "sD"), 0.40),
    ]
    fake = _FakeLLM(boom=True)                       # 리랭커가 LLMError 로 죽는다
    _wire(monkeypatch, pairs, fake)

    out = pipeline.search_chunks("p1", "q", k=3)

    assert [r["text"] for r in out] == ["A", "B", "C"]         # 코사인 순서 top-k 폴백
    assert out[0]["score"] == pytest.approx(0.90)              # 코사인 점수(1.0-0.10) 유지
    assert len(fake.calls) == 1                                # 리랭커를 시도는 했다


def test_search_chunks_angle_hard_filters(monkeypatch):
    from api.briefing import pipeline

    pairs = [                                        # 현상·원인·활용 섞여 있음
        (_Chunk("현상1", "s1", "현상"), 0.10),
        (_Chunk("원인X", "s2", "원인"), 0.15),
        (_Chunk("현상2", "s3", "현상"), 0.20),
        (_Chunk("활용X", "s4", "활용"), 0.25),
        (_Chunk("현상3", "s5", "현상"), 0.30),
        (_Chunk("현상4", "s6", "현상"), 0.40),
    ]
    fake = _FakeLLM(ranked=[(0, 0.9), (1, 0.8), (2, 0.7)])
    sess = _wire(monkeypatch, pairs, fake)

    out = pipeline.search_chunks("p1", "q", k=3, angle="현상")

    docs = fake.calls[0][1]                                    # 리랭커에 넘어간 후보
    assert docs == ["현상1", "현상2", "현상3", "현상4"]         # 현상 슬롯만 후보
    assert "원인X" not in docs and "활용X" not in docs         # 비매칭 슬롯은 배제
    assert all(r["text"].startswith("현상") for r in out)      # 결과도 현상만
    assert sess.captured.compile().params.get("angle_1") == "현상"   # WHERE angle 하드필터 실림


def test_search_chunks_small_candidate_set_skips_rerank(monkeypatch):
    from api.briefing import pipeline

    pairs = [                                        # 후보 2개 ≤ k=3
        (_Chunk("A", "sA"), 0.10),
        (_Chunk("B", "sB"), 0.20),
    ]
    fake = _FakeLLM(ranked=[(0, 0.9)])
    _wire(monkeypatch, pairs, fake)

    out = pipeline.search_chunks("p1", "q", k=3)

    assert [r["text"] for r in out] == ["A", "B"]             # 코사인 순서 그대로 반환
    assert out[0]["score"] == pytest.approx(0.90)             # 코사인 점수 유지
    assert fake.calls == []                                   # 리랭커 호출 자체가 없다


def test_search_chunks_drops_out_of_range_and_clamps_to_k(monkeypatch):
    from api.briefing import pipeline

    pairs = [                                        # 후보 4개(> k) → 리랭커 경로 진입
        (_Chunk("A", "sA"), 0.10),
        (_Chunk("B", "sB"), 0.20),
        (_Chunk("C", "sC"), 0.30),
        (_Chunk("D", "sD"), 0.40),
    ]
    # 리랭커가 범위 밖 index(99)와 k 초과 개수를 돌려줘도: 범위 밖은 버리고 k 로 클램프
    fake = _FakeLLM(ranked=[(0, 0.9), (99, 0.8), (1, 0.7), (0, 0.6)])
    _wire(monkeypatch, pairs, fake)

    out = pipeline.search_chunks("p1", "q", k=2)

    assert len(out) <= 2                                       # k 로 클램프
    assert all(isinstance(r, dict) and "text" in r for r in out)   # 유효 dict 만(범위 밖 제거)
    assert [r["text"] for r in out] == ["A", "B"]             # 99 스킵 → 상위 k=2(0→A, 1→B)
    assert [r["score"] for r in out] == [0.9, 0.7]
