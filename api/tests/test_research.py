"""Apify 리서치 — search 슬롯 귀속·dedup, crawl 부분 실패 (네트워크 없이)."""
from __future__ import annotations

from api.services import research


def test_search_maps_slot_and_dedups(monkeypatch):
    fake_items = [
        {"searchQuery": {"term": "q1"}, "organicResults": [
            {"title": "A", "url": "http://a", "description": "sa"},
            {"title": "B", "url": "http://b", "description": "sb"}]},
        {"searchQuery": {"term": "q2"}, "organicResults": [
            {"title": "A2", "url": "http://a", "description": "dup"},   # 중복 URL
            {"title": "C", "url": "http://c", "description": "sc"}]},
    ]
    monkeypatch.setattr(research, "_run_actor", lambda actor, run_input: fake_items)
    cands = research.search({"현상": ["q1"], "활용": ["q2"]})
    assert [c.url for c in cands] == ["http://a", "http://b", "http://c"]
    assert cands[0].angle == "현상"     # q1 슬롯
    assert cands[2].angle == "활용"     # q2 슬롯


def test_crawl_skips_empty(monkeypatch):
    monkeypatch.setattr(research, "_run_actor", lambda actor, run_input: [
        {"url": "http://a", "text": "본문A"},
        {"url": "http://b", "text": ""},        # 빈 본문 → 스킵
    ])
    assert research.crawl(["http://a", "http://b"]) == {"http://a": "본문A"}


def test_search_empty_returns_empty(monkeypatch):
    monkeypatch.setattr(research, "_run_actor", lambda actor, run_input: [])
    assert research.search({}) == []
