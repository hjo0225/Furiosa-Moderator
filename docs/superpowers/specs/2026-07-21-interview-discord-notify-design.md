# 인터뷰 응답 실시간 Discord 알림 (n8n 경유) — 설계

- 날짜: 2026-07-21
- 상태: 구현됨 — **단, 아키텍처 변경: n8n 경유 → 직접 Discord 웹훅** (n8n self-host 운영부담 회피). 아래 n8n 관련 서술은 이력용이며, 실제 구현은 `notify.py` 가 Discord embed 를 직접 만들어 `DISCORD_WEBHOOK_URL` 로 POST 한다.
- 관련: `api/routers/public.py`(submit) · `api/services/store.py` · `api/prompts/insight.py` · `api/config.py`

## 목표

응답자가 인터뷰를 **제출(`submit`)할 때마다**, 그 세션의 **요약 · 감정 · 문항 커버리지 · 전사 합본**을
n8n 웹훅으로 보내고, n8n이 이를 **Discord 채널에 embed**로 게시한다.

## 하지 않을 것 (Non-goals)

- **실제 오디오 전송 안 함.** 현재 응답자 음성은 STT 입력으로만 쓰이고 저장되지 않는다. "음성 데이터"는
  마스킹된 **전사 텍스트**를 뜻한다(브레인스토밍에서 확정). 오디오 저장·병합은 범위 밖.
- **정기 리포트·마일스톤 알림 안 함.** 1순위는 실시간 제출 알림 하나. n8n에서 나중에 확장.
- **양방향(Discord→mindlens) 안 함.** 단방향 아웃바운드 알림만.

## 배경 (현재 코드 사실)

- `POST /api/public/projects/{pid}/sessions/{sid}/submit` 이 "응답 1건"이 확정되는 지점이다.
  세션 status 가 `completed` 로 넘어가고 `ended_at` 이 찍힌다. 이미 `log.info("세션 제출 완료…")` 가 있다.
- **아웃바운드 알림 코드는 전무**(httpx 는 LLM 클라이언트 내부에만 쓰임). 그린필드.
- 제출 시점엔 `sessions.summary` 가 **아직 비어 있다**. 요약은 원래 `build_insight` 에서 지연 생성된다.
- 데이터 소스: `store.list_turns(pid, sid)`(마스킹된 문답), `session.covered`/`asked`, `guide.questions`(총 문항),
  turn 별 `emotion`. 전사는 `turns.text` 로 **이미 마스킹**되어 있다.
- **PII 원칙**: 저장 전 마스킹, 식별정보 미보관. 알림 payload 도 이 선을 지킨다(원문 오디오·비마스킹 없음).

## 결정 (브레인스토밍 확정)

| 항목 | 결정 |
|---|---|
| 트리거 | 실시간 — 제출마다 1건 |
| 내용 | 요약 카드 + 세션 전사 합본(마스킹 텍스트) |
| 아키텍처 | **B. FastAPI → n8n 웹훅 → Discord** (mindlens 는 이벤트만 emit) |
| 요약 생성 | 제출 시 백그라운드로 1회 생성·저장해 payload 에 포함 (실패 시 transcript-only 폴백) |
| 서명 | **HMAC 생략** — webhook URL 자체를 시크릿으로 취급 (잔여 리스크는 아래 참고) |
| n8n 워크플로우 | import 가능한 JSON + Discord embed 포맷까지 동봉 |

## 아키텍처 / 데이터 흐름

```
응답자 submit
  → FastAPI submit 핸들러 (세션 completed 전환)
  → BackgroundTask 등록 후 즉시 200 반환  ← 응답자 흐름 절대 안 막음
        └─(비동기) notify.emit_session_completed(pid, sid)
              1. 세션 요약 1회 생성·저장 (best-effort)
              2. payload 빌드 (마스킹 데이터만)
              3. n8n Webhook 으로 POST (타임아웃·재시도)
  → n8n: Webhook 수신 → Function(embed 포맷) → Discord 노드 게시
```

mindlens 책임은 **"구조화 이벤트 JSON 을 설정된 n8n URL 로 POST"** 까지. 포맷·라우팅·재시도·전송은 n8n 이 맡는다.
→ 나중에 Slack·스프레드시트 팬아웃은 n8n 에서 노코드로 확장(규모 확장 여지 확보).

## 컴포넌트

**신규 — `api/services/notify.py`**
- `emit_session_completed(pid: str, sid: str) -> None` — 단일 진입점. 알림만 담당(단일 책임).
  - `settings.n8n_webhook_url` 이 비면 조용히 return(로컬·미설정 환경에서 알림 비활성).
  - 내부에서 payload 빌드 + POST. **모든 예외를 자체 흡수**하고 `log.warning` 만 남긴다 — 호출부로 전파 금지.
- `_build_payload(pid, sid, settings) -> dict` — 아래 계약대로 payload 구성. 요약 생성 포함(실패 시 `summary=None`).
- `_post(url, payload, settings)` — httpx POST, timeout 5s, 최대 2회 재시도(지수 백오프).

**변경 — `api/routers/public.py` `submit`**
- 시그니처에 `background_tasks: BackgroundTasks` 추가.
- 세션을 `completed` 로 업데이트한 **직후** `background_tasks.add_task(notify.emit_session_completed, pid, sid)` 한 줄.
- 멱등 경로(이미 completed 라 early-return)에서는 **알림을 다시 쏘지 않는다**(중복 클릭·재전송으로 중복 알림 금지).

**변경 — `api/config.py`**
- `n8n_webhook_url: str = ""` (env `N8N_WEBHOOK_URL`). 비면 알림 비활성.

**변경 — `.env.example`**
- `N8N_WEBHOOK_URL=` 항목 추가 + "실값은 Secret Manager" 주석.

**신규 산출물 — n8n 워크플로우**
- `n8n/interview-notify.workflow.json` — import 가능한 워크플로우(Webhook → Function → Discord).
- `n8n/README.md` — import 방법·Discord webhook 연결·payload→embed 매핑 설명.

## Payload 계약 (mindlens → n8n)

마스킹된 데이터만 담는다. n8n 이 이 JSON 을 소비해 embed 를 만든다.

```json
{
  "event": "session.completed",
  "project": { "id": "…", "title": "…", "topic": "…" },
  "session": {
    "id": "…",
    "respondent_ref": "…(짧은 해시 — 원 식별자 미노출)",
    "asked": 6,
    "duration_sec": 214
  },
  "metrics": {
    "emotion": { "positive": 3, "neutral": 2, "negative": 1 },
    "coverage": { "covered": ["q1","q3","q4"], "total": 5 }
  },
  "summary": "…제출 시 생성. 실패 시 null…",
  "transcript": "진행자: …\n응답자: …\n진행자: …\n응답자: …",
  "dashboard_url": "{PUBLIC_WEB_BASE}/projects/{project_id}"
}
```

- `transcript` — `store.list_turns` 를 `build_insight` 와 같은 방식(`진행자:/응답자:`)으로 합본. 이미 마스킹됨.
- `metrics.emotion` — 해당 세션 turn 들의 `emotion` 카운트(프로젝트 전체가 아니라 세션 단위).
- `respondent_ref` — `respondent_id`(또는 `consent_ua_hash`)의 짧은 해시. 원 식별자·PII 미노출.

## 요약 생성 동작

- 백그라운드 태스크 안에서 기존 `SESSION_SUMMARY_SYSTEM` + `session_summary_user(goal, transcript)` 로 1회 생성.
  `goal` 은 `guide.goal`(없으면 `project.topic`).
- 생성 성공 시 `store.update_session(pid, sid, {"summary": …})` 로 저장 → 이후 `build_insight` 도 재사용해 빨라짐.
- 생성 실패(LLM 오류·타임아웃) 시 `summary=None` 으로 **전사만** 전송(best-effort). 알림 자체를 실패시키지 않는다.
- 비동기 실행이라 응답자 제출 응답은 지연되지 않는다.

## 에러 처리 / 신뢰성

- 알림은 **본류(인터뷰)를 절대 막지 않는다** — 프로젝트의 기존 원칙과 일치.
- POST 실패는 2회 재시도 후 `log.warning` 만. 예외는 submit 응답에 영향 없음(제출은 이미 200 반환).
- n8n/Discord 장애 시 알림만 조용히 유실된다(인터뷰·집계는 정상). 유실은 로그로 추적 가능.

## 보안 / 잔여 리스크

- HMAC 서명은 이번 범위에서 **생략**. 대신 **n8n webhook URL 자체를 시크릿으로 취급**한다 — Secret Manager 에
  두고 코드·로그·워크플로에 노출 금지.
- 잔여 리스크: URL 을 아는 누구나 가짜 `session.completed` 를 Discord 로 흘릴 수 있다. 내부 채널·저트래픽이라
  현 단계 수용 가능. **향후 강화**: 정적 토큰 헤더 또는 HMAC 서명을 n8n 첫 노드에서 검증(비파괴적 추가).

## 배포 / 설정

- `N8N_WEBHOOK_URL` 을 Secret Manager 에 등록하고 Cloud Run api 서비스에 주입.
- **Cloud Run 주의(known gap)**: 기본값은 요청 밖 CPU 스로틀이라 응답 후 BackgroundTask(요약 LLM 호출)가
  지연·중단될 수 있다. mindlens api 서비스에 **"CPU always allocated"** 를 켜거나, 신뢰성이 더 필요하면
  Cloud Tasks/PubSub 로 이관한다. MVP 는 BackgroundTask + CPU always allocated 로 간다.
- 값 미설정 시 알림은 자동 비활성 → 로컬·CI 에서 안전.

## 테스트

- `notify` 가 계약대로의 payload 로 n8n URL 에 POST 하는지 (httpx 목킹).
- 요약 생성 실패 시 `summary=None` + transcript-only 로 폴백하는지.
- `N8N_WEBHOOK_URL` 미설정 시 아무 것도 POST 하지 않고 조용히 return 하는지.
- POST 실패(예외·타임아웃)해도 `emit_session_completed` 가 예외를 던지지 않는지.
- submit 이 background task 를 등록하되, 알림 경로와 무관하게 200 을 반환하는지.
- payload 에 원문 오디오·비마스킹 PII 가 없는지(마스킹된 `turns.text` 만).
- 멱등 재제출(이미 completed) 시 알림을 중복 발사하지 않는지.

## n8n 워크플로우 설계 (동봉 산출물)

노드 구성:
1. **Webhook** (POST, path `/mindlens-interview`) — payload 수신.
2. **Function/Set** — payload → Discord embed 매핑:
   - title: `새 인터뷰 응답 · {project.title}`
   - description: `summary` (없으면 "요약 없음")
   - fields: 감정 분포 · 커버리지 `covered/total` · 소요시간 · 문항 수
   - transcript 는 길이가 커서 별도 필드/코드블록 또는 첨부로(2000자 초과 시 잘라내기)
   - url: `dashboard_url`
3. **Discord** 노드 — 대상 채널의 Discord webhook 으로 게시.

베이스: awesome-n8n-templates 의 Discord 템플릿. 우리 payload 계약에 맞춰 매핑만 조정.

## 향후 확장 (규모 성장 시)

- n8n 에서 Slack·시트·이메일로 팬아웃(노코드).
- 프로젝트별 채널 라우팅(payload 의 `project.id` 로 분기).
- 정기 현황 리포트(n8n Cron → mindlens `/dashboard`·`/stats` 폴링).
- 서명 검증 추가(위 보안 항목).
