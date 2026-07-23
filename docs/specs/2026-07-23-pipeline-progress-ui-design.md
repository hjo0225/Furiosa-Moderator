<!--
==========================================================================
 설계 스펙 — 무거운 작업의 실시간 진행 화면 (SSE 파이프라인 이벤트)
 · 브레인스토밍(2026-07-23) 결과. 구현은 이 문서를 근거로만 한다.
 · 확정 사항: 대상 3작업 / 목적=발표·데모 / 접근 A(SSE) / 배치=전체 화면 진행 뷰.
 · 디자인 토큰·컴포넌트 규약의 정본은 `design.md` — 이 문서는 그 §5에 절을 하나 더한다.
==========================================================================
-->

# 무거운 작업의 실시간 진행 화면 — 설계 스펙

**상태:** 설계 확정 · 구현 대기
**기준 시점:** 2026-07-23 / 브랜치 `fix/brand-tab-and-sidebar-cta`

---

## 1. 문제

의뢰자가 누르는 버튼 중 셋이 수십 초~수 분 걸린다. 그동안 화면이 알려주는 것은 버튼 라벨 하나뿐이다.

| 작업 | 현재 피드백 | 상한 |
|---|---|---|
| 가이드 생성 | 버튼 라벨 `만드는 중…` (`guide-panel.tsx:394`) | LLM 타임아웃 **180초** (`api/config.py:42`) |
| 인사이트 생성 | 버튼 라벨 `분석 중…` (`results-panel.tsx:302`) | 세션 수 N에 비례(세션마다 LLM 1회) |
| 자료 업로드·웹 리서치 | 없음 | 파일 크기·후보 수에 비례 |

서버는 통짜 POST 하나로 끝날 때까지 아무것도 내보내지 않는다. 사용자는 멈춘 것과 일하는 것을 구별할 수 없다.

## 2. 목적 — 발표·데모

1순위는 답답함 해소가 아니라 **발표에서 "RNGD가 지금 일하고 있다"를 보이게 만드는 것**이다. 이 선택이 아래 설계를 지배한다.

- 단계 이름만이 아니라 **실제로 무엇을 했는지**를 드러낸다 — 찾아온 근거 스니펫, 세션 `i/N`, 실측 토큰 수, 모델명.
- 수치는 전부 실측이다. `Usage(model, prompt_tokens, completion_tokens)`가 이미 모든 LLM 호출에서 돌아온다(`llm_client.py:212`, `:311`). **추정치를 실측처럼 보여주지 않는다**(AGENTS.md §5, 보고서 §8과 동일 기준).
- AGENTS.md §0.1 계약 1("집계 숫자는 LLM이 세지 않는다")은 인사이트 진행 화면의 한 단계로 **눈에 보이게** 만든다.

### 채택하지 않은 접근

- **잡 테이블 + 폴링** — 새로고침·다중 관전에 강하지만 마이그레이션 + 상태 전이 동시성 설계(§2)가 붙고, Cloud Run은 요청 밖 백그라운드에서 CPU를 스로틀한다. 일정 대비 과하다.
- **프론트에서 예상 시간으로 단계 굴리기** — AGENTS.md §5 "실데이터 필수"에 정면으로 걸린다. 발표에서 실제와 어긋나면 진행 UI가 없느니만 못하다.

---

## 3. 이벤트 계약

기존 `public.py:167`의 `_sse()` 포맷(`data: {json}\n\n`)을 그대로 쓴다. 이벤트는 네 종류뿐이다.

```jsonc
// ① 최초 1회 — 프론트가 회색 ○ 목록을 미리 그린다
{"steps": [{"key": "material", "label": "자료 요약 조합"},
           {"key": "evidence", "label": "근거 검색"}, …]}

// ② 단계 전이
{"step": "evidence", "status": "start"}
{"step": "evidence", "status": "done", "ms": 1834,
 "detail": {"found": 3, "samples": [{"text": "…", "source": "보고서.pdf"}]}}

// ③ 최종 결과 — 기존 응답 스키마 그대로
{"result": { … }}

// ④ 실패
{"error": "가이드 생성에 실패했습니다: …"}
```

**`status` = `start | done | skip | error`.**

`skip`은 장식이 아니다. 자료가 없으면 RAG 검색을 통째로 건너뛴다(`projects.py:188`). 이를 "완료"로 위장하지 않고 "건너뜀"으로 표시한다.

**진행 중 갱신이 필요한 단계**(세션 요약 N회, 청크 임베딩 N개)는 `status: "start"`를 `detail.done`/`detail.total`을 실어 여러 번 보낸다. 프론트는 같은 `step` 키의 마지막 값으로 덮어쓴다.

```jsonc
{"step": "summarize", "status": "start", "detail": {"done": 3, "total": 12}}
```

**타입 정의**(`web/lib/pipeline.ts`)

```ts
export type StepStatus = "start" | "done" | "skip" | "error";
export type StepDecl = { key: string; label: string };
export type PipelineEvent =
  | { steps: StepDecl[] }
  | { step: string; status: StepStatus; ms?: number; detail?: Record<string, unknown> }
  | { result: unknown }
  | { error: string };
```

---

## 4. 백엔드 — 구현은 한 벌, 노출은 두 겹

로직을 복제하면 반드시 갈라진다. 각 작업의 본문을 **이벤트를 yield하는 제너레이터 하나**로 옮기고, 두 엔드포인트가 같은 제너레이터를 공유한다.

```python
# api/services/progress.py (신규) — 공통 헬퍼
def sse(events: Iterator[Event]) -> Iterator[str]: ...   # data: {json}\n\n
def drain(events: Iterator[Event]) -> Any: ...           # result 반환, error 는 HTTPException 으로 승격

# api/routers/projects.py
def run_guide(pid, body) -> Iterator[Event]:             # 단계마다 yield, 마지막에 {"result": …}
    ...

@router.post("/{pid}/guide", response_model=InterviewGuide)   # 기존 — 계약 그대로
def generate_guide(pid, body): return drain(run_guide(pid, body))

@router.post("/{pid}/guide/stream")                           # 신규
def generate_guide_stream(pid, body):
    return StreamingResponse(sse(run_guide(pid, body)), media_type="text/event-stream")
```

**기존 엔드포인트 4개의 시그니처·응답 스키마·에러 코드는 바뀌지 않는다.** API 테스트 276건은 그대로 통과해야 한다 — 이것이 이 구조를 택한 이유다.

### 신규 엔드포인트

| 신규 | 기존(유지) |
|---|---|
| `POST /projects/{pid}/guide/stream` | `POST /projects/{pid}/guide` |
| `POST /projects/{pid}/insight/stream` | `POST /projects/{pid}/insight` |
| `POST /projects/{pid}/material/stream` (multipart) | `POST /projects/{pid}/material` |
| `POST /projects/{pid}/research/stream` | `POST /projects/{pid}/research` |
| `POST /projects/{pid}/materials/web/stream` | `POST /projects/{pid}/materials/web` |

웹 리서치는 호출이 둘로 갈려 있다(`/research` = 검색어 생성 + SERP, `/materials/web` = 크롤 + 저장 + 인덱싱). 스트림도 둘로 둔다. 합치지 않는다 — 사이에 사용자가 후보를 고르는 단계가 있다.

---

## 5. 단계 정의 (실제 코드에서 뽑은 것)

### 5.1 가이드 생성 — 6단계 (`projects.py:218-264`)

| key | 라벨 | 내용 | detail |
|---|---|---|---|
| `material` | 자료 요약 조합 | `compose_guide_material(get_slot_summaries)` | `{"slots": n}` |
| `evidence` | 근거 검색 | 슬롯별 임베딩 검색 2~3회 · dedup · cap 9 | `{"found": n, "samples": [{text, source}]}` · 자료 없으면 **skip** |
| `audience` | 대상 청중 수집 | `collect_personas(p)` | `{"personas": n}` · 코퍼스 비면 **skip** |
| `llm` | 문항 생성 | `structured(…, max_tokens=2000)` — **RNGD** | `{"model": …, "tokens": n, "questions": n}` |
| `normalize` | 응답 버킷 정규화 | `_split_goal_from_text` · `_normalize_buckets` | `{"buckets": n}` |
| `quality` | 품질 점검 | `evals.guide_quality_report` (비차단) | `{"leading": n, "warnings": n}` |

`evidence`의 `samples`는 최대 2건, 각 120자로 잘라 보낸다 — 발표 화면에서 읽히는 분량이면 충분하고, 자료 본문을 통째로 흘리지 않는다.

### 5.2 인사이트 생성 — 5단계 (`projects.py:450-541`)

| key | 라벨 | 내용 | detail |
|---|---|---|---|
| `sessions` | 완료 세션 수집 | `list_sessions` 중 `completed` | `{"total": n}` · 0건이면 **error**(기존 400 유지) |
| `summarize` | 세션 요약 | 세션마다 `llm.text` — **진행 중 `done/total` 갱신** | `{"done": i, "total": n, "cached": m}` |
| `insight` | 종합 인사이트 | `structured(Insight, max_tokens=3000)` + overall 보정 | `{"model": …, "tokens": n, "themes": n}` |
| `counts` | **DB 실측 집계** | `sentiment_counts` · `theme_mention_counts` · `bucket_distribution` | `{"source": "db-group-by", "sentiment": n, "buckets": n}` |
| `qsummary` | 문항별 요약 | `structured(QuestionSummariesOut)` (best-effort) | `{"items": n}` · 실패해도 **skip**으로 넘어감 |

`counts` 단계의 라벨은 화면에서 `감정·테마·버킷 분포 — DB group-by (LLM 아님)`으로 쓴다. AGENTS.md §0.1 계약 1을 관객에게 보이게 만드는 지점이다.

`summarize`의 `cached`는 이미 `s.summary`가 있어 LLM을 안 태운 세션 수다. 재분석 시 왜 빠른지가 화면에 설명된다.

### 5.3 자료 업로드 — 4단계 (`projects.py:325-346`, `pipeline.py:196-240`)

| key | 라벨 | 내용 | detail |
|---|---|---|---|
| `extract` | 텍스트 추출 | `extract_text` (PDF 파싱) | `{"chars": n}` |
| `chunk` | 청킹 | `chunks_with_angle` | `{"chunks": n}` |
| `embed` | 임베딩 | `embed_texts` — **RNGD · Qwen3-Embedding-8B** | `{"chunks": n}` |
| `slot` | 슬롯 요약 | `refresh_slot` → `summarize_slot` (LLM) | `{"angle": "현상"}` |

`index_material`은 지금 청킹·임베딩·저장을 한 함수 안에서 한다. 진행 표시를 위해 **내부를 쪼개지 않는다** — 대신 `chunk`/`embed`를 이 함수 진입 전후로 감싸고, 청크 수는 `chunks_with_angle` 결과로 미리 센다. 인덱싱 실패를 흡수하는 현재 동작(`pipeline.py:230`)은 그대로 두고 `skip`으로 표시한다.

### 5.4 웹 리서치 — `/research` 2단계 + `/materials/web` 4단계

`queries`(검색어 생성 LLM) → `serp`(SERP 검색) / `crawl`(본문 수집) → `store`(저장) → `embed`(증분 인덱싱) → `slot`(슬롯 재요약).

---

## 6. 프론트

### 6.1 파일

| 파일 | 역할 |
|---|---|
| `web/lib/sse.ts` (신규) | `fetch` + `ReadableStream` SSE 파서. `EventSource`는 POST가 안 돼서 fetch로 간다. |
| `web/lib/pipeline.ts` (신규) | 이벤트 타입 + `usePipeline()` 훅 (단계 배열·경과·토큰 누적·중단) |
| `web/components/shared/pipeline-progress.tsx` (신규) | 전체 화면 진행 뷰 |
| `guide-panel.tsx` · `results-panel.tsx` · 자료 업로드 | 위 컴포넌트를 호출만 |

**현재 웹은 SSE를 전혀 소비하지 않는다.** 서버 패턴(`public.py:194`)은 프로덕션에서 검증됐지만 클라이언트 파서는 새로 쓴다. `sendTurn`은 비스트림 POST다.

### 6.2 전체 화면 진행 뷰

작업이 시작되면 콘텐츠 영역 전체를 차지한다. 사이드바·헤더바는 유지한다(길을 잃지 않게).

```
          가이드를 만들고 있어요
                   0:24

  ✓ 자료 요약 조합                 0.1s
  ✓ 근거 검색 · 3건 찾음          1.8s
    “20대 아침식사 결식률 42%…”
     └ 보고서.pdf
  ◐ 문항 생성
     └ RNGD · Qwen3-32B-FP8
  ○ 응답 버킷 정규화
  ○ 품질 점검
  ─────────────────────────────────
  3/6 단계 · 토큰 1,240 · 백그라운드로 두기
```

- 완료 단계의 소요 시간은 서버가 보낸 `ms`를 쓴다(클라이언트 추정 아님).
- 상단 경과 타이머만 클라이언트 계산이며, 이건 벽시계라 추정이 아니다.
- 아직 안 온 단계는 회색 `○` — `steps` 선언 덕분에 처음부터 전체 길이가 보인다.
- **모델명은 프론트에 박지 않는다.** 서버가 `detail.model`로 실어 보낸다 — LLM은 `Usage.model`,
  임베딩은 `get_settings().embed_model`(기본 `furiosa-ai/Qwen3-Embedding-8B`, `config.py:46`).
  환경변수로 모델을 바꿔도 화면이 거짓말하지 않게 한다. 값이 없으면 `—`.

---

## 7. design.md 델타 (구현보다 먼저 커밋)

`design.md` §5에 **`작업 진행(파이프라인) 화면`** 절을 새로 넣는다. 현재 §5 "상태 화면"은 로딩을 **"스켈레톤 시머(텍스트 없음)"**로만 규정하고 `불러오는 중…` 텍스트를 폐기했기 때문에, 단계 이름이 보이는 화면은 디자인 시스템에 없는 범주다. 규정할 것:

- **스켈레톤과의 경계** — 1초 미만 예상 = 스켈레톤, 그 이상 = 진행 뷰. 둘을 섞지 않는다.
- **단계 아이콘** — `check`(완료) · `loader-2`(진행, 회전) · `circle`(대기) · `minus`(건너뜀) · `alert-triangle`(실패). 전부 `lucide-react`, **이모지 금지**(AGENTS.md §2 하드룰).
- **수치 = 텔레메트리 mono**, 미측정은 `—`. 벤치마크 화면과 같은 규칙(design.md §5 벤치마크).
- **색** — 진행 중 = `red`(NPU가 일하는 중), 완료 = `go`, 건너뜀 = `ink-faint`, 실패 = `maroon`(brand red와 절대 안 섞음, design.md §1 시맨틱).
- **모션** — `loader-2` 회전만. `prefers-reduced-motion`은 globals.css 전역 규칙이 이미 처리한다.

---

## 8. 실패 · 중단 · 이탈

### 8.1 저장 시점을 앞당긴다 (동작 변경 — 검토 필요)

현재 `generate_guide`는 함수 끝에서 저장한다(`projects.py:264`). 스트림 중 클라이언트가 끊기면 제너레이터는 다음 yield 지점에서 중단되고, **3분짜리 NPU 작업이 통째로 날아간다.**

→ **LLM 생성 + 정규화 직후에 저장하고**, 품질 점검(비차단 로그 전용)은 그 뒤로 둔다. 새로고침·실수로 이탈해도 결과가 남는다.

품질 점검은 이미 반환 가이드를 바꾸지 않고 실패해도 생성을 막지 않는 로그 전용이므로(`projects.py:248-262`) 저장 뒤로 옮겨도 의미가 보존된다. **다만 이는 진행 UI와 무관한 동작 변경이므로 구현 전 사람 확인을 받는다.** 승인이 안 나면 저장 순서는 그대로 두고 이탈 시 손실을 감수한다.

### 8.2 중단

`AbortController`로 스트림만 끊는다. 이미 떠난 NPU 호출을 중간에 죽일 수는 없으므로 버튼 문구는 **"취소"가 아니라 "백그라운드로 두기"**로 한다. 취소라고 쓰면 거짓말이 된다.

### 8.3 실패

`error` 이벤트가 오면 그 단계만 `maroon` + `alert-triangle`로 남기고 앞선 완료 단계는 그대로 둔다(어디까지 갔는지가 정보다). 하단에 `ErrorState`의 `rotate-cw` 재시도.

### 8.4 멱등성 (AGENTS.md §2)

세 작업 모두 **기존 행을 덮어쓰는 upsert**다(`save_guide` · `save_insight`). 중복 실행이 행을 늘리지 않으므로 새 멱등성 가드는 필요 없다. 다만 **더블클릭 방지는 프론트에서** — 진행 뷰가 떠 있는 동안 트리거 버튼은 언마운트된다(비활성화가 아니라 화면이 바뀜).

자료 업로드는 행이 늘어나지만 이건 기존 동작이고 이 작업의 범위가 아니다.

---

## 9. 테스트

**API** (`api/tests/`, LLM 목킹은 `test_interview_moderator.py` 패턴)
1. `steps` 선언의 key 집합이 실제 방출된 `step` 이벤트의 key 집합과 일치한다(선언과 실제가 갈리는 것을 막는다).
2. `drain(run_x(...))`의 반환이 기존 엔드포인트 응답과 동일하다 — 두 겹 노출의 핵심 보증.
3. LLM 실패 시 `error` 이벤트가 나오고, 비스트림 경로에서는 같은 상황이 기존과 같은 HTTP 코드로 뜬다.
4. 자료 없는 프로젝트에서 `evidence`가 `skip`으로 방출된다.

**웹** — `npm run typecheck` · `npm run build` · `npm run lint`. SSE 파서는 순수 함수(문자열 청크 → 이벤트 배열)로 분리해 단위 테스트 가능하게 둔다.

**CI 4종 전부 로컬 통과 후 PR**(AGENTS.md §0).

---

## 10. 범위 밖 (별건)

- **가이드 문항 수 vs 인터뷰 턴 예산** — `MAX_ASKED = 12`(`strategize.py:9`)와 `Q_STREAK_CAP = 4`(`:11`) 아래에서 문항이 7개면 문항당 평균 1.7턴이다. 앞 문항이 4턴을 먹으면 뒤 문항은 `pending`인 채 `end_reason="max_turns"`로 끝난다. 커버리지 문제이며 진행 UI와 무관하다. 별도 티켓.
- 가이드 생성 LLM을 스트리밍으로 바꿔 JSON이 써지는 걸 글자 단위로 보여주는 안 — `structured`의 자가교정 재시도 계약을 건드려 별도 결정이 필요하다.
- 잡 테이블 기반 백그라운드 실행(§2 채택하지 않은 접근).
