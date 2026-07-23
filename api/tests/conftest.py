"""테스트 공통 픽스처.

레이트리밋(api/main.py)은 프로세스 전역 dict 에 히트를 쌓는다 — 60초 창에 IP 당 30회.
TestClient 는 모든 테스트가 같은 IP(testserver)로 보이므로, 한 스위트를 돌리면 히트가
누적돼 뒤쪽 테스트가 429 로 떨어진다. 실패가 "그 테스트의 버그"처럼 보이지만 원인은
앞선 테스트가 예산을 먹은 것이라, 새 테스트를 추가할 때마다 엉뚱한 파일이 빨개진다.
매 테스트 전에 비워 그 연결을 끊는다.
"""
from __future__ import annotations

import pytest

import api.main as main


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    main._hits.clear()
    yield
    main._hits.clear()
