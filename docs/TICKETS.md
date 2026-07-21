# mindlens × LangGraph — 실행 티켓

> 출처: [`LANGGRAPH_PLAN.md`](../LANGGRAPH_PLAN.md) · 그림 문서: [`docs/langgraph-plan.html`](./langgraph-plan.html)
> 상태: **설계 단계 · 코드 착수 전** — 이 티켓들이 착수 목록이다.
> 단위: 마이그레이션 0~5단계 = 티켓 6장. 각 티켓은 **목표 / 작업 / 검증 / 의존성**.

## 진행 순서 · 의존성

```
🔵 필수 코어 (여기까지만 해도 성립)          🟡 선택 확장 (원할 때 하나씩)
TICKET-0 ─▶ TICKET-1 ─▶ TICKET-2 ──┬─▶ TICKET-3
(게이트)   (필수①②)   (필수③)     ├─▶ TICKET-4
                                    └─▶ TICKET-5 (코어와 독립, 병행 가능)
```

- **TICKET-0이 게이트다.** Qwen3 자율 tool choice 실측이 통과 못 하면 TICKET-5(도구 4종) 설계가 폴백으로 틀어진다 → 최대 리스크를 먼저 제거.
- **TICKET-5는 코어와 독립**이라 1~4와 병행 가능. 나머지는 순차.

## 전역 불변식 (모든 티켓 공통 제약 — §7)

- **PII는 그래프 진입 전, HTTP 핸들러에서 마스킹.** `Command(resume=원문)`은 체크포인트에 박제된다.
- **interrupt 재개 시 노드는 처음부터 재실행**(LangGraph 규약) → interrupt 앞 로직은 멱등. 저장은 `speak`에서 완료 후 잠듦.
- 가드레일 문안·정규식·재귀 금지 그대로. **12턴 하드 가드 = 결정론 엣지.**
- "숫자는 DB가 센다" — 대시보드 집계는 SQL. `turns`/`sessions` 테이블 유지.
- NPU 순수성 — LLM·임베딩·(리랭커) 전부 Furiosa.
- `(전사, ok)` 계약·speech 계층 불변. `llm_client`의 Qwen3 튜닝 보존(기존 메서드 불변, **추가**만).
- 구엔진(`moderator.py`)은 플래그로 병행하다 마지막에 제거.

---

## TICKET-0 — 기반 공사 + Qwen3 도구선택 실측 🚧 게이트

**목표.** 그래프를 얹기 전 토대를 깔고, **최대 리스크(Qwen3 자율 tool choice 미검증)를 30분 실측으로 먼저 제거**한다. 이 실험 통과가 이후 전체의 게이트.

**작업.**
- [x] `llm_client.py`에 `chat(tools=)` **추가** — 기존 메서드 불변(Qwen3 튜닝 보존)
- [x] `llm_client.py`에 `embed()` **추가**
- [x] `requirements`에 langgraph 2종 + `langgraph-checkpoint-postgres`
- [x] Postgres: `CREATE EXTENSION vector` (같은 Cloud SQL, PG15 지원)
- [x] **Qwen3 자율 tool choice 30분 실측** — 도구 4종 후보로 호출 품질 확인

**검증.** tool choice 실험 통과 = **게이트**. 통과해야 다음 진행. 실패 시 폴백(도구 선택만 구조화 출력 강제)으로 방향 확정.

**결과(2026-07-21).** 게이트 ❌ 미달 → **폴백 확정**: 정확도 71%(기준 80%) · 오발동 0% · JSON 유효율 100% · 지연 1.16s. thinking=on 은 57%/11%/4.4s 로 전면 악화. 임베딩은 기본 4096, `dimensions=1024` 네이티브 지원(→ 1024 MRL 채택). pgvector 라이브 검증은 DB env 부재로 배포 환경에서 수행 예정. 상세: [실측 문서](./experiments/2026-07-21-qwen3-tool-choice.md)

**의존성.** 없음 (첫 단계).

**리스크(§8, 최대).** Qwen3 자율 tool choice 미검증. 이 게이트가 TICKET-5(도구 4종) 설계 전체를 좌우.

---

## TICKET-1 — 그래프 골격: 스레드화 + 노드 분해 (필수①②)

**목표.** 인터뷰 하나를 **살아있는 실행 하나**로 만들고(스레드화), 만능 1콜을 **역할별 노드**로 쪼갠다. LLM 호출 수는 지금과 동일 — 콜 증가가 아니라 역할 분리.

**작업.**
- [ ] `api/interview/graph.py` — interrupt 루프: 세션 시작=그래프 시작 · `interrupt()`로 발화 대기 · `Command(resume)`로 재개 · `END`로 종료
- [ ] `thread_id = session_id`
- [ ] 노드 5개: `listen` / `strategize` / `generate` / `guard` / `speak`
- [ ] `PostgresSaver` 체크포인터 연결 (`setup()`)
- [ ] `routers/public.py`: turn → `Command(resume=마스킹된 발화)`
- [ ] PII 마스킹은 그래프 진입 전 HTTP 핸들러에서 (전역 불변식)
- [ ] interrupt 앞 로직 멱등 보장, 저장은 `speak`에서
- [ ] `main.py` `_GUARDED` 확장
- [ ] 구엔진(`moderator.py`)은 플래그로 병행

**검증.** 기존 pytest 통과 + **턴 지연 실측**.

**의존성.** TICKET-0 (`chat`, langgraph 설치, 체크포인트 테이블).

---

## TICKET-2 — 상태 이동 + 커버리지 원장 (필수③)

**목표.** 대화·커버리지·페이스를 **그래프 State로** 옮겨 체크포인트가 저장할 대상을 만든다. 커버리지를 출석부(`covered=[q1,q2]`)에서 **취재 수첩(원장)**으로 바꾼다.

**작업.**
- [ ] `api/interview/state.py`: `InterviewState` (messages+`add_messages` · ledger · asked · probe_streak · analysis · plan · draft · done · end_reason)
- [ ] `CoverageEntry`: `status`(pending/touched/satisfied/saturated) · `facts`(알아낸 것) · `hooks`(안 판 떡밥)
- [ ] 출석부 → 원장 전환 및 갱신 로직 (v1은 노드 내 갱신; 슬로우패스 이사는 TICKET-4)
- [ ] **정직한 종료**: "문항 다 입에 올림"이 아니라 모든 goal이 `satisfied`이거나 `saturated`일 때
- [ ] revisit 근거 확보 (빈약 문항 재방문 판단 재료)
- [ ] 대시보드용 도메인 테이블은 그대로 유지 (이원화가 의도된 설계)

**검증.** `stats`로 **probe율 비교** (기존 대비).

**의존성.** TICKET-1 (그래프가 State를 소유하는 구조).

---

## TICKET-3 — 행동 7종 확장

**목표.** 행동 메뉴를 2개 → 7개로. `strategize`가 구조화 출력으로 행동을 고르고 **조건 엣지**로 분기한다.

**작업.**
- [ ] `strategize` 노드: 구조화 출력으로 행동 7종 선택 → 조건 엣지 분기
- [ ] 추가 행동 4종: `clarify`(되묻기) · `challenge`(모순 확인) · `revisit`(재방문) · `redirect`(복귀) — 기존 probe·advance·close에 더함
- [ ] `challenge`·콜백: `listen` 노드에 "앞선 발언과 모순 확인" 지시 (recall 없이 — 전체 대화가 프롬프트에 다 있음)
- [ ] 12턴 하드 가드 = 결정론 엣지로 유지

**검증.** 대화 품질 **수동 평가**.

**의존성.** TICKET-2 (원장 — `revisit`이 빈약 문항 근거로 필요).

---

## TICKET-4 — 슬로우패스 + SSE 스트리밍

**목표.** 무거운 분석을 **응답자가 말하는 ~20–30초(공짜 시간)**에 병렬로 숨기고, 질문을 스트리밍으로 내보낸다. 목표 체감 첫 토큰 1.5~2.5s (현재 2.4~3.8s 동급 이하).

**작업.**
- [ ] `reflect` 노드 (슬로우패스, `Send` 병렬): 원장 갱신 · 요약 압축 · 다음 수 예습
- [ ] 원장 갱신을 슬로우패스로 이사 (체감 지연 0)
- [ ] 감정 태깅을 슬로우패스로 이사 (다음 질문 생성에 미사용임 확인)
- [ ] SSE: 기존 `stream_text`(TTFT 0.26s) 연결만 — `routers/public.py`
- [ ] `guard` 위치: v1은 스트리밍 **앞** (+~0.5s. 유도신문은 스트리밍 후 무를 수 없음) — §11 미결정, 제안값

**검증.** 턴 지연 **재실측** (목표 체감 첫 토큰 1.5~2.5s).

**의존성.** TICKET-1 (`speak`), TICKET-2 (원장 — 슬로우패스가 갱신 대상).

---

## TICKET-5 — 브리핑 라이트(RAG) + 도구 4종 · 코어와 독립

**목표.** 의뢰자 도메인을 아는 인터뷰어. 교과서 RAG 파이프라인 — **업로드 전용**(웹 자동 리서치·승인 게이트는 제거)이고, tool-loop의 재료가 될 도구 4종을 붙인다.

**작업.**
- [ ] `api/briefing/`: 업로드→청크 분할→임베딩→`pgvector(briefing_chunks)` 인덱싱 파이프라인 (단순 — LangGraph 불필요)
- [ ] `api/services/embeddings.py`
- [ ] 도구 4종을 `generate` 노드에 연결:
  - [ ] `brief(term)` — `briefing_chunks` 유사도 검색 (진짜 RAG). 중립성 필터(용어·사실만)·출처 보존
  - [ ] `playbook(situation)` — 정성조사 기법 사전(5 Why·래더링·CIT), 결정론
  - [ ] `ledger_report()` — 원장 요약(남은 goal·빈약 문항·미회수 떡밥), 결정론
  - [ ] `pace()` — 남은 턴 예산·페이스 경고, 결정론
- [ ] 리랭커: v1은 임베딩 top-k만, API 형태 확인 후 추가 (§8 리스크)

**검증.** `brief` 품질 평가.

**의존성.** TICKET-0 (`embed`, pgvector), TICKET-2 (`ledger` — `ledger_report` 대상). **나머지 코어와 독립 → 병행 가능.**

---

## 착수 전/중 결정할 것 (§11 미결정 — 팀 논의)

- [ ] `guard` 위치: 스트리밍 앞/뒤 → **TICKET-4** (제안: 앞)
- [ ] 임베딩 차원 → **TICKET-0/5** (제안: 1024 MRL)
- [ ] `listen`+`strategize` 통합 1콜 vs 분리 2콜 → **TICKET-1** (제안: 통합 시작)
- [ ] 브리핑 업로드 UI 위치 → **TICKET-5** (제안: guide-panel 옆 탭)
- [ ] LangSmith 트레이싱 도입 여부 (도입 시 `hide_inputs` 필수 — PII)
