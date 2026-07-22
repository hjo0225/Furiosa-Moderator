"""웹 리서치 — Apify 조합(SERP → 선택 → 본문 크롤). select-then-crawl.

검색은 apify/google-search-scraper, 본문은 apify/website-content-crawler.
Apify 호출은 _run_actor 한 곳으로 모으고 테스트는 그 경계를 monkeypatch 한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config import get_settings

log = logging.getLogger(__name__)

SEARCH_ACTOR = "apify/google-search-scraper"
CRAWL_ACTOR = "apify/website-content-crawler"
RESULTS_PER_QUERY = 5


class ResearchError(RuntimeError):
    """리서치 실패 — 라우터가 502 로 변환."""


@dataclass
class Candidate:
    angle: str
    title: str
    url: str
    snippet: str


def _run_actor(actor_id: str, run_input: dict) -> list[dict]:
    """Apify actor 동기 실행 → dataset items. 테스트는 이 경계를 monkeypatch."""
    token = get_settings().apify_token
    if not token:
        raise ResearchError("APIFY_TOKEN 이 설정되지 않았습니다.")
    from apify_client import ApifyClient

    client = ApifyClient(token)
    run = client.actor(actor_id).call(run_input=run_input)
    if not run or not run.get("defaultDatasetId"):
        raise ResearchError(f"Apify actor 실행 실패: {actor_id}")
    return client.dataset(run["defaultDatasetId"]).list_items().items


def search(slot_queries: dict[str, list[str]]) -> list[Candidate]:
    """슬롯별 쿼리 → SERP 후보. URL 중복은 먼저 나온 슬롯 각도로 귀속."""
    q_angle: dict[str, str] = {}
    ordered: list[str] = []
    for angle, qs in slot_queries.items():
        for q in qs:
            if q and q not in q_angle:
                q_angle[q] = angle
                ordered.append(q)
    if not ordered:
        return []

    items = _run_actor(SEARCH_ACTOR, {
        "queries": "\n".join(ordered),
        "maxPagesPerQuery": 1,
        "resultsPerPage": RESULTS_PER_QUERY,
        "languageCode": "ko",
    })

    first_slot = next(iter(slot_queries), "현상")
    out: list[Candidate] = []
    seen: set[str] = set()
    for i, item in enumerate(items):
        term = (item.get("searchQuery") or {}).get("term") or (ordered[i] if i < len(ordered) else "")
        angle = q_angle.get(term, first_slot)
        for res in (item.get("organicResults") or []):
            url = res.get("url") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(Candidate(
                angle=angle, title=res.get("title") or url,
                url=url, snippet=res.get("description") or "",
            ))
    return out


def crawl(urls: list[str]) -> dict[str, str]:
    """선택 URL 본문 크롤. 부분 실패 허용 — 성공분만 반환."""
    if not urls:
        return {}
    items = _run_actor(CRAWL_ACTOR, {
        "startUrls": [{"url": u} for u in urls],
        "maxCrawlDepth": 0,
        "maxCrawlPages": len(urls),
    })
    out: dict[str, str] = {}
    for it in items:
        url = it.get("url") or ""
        text = (it.get("text") or it.get("markdown") or "").strip()
        if url and text:
            out[url] = text
    return out
