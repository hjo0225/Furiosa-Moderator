"""저장소 계층 — Cloud SQL(Postgres).

Firestore 에서 옮겨왔다. **함수 시그니처는 그대로 유지**한다 — 라우터·모더레이터는
저장소가 바뀐 걸 모른다. project_id 를 계속 받는 것도 그래서다(Postgres 에서는
session_id 만으로 찾을 수 있지만, 인자로 받은 project_id 와 대조해 다른 프로젝트의
세션에 접근하는 걸 막는 데 쓴다 — PRD 9절 '자신의 프로젝트 데이터만 접근').
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from ..schemas.models import (
    ConsentLog,
    GuideQuestion,
    Insight,
    InterviewGuide,
    Project,
    Session,
    ThemeInsight,
    Turn,
)
from .db import GuideRow, InsightRow, ProjectRow, SessionRow, TurnRow, db_session


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


# --- 행 ↔ 스키마 변환 ---------------------------------------------------------

def _project(r: ProjectRow, sessions: int = 0, completed: int = 0) -> Project:
    return Project(
        id=r.id, owner=r.owner, title=r.title, topic=r.topic, target=r.target,
        material_text=r.material_text, status=r.status, created_at=r.created_at,
        session_count=sessions, completed_count=completed,
    )


def _session(r: SessionRow) -> Session:
    return Session(
        id=r.id, project_id=r.project_id, respondent_id=r.respondent_id, status=r.status,
        started_at=r.started_at, ended_at=r.ended_at, asked=r.asked,
        summary=r.summary, covered=list(r.covered or []),
    )


def _turn(r: TurnRow) -> Turn:
    return Turn(
        id=r.id, session_id=r.session_id, role=r.role, text=r.text, emotion=r.emotion,
        emotion_confidence=r.emotion_confidence, is_probe=r.is_probe,
        question_id=r.question_id, pii_types=list(r.pii_types or []),
        guardrail_rewritten=r.guardrail_rewritten, created_at=r.created_at,
    )


# --- Project ----------------------------------------------------------------

def create_project(p: Project) -> Project:
    p.id = p.id or new_id("p_")
    with db_session() as s:
        s.add(ProjectRow(
            id=p.id, owner=p.owner, title=p.title, topic=p.topic,
            target=p.target, material_text=p.material_text,
            status=p.status, created_at=p.created_at,
        ))
        s.commit()
    return p


# 이 시간이 지나도록 제출되지 않은 세션은 이탈로 본다. 인터뷰는 5~10분짜리라 몇 시간씩
# 정상적으로 걸리는 경우가 없다. 넉넉히 잡아도 오탐이 안 난다.
_ABANDON_AFTER_HOURS = 6


def _spoke():
    """'응답자가 한 마디라도 한 세션' 조건. 동의만 누르고 닫은 세션을 걸러낸다."""
    return (
        select(TurnRow.session_id)
        .where(TurnRow.role == "respondent", TurnRow.session_id == SessionRow.id)
        .exists()
    )


def _sweep_abandoned(s, pids: list[str]) -> None:
    """오래 방치된 미제출 세션을 abandoned 로 떨군다.

    스케줄러가 없어서 읽는 김에 처리한다(lazy expiry). 보통 갱신할 행이 없어 UPDATE 한 번이
    헛돌 뿐이고, 이게 없으면 이탈자가 영원히 '진행중'으로 남아 진짜 진행중인 사람과 섞인다.

    기준시각은 started_at 이다. 마지막 턴 시각을 쓰는 게 더 정밀하지만 조인이 붙고, 6시간
    임계값에서는 어차피 결과가 같다.
    """
    if not pids:
        return
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_ABANDON_AFTER_HOURS)
    s.execute(
        update(SessionRow)
        .where(
            SessionRow.project_id.in_(pids),
            SessionRow.status.in_(("consented", "active", "pending")),
            SessionRow.started_at < cutoff,
        )
        .values(status="abandoned")
    )
    s.commit()


def _counts(s, pids: list[str]) -> dict[str, tuple[int, int]]:
    """프로젝트별 (참여 세션, 제출 완료 세션) — N+1 쿼리를 피해 한 번에 센다.

    '참여'는 **응답자 턴이 1개 이상 있는 세션**이다. 동의만 누르고 창을 닫은 사람은 세지
    않는다 — 예전엔 세션 행 전체를 세서 동의 클릭만으로 '응답 1건'이 잡혔다.
    abandoned 도 뺀다. 그래야 (참여 − 완료)가 '지금 진행 중'과 실제로 일치한다.
    """
    if not pids:
        return {}
    _sweep_abandoned(s, pids)
    rows = s.execute(
        select(
            SessionRow.project_id,
            func.count(SessionRow.id).filter(_spoke(), SessionRow.status != "abandoned"),
            func.count(SessionRow.id).filter(SessionRow.status == "completed"),
        )
        .where(SessionRow.project_id.in_(pids))
        .group_by(SessionRow.project_id)
    ).all()
    return {pid: (total, done) for pid, total, done in rows}


def get_project(pid: str) -> Project | None:
    with db_session() as s:
        r = s.get(ProjectRow, pid)
        if not r:
            return None
        total, done = _counts(s, [pid]).get(pid, (0, 0))
        return _project(r, total, done)


def list_projects(limit: int = 50) -> list[Project]:
    with db_session() as s:
        rows = s.scalars(
            select(ProjectRow).order_by(ProjectRow.created_at.desc()).limit(limit)
        ).all()
        counts = _counts(s, [r.id for r in rows])
        return [_project(r, *counts.get(r.id, (0, 0))) for r in rows]


def update_project(pid: str, patch: dict) -> None:
    with db_session() as s:
        r = s.get(ProjectRow, pid)
        if not r:
            return
        for k, v in patch.items():
            if hasattr(r, k):
                setattr(r, k, v)
        s.commit()


# --- Guide ------------------------------------------------------------------

def save_guide(pid: str, g: InterviewGuide) -> InterviewGuide:
    g.project_id = pid
    g.updated_at = datetime.now(timezone.utc)
    with db_session() as s:
        r = s.get(GuideRow, pid)
        payload = [q.model_dump() for q in g.questions]
        if r:
            r.goal, r.questions, r.version, r.updated_at = g.goal, payload, g.version, g.updated_at
        else:
            s.add(GuideRow(project_id=pid, goal=g.goal, questions=payload,
                           version=g.version, updated_at=g.updated_at))
        s.commit()
    return g


def get_guide(pid: str) -> InterviewGuide | None:
    with db_session() as s:
        r = s.get(GuideRow, pid)
        if not r:
            return None
        return InterviewGuide(
            project_id=r.project_id, goal=r.goal,
            questions=[GuideQuestion(**q) for q in (r.questions or [])],
            version=r.version, updated_at=r.updated_at,
        )


# --- Session ----------------------------------------------------------------

def create_session(sess: Session, consent: ConsentLog) -> Session:
    sess.id = sess.id or new_id("s_")
    sess.respondent_id = sess.respondent_id or new_id("r_")
    with db_session() as s:
        s.add(SessionRow(
            id=sess.id, project_id=sess.project_id, respondent_id=sess.respondent_id,
            status=sess.status, started_at=sess.started_at, asked=sess.asked,
            summary=sess.summary, covered=list(sess.covered),
            consent_agreed=consent.agreed, consent_at=consent.at,
            consent_purpose_version=consent.purpose_version,
            consent_ua_hash=consent.user_agent_hash,
        ))
        s.commit()
    return sess


def get_session(pid: str, sid: str) -> Session | None:
    with db_session() as s:
        r = s.get(SessionRow, sid)
        # 다른 프로젝트의 세션 id 로 접근하는 걸 막는다
        if not r or r.project_id != pid:
            return None
        return _session(r)


def update_session(pid: str, sid: str, patch: dict) -> None:
    with db_session() as s:
        r = s.get(SessionRow, sid)
        if not r or r.project_id != pid:
            return
        for k, v in patch.items():
            if hasattr(r, k):
                setattr(r, k, v)
        s.commit()


def list_sessions(pid: str, limit: int = 200) -> list[Session]:
    with db_session() as s:
        rows = s.scalars(
            select(SessionRow).where(SessionRow.project_id == pid)
            .order_by(SessionRow.started_at.desc()).limit(limit)
        ).all()
        return [_session(r) for r in rows]


# --- Turn -------------------------------------------------------------------

def add_turn(pid: str, sid: str, t: Turn) -> Turn:
    t.id = t.id or new_id("t_")
    t.session_id = sid
    with db_session() as s:
        s.add(TurnRow(
            id=t.id, session_id=sid, role=t.role, text=t.text, emotion=t.emotion,
            emotion_confidence=t.emotion_confidence, is_probe=t.is_probe,
            question_id=t.question_id, pii_types=list(t.pii_types),
            guardrail_rewritten=t.guardrail_rewritten, created_at=t.created_at,
        ))
        s.commit()
    return t


def list_turns(pid: str, sid: str, limit: int = 200) -> list[Turn]:
    with db_session() as s:
        rows = s.scalars(
            select(TurnRow).join(SessionRow).where(
                TurnRow.session_id == sid, SessionRow.project_id == pid
            ).order_by(TurnRow.created_at).limit(limit)
        ).all()
        return [_turn(r) for r in rows]


# --- 집계 -------------------------------------------------------------------

def sentiment_counts(pid: str) -> dict[str, int]:
    """완료 세션의 감정 분포를 **DB 에서 직접 센다**.

    이전에는 LLM 이 요약을 읽고 숫자를 '세어' 넣었다. 응답자가 수십 명이 되면 그 숫자는
    믿을 수 없다. 우리는 이미 턴마다 emotion 라벨을 저장하므로 세는 건 DB 가 해야 한다.

    세션당 1표로 집계한다(발화 수로 세면 말 많은 응답자가 분포를 지배한다).
    각 세션의 대표 감정은 '중립이 아닌 감정 중 최빈값', 없으면 중립.
    """
    with db_session() as s:
        rows = s.execute(
            select(SessionRow.id, TurnRow.emotion, func.count(TurnRow.id))
            .join(TurnRow, TurnRow.session_id == SessionRow.id)
            .where(
                SessionRow.project_id == pid,
                SessionRow.status == "completed",
                TurnRow.role == "respondent",
                TurnRow.emotion != "",
            )
            .group_by(SessionRow.id, TurnRow.emotion)
        ).all()

    per_session: dict[str, dict[str, int]] = {}
    for sid, emotion, n in rows:
        per_session.setdefault(sid, {})[emotion] = n

    out: dict[str, int] = {}
    for counts in per_session.values():
        non_neutral = {k: v for k, v in counts.items() if k != "중립"}
        label = max(non_neutral or counts, key=lambda k: (non_neutral or counts)[k])
        out[label] = out.get(label, 0) + 1
    return out


def coverage_stats(pid: str) -> dict:
    """가이드 커버리지·probing 비율 (M-1/R-3 실측).

    sessions 기준은 _counts 와 같다 — 두 엔드포인트가 다른 숫자를 내면 안 된다.
    """
    with db_session() as s:
        _sweep_abandoned(s, [pid])
        total, completed = s.execute(
            select(
                func.count(SessionRow.id).filter(_spoke(), SessionRow.status != "abandoned"),
                func.count(SessionRow.id).filter(SessionRow.status == "completed"),
            ).where(SessionRow.project_id == pid)
        ).one()
        probes, mod_turns, rewritten = s.execute(
            select(
                func.count(TurnRow.id).filter(TurnRow.is_probe.is_(True)),
                func.count(TurnRow.id),
                func.count(TurnRow.id).filter(TurnRow.guardrail_rewritten.is_(True)),
            )
            .join(SessionRow, TurnRow.session_id == SessionRow.id)
            .where(SessionRow.project_id == pid, TurnRow.role == "moderator")
        ).one()
    return {
        "sessions": total,
        "completed": completed,
        "moderator_turns": mod_turns,
        "probe_turns": probes,
        "probe_rate": round(probes / mod_turns, 3) if mod_turns else 0.0,
        "guardrail_rewrites": rewritten,
    }


def theme_mention_counts(pid: str, theme_keywords: dict[str, list[str]]) -> dict[str, int]:
    """주제별 언급 응답자 수 — 전사 원문에서 직접 센다(LLM 추정 대체).

    theme 명이 아니라 **keywords** 로 매칭한다. theme 은 '배달비 및 할인 제도에 대한
    불만족' 같은 서술형이라 전사에 그대로 등장할 리 없고, 실제로 카운트가 전부 0 이 됐다.

    단순 부분문자열 매칭이다(형태소 분석 아님) — '배달비'가 '배달비용'에도 걸린다.
    LLM 이 눈대중으로 세는 것보다 재현 가능하고 검증 가능하다는 게 요점이다.
    """
    if not theme_keywords:
        return {}
    themes = list(theme_keywords)
    with db_session() as s:
        rows = s.execute(
            select(SessionRow.id, func.string_agg(TurnRow.text, " "))
            .join(TurnRow, TurnRow.session_id == SessionRow.id)
            .where(
                SessionRow.project_id == pid,
                SessionRow.status == "completed",
                TurnRow.role == "respondent",
            )
            .group_by(SessionRow.id)
        ).all()
    out = {t: 0 for t in themes}
    for _sid, blob in rows:
        text = blob or ""
        for t in themes:
            # keywords 가 비면 theme 명으로 폴백한다(없는 것보단 낫다)
            terms = [k for k in theme_keywords.get(t) or [t] if k]
            if any(k in text for k in terms):
                out[t] += 1
    return out


# --- Insight ----------------------------------------------------------------

def save_insight(pid: str, i: Insight) -> Insight:
    i.project_id = pid
    i.generated_at = datetime.now(timezone.utc)
    with db_session() as s:
        r = s.get(InsightRow, pid)
        themes = [t.model_dump() for t in i.themes]
        if r:
            r.overall, r.themes, r.sentiment = i.overall, themes, i.sentiment
            r.session_count, r.generated_at = i.session_count, i.generated_at
        else:
            s.add(InsightRow(
                project_id=pid, overall=i.overall, themes=themes, sentiment=i.sentiment,
                session_count=i.session_count, generated_at=i.generated_at,
            ))
        s.commit()
    return i


def get_insight(pid: str) -> Insight | None:
    with db_session() as s:
        r = s.get(InsightRow, pid)
        if not r:
            return None
        return Insight(
            project_id=r.project_id, overall=r.overall,
            themes=[ThemeInsight(**t) for t in (r.themes or [])],
            sentiment=dict(r.sentiment or {}), session_count=r.session_count,
            generated_at=r.generated_at,
        )
