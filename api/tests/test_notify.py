"""Discord 직접 웹훅 알림 단위테스트 (네트워크·DB 없이 monkeypatch)."""
from __future__ import annotations

import json


def test_settings_reads_discord_webhook_url(monkeypatch):
    from api.config import get_settings

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/xyz")
    monkeypatch.setenv("PUBLIC_WEB_BASE", "https://web.example")
    get_settings.cache_clear()
    s = get_settings()
    assert s.discord_webhook_url == "https://discord.com/api/webhooks/xyz"
    assert s.public_web_base == "https://web.example"
    get_settings.cache_clear()   # 다른 테스트에 캐시가 새지 않게


def _fake_turns():
    from api.schemas.models import Turn
    return [
        Turn(role="moderator", text="배달앱을 주로 어떤 목적으로 쓰세요?", question_id="q1"),
        Turn(role="respondent", text="야근할 때 시켜요", emotion="긍정"),
        Turn(role="moderator", text="어떤 앱을 쓰세요?", question_id="q2"),
        Turn(role="respondent", text="배민이요", emotion="중립"),
    ]


def _patch_store(monkeypatch, sess, proj, guide, turns):
    from api.services import notify
    monkeypatch.setattr(notify.store, "get_session", lambda pid, sid: sess)
    monkeypatch.setattr(notify.store, "get_project", lambda pid: proj)
    monkeypatch.setattr(notify.store, "get_guide", lambda pid: guide)
    monkeypatch.setattr(notify.store, "list_turns", lambda pid, sid: turns)
    monkeypatch.setattr(notify.store, "update_session", lambda pid, sid, patch: None)


def _patch_llm(monkeypatch, text):
    from api.services import notify

    class _LLM:
        def text(self, system, user, **kw):
            return text, {}
    monkeypatch.setattr(notify, "get_llm", lambda: _LLM())


def test_build_payload_discord_embed(monkeypatch):
    from api.services import notify
    from api.config import Settings
    from api.schemas.models import Session, Project, InterviewGuide, GuideQuestion

    sess = Session(id="s_1", project_id="p_1", respondent_id="r_abc",
                   status="completed", asked=2, covered=["q1", "q2"])
    proj = Project(id="p_1", title="배달앱 조사", topic="배달앱 사용 경험")
    guide = InterviewGuide(goal="배달앱 사용 경험 파악", questions=[
        GuideQuestion(id="q1", text="a"), GuideQuestion(id="q2", text="b"),
        GuideQuestion(id="q3", text="c")])
    _patch_store(monkeypatch, sess, proj, guide, _fake_turns())
    _patch_llm(monkeypatch, "이 응답자는 야근 시 배달앱을 쓴다.")

    payload = notify._build_payload("p_1", "s_1", Settings(public_web_base="https://web.example"))

    embed = payload["embeds"][0]
    assert "배달앱 조사" in embed["title"]
    assert embed["description"] == "이 응답자는 야근 시 배달앱을 쓴다."
    assert embed["url"] == "https://web.example/projects/p_1"
    fields = {f["name"]: f["value"] for f in embed["fields"]}
    assert fields["감정"] == "긍정 1 · 중립 1"
    assert fields["커버리지"] == "2/3"
    assert fields["진행자 질문"] == "2"
    assert "응답자: 야근할 때 시켜요" in payload["content"]
    assert "진행자: 어떤 앱을 쓰세요?" in payload["content"]
    # 응답자 원 식별자는 payload 어디에도 없어야 한다(PII)
    assert "r_abc" not in json.dumps(payload, ensure_ascii=False)


def test_build_payload_summary_fallback_on_llm_error(monkeypatch):
    from api.services import notify
    from api.services.llm_client import LLMError
    from api.config import Settings
    from api.schemas.models import Session, Project, InterviewGuide

    sess = Session(id="s_1", project_id="p_1", respondent_id="r_x", status="completed")
    _patch_store(monkeypatch, sess, Project(id="p_1", topic="주제"),
                 InterviewGuide(goal="목표"), _fake_turns())

    class _BoomLLM:
        def text(self, system, user, **kw):
            raise LLMError("boom")
    monkeypatch.setattr(notify, "get_llm", lambda: _BoomLLM())

    payload = notify._build_payload("p_1", "s_1", Settings())
    assert payload["embeds"][0]["description"] == "(요약 없음)"
    assert payload["content"]   # 전사는 그대로


def test_build_payload_omits_url_when_base_relative(monkeypatch):
    from api.services import notify
    from api.config import Settings
    from api.schemas.models import Session, Project, InterviewGuide

    sess = Session(id="s_1", project_id="p_1", status="completed")
    _patch_store(monkeypatch, sess, Project(id="p_1", topic="주제"),
                 InterviewGuide(goal="목표"), _fake_turns())
    _patch_llm(monkeypatch, "요약")

    payload = notify._build_payload("p_1", "s_1", Settings())   # public_web_base 비어있음
    assert "url" not in payload["embeds"][0]


def test_build_payload_truncates_long_transcript(monkeypatch):
    from api.services import notify
    from api.config import Settings
    from api.schemas.models import Session, Project, InterviewGuide, Turn

    long_turns = [Turn(role="respondent", text="가" * 5000, emotion="중립")]
    sess = Session(id="s_1", project_id="p_1", status="completed")
    _patch_store(monkeypatch, sess, Project(id="p_1", topic="주제"),
                 InterviewGuide(goal="목표"), long_turns)
    _patch_llm(monkeypatch, None)

    payload = notify._build_payload("p_1", "s_1", Settings())
    assert len(payload["content"]) <= 2000   # Discord content 한도


def test_build_payload_none_when_session_missing(monkeypatch):
    from api.services import notify
    from api.config import Settings
    monkeypatch.setattr(notify.store, "get_session", lambda pid, sid: None)
    assert notify._build_payload("p_1", "s_x", Settings()) is None


def _capture_post(monkeypatch):
    from api.services import notify
    captured = {}

    class _R:
        def raise_for_status(self): pass
    def _post(url, json, timeout):
        captured["url"] = url
        return _R()
    monkeypatch.setattr(notify.httpx, "post", _post)
    monkeypatch.setattr(notify, "_build_payload",
                        lambda pid, sid, settings: {"content": "x", "embeds": []})
    return captured


def test_emit_routes_to_project_webhook_when_set(monkeypatch):
    from api.services import notify
    from api.config import Settings
    from api.schemas.models import Project

    monkeypatch.setattr(notify, "get_settings", lambda: Settings(discord_webhook_url="https://default"))
    monkeypatch.setattr(notify.store, "get_project",
                        lambda pid: Project(id="p_1", topic="t", discord_webhook_url="https://project"))
    captured = _capture_post(monkeypatch)

    notify.emit_session_completed("p_1", "s_1")
    assert captured["url"] == "https://project"   # 프로젝트 웹훅 우선


def test_emit_falls_back_to_default_webhook(monkeypatch):
    from api.services import notify
    from api.config import Settings
    from api.schemas.models import Project

    monkeypatch.setattr(notify, "get_settings", lambda: Settings(discord_webhook_url="https://default"))
    monkeypatch.setattr(notify.store, "get_project",
                        lambda pid: Project(id="p_1", topic="t"))   # discord_webhook_url 비어있음
    captured = _capture_post(monkeypatch)

    notify.emit_session_completed("p_1", "s_1")
    assert captured["url"] == "https://default"


def test_emit_skips_when_no_webhook_anywhere(monkeypatch):
    from api.services import notify
    from api.config import Settings
    from api.schemas.models import Project

    monkeypatch.setattr(notify, "get_settings", lambda: Settings(discord_webhook_url=""))
    monkeypatch.setattr(notify.store, "get_project", lambda pid: Project(id="p_1", topic="t"))
    calls = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **k: calls.append(1))

    notify.emit_session_completed("p_1", "s_1")
    assert calls == []


def test_emit_skips_when_url_unset(monkeypatch):
    from api.services import notify
    from api.config import Settings

    monkeypatch.setattr(notify, "get_settings", lambda: Settings(discord_webhook_url=""))
    monkeypatch.setattr(notify.store, "get_project", lambda pid: None)
    calls = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **k: calls.append((a, k)))

    notify.emit_session_completed("p_1", "s_1")
    assert calls == []   # URL 없으면 아무 것도 안 보냄


def test_emit_posts_payload(monkeypatch):
    from api.services import notify
    from api.config import Settings

    monkeypatch.setattr(notify, "get_settings",
                        lambda: Settings(discord_webhook_url="https://discord.com/api/webhooks/xyz"))
    monkeypatch.setattr(notify.store, "get_project", lambda pid: None)
    monkeypatch.setattr(notify, "_build_payload",
                        lambda pid, sid, settings: {"content": "x", "embeds": []})

    captured = {}

    class _Resp:
        def raise_for_status(self): pass
    def _fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _Resp()
    monkeypatch.setattr(notify.httpx, "post", _fake_post)

    notify.emit_session_completed("p_1", "s_1")
    assert captured["url"] == "https://discord.com/api/webhooks/xyz"
    assert captured["json"] == {"content": "x", "embeds": []}


def test_emit_swallows_post_errors(monkeypatch):
    from api.services import notify
    from api.config import Settings

    monkeypatch.setattr(notify, "get_settings",
                        lambda: Settings(discord_webhook_url="https://discord.com/api/webhooks/xyz"))
    monkeypatch.setattr(notify.store, "get_project", lambda pid: None)
    monkeypatch.setattr(notify, "_build_payload",
                        lambda pid, sid, settings: {"content": "x", "embeds": []})

    def _boom(url, json, timeout):
        raise RuntimeError("network down")
    monkeypatch.setattr(notify.httpx, "post", _boom)
    monkeypatch.setattr(notify.time, "sleep", lambda *_: None)   # 재시도 백오프 빨리감기

    # 예외가 밖으로 새지 않아야 한다 — 실패해도 조용히 반환
    notify.emit_session_completed("p_1", "s_1")


def test_emit_does_not_log_webhook_url_on_http_error(monkeypatch, caplog):
    import logging
    import httpx
    from api.services import notify
    from api.config import Settings

    url = "https://discord.com/api/webhooks/SECRET-abc123"
    monkeypatch.setattr(notify, "get_settings", lambda: Settings(discord_webhook_url=url))
    monkeypatch.setattr(notify.store, "get_project", lambda pid: None)
    monkeypatch.setattr(notify, "_build_payload",
                        lambda pid, sid, settings: {"content": "x", "embeds": []})
    monkeypatch.setattr(notify.time, "sleep", lambda *_: None)

    req = httpx.Request("POST", url)
    resp = httpx.Response(404, request=req)

    def _boom(u, json, timeout):
        resp.raise_for_status()   # 실제 httpx 메시지에 URL 이 포함된다
    monkeypatch.setattr(notify.httpx, "post", _boom)

    with caplog.at_level(logging.WARNING):
        notify.emit_session_completed("p_1", "s_1")

    assert "SECRET-abc123" not in caplog.text
    assert url not in caplog.text


def test_submit_schedules_notification(monkeypatch):
    from fastapi import BackgroundTasks
    from api.routers import public
    from api.schemas.models import Session

    sess = Session(id="s_1", project_id="p_1", status="active")
    monkeypatch.setattr(public.store, "get_session", lambda pid, sid: sess)
    monkeypatch.setattr(public.store, "update_session", lambda pid, sid, patch: None)

    bt = BackgroundTasks()
    public.submit("p_1", "s_1", bt)

    assert any(t.func is public.notify.emit_session_completed for t in bt.tasks)
    assert any(t.args == ("p_1", "s_1") for t in bt.tasks)


def test_submit_idempotent_no_duplicate_notification(monkeypatch):
    from fastapi import BackgroundTasks
    from api.routers import public
    from api.schemas.models import Session

    done = Session(id="s_1", project_id="p_1", status="completed")
    monkeypatch.setattr(public.store, "get_session", lambda pid, sid: done)

    bt = BackgroundTasks()
    public.submit("p_1", "s_1", bt)
    assert bt.tasks == []   # 이미 completed — 알림 재발사 금지
