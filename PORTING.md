> **[2026-07-20 갱신] 이 문서는 이식 '계획'이었고, 이제 구현이 끝났다.**
> 아래 계획 대비 실제로 달라진 것만 먼저 적는다. 나머지 본문은 당시 판단 기록으로 남겨둔다.
>
> - **§2 "tool-use 못 쓴다"는 틀렸다.** Anthropic 방식은 못 쓰지만 OpenAI forced `tool_choice` 는
>   정상 동작한다. 구조화 출력은 그 경로를 쓰고 `json_object` 는 폴백으로 뒀다.
> - **모델은 Llama 3.1 8B 가 아니라 `furiosa-ai/Qwen3-32B-FP8`.** 추론 모델이라
>   `enable_thinking=False` 와 온도 명시(텍스트 0.6 / 구조화 0.3)가 **필수**다. 안 하면
>   응답이 잘리거나 다국어 잡음으로 깨진다. 자세한 건 `api/services/llm_client.py` 주석.
> - **저장소는 Cloud SQL Postgres.** Firestore 로 먼저 만들었다가 관계형이 맞아 갈아탔다.
> - **집계 숫자는 LLM 이 세지 않는다.** `sentiment`·`mention_count` 는 DB 실측으로 덮어쓴다
>   (`store.sentiment_counts` / `theme_mention_counts`). LLM 은 주제·요약·인용·검색어만 만든다.
> - **테스트 파일의 import 경로가 원본 구조(`prompts/survey/`)를 물고 있어 수집조차 안 됐다.** 고쳤다.
> - **PII 정규식이 `\b` 때문에 무력했다.** "010-1234-5678이고" 처럼 숫자 뒤에 한글이 붙으면
>   워드경계가 없어 전화번호가 통째로 샜다. 숫자 룩어라운드로 교체.
> - 배포 주소·프로젝트는 아래 "배포" 절 참고.
>
> ---

# mindlens → Furiosa NPU 부트캠프 이식 노트

원본 레포: `C:\Users\ABC\Desktop\Project\mindlens_solution` (751 파일)
PRD: `mindlens_PRD.docx` v0.1 (2026-07-20) — 5일 MVP
복사일: 2026-07-20

**통째 이식이 아니라 선별 복사다.** 원본은 한양대 패널 운영(보상·국적쿼터·검수 워크플로우) + Firebase + GCS +
alembic 20여 개에 깊이 묶여 있어, 떼어내는 비용이 새로 짜는 비용보다 크다.
결합이 없거나 얕은 것만 가져왔고, 나머지는 `_reference/`에 넣어 **읽고 다시 짜는** 용도로 뒀다.

---

## ⚠️ 먼저 알아야 할 3가지

### 1. `interview-flow.tsx`는 프로덕션에서 꺼져 있다 — 실동작 미검증
원본 `apps/web/app/(survey-public)/survey/s/[id]/page.tsx:806`:
```ts
// 인터뷰 모더레이터(미완성)는 비활성 — 모든 설문을 표준 문항 UI로 렌더한다.
const isInterview: boolean = false;
```
컴포넌트(232줄)와 백엔드 엔드포인트는 온전하지만 **실사용자를 태운 적이 없다.**
"검증된 코드 재사용"이 아니라 **"작동할 가능성이 높은 초안"** 으로 취급할 것. 실기기(특히 iOS 사파리) 테스트 시간 필수.

### 2. `llm_client.py`는 현재 상태로 Furiosa에 못 붙는다 — 단, 수정 지점은 3곳
PRD는 "Furiosa-LLM(OpenAI 호환)"을 전제하지만 원본 코드에 `base_url` 주입구가 없다.

| 위치 | 문제 | 해야 할 일 |
|---|---|---|
| `services/llm_client.py:72` | `Anthropic(api_key=..., timeout=..., max_retries=0)` — `base_url` 인자 없음 | `base_url` 추가 |
| `services/llm_client.py:276` | `OpenAI(api_key=...)` — `base_url` 인자 없음 | `base_url=settings.llm_base_url` 추가 |
| `services/llm_client.py:35-37` | `_is_openai_model()`이 **모델명 prefix**(`gpt-`, `o1`…)로 provider 판별 | Furiosa가 `Llama-3.1-8B` 같은 이름을 쓰면 **Anthropic 경로로 오분기** → tool-use 호출이 터진다. provider를 **설정값으로** 판별하도록 재설계 |

추가로 **Furiosa-LLM은 Anthropic tool-use를 지원하지 않는다.** `structured()`의 tool-use 경로(L214 이하)는 못 쓰고,
OpenAI `json_object` 경로(L266 이하 `_structured_openai`)로 **강제**해야 한다.

살릴 가치가 있어서 가져온 것: 재시도·백오프, **truncation 가드**, **스키마 검증 실패 시 자가교정 재시도**.
직접 짜면 반나절 걸리는 부분이다. 버릴 것: `web_research`(Claude 전용 서버툴), `vision`.

### 3. 음성은 사실상 새로 짜야 한다
원본 `routers/speech.py`는 **Google Cloud STT v2 + TTS에 완전 결합** + **실시간이 아니다**
(파일 주석 L3-5: "실시간 WebSocket 스트리밍 대신 녹음 → 업로드 → 일괄 전사").
PRD의 "실시간 음성 인터뷰 / TTFT ≤ 1.5초"와 **아키텍처가 다르다.** → `_reference/speech_router.py`로만 뒀다.

거기서 건질 것 3가지:
- `_spellfix()` (L108-137) — STT 맞춤법 보정. "의미·어휘 변경 금지, 표기만 교정" 프롬프트. **엔진 무관, 그대로 재사용 가능**
- `_recognize()` (L169-179) — **(전사, 성공여부) 튜플 반환.** 빈 transcript만으로는 무음(성공)과 엔진실패를 구별 못 해
  중국어 STT 400이 한 달간 조용히 저장된 실장애가 있었다. **transcribe 200 ≠ 성공.** 엔진 바꿔도 유효한 교훈
- 오디오 크기/MIME 가드 (L28-36, L196-198)

---

## 복사된 것 — PRD 요구사항 매핑

### 백엔드 `api/`

| 경로 | PRD ID | 역할 | 결합 |
|---|---|---|---|
| `prompts/interview_moderator.py` | **M-1, R-3, R-4** | 모더레이터 엔진 핵심. 목표+대화이력+asked → 다음 발화 + 종료여부. "한 번에 질문 하나", "꼬리질문 → 다음 주제", 6~10턴 자동종료 | **없음** (import 0개) |
| `prompts/interview_followup.py` | **R-3** | 직전 질문+답변 → 후속질문 1개 | **없음** |
| `prompts/questions.py` | **C-2** | 주제 → 질문 가이드 자동 생성 | **없음** |
| `prompts/topics.py` | **C-2** | 주제 확장 | **없음** |
| `prompts/summary.py` | **M-4** | 요약. ⚠️ **문항별 답변 리스트용이지 대화 전사용이 아니다** | **없음** |
| `services/llm_client.py` | 인프라 | 재시도·구조화출력·토큰집계 | ⚠️ 위 §2 참조 |
| `schemas/interview.py` | — | **발췌 생성** (원본 `schemas/survey.py` L397-399, L663-690) | 없음 |
| `routers/interview.py` | — | **발췌 생성** (원본 `routers/survey.py` L2080-2134). Firebase 인증 제거함 | 없음 |
| `tests/test_interview_moderator.py` | — | 프롬프트 단위테스트. 라우트 등록 검증 케이스는 새 앱에 맞게 수정 필요 | 소 |

### 프론트엔드 `web/`

| 경로 | PRD ID | 역할 | 난이도 |
|---|---|---|---|
| `lib/recorder-session.ts` | **R-2** | **최고 가치.** MediaRecorder 정지/일시정지 순수 로직. `stopRecording()`은 "절대 reject 하지 않는다" 계약 — 마이크 뺏김(전화 수신) 시 `InvalidStateError` 동기 throw가 상태 정리를 스킵해 **버튼 영구 잠금**되던 실사고(2026-07-17) 수정본. 3초 타임아웃 폴백 포함 | 하 |
| `lib/voice-input.ts` | **R-2** | 음성 우선 → 텍스트 폴백 상태머신(미지원/권한거부/전사 2회 실패 시 편도 전환) | 하 |
| `lib/utils.ts` | 기반 | `cn()`. ⚠️ tailwind.config의 fontSize 토큰과 **반드시 동기화**. 없으면 `text-accent-on`(색)이 `text-lead`(크기)에 먹혀 버튼 글자가 검게 나옴 | 하 |
| `hooks/useAudio.ts` | **R-2** | `useTts`(재생+설정 영속) + `useRecorder`(phase machine, 경과초, iOS pause 미지원 감지, 언마운트 시 마이크 트랙 정리) | 중 |
| `components/interview-flow.tsx` | **R-2, R-3** | 인터뷰 UI 본체. `idle→thinking→awaiting→recording→transcribing→done`. 자동재생 정책 대응, IME 조합 중 Enter 차단(한국어 필수). props 4개로 깔끔히 격리 | 중 |
| `components/response-viewer.tsx` | **C-4** | 의뢰자 응답 열람. **L163-186 전사 렌더 블록이 정확히 필요한 것.** 제거 대상: 6-Lens 에이전트(L51-64, 155-162), 메모 저장(L93-104) | 중 |
| `components/in-app-bridge.tsx` + `lib/in-app-browser.ts` | **C-3** | 카톡 등 인앱 브라우저 감지 → 외부 브라우저 유도. **링크 배포형에 필수** (인앱은 마이크가 막힌다) | 하 |
| `hooks/use-stick-to-bottom.ts` | **R-2** | 채팅 바닥 고정 + 사용자 스크롤 시 해제/복귀 | 하 |
| `components/shared/{button,container}.tsx` | 기반 | pill 버튼, max-w 래퍼 | 하 |
| `tailwind.config.ts` + `styles/globals.css` | 기반 | **묶음이다.** globals.css의 `--accent*` 변수를 tailwind.config가 `var(--accent)`로 참조 → 하나만 빠지면 액센트 색 전부 무효 | 하 |

**의존 패키지**: `clsx`, `tailwind-merge`, `pretendard`, `tailwindcss@3.4`. 집계 차트 쓸 때만 `recharts`.
**`firebase`/`firebase-admin`은 뺄 수 있다** — 위 목록 어디에도 필수가 아니다.

---

## `_reference/` — 복사했지만 그대로 쓰지 말 것

| 경로 | 왜 뒀나 |
|---|---|
| `api/_reference/validation_moderator_prompt.py` | **L162-169가 이 레포 유일의 유도신문 방지 규칙.** "답을 정해놓고 끌어내지 마세요… 전제·방향을 깐 질문은 금지", "5 Why". **M-2 중립성 가드레일 문안의 원본으로 최고 가치.** 단 코드는 가상 FGI 다자토론 전용이니 **문구만 발췌**할 것 |
| `api/_reference/speech_router.py` + `speech_schemas.py` | 위 §3 참조 — `_spellfix`, `(전사,성공여부)` 패턴만 마이닝 |
| `web/_reference/survey-api.ts` | 1012줄 중 90%가 불필요(보상/쿼터/에이전트/백오피스/번역). 필요한 건 6함수뿐 — 아래 참조 |

---

## 새로 짜야 하는 것 (원본에 없음 — 전수 grep 확인)

| PRD ID | 항목 | 현황 |
|---|---|---|
| **M-5** | **PII 마스킹** | **레포 전체 0건.** 존재하는 건 `mask_phone()`(로그 출력 전용, 저장은 원본) / `mask_email()`(계정 힌트)뿐. 인터뷰 텍스트에서 개인정보 탐지·마스킹은 **전부 신규** |
| **M-2** | **중립성 가드레일 (실행 코드)** | 프롬프트 **지시문만** 있고, 생성된 질문이 유도신문인지 **검사·차단하는 코드는 없다.** 사후 검증 레이어 신규 |
| **M-3** | **감정·톤 태깅** | 인터뷰 경로엔 없음. `sentiment`는 가상패널 발화 전용("긍정\|우려\|중립" 3분류). 스키마 아이디어만 참고 |
| **R-2** | **실시간 STT/TTS** | 현재는 배치 업로드. WebSocket/스트리밍 계층 신규. `interview-flow.tsx`도 **턴 단위 요청/응답**이지 스트리밍이 아니다 |
| **M-4** | **전사 요약·집계** | 기존 `summary.py`는 문항-답변용. 대화 transcript → 요약/주제추출/크로스응답자 집계는 신규 |
| **R-1** | **동의 화면** | 독립 동의 화면이 없다. 원본은 구글 로그인 게이트 + 프로필 폼에 흡수됨. 신규 |
| **C-3** | **배포·링크 발급** | 원본은 검수 워크플로우(draft→under_review→final)에 묶여 있음. "즉시 링크 발급" MVP와 형태가 달라 재설계 |
| — | **무인증 API 클라이언트** | `survey-api.ts` 이식보다 신규 ~150줄이 빠르다. 필요 함수: `interviewTurn`, `transcribeAudio`, `synthesizeSpeech`, `fetchVoices`, `getPublicSurvey`, `submitResponse` |
| — | **Furiosa-LLM 어댑터** | 위 §2 |

---

## 제안 순서 (PRD 마일스톤 대응)

- **Day 1** — 순수 로직 복사분 배선(`recorder-session` → `voice-input` → `utils` + tailwind/globals + button/container). 전부 난이도 하
- **Day 2** — Furiosa-LLM 어댑터(§2 3곳 패치) + 무인증 API 클라이언트 6함수 + `useAudio` 이식
- **Day 3** — `interview-flow.tsx` 이식 + 가이드 생성(`questions.py`) + 중립성 가드레일 **신규**
- **Day 4** — 의뢰자 대시보드(전사 렌더는 `response-viewer.tsx` L163-186 복사) + 벤치마크
- **Day 5** — 통합·데모

**SSE 실시간은 후순위** — 현행 턴 단위 요청/응답으로도 인터뷰는 성립한다. TTFT 목표만 먼저 재보는 걸 권한다.

---

## 미해결 / 확인 필요

- **원본 레포 라이선스·소유권** — mindlens_solution은 한양대 프로젝트다. 부트캠프 산출물로 재사용하는 게 계약상 문제없는지 확인 필요. (코드를 옮기긴 했지만 이 판단은 하지 않았다.)
- **무인증 전환의 보안 구멍** — `routers/interview.py`에서 Firebase 인증을 걷어냈다. 그대로 배포하면 LLM 호출이 외부에 열린다. rate limit 또는 세션 토큰 필수.
- 복사만 했고 **새 폴더에서 빌드·테스트는 돌리지 않았다.** `package.json` / `pyproject.toml` / import 경로 재배선이 아직 없다.

---

## 배포 (2026-07-20)

GCP 프로젝트 **`mindlens-furiosa-2026`** (asia-northeast3). 기존 `mindlens-473707`·`mindlens-ai-498501` 은 건드리지 않았다.

| | 주소 |
|---|---|
| 의뢰자 웹 | https://mindlens-web-128792069861.asia-northeast3.run.app |
| API | https://mindlens-api-128792069861.asia-northeast3.run.app |
| 응답자 링크 | `{웹}/i/{project_id}` — `POST /api/projects/{id}/deploy` 가 발급 |

- Cloud Run × 2 (API 는 `api/` 소스빌드, 웹은 Next.js standalone 이미지)
- Cloud SQL Postgres 15 `mindlens-db` (db-f1-micro) — Cloud SQL Python Connector 로 접속
- 시크릿은 전부 Secret Manager. **PowerShell 파이프로 시크릿을 만들지 말 것** — BOM 과 `\r\r\n` 이 붙는다. 파일로 써서 `--data-file` 로 넣어야 한다.

### 실측 (Furiosa RNGD / Qwen3-32B-FP8)

| 항목 | 값 |
|---|---|
| 스트리밍 TTFT | **0.26초** (PRD 목표 1.5초) |
| 인터뷰 한 턴 | 2.4~3.8초 (감정태깅+모더레이터+가드레일 포함) |
| 가이드 생성 | 60~85초 — 문항별 응답 버킷·어휘까지 한 번에 생성 |
| 세션 요약+집계(M-4) | 9~10초 |

`GET /api/projects/{id}/stats` 가 커버리지·probe 비율·가드레일 발동 수를 실측으로 돌려준다 (Day 4 벤치마크용).

## 남은 일

- **실기기 음성 테스트가 아직이다.** 브라우저 자동화가 마이크 권한 모달에서 막혀 동의 화면까지만 확인했다. `interview-flow.tsx` 는 원본에서도 실사용자를 태운 적이 없는 코드라(§1) iOS 사파리 실기기 확인이 필수다.
- **동의 화면의 보관기간 "1년"은 임의로 넣은 값이다.** 법적 문구라 실제 응답자를 받기 전에 확정해야 한다 (`web/app/i/[projectId]/respondent-view.tsx` 의 `RETENTION`).
- **무인증이다.** IP 레이트리밋(60초 30회)만 걸려 있다. 배포 링크를 아는 사람은 누구나 LLM 을 태울 수 있다.
- 원본 레포(한양대 프로젝트) 재사용의 계약상 검토 — 여전히 미해결.
