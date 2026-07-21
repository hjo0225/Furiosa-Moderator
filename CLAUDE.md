# mindlens — Claude 작업 가이드

> FuriosaAI RNGD NPU 위에서 도는 실시간 음성 AI 시장조사 모더레이터.
> 의뢰자가 주제만 주면 AI 모더레이터가 다수 응답자를 인터뷰하고 결과를 대시보드에 누적한다.
> `api/`(FastAPI) + `web/`(Next.js 14) 모노레포. Cloud Run ×2 + Cloud SQL Postgres.
> 배경·판단 근거는 [`README.md`](README.md) / [`PORTING.md`](PORTING.md), 디자인 토큰은 [`design.md`](design.md).

이 파일은 매 세션 컨텍스트에 실린다. **한 줄 한 줄이 값을 해야 한다** — 코드로 읽으면 되는 건 적지 않는다.

---

## 명령어

Windows / PowerShell 기준. venv 는 리포 루트의 `.venv` 하나를 쓴다(파이썬 경로는 `./.venv/Scripts/python.exe`).

```bash
# 최초 1회
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r api/requirements.txt
cp .env.example .env.local        # 값 채우기 (키는 Secret Manager 에서)

# API 로컬 기동 (포트는 자유, 아래는 예)
./.venv/Scripts/python.exe -m uvicorn api.main:app --port 8099 --reload

# 웹 로컬 기동
cd web && npm install && npm run dev   # NEXT_PUBLIC_API_BASE 로 API 주소 지정 (미설정 시 :8000)
```

```bash
# 테스트 / 검사
./.venv/Scripts/python.exe -m pytest api/tests -q   # API 유닛 테스트
cd web && npm run typecheck                          # tsc --noEmit
cd web && npm run build                              # next build (CI 가 도는 것과 동일)
cd web && npm run lint                               # next lint
```

## 테스트

**커밋 전 최소선**: 파이썬을 건드렸으면 `pytest api/tests -q`, 웹을 건드렸으면 `npm run typecheck`.
**PR 전**: CI(`test.yml`)가 도는 것과 같은 4종 — pytest · import 검사 · `tsc --noEmit` · `next build` — 를 로컬에서 통과시킨다.
현재 테스트는 모더레이터 한 턴 오케스트레이션(`api/tests/test_interview_moderator.py`)에 몰려 있다. LLM 을 실제로 태우지 않고 클라이언트를 목킹한다.

## 프로젝트 구조

```
api/                    FastAPI
  main.py               앱 엔트리 · CORS · IP 레이트리밋 · /health
  config.py             환경변수 단일 소스 (Settings, lru_cache)
  services/
    llm_client.py       OpenAI 호환 클라이언트 (재시도·구조화출력·자가교정)
    moderator.py        인터뷰 한 턴의 오케스트레이션 (아키텍처 §5.2)
    guardrail.py        M-2 중립성 가드레일 (정규식 사전검사 → LLM 판정 → 재작성)
    pii.py              M-5 PII 마스킹 (저장 전, 결정론적, LLM 안 씀)
    speech.py           STT/TTS
    store.py / db.py    저장소 · ORM · 커넥션 (Cloud SQL)
  routers/              projects(의뢰자) · public(응답자) · speech  ← main.py 가 마운트하는 3개
  prompts/              가이드 생성 · 모더레이터 · 요약/집계/감정
  _reference/           원본 레포 참고 코드. 그대로 쓰지 말 것.
web/                    Next.js 14 App Router
  app/projects/         의뢰자 대시보드 (C-1~C-5)
  app/i/[projectId]/    응답자 인터뷰 (R-1~R-4)
  components/           interview-flow.tsx · moderator-avatar.tsx · shared/
  hooks/useAudio.ts     마이크 캡처
  lib/recorder-session.ts  MediaRecorder 순수 로직 — "절대 reject 하지 않는다" 계약
  styles/globals.css    디자인 토큰 SSOT (@theme). design.md 아님.
```

라우터 prefix: `/api/projects`(의뢰자) · `/api/public/projects`(응답자) · `/api/speech`. `interview.py`(`/interview`)는 `main.py` 에 마운트돼 있지 않다 — 손대기 전에 실제 사용 여부부터 확인.

## 절대 깨면 안 되는 계약

이 셋은 원본 운영에서 실장애로 배운 것이다. "개선"으로 되돌리지 말 것 — 바꾸려면 먼저 사람에게 확인한다.

1. **집계 숫자는 LLM 이 세지 않는다.** `sentiment`·`mention_count` 는 DB 실측으로 덮어쓴다. LLM 은 주제·요약·인용·검색어만 만든다. 응답자가 수십 명이면 눈대중 카운트는 틀리고 검증도 불가능하다.
2. **PII 마스킹은 저장 경로에 있고 LLM 을 안 쓴다** (`services/pii.py`). LLM 이 실패·타임아웃하면 원문이 그대로 저장될 위험이 생긴다. 마스킹을 LLM 호출 뒤로 옮기지 말 것.
3. **`transcribe` 는 `(전사, 성공여부)` 를 돌려준다.** 빈 문자열만으로는 무음(성공)과 엔진실패를 구별할 수 없다. 원본에서 중국어 STT 400 이 한 달간 조용히 저장된 실장애가 있었다.
4. **추론은 전부 NPU 에서 돈다.** 상용 LLM API 로 빼는 폴백 경로를 만들지 말 것 — tokens/s/W 벤치마크를 오염시킨다.
5. **provider 판별은 설정값(`LLM_PROVIDER`)으로 한다**, 모델명 prefix 로 하지 않는다. `furiosa-ai/Qwen3-*` 가 Anthropic 경로로 오분기한다(PORTING.md §2).
6. **Qwen3 는 `LLM_DISABLE_THINKING=1` 필수.** 켜두면 200 토큰 중 174 개를 사고에 쓰고 응답이 잘린다(3.44s → 0.75s).

## 설정 · 시크릿

- 환경변수 단일 소스는 `api/config.py`. `.env.example` 이 전체 목록이다.
- **시크릿은 코드·로그·워크플로에 절대 남기지 않는다.** Cloud Run 은 Secret Manager 가 `LLM_API_KEY` / `EMBED_API_KEY` / `RERANK_API_KEY` 를 주입한다. `/health` 는 키 값이 아니라 `llm_key_present` 불리언만 노출한다.
- 무인증 MVP 다. 방어는 IP 레이트리밋(60초 30회, 인메모리·인스턴스별)뿐 — LLM 을 태우는 POST/PUT 경로에만 건다(`main.py`).

## 배포 / CI

`main` 에 머지되면 GitHub Actions 가 **자동 배포**한다. 인증은 Workload Identity Federation(서비스계정 키 없음).

| 워크플로 | 시점 | 하는 일 |
|---|---|---|
| `test.yml` | PR → main | pytest · import 검사 · `tsc --noEmit` · `next build` · 시크릿 스캔 |
| `deploy.yml` | push → main | 테스트 → **변경된 서비스만** 배포 → 스모크 → 실패 시 자동 롤백 |

- `api/` 만 고치면 웹(3분 빌드)은 안 건드린다. 판별 불가면 둘 다 배포.
- **환경변수·시크릿을 워크플로에 적지 않는다.** 기존 서비스 설정을 물려받아 이미지만 바꾼다 — 값이 빠지면 조용히 설정이 지워진다.
- 스모크가 실패하면 직전 리비전으로 트래픽을 되돌린다. API 는 `/health` 가 `ok` 와 `llm_key_present` 를 둘 다 만족해야 통과.
- 수동 전체 배포: Actions → deploy → Run workflow → `force_all` 체크.

## gstack 워크플로

이 리포는 gstack 위에서 굴린다. 아래 슬래시 커맨드를 상황에 맞춰 쓴다.

| 하려는 일 | 커맨드 | 메모 |
|---|---|---|
| 브랜치를 PR 로 마무리 | `/ship` | base 병합 → 테스트 → diff 리뷰 → VERSION/CHANGELOG → 커밋 → push → PR. **실제 배포는 이게 아니라** 머지 후 `deploy.yml` 이 한다. |
| PR 랜딩 전 리뷰 | `/review` | 랜딩 전 diff 리뷰. `/code-review ultra` 는 클라우드 멀티에이전트(사용자 트리거·과금, 내가 못 켠다). |
| 랜딩 + 배포 흐름 | `/land-and-deploy` | 이 리포의 실제 배포 경로는 GitHub Actions 이므로, 배포 단계는 머지 = `deploy.yml` 로 읽는다. |
| 버그 파고들기 | `/investigate` | 근본원인 중심 체계적 디버깅. |
| 웹 QA (헤드리스 브라우저) | `/qa` (수정까지) · `/qa-only` (리포트만) · `/browse` | 응답자 인터뷰·대시보드 실동작 확인. |
| 디자인 점검 | `/design-review` | design.md / globals.css 기준 시각 QA + 수정. |
| 코드 건강도 | `/health` | 품질 대시보드. |
| 배포 후 감시 | `/canary` | 릴리스 직후 카나리 모니터링. |
| 보안 감사 | `/cso` | OWASP/STRIDE. 무인증·PII 라 랜딩 전 유용. |
| 문서 | `/document-generate` (신규) · `/document-release` (배포 후 갱신) | |
| 파괴적 명령 안전벨트 | `/careful` · `/guard` · `/freeze` | 배포·DB·스키마 건드릴 때. |
| 기능/작업 사전 정리 | `/jo-interview` · `/jo-ticket-builder` · `/spec` | "~해줘" 류 실작업은 먼저 스펙부터. |

주의: `/ship` 은 없던 `VERSION`/`CHANGELOG.md` 를 도입한다. 이 리포엔 아직 없으니 처음 쓸 때 팀과 합의.

## 코드 컨벤션

- **커밋 메시지는 한국어 현재형 서술** — "무엇을 한다". 예: `마이크 캡처 제약을 명시한다`, `시크릿 스캔이 자기 자신을 잡던 것을 고친다`. "왜"가 비자명하면 본문에 남긴다.
- **주석은 "왜"를 적는다.** 이 코드베이스는 판단 근거(실측치·과거 장애·트레이드오프)를 주석에 촘촘히 남기는 스타일이다. 주변 밀도에 맞춘다.
- 파이썬: `from __future__ import annotations`, 타입힌트, pydantic 모델. 웹: TypeScript strict, App Router, Tailwind + design.md 토큰.
- 새 값(색·타이포·radii)은 `web/styles/globals.css` 의 `@theme` 이 SSOT. design.md 는 스펙 보존용이지 편집 대상 아님.

## 알려진 미해결 / 지뢰

- **실기기 음성 테스트 미완.** `interview-flow.tsx` 는 실사용자를 태운 적이 없다. iOS 사파리 확인 필요.
- **동의 화면 보관기간 "1년" 은 임의값.** 법적 문구라 실응답자 받기 전 확정.
- **무인증.** 링크를 아는 사람은 누구나 LLM 을 태울 수 있다(레이트리밋만 있음).
- **`_reference/` 는 한양대 프로젝트 원본 코드.** 재사용 계약 검토 미완 — 이 리포를 공개로 바꾸기 전 반드시 확인.
