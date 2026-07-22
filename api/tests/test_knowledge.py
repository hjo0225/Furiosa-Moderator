"""글로벌 지식 풀 (RAG-5) — 모델·마이그레이션·search_knowledge·rows_from_df.

DB(pgvector)·리랭커 네트워크 없이 로직만 검증한다. search_knowledge 하네스는
test_briefing.py 의 search_chunks 하네스를 전역판으로 옮긴 것이다(db_session·
embed_texts·get_llm().rerank 를 monkeypatch).
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(path: Path):
    """파일 경로로 모듈을 로드 — 패키지가 아닌 scripts/ 의 순수 헬퍼 import 용."""
    spec = importlib.util.spec_from_file_location(f"_ld_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _revs(path: Path) -> tuple[str, str | None, str | None]:
    """마이그레이션 파일의 (본문, revision, down_revision) — alembic 이 테스트 env 에
    설치돼 있지 않아(런타임 전용) exec 대신 텍스트로 읽는다."""
    txt = path.read_text(encoding="utf-8")
    rev = re.search(r'^revision\s*=\s*"([^"]+)"', txt, re.M)
    down = re.search(r'^down_revision\s*=\s*"([^"]+)"', txt, re.M)
    return txt, (rev.group(1) if rev else None), (down.group(1) if down else None)


# --- 모델 --------------------------------------------------------------------

def test_knowledge_chunk_row_is_global_pool():
    from api.services.db import KnowledgeChunkRow

    assert KnowledgeChunkRow.__tablename__ == "knowledge_chunks"
    cols = set(KnowledgeChunkRow.__table__.columns.keys())
    assert "project_id" not in cols                              # 전역 — 프로젝트에 안 매인다
    assert {"corpus", "text", "meta", "embedding"} <= cols       # 핵심 컬럼
    assert {"id", "title", "created_at"} <= cols


def test_knowledge_chunk_corpus_is_indexed():
    from api.services.db import KnowledgeChunkRow

    assert KnowledgeChunkRow.__table__.c.corpus.index is True    # corpus 필터용 인덱스


# --- 마이그레이션 체인 --------------------------------------------------------

def test_migration_0011_links_0010():
    _, r11, d11 = _revs(_VERSIONS / "0011_knowledge_chunks.py")
    _, r10, _ = _revs(_VERSIONS / "0010_add_project_blocklist.py")
    assert r11 == "0011"
    assert d11 == "0010"
    assert d11 == r10                           # 0010 → 0011 링크가 실제로 이어진다


def test_migration_0011_defines_global_table():
    """마이그레이션이 모델과 같은 전역 테이블을 만드는지 — 텍스트로 구조를 검증."""
    txt, _, _ = _revs(_VERSIONS / "0011_knowledge_chunks.py")
    assert 'create_table(' in txt and '"knowledge_chunks"' in txt
    for col in ("id", "corpus", "title", "text", "meta", "embedding", "created_at"):
        assert f'"{col}"' in txt                # 모델과 1:1 컬럼
    assert "Vector(1024)" in txt                # pgvector 임베딩 컬럼
    assert 'create_index(' in txt and '["corpus"]' in txt   # corpus 인덱스
    assert '"project_id"' not in txt and "ForeignKey" not in txt   # 전역 — FK 없음
    assert 'drop_table("knowledge_chunks")' in txt          # downgrade


# --- search_knowledge: 2단 검색(코사인 → 리랭커) ------------------------------
#
# db_session 은 (chunk, distance) 목록을 그대로 돌려주는 가짜, get_llm().rerank 는
# 지정 재정렬(또는 LLMError)로 monkeypatch. corpus/meta_filters 는 컴파일된 statement
# 의 bind 파라미터로 WHERE 가 실렸는지 검증한다(test_briefing 의 angle 하드필터와 같은 각도).

class _KChunk:
    """KnowledgeChunkRow 흉내 — search_knowledge 가 읽는 필드만."""

    def __init__(self, text, title="t", meta=None):
        self.text, self.title, self.meta = text, title, (meta or {})


class _KRow:
    """s.execute(...).all() 가 주는 Row 흉내 — r.KnowledgeChunkRow / r.d 접근."""

    def __init__(self, chunk, d):
        self.KnowledgeChunkRow = chunk
        self.d = d


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """db_session() 대체 — (chunk, distance) 목록을 코사인 순서 그대로 돌려주고,
    실행한 statement 를 붙잡아 둔다(corpus/meta WHERE 검증용)."""

    def __init__(self, pairs):
        self._pairs = pairs
        self.captured = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, stmt):
        self.captured = stmt
        return _Result([_KRow(c, d) for c, d in self._pairs])


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
    from api.briefing import pipeline

    sess = _FakeSession(pairs)
    monkeypatch.setattr(pipeline, "embed_texts", lambda texts: [[0.1, 0.2, 0.3]])
    monkeypatch.setattr(pipeline, "db_session", lambda: sess)
    monkeypatch.setattr("api.services.llm_client.get_llm", lambda: fake_llm)
    return sess


def test_search_knowledge_rerank_reorders(monkeypatch):
    from api.briefing import pipeline

    pairs = [                                        # 코사인 오름차순(=관련도 내림차순)
        (_KChunk("A", "tA", {"age": "30"}), 0.10),
        (_KChunk("B", "tB"), 0.20),
        (_KChunk("C", "tC"), 0.30),
        (_KChunk("D", "tD"), 0.40),
    ]
    fake = _FakeLLM(ranked=[(2, 0.99), (0, 0.80), (3, 0.55)])   # C, A, D 로 재정렬
    _wire(monkeypatch, pairs, fake)

    out = pipeline.search_knowledge("q", k=3)

    assert [r["text"] for r in out] == ["C", "A", "D"]         # 리랭커 순서로 재정렬
    assert [r["title"] for r in out] == ["tC", "tA", "tD"]     # title 보존
    assert [r["score"] for r in out] == [0.99, 0.80, 0.55]     # 코사인 → 리랭크 점수
    assert out[1]["meta"] == {"age": "30"}                     # A 의 meta 보존
    assert fake.calls[0][1] == ["A", "B", "C", "D"]            # 후보 4개 전부 리랭커에
    assert fake.calls[0][2] == 3                               # top_n == k


def test_search_knowledge_rerank_failure_falls_back_to_cosine(monkeypatch):
    from api.briefing import pipeline

    pairs = [
        (_KChunk("A"), 0.10),
        (_KChunk("B"), 0.20),
        (_KChunk("C"), 0.30),
        (_KChunk("D"), 0.40),
    ]
    fake = _FakeLLM(boom=True)                       # 리랭커가 LLMError 로 죽는다
    _wire(monkeypatch, pairs, fake)

    out = pipeline.search_knowledge("q", k=3)

    assert [r["text"] for r in out] == ["A", "B", "C"]         # 코사인 순서 top-k 폴백
    assert out[0]["score"] == pytest.approx(0.90)              # 코사인 점수(1.0-0.10) 유지
    assert len(fake.calls) == 1                                # 리랭커를 시도는 했다


def test_search_knowledge_small_candidate_set_skips_rerank(monkeypatch):
    from api.briefing import pipeline

    pairs = [(_KChunk("A"), 0.10), (_KChunk("B"), 0.20)]       # 후보 2개 ≤ k=5(기본)
    fake = _FakeLLM(ranked=[(0, 0.9)])
    _wire(monkeypatch, pairs, fake)

    out = pipeline.search_knowledge("q")

    assert [r["text"] for r in out] == ["A", "B"]              # 코사인 순서 그대로
    assert out[0]["score"] == pytest.approx(0.90)
    assert fake.calls == []                                    # 리랭커 호출 자체가 없다


def test_search_knowledge_corpus_hard_filters(monkeypatch):
    from api.briefing import pipeline

    pairs = [(_KChunk("A"), 0.10), (_KChunk("B"), 0.20)]       # ≤ k → 리랭커 스킵, WHERE 만 확인
    fake = _FakeLLM(ranked=[])
    sess = _wire(monkeypatch, pairs, fake)

    pipeline.search_knowledge("q", corpus="personas")

    assert sess.captured.compile().params.get("corpus_1") == "personas"   # WHERE corpus 하드필터
    assert fake.calls == []


def test_search_knowledge_meta_filters_add_where(monkeypatch):
    from api.briefing import pipeline

    pairs = [(_KChunk("A"), 0.10)]
    fake = _FakeLLM(ranked=[])
    sess = _wire(monkeypatch, pairs, fake)

    pipeline.search_knowledge("q", meta_filters={"age": 30, "sex": "F"})

    params = sess.captured.compile().params
    # JSONB 동등 하드필터: meta ->> 'age' = '30'  (int 30 → str "30" 로 강제됨을 함께 검증)
    assert params.get("meta_1") == "age" and params.get("param_1") == "30"
    assert params.get("meta_2") == "sex" and params.get("param_2") == "F"


def test_search_knowledge_drops_out_of_range_and_clamps_to_k(monkeypatch):
    from api.briefing import pipeline

    pairs = [                                        # 후보 4개(> k) → 리랭커 경로 진입
        (_KChunk("A"), 0.10),
        (_KChunk("B"), 0.20),
        (_KChunk("C"), 0.30),
        (_KChunk("D"), 0.40),
    ]
    # 리랭커가 범위 밖 index(99)와 k 초과 개수를 돌려줘도: 범위 밖은 버리고 k 로 클램프
    fake = _FakeLLM(ranked=[(0, 0.9), (99, 0.8), (1, 0.7), (0, 0.6)])
    _wire(monkeypatch, pairs, fake)

    out = pipeline.search_knowledge("q", k=2)

    assert len(out) <= 2                                       # k 로 클램프
    assert all(isinstance(r, dict) and "text" in r for r in out)   # 유효 dict 만(범위 밖 제거)
    assert [r["text"] for r in out] == ["A", "B"]             # 99 스킵 → 상위 k=2
    assert [r["score"] for r in out] == [0.9, 0.7]


# --- rows_from_df (ingest CLI 순수 변환부) ------------------------------------

def test_rows_from_df_concatenates_skips_blanks_and_extracts_meta():
    pd = pytest.importorskip("pandas")   # pandas 는 오프라인 ingest 전용 dep — CI(미설치)에선 스킵

    ing = _load(_SCRIPTS / "ingest_knowledge.py")
    df = pd.DataFrame([
        {"a": "머리말", "b": "", "c": "본문", "name": "김철수", "age": 30, "sex": "M"},
        {"a": "", "b": "둘째", "c": "", "name": "", "age": 25, "sex": "F"},
    ])
    rows = ing.rows_from_df(df, "personas", ["a", "b", "c"],
                            meta_cols=["age", "sex"], title_col="name")

    assert rows[0]["text"] == "머리말\n본문"          # 빈 b 는 건너뛰고 \n 로 연결
    assert rows[1]["text"] == "둘째"                  # a·c 비어 b 만 남는다
    assert rows[0]["title"] == "김철수"               # title_col 매핑
    assert rows[1]["title"] == ""                     # 빈 이름 → 빈 title
    assert rows[0]["meta"] == {"age": 30, "sex": "M"}  # meta dict 추출(numpy → 파이썬 int)
    assert rows[0]["corpus"] == "personas"


def test_main_ingests_rows_with_embeddings(monkeypatch):
    """main() dry-run — read_parquet·embed_texts·db_session 을 가짜로, insert 를 검증."""
    pd = pytest.importorskip("pandas")   # pandas 는 오프라인 ingest 전용 dep — CI(미설치)에선 스킵

    ing = _load(_SCRIPTS / "ingest_knowledge.py")
    df = pd.DataFrame([
        {"persona": "페르소나1", "age": 30},
        {"persona": "페르소나2", "age": 40},
    ])
    monkeypatch.setattr("pandas.read_parquet", lambda path: df)
    monkeypatch.setattr("api.services.embeddings.embed_texts",
                        lambda texts: [[0.0, 0.0, 0.0, 0.0] for _ in texts])

    class _S:
        def __init__(self):
            self.added = []

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def add(self, row):
            self.added.append(row)

        def commit(self):
            pass

    fake = _S()
    monkeypatch.setattr("api.services.db.db_session", lambda: fake)

    ing.main(["--parquet", "x.parquet", "--corpus", "personas",
              "--text-cols", "persona", "--meta-cols", "age"])

    assert len(fake.added) == 2                                # 두 행 모두 insert
    assert all(row.embedding == [0.0, 0.0, 0.0, 0.0] for row in fake.added)   # 임베딩 부착
    assert {row.corpus for row in fake.added} == {"personas"}
    assert fake.added[0].meta == {"age": 30}                   # meta 함께 저장
    assert fake.added[0].id.startswith("k_")                   # new_id("k_")


def test_main_replace_deletes_corpus_before_insert(monkeypatch):
    """--replace 면 insert 전에 해당 corpus 대상 delete 문이 먼저 실행된다(멱등 재적재)."""
    pd = pytest.importorskip("pandas")   # pandas 는 오프라인 ingest 전용 dep — CI(미설치)에선 스킵

    ing = _load(_SCRIPTS / "ingest_knowledge.py")
    df = pd.DataFrame([{"persona": "페르소나1", "age": 30}])
    monkeypatch.setattr("pandas.read_parquet", lambda path: df)
    monkeypatch.setattr("api.services.embeddings.embed_texts",
                        lambda texts: [[0.0, 0.0, 0.0, 0.0] for _ in texts])

    events = []   # (종류, 인자) 시간순 로그 — delete 가 insert 보다 먼저인지 검증

    class _S:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, stmt):
            events.append(("execute", stmt))

        def add(self, row):
            events.append(("add", row))

        def commit(self):
            events.append(("commit", None))

    monkeypatch.setattr("api.services.db.db_session", lambda: _S())

    ing.main(["--parquet", "x.parquet", "--corpus", "personas",
              "--text-cols", "persona", "--meta-cols", "age", "--replace"])

    kinds = [e[0] for e in events]
    assert "execute" in kinds and "add" in kinds
    assert kinds.index("execute") < kinds.index("add")         # delete 가 insert 보다 먼저
    delete_stmt = events[kinds.index("execute")][1]
    compiled = delete_stmt.compile()
    assert "DELETE FROM knowledge_chunks" in str(compiled)     # DELETE 문
    assert compiled.params.get("corpus_1") == "personas"       # 해당 corpus 대상


def test_main_without_replace_issues_no_delete(monkeypatch):
    """플래그 없으면(기본) delete 없이 append — 기존 동작 불변 회귀."""
    pd = pytest.importorskip("pandas")   # pandas 는 오프라인 ingest 전용 dep — CI(미설치)에선 스킵

    ing = _load(_SCRIPTS / "ingest_knowledge.py")
    df = pd.DataFrame([{"persona": "페르소나1", "age": 30}])
    monkeypatch.setattr("pandas.read_parquet", lambda path: df)
    monkeypatch.setattr("api.services.embeddings.embed_texts",
                        lambda texts: [[0.0, 0.0, 0.0, 0.0] for _ in texts])

    executed = []

    class _S:
        def __init__(self):
            self.added = []

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, stmt):
            executed.append(stmt)

        def add(self, row):
            self.added.append(row)

        def commit(self):
            pass

    fake = _S()
    monkeypatch.setattr("api.services.db.db_session", lambda: fake)

    ing.main(["--parquet", "x.parquet", "--corpus", "personas",
              "--text-cols", "persona", "--meta-cols", "age"])

    assert executed == []                                      # delete 없음(append 동작 유지)
    assert len(fake.added) == 1
