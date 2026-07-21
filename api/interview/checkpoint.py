"""체크포인터 배선 — PostgresSaver(psycopg3) 를 도메인 DB 와 같은 Postgres 에 붙인다.

접속 경로가 도메인 DB(pg8000+커넥터)와 다른 이유: Cloud SQL Python Connector 는
psycopg3 드라이버를 지원하지 않는다. 그래서
- 로컬:      DATABASE_URL (postgresql+pg8000:// 접두어는 psycopg 용으로 정규화)
- Cloud Run: --add-cloudsql-instances 유닉스 소켓 (host=/cloudsql/<ICN>) — 배포 플래그 필요
"""
from __future__ import annotations

import os
from functools import lru_cache


def conn_string() -> str:
    icn = os.environ.get("INSTANCE_CONNECTION_NAME", "")
    if icn:
        user = os.environ.get("DB_USER", "postgres")
        pw = os.environ.get("DB_PASSWORD", "")
        db = os.environ.get("DB_NAME", "mindlens")
        return f"host=/cloudsql/{icn} dbname={db} user={user} password={pw}"
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("체크포인터: INSTANCE_CONNECTION_NAME 또는 DATABASE_URL 이 필요합니다.")
    for prefix in ("postgresql+pg8000://", "postgres+pg8000://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


@lru_cache
def get_checkpointer():
    """PostgresSaver 싱글톤 — 커넥션 풀 + setup(멱등). 실패는 호출부(engine.ready)가 처리."""
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(
        conn_string(),
        min_size=0,
        max_size=4,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    saver = PostgresSaver(pool)
    saver.setup()  # 체크포인트 테이블 생성(멱등)
    return saver
