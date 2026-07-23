# mindlens — 실시간 음성 AI 시장조사 모더레이터

FuriosaAI RNGD NPU 위에서 도는 양면형 AI 음성 인터뷰 플랫폼.
의뢰자가 주제만 입력하면 AI 모더레이터가 다수 응답자를 인터뷰하고 결과를 대시보드에 누적한다.

팀 보람보람 (팀장 · 허정오 · 박석준) · 부트캠프 5일 MVP

## 무엇이 도는가

| | 주소 |
|---|---|
| 의뢰자 웹 | https://mindlens-web-128792069861.asia-northeast3.run.app |
| API | https://mindlens-api-128792069861.asia-northeast3.run.app |
| 응답자 링크 | `{웹}/i/{project_id}` — `POST /api/projects/{id}/deploy` 가 발급 |

GCP 프로젝트 `mindlens-furiosa-2026` (asia-northeast3) · Cloud Run ×2 + Cloud SQL Postgres + Secret Manager.

## 실측 (Furiosa RNGD · Qwen3-32B-FP8)

| 항목 | 값 | PRD 목표 |
|---|---|---|
| 스트리밍 TTFT | **0.26초** | ≤ 1.5초 |
| 인터뷰 한 턴 | 2.4~3.8초 | 3초 내 응답 |
| 가이드 생성 | 60~85초 | 문항별 응답 버킷·어휘까지 한 번에 생성 |
| 세션 요약 + 집계 | 9~10초 | — |

추론은 **전부 NPU 에서 돈다.** 상용 LLM API 로 빼는 경로는 없다 — tokens/s/W 벤치마크를 오염시키지 않기 위해서다.

## 구조

```
api/                    FastAPI
  main.py               앱 엔트리 · CORS · IP 레이트리밋 · /health
  config.py             환경변수 단일 소스 (Settings)
  briefing/
    pipeline.py         청크·2단 검색(코사인 넓게 → 리랭커 top-k) — 프로젝트 자료(briefing_chunks) + 전역 지식 풀(knowledge_chunks)
  services/
    llm_client.py       OpenAI 호환 클라이언트 (재시도·구조화출력·자가교정·rerank)
    moderator.py        한 턴의 오케스트레이션 (아키텍처 §5.2)
    guardrail.py        M-2 중립성 가드레일 (정규식 사전검사 → LLM 판정 → 재작성)
    pii.py              M-5 PII 마스킹 (저장 전, 결정론적)
    audience.py         브리프 → 전역 페르소나 풀 검색 → 가이드 생성용 대상 청중 주입
    speech.py           STT/TTS
    store.py            저장소 로직 (Cloud SQL Postgres)
    db.py               ORM 테이블 · 커넥션 (SQLAlchemy + Cloud SQL Connector)
  routers/              projects(의뢰자) · public(응답자) · speech
  prompts/              가이드 생성 · 모더레이터 · 요약/집계/감정 · 오디언스
  _reference/           원본 레포에서 참고용으로만 가져온 코드. 그대로 쓰지 말 것.
scripts/
  ingest_knowledge.py   전역 지식 풀(knowledge_chunks) 적재 CLI — parquet → 임베딩, 멱등(--replace)
web/                    Next.js 14 App Router
  app/projects/         의뢰자 대시보드 (C-1~C-5)
  app/projects/benchmark/  NPU vs GPU 벤치마크 뷰 — M1/M2/M3·손익분기 S*, 측정 전엔 전부 null(—)
  app/i/[projectId]/    응답자 인터뷰 (R-1~R-4)
  components/shell/sidebar.tsx  좌측 앱 셸(무인증 — 계정/워크스페이스 UI 없음)
  components/benchmark/ 벤치마크 뷰 구성요소 (지표 카드 · 손익분기 패널 · 전력 차트 · 정직성 배너)
  components/           interview-flow · moderator-avatar · response-viewer
  public/mindlens-logo.svg  서비스 로고
  hooks/useAudio.ts     마이크 캡처
  lib/recorder-session.ts  MediaRecorder 순수 로직 — "절대 reject 하지 않는다" 계약
  _reference/           원본 레포 참고 코드 (survey-api.ts). 그대로 쓰지 말 것.
```

가이드 생성은 프로젝트 자료 풀과 전역 지식 풀(합성 페르소나 등, `scripts/ingest_knowledge.py`로 적재) 양쪽을 2단 검색(코사인 후보 → 리랭커 재정렬)으로 조회해 근거·대상 청중을 프롬프트에 주입한다. RAG는 가이드 생성 시점에만 발동하고, 인터뷰 진행 중에는 라이브 검색을 하지 않는다.

## 설계에서 물러서지 않은 것

- **집계 숫자는 LLM 이 세지 않는다.** `sentiment`·`mention_count` 는 DB 실측으로 덮어쓴다.
  LLM 은 주제·요약·인용·검색어만 만든다. 응답자가 수십 명이 되면 눈대중 카운트는 틀리고 검증도 불가능하다.
- **PII 마스킹은 저장 경로에 있고 LLM 을 쓰지 않는다.** LLM 이 실패·타임아웃하면 원문이 그대로 저장될 위험이 생긴다.
- **`transcribe` 는 `(전사, 성공여부)` 를 돌려준다.** 빈 전사만으로는 무음(성공)과 엔진실패를 구별할 수 없다.
  원본 운영에서 중국어 STT 400 이 한 달간 조용히 저장된 실장애가 있었다.

## 로컬 실행

```bash
# 최초 1회 — venv + API 의존성
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r api/requirements.txt

# 환경변수 — .env.example 을 복사해 값 채우기 (LLM 키는 Secret Manager 에)
cp .env.example .env.local

# API — .env.local 을 반드시 로드한다. 앱은 os.environ 만 읽으므로 --env-file 이 없으면
# 키가 비어 /health 의 llm_key_present 가 false 가 된다.
./.venv/Scripts/python.exe -m uvicorn api.main:app --port 8099 --env-file .env.local

# 웹 — NEXT_PUBLIC_API_BASE 로 위 API 주소를 가리킨다 (미설정 시 http://localhost:8000)
cd web && npm install && npm run dev
```

로컬 DB 는 두 갈래다 (`db.py`): `INSTANCE_CONNECTION_NAME` 이 있으면 Cloud SQL Connector 로 붙고
(gcloud ADC 인증 필요), 없으면 `DATABASE_URL` 로 로컬 Postgres 에 붙는다. 둘 다 없으면 기동 시 뜬다.

테스트: `./.venv/Scripts/python.exe -m pytest api/tests -q`

## CI/CD

`main` 에 머지되면 자동 배포된다. 인증은 **Workload Identity Federation** — GitHub 에 서비스 계정
키를 저장하지 않는다. `hjo0225/Furiosa-Moderator` 에서 온 OIDC 토큰만 배포 SA 를 가장할 수 있다.

| 워크플로 | 시점 | 하는 일 |
|---|---|---|
| `test.yml` | PR → main | pytest · import 검사 · `tsc --noEmit` · `next build` · 시크릿 스캔 |
| `deploy.yml` | push → main | 테스트 → 변경된 서비스만 배포 → 스모크 테스트 → 실패 시 자동 롤백 |

- **변경 감지**: `api/` 만 고치면 웹(3분 빌드)은 건드리지 않는다. 판별이 불가능하면 둘 다 배포한다.
- **환경변수·시크릿은 워크플로에 적지 않는다.** 기존 서비스 설정을 물려받아 이미지만 바꾼다 —
  워크플로에 값이 빠지면 조용히 설정이 지워지기 때문이다.
- **스모크 테스트가 실패하면 직전 리비전으로 트래픽을 되돌린다.** API 는 `/health` 가
  `ok` 와 `llm_key_present` 를 둘 다 만족해야 통과다(시크릿 주입 누락을 잡는다).
- 수동 전체 배포: Actions → deploy → Run workflow → `force_all` 체크.

## 알려진 미해결

- **실기기 음성 테스트가 아직이다.** `interview-flow.tsx` 는 원본에서도 실사용자를 태운 적이 없다. iOS 사파리 확인 필요.
- **동의 화면의 보관기간 "1년" 은 임의값이다.** 법적 문구라 실제 응답자를 받기 전에 확정해야 한다.
- **무인증이다.** IP 레이트리밋(60초 30회)만 있다. 링크를 아는 사람은 누구나 LLM 을 태울 수 있다.
- **`_reference/` 는 한양대 프로젝트 원본 코드다.** 재사용의 계약상 검토가 끝나지 않았다 — 이 레포를 공개로 바꾸기 전에 반드시 확인할 것.

## 더 읽을 것

- [`PORTING.md`](PORTING.md) — 이식 경위와 판단 근거
- [`design.md`](design.md) — 디자인 시스템 정본(SoT). `web/styles/globals.css`의 `@theme`가 이 문서의 구현이다.
- [`AGENTS.md`](AGENTS.md) — 에이전트 하네스 정본(라이프사이클·게이트·프로젝트 컨텍스트). `CLAUDE.md`는 이 파일을 가리키는 한 줄이다.
