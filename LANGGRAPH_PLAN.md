# mindlens × LangGraph — 도입 계획

> **전제: 우리는 LangGraph를 쓰기로 결정했다.** 질문은 "쓸까 말까"가 아니라
> "LangGraph의 핵심 기능을 장식이 아니라 하중을 받게 쓰려면 mindlens를 어떻게 바꾸나"다.
>
> 상태: 설계 단계 — 코드 착수 전.
> 팀 공유용 그림 문서: https://claude.ai/code/artifact/c15620b5-784f-413d-97b8-a2ff559599df

## 0. 확정된 범위 (2026-07 결정 — 컷 2건 반영)

과설계를 덜어낸 뒤의 최종 범위. 아래 표가 이 문서 전체의 요약이다.

| 항목 | 결정 | 근거 |
|---|---|---|
| 인터뷰 스레드화 (interrupt 루프) | ✅ 필수 | LangGraph의 존재 이유. §3 필수① |
| 만능 1콜 → 노드 분해 | ✅ 필수 | 노드 1개는 그래프가 아님. §3 필수② |
| 상태를 그래프 State로 | ✅ 필수 | 체크포인트가 저장할 대상. §3 필수③ |
| 커버리지 **원장** (물었음→알아냈음) | ✅ 유지 | 인프라 불필요. revisit·정직한 종료의 근거 |
| 행동 메뉴 7종 | ✅ 유지 | 조건 엣지의 분기 대상. challenge·콜백은 전체 대화 참조로 가능 |
| 슬로우패스 (Send 병렬) | ✅ 유지 | 노드 분해의 지연을 사람의 시간에 숨김 |
| SSE 스트리밍 | ✅ 유지 | 기존 `stream_text`(TTFT 0.26s) 연결만 |
| 브리핑 **라이트** (RAG) | ✅ 유지, 축소 | 교과서 RAG. **업로드 전용** — 웹 자동 리서치·승인 게이트 제거 |
| **recall (과거 발화 검색)** | ✂️ **컷** | 인터뷰가 ~24턴(≈4K 토큰) · 12턴 캡. Qwen3 32K 창에 **전체 대화가 다 들어감** → 검색 불필요 |
| **스터디 메모리 (Store)** | ✂️ **컷** | 12질문 규모에 과함. 세션 간 장기기억은 이번 범위 밖 |

컷의 파급: `turn_embeddings` 테이블 소멸, 슬로우패스의 "임베딩 적재" 작업 소멸,
pgvector는 `briefing_chunks` 하나만 담당, 도구 6종 → **4종**, 웹 검색 API 의존 소멸.

---

## 1. STEP 1 — 지금의 한계 4가지

현재도 잘 돈다. 하지만 구조적으로 막힌 게 4개 있고, 전부 "더 좋은 인터뷰어"로 가는 길목이다.

1. **생각이 한 덩어리 (만능 1콜).** 파고들지·넘어갈지·끝낼지를 LLM 1콜이 전부 결정.
   행동을 프롬프트 문장 순서로 조종하다 "7턴 내내 대본만 읽은" 사고 (`moderator.py:46` 주석).
2. **매 턴 기억 재조립.** "기다림"이 코드에 없다. 요청마다 DB에서 대화 전체를 다시 읽고,
   답하고, 전부 잊는다 — 매 턴 새 직원이 서류철 읽고 퇴근하는 구조.
3. **행동이 2개뿐.** "꼬리질문 / 다음 문항"만. 모순 확인·되묻기·재방문을 넣을 자리가 없다.
4. **의뢰자의 도메인을 모른다.** 응답자가 "배민클럽 때문에 갈아탔어요"라고 해도 그게 뭔지 모른다.
   → 헛다리 질문 또는 "그게 뭐예요?"(응답자가 설명하느라 흐름 끊김). **이 한계만 RAG가 필요.**
   나머지 3개는 RAG 없이 해결된다.

## 2. STEP 2 — LangGraph는 언제 쓰나 (판단 기준)

병렬처리·분기·재시도는 파이썬 기본기다. LangGraph의 본체는 **"실행을 게임 세이브처럼
저장했다 이어하기"**(durable execution) — 일반 함수로는 못 만드는 능력이다.

**판단 기준 (하나라도 맞으면 값어치):**
- 사람 입력을 기다렸다 이어가야 한다 → 인터뷰가 정확히 이것 ✓
- 실행이 요청 하나보다 오래 산다 → 인터뷰는 6~12턴 ✓
- 같은 루프를 돌며 상태가 쌓인다 → 인터뷰의 본질 ✓
- 중간 상태를 저장·복원·되감기 → "7턴에 왜 안 캐물었지?" 디버깅 ✓

**같은 기준을 RAG에도 적용한다 (RAG = 프롬프트에 다 못 싣거나 낭비일 때만):**

| | 크기 | 프롬프트에 다 들어가나 | 결론 |
|---|---|---|---|
| 대화 이력 | ~24턴 ≈ 4K 토큰, 12턴 캡 | ✅ 32K 창에 여유 | RAG 불필요 → **recall 컷** |
| 브리핑 문서 | 의뢰자가 뭘 올릴지 통제 불가 (30페이지일 수도) | ❌ 보장 못 함 | 검색 필요 → **brief 유지 (진짜 RAG)** |

## 3. STEP 3 — 무엇을 바꾸나

LangGraph = "노드들이 · 공유 State를 주고받으며 · 오래 사는 실행 안에서" 도는 것.
지금 코드엔 셋 다 없다. 그 셋을 만드는 게 **필수 개조 3개**.

**필수 ① 인터뷰를 스레드로.** `thread_id=session_id`. 세션 시작=그래프 시작, 발화 대기=`interrupt()`로
잠들기, 턴 요청=`Command(resume=발화)`로 깨우기, 종료=END. → 일시정지·이어하기·크래시 복구·타임트래블 해금.

**필수 ② 만능 1콜을 노드로 분해.** listen(분석)/strategize(전략)/generate(질문)/guard(검수)/speak(출력).
**LLM 콜 수는 지금과 동일** — 콜 증가가 아니라 역할 분리. 판단마다 기록·테스트·디버깅 가능.

**필수 ③ 상태를 그래프 State로.** 대화·커버리지·페이스를 그래프가 소유 → 체크포인트가 저장할 대상이 생김.
(대시보드용 도메인 테이블은 그대로 유지 — 이원화가 의도된 설계.)

**선택 확장 5개** (원할 때 하나씩, 전부 미루거나 잘라도 됨):
행동 7종 · 슬로우패스 · SSE 스트리밍 · 브리핑 라이트(RAG) · 도구 4종.

### 3.1 상태 설계 — 원장(ledger)이란

지금 `covered = [q1, q2]`는 **출석부**다("q1을 입에 올렸다"가 전부). "잘 몰라요"로 끝나도 ✓ 처리된다.
원장은 문항별 **취재 수첩**으로 바꾼다 — 상태·알아낸 사실·안 판 떡밥 3칸.

```python
class CoverageEntry(TypedDict):
    status: Literal["pending", "touched", "satisfied", "saturated"]
    facts: list[str]        # 이 문항에서 실제로 알아낸 것
    hooks: list[str]        # 파고들 만했는데 안 판 떡밥

class InterviewState(TypedDict):
    project_id: str; session_id: str; guide: dict; lang: str
    messages: Annotated[list, add_messages]     # 전체 대화(12턴 캡이라 통째 보관)
    ledger: dict[str, CoverageEntry]
    asked: int; probe_streak: int
    analysis: dict; plan: dict; draft: str
    done: bool; end_reason: str
```

원장이 있어야: **revisit**(빈약한 문항 재방문 — 지금은 이미 ✓라 다시 갈 이유를 모름),
**정직한 종료**("문항 다 입에 올림"이 아니라 "모든 goal이 satisfied이거나 더 캐도 안 나올 때").
갱신은 슬로우패스에서 하므로 체감 지연 0.

### 3.2 행동 메뉴 7종 (조건 엣지의 분기 대상)

probe · advance · close (기존) + clarify(되묻기) · challenge(모순 확인) · revisit(재방문) · redirect(복귀).
challenge·콜백은 **전체 대화가 프롬프트에 다 있으므로** listen 노드에 "앞선 발언과 모순 확인"을
지시하면 recall 없이 잡힌다. 12턴 하드 가드는 결정론 엣지로 유지.

### 3.3 도구 4종 (tool-loop의 재료)

| 도구 | 정체 | 기반 |
|---|---|---|
| `brief(term)` | 브리핑 팩 검색 — 도메인 용어·사실 (진짜 RAG) | briefing_chunks · NPU 임베딩(+리랭커) |
| `playbook(situation)` | 정성조사 기법 사전(5 Why·래더링·CIT) — `_reference`의 "5 Why" 승격 | 결정론 사전 |
| `ledger_report()` | 원장 요약 — 남은 goal·빈약 문항·미회수 떡밥 | 결정론 |
| `pace()` | 남은 턴 예산·페이스 경고 | 결정론 |

### 3.4 브리핑 라이트 (유일한 RAG 자리)

교과서 RAG 파이프라인 — 바뀌는 건 문서 입구뿐:

```
문서 입구 → 청크 분할 → 임베딩 → pgvector(briefing_chunks) → brief() 유사도 검색 → 프롬프트 주입
   ↑
[의뢰자 업로드만]   ← 라이트. 웹 자동 리서치·승인 게이트는 제거(풀버전에서 컷)
```

인터뷰 중: 응답자가 "배민클럽"을 말함 → `brief("배민클럽")` → 업로드 문서의 청크 발견 →
"배민클럽 구독하고 나서 주문 패턴이 어떻게 달라지셨어요?" (아는 사람의 질문).
나중에 풀버전이 필요하면 입구에 research 노드만 추가 — RAG 본체는 그대로.

**규칙:** 인덱싱(업로드→임베딩)은 단순 파이프라인이라 LangGraph 불필요. brief() 검색만
인터뷰 그래프의 도구로 쓰인다. 중립성 필터(용어·사실만 검색 대상)·출처 보존은 유지.

## 4. STEP 4 — 완성된 그래프

```
           START → opening → speak(스트리밍+저장)
                                │
    ┌────────────────────▶ reflect ── 슬로우패스(Send 병렬): 원장 갱신·요약 압축·다음 수 예습
    │                          │
    │                     【interrupt】 발화 대기(체크포인트) — Command(resume=마스킹된 발화)
    │                          │
    │                       listen ── 사실·감정·떡밥·모순·품질
    │                          │
    │                     strategize ── 행동 7종 선택(구조화 출력 → 조건 엣지)
    │                          │
    │        ┌─────────────────┴──────────────┐ close → farewell → END
    │        │ probe/clarify/challenge/         │
    │        │ advance/revisit/redirect         │
    │      generate ── 도구: brief·playbook·ledger·pace
    │        │
    │      guard ── 가드레일 서브그래프(기존 자산)
    └────── speak
```

Supervisor(자유 LLM 라우팅)는 안 쓴다 — 라우팅마다 LLM 콜이라 지연 1.5~2배(실전 보고).
구조화 출력 → 조건 엣지가 더 빠르고 디버깅 가능.

**얻는 것:** 더 인터뷰어다운 대화(콜백·모순 확인·재방문) · 타임머신 디버깅 ·
지연 동급 이하 · 끊기지 않는 인터뷰(크래시 복구) · 눈에 보이는 구조 · LangGraph 9/10 활용.

## 5. 지연 예산

- 패스트패스: listen+strategize 통합 1콜(~0.8–1.2s) + generate 스트리밍(TTFT 0.26s) + guard
- 목표 체감 첫 토큰 **1.5~2.5s** (현재 2.4~3.8s 동급 이하). 비결: 슬로우패스 프리페치
- 감정 태깅은 슬로우패스로 이사(다음 질문 생성에 미사용 확인)
- guard 위치: v1은 스트리밍 앞(+~0.5s, 유도신문은 스트리밍 후 무를 수 없음)

## 6. 구조 개편 · DB

```
api/interview/   state.py graph.py nodes/(listen strategize generate guard speak reflect farewell)
                 tools/(brief playbook ledger pace)
api/briefing/    업로드→청크→임베딩 인덱싱 파이프라인 (단순)
api/services/embeddings.py
```

수정: `routers/public.py`(turn → Command(resume) + SSE), `llm_client.py`에 `chat(tools=)`·`embed()`
**추가**(기존 메서드 불변 — Qwen3 튜닝 보존), requirements에 langgraph 2종(+ langgraph-checkpoint-postgres),
main.py `_GUARDED` 확장.

| DB | 용도 |
|---|---|
| `briefing_chunks` | 브리핑 팩 (pgvector + 출처 메타) |
| 체크포인트 테이블 | PostgresSaver.setup() — 같은 Cloud SQL |
| `CREATE EXTENSION vector` | Postgres 15 지원. 임베딩 차원 MRL 1024 제안 |

~~`turn_embeddings`~~ — recall 컷으로 불필요.

## 7. 지키는 불변식

- **PII는 그래프 진입 전, HTTP 핸들러에서 마스킹.** `Command(resume=원문)`은 체크포인트에 박제된다.
- **interrupt 재개 시 노드는 처음부터 재실행**(규약) — interrupt 앞 로직 멱등. 저장은 speak에서 완료 후 잠듦.
- 가드레일 문안·정규식·재귀 금지 그대로. 12턴 하드 가드 = 결정론 엣지.
- "숫자는 DB가 센다" — 대시보드 집계는 SQL. turns/sessions 테이블 유지.
- NPU 순수성 — LLM·임베딩·(리랭커) 전부 Furiosa.
- `(전사, ok)` 계약·speech 계층 불변.

## 8. 리스크

| 리스크 | 대응 |
|---|---|
| **Qwen3 자율 tool choice 미검증** (최대) | 0단계 30분 실측이 게이트. 폴백: 도구 선택만 구조화 출력 강제 |
| 브리핑 검색 리랭커 API 형태 미확인 | v1은 임베딩 top-k만, 확인 후 추가 |
| 체크포인트 쓰기 지연 | durability 조정 + 1단계 실측 |

(✂️ 웹 검색 API 의존·자동 수집물 품질 리스크는 브리핑 라이트로 소멸)

## 9. 마이그레이션

| 단계 | 내용 | 검증 |
|---|---|---|
| 0 | llm_client.chat/embed · pgvector · **tool choice 실측** | 실험 통과가 게이트 |
| 1 | 그래프 골격: interrupt 루프 + 노드 5개 (필수①②) | 기존 pytest + 지연 실측 |
| 2 | 상태 이동 + 커버리지 원장 (필수③) | stats로 probe율 비교 |
| 3 | 행동 7종 확장 (challenge·revisit·clarify·redirect) | 대화 품질 수동 평가 |
| 4 | 슬로우패스 + SSE 스트리밍 | 턴 지연 재실측 |
| 5 | 브리핑 라이트(RAG) + 도구 4종 — 독립, 병행 가능 | brief 품질 평가 |

구엔진(`moderator.py`)은 플래그로 병행하다 제거.

## 10. LangGraph 기능 사용 체크 (9/10)

interrupt/Command · Checkpointer · State/Reducer · 조건 엣지 · tool-loop · Send · 스트리밍 ·
서브그래프 · 타임트래블 → **9개 실사용**.
Store(세션 간 장기기억) 1개만 의식적으로 제외 — 12질문 규모엔 과함. 나중에 언제든 추가 가능.
검수 기준: "장식으로 쓰는 기능이 하나도 없다."

## 11. 미결정 (팀 논의)

- [ ] guard 위치: 스트리밍 앞/뒤 (제안: 앞)
- [ ] 임베딩 차원 (제안: 1024 MRL)
- [ ] listen+strategize 통합 1콜 vs 분리 2콜 (제안: 통합 시작)
- [ ] 브리핑 업로드 UI 위치 (제안: guide-panel 옆 탭)
- [ ] LangSmith 트레이싱 도입 여부 (도입 시 hide_inputs 필수 — PII)
