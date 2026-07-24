"""글로벌 지식 풀 적재 CLI (RAG-5) — parquet → knowledge_chunks(pgvector).

앱이 import 하지 않는 독립 실행 스크립트다. 대규모 사전 임베딩 데이터셋(예: 합성
페르소나)을 knowledge_chunks 전역 풀에 한 번에 밀어 넣는 범용 로더. 순수 변환
(rows_from_df)과 부작용(임베딩·DB insert)을 분리해 변환부만 단위 테스트한다.

페르소나 시드(personas_1k.parquet — uuid/age/sex/marital_status/education_level/
occupation/district/province/persona/embed_text/embedding, 1,000행)를 넣는 정본 명령:

  python scripts/ingest_knowledge.py --parquet personas_1k.parquet --corpus personas \\
      --text-cols embed_text --title-col persona \\
      --meta-cols age,sex,province,district,occupation,education_level,marital_status --replace

컬럼 선택 근거 — services/audience.collect_personas 가 `title or text` 를 200자로 잘라
[대상 청중] 불릿으로 쓴다. `persona`(한 줄 요약, ~81자)가 title 로 딱 맞고 검색 본문은
`embed_text`(전체 서술)여야 리콜이 산다. 하드필터는 age(숫자 범위)·sex 뿐이고 시드의
sex 값이 "남자"/"여자" 라 AudienceSpec 의 Literal 과 그대로 맞는다.

시드의 `embedding` 열은 쓰지 않고 여기서 다시 임베딩한다 — 검색 질의는 우리 임베드
엔드포인트로 벡터화되므로 코퍼스도 같은 모델이어야 한다. (2026-07-24 확인: 시드 벡터와
우리 출력의 코사인이 1.0000/1024dim 으로 동일 모델이었지만, 그 사실이 계약은 아니다.)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _blank(v) -> bool:
    """빈 셀 판정 — None·NaN·공백 문자열(pandas 미설치 없이도 동작)."""
    if v is None:
        return True
    if isinstance(v, float) and v != v:   # NaN(자기 자신과 다른 유일한 값)
        return True
    return str(v).strip() == ""


def _clean(v):
    """meta 값 정규화 — numpy 스칼라를 파이썬 네이티브로(JSONB 직렬화 안전)."""
    item = getattr(v, "item", None)
    return item() if callable(item) else v


def rows_from_df(df, corpus, text_cols, meta_cols=(), title_col=None) -> list[dict]:
    """DataFrame → [{"corpus","title","text","meta"}] (임베딩 없음, 순수 함수).

    text_cols 는 "\\n" 로 이어 붙이되 빈 셀은 건너뛴다. meta_cols 는 동등 하드필터
    재료로 meta dict 에 담는다(빈 값 제외). title_col 이 있으면 title 로 매핑한다.
    """
    rows: list[dict] = []
    for _, r in df.iterrows():
        parts = [str(r[c]).strip() for c in text_cols if c in df.columns and not _blank(r[c])]
        meta = {c: _clean(r[c]) for c in meta_cols if c in df.columns and not _blank(r[c])}
        title = str(r[title_col]).strip() if title_col and title_col in df.columns \
            and not _blank(r[title_col]) else ""
        rows.append({"corpus": corpus, "title": title, "text": "\n".join(parts), "meta": meta})
    return rows


def _split(csv: str | None) -> list[str]:
    return [c.strip() for c in (csv or "").split(",") if c.strip()]


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="글로벌 지식 풀 적재 (parquet → knowledge_chunks)")
    p.add_argument("--parquet", required=True)
    p.add_argument("--corpus", required=True)
    p.add_argument("--text-cols", required=True, help="쉼표구분; \\n 로 이어 붙여 text 로")
    p.add_argument("--title-col", default=None)
    p.add_argument("--meta-cols", default="")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--replace", action="store_true",
                   help="적재 전 해당 corpus 의 기존 행을 지운다(멱등 재적재)")
    args = p.parse_args(argv)

    import pandas as pd

    from api.services.db import KnowledgeChunkRow, db_session
    from api.services.embeddings import embed_texts
    from api.services.store import new_id

    df = pd.read_parquet(args.parquet)
    if args.limit is not None:
        df = df.head(args.limit)
    rows = rows_from_df(df, args.corpus, _split(args.text_cols),
                        meta_cols=_split(args.meta_cols), title_col=args.title_col)
    rows = [r for r in rows if r["text"]]     # 본문 없는 행은 버린다(임베딩 낭비 방지)
    print(f"{len(rows)} rows to ingest (corpus={args.corpus})")

    if args.replace:                          # 멱등 재적재 — 기존 코퍼스 행을 먼저 지운다(자체 커밋 트랜잭션)
        from sqlalchemy import delete
        with db_session() as s:
            s.execute(delete(KnowledgeChunkRow).where(KnowledgeChunkRow.corpus == args.corpus))
            s.commit()

    inserted = 0
    with db_session() as s:
        for i in range(0, len(rows), args.batch):
            batch = rows[i:i + args.batch]
            vecs = embed_texts([r["text"] for r in batch])
            for r, v in zip(batch, vecs):
                s.add(KnowledgeChunkRow(id=new_id("k_"), corpus=r["corpus"], title=r["title"],
                                        text=r["text"], meta=r["meta"], embedding=v))
            s.commit()
            inserted += len(batch)
            print(f"  {inserted}/{len(rows)}")
    print(f"done — {inserted} chunks into knowledge_chunks")


if __name__ == "__main__":
    main()
