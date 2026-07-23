"""테스트 공통 픽스처.

레이트리밋(api/main.py)은 프로세스 전역 dict 에 히트를 쌓는다 — 60초 창에 IP 당 30회.
TestClient 는 모든 테스트가 같은 IP(testserver)로 보이므로, 한 스위트를 돌리면 히트가
누적돼 뒤쪽 테스트가 429 로 떨어진다. 실패가 "그 테스트의 버그"처럼 보이지만 원인은
앞선 테스트가 예산을 먹은 것이라, 새 테스트를 추가할 때마다 엉뚱한 파일이 빨개진다.
매 테스트 전에 비워 그 연결을 끊는다.
"""
from __future__ import annotations

import asyncio
import sys

import pytest

import api.main as main

# Windows 기본 ProactorEventLoop 는 GC 될 때 self-pipe 정리에서 터진다
# (OSError WinError 10014 / AttributeError '_ssock'). TestClient 가 테스트마다 루프를
# 만들고 버리므로 이 unraisable 예외가 그때 돌던 아무 테스트에나 붙어 스위트가 무작위로
# 빨개진다. Selector 루프는 그 self-pipe 경로를 안 쓴다. 리눅스(CI)에서는 no-op.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    main._hits.clear()
    yield
    main._hits.clear()
