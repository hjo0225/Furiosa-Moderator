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


def test_build_payload_shape(monkeypatch):
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

    class _FakeLLM:
        def text(self, system, user, **kw):
            return "이 응답자는 야근 시 배달앱을 쓴다.", {}
    monkeypatch.setattr(notify, "get_llm", lambda: _FakeLLM())

    payload = notify._build_payload("p_1", "s_1", Settings(public_web_base="https://web.example"))

    assert payload["event"] == "session.completed"
    assert payload["project"] == {"id": "p_1", "title": "배달앱 조사", "topic": "배달앱 사용 경험"}
    assert payload["session"]["asked"] == 2
    assert payload["session"]["respondent_ref"] and payload["session"]["respondent_ref"] != "r_abc"
    assert payload["metrics"]["coverage"] == {"covered": ["q1", "q2"], "total": 3}
    assert payload["metrics"]["emotion"] == {"긍정": 1, "중립": 1}
    assert payload["summary"] == "이 응답자는 야근 시 배달앱을 쓴다."
    assert "응답자: 야근할 때 시켜요" in payload["transcript"]
    assert "진행자: 어떤 앱을 쓰세요?" in payload["transcript"]
    assert payload["dashboard_url"] == "https://web.example/projects/p_1"


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
    assert payload["summary"] is None
    assert payload["transcript"]   # 전사는 그대로


def test_build_payload_none_when_session_missing(monkeypatch):
    from api.services import notify
    from api.config import Settings
    monkeypatch.setattr(notify.store, "get_session", lambda pid, sid: None)
    assert notify._build_payload("p_1", "s_x", Settings()) is None
