"""n8n 경유 Discord 알림 단위테스트 (네트워크·DB 없이 monkeypatch)."""
from __future__ import annotations


def test_settings_reads_n8n_webhook_url(monkeypatch):
    from api.config import get_settings

    monkeypatch.setenv("N8N_WEBHOOK_URL", "https://n8n.example/webhook/xyz")
    monkeypatch.setenv("PUBLIC_WEB_BASE", "https://web.example")
    get_settings.cache_clear()
    s = get_settings()
    assert s.n8n_webhook_url == "https://n8n.example/webhook/xyz"
    assert s.public_web_base == "https://web.example"
    get_settings.cache_clear()   # 다른 테스트에 캐시가 새지 않게
