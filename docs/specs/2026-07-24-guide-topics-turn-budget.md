# 스펙 A — 가이드 주제화 + 턴 예산

- 날짜: 2026-07-24
- 상태: 승인됨 (브레인스토밍 완료, 구현 계획 대기)
- 후속: 스펙 B `2026-07-24-results-insight-report.md` — **이 스펙이 먼저 들어가야 한다**

## 1. 문제

가이드가 **질문 평면 리스트**다. 의뢰자가 질문 문장을 하나씩 적고, 진행자는 그걸 순회한다.
조사를 설계할 때 사람이 실제로 생각하는 단위는 질문이 아니라 **주제**인데 화면이 그걸
표현하지 못한다. 턴 예산도 주제와 무관한 고정 상수(`MAX_ASKED = 12`)라 가이드가 크든
작든 12턴에서 잘린다.

## 2. 결정

### 2.1 가이드는 주제 > 질문 2단이다

```
InterviewGuide
├─ goal, vocabulary, version
└─ topics: [GuideTopic]              ← 신규
   ├─ id, title, goal, order
   └─ questions: [GuideQuestion]     ← 기존 모델 그대로
      └─ id, text, goal, order, response_buckets, stimulus
```

**버킷은 질문마다 붙는다** (주제가 아니라). 지금 코드북·프로빙 목표가 질문 단위로 동작하고
(`api/interview/nodes/reflect.py:99`), 분류 결과는 `turns.bucket_id` 에 질문 기준으로 쌓인다.
주제로 올리면 그 계약이 통째로 바뀌므로 올리지 않는다.

> **알고 받아들인 비용:** 질문마다 버킷이면 분포의 N 이 질문 수만큼 쪼개진다. 응답 4건짜리
> 라이브 프로젝트에서 이미 한 문항의 버킷 7개 중 6개가 `0 · 0%` 로 비어 있다. 이 빈 칸을
> 화면에서 어떻게 다룰지는 **스펙 B §4** 가 맡는다 — 데이터 구조로 풀지 않는다.

### 2.2 기존 가이드는 운영 DB 를 건드리지 않는다

가이드는 `guides.questions` (JSONB) 에 평면으로 저장돼 있고, 라이브 프로젝트들은 이미
질문 7개 · 버킷 37~47개를 갖고 있다.

**호환 읽기로 처리한다.** `store.load_guide` 가 `topics` 없는 레코드를 읽으면 기존
`questions` 를 **주제 1개(`title="전체"`)** 로 감싸서 돌려준다. 마이그레이션 스크립트도,
운영 DB 쓰기도 없다(운영 DB 쓰기는 AGENTS.md §1 하드게이트).

저장은 항상 새 형식(`topics`)으로 한다 — 기존 프로젝트도 의뢰자가 가이드를 한 번 저장하면
그때 자연스럽게 승격된다. 롤백이 필요하면 읽기 호환이 양방향이어야 하므로, **`topics` 를
저장할 때 `questions` 평면 배열도 함께 기록한다**(파생 필드, 읽기 우선순위는 `topics`).

### 2.3 턴 예산 = 주제당 질문수 + 1. 전체 상한은 없다

| 지금 | 바뀜 |
|---|---|
| `MAX_ASKED = 12` (전체 상한) | **제거** — 총 턴은 주제별 예산의 합으로 자연 결정 |
| `Q_STREAK_CAP = 4` (문항당) | **주제당 = 그 주제의 질문수 + 1** 로 대체 |
| `PROBE_STREAK_CAP = 3` | 유지 (보조 가드) |

`+1` 은 꼬리질문 몫이다. 질문마다 최소 1턴을 써야 그 질문의 버킷이 채워지므로, 질문 수만큼은
반드시 확보하고 남는 1턴을 진행자가 주제 안 어디에든 쓴다.

**강제 advance 규칙 (신규):** 주제 안에서 `남은 질문 수 >= 남은 턴 수` 면 probe/clarify/
challenge/redirect 를 막고 다음 질문으로 넘긴다. 없으면 진행자가 앞 질문에서 꼬리질문을 다
써버려 **뒤 질문의 버킷이 영영 빈 채로 남는다.**

> **알고 받아들인 위험:** 전체 상한을 없애면 폭주 안전망이 사라진다. 주제 10개 × 질문 5개
> 가이드는 60턴 인터뷰가 되고 응답자는 중간에 이탈한다. 지금 규모(주제 1~3개)에서는 문제가
> 아니지만 **실응답자를 받기 전에 다시 봐야 한다.** 대신 완화책으로 가이드 화면에 예상 턴수를
> 실시간 노출한다(§3).
>
> 부수효과: 호환 처리된 기존 가이드(주제 1 · 질문 7)는 **8턴**이 된다. 지금 12턴보다 짧다.

## 3. 가이드 화면 (의뢰자)

- 주제 카드 안에 질문 카드가 들어가는 2단. 주제 추가 / 주제 안 질문 추가.
- 질문 편집 요소(텍스트·알아낼 것·버킷·자극물)는 지금 것을 그대로 옮긴다.
- **헤더에 `최대 N턴` 을 실시간 표시**한다 (`N = 총질문수 + 주제수`). 질문을 늘리면 인터뷰가
  길어지는 것을 의뢰자가 즉시 본다 — §2.3 에서 없앤 안전망을 사람이 보는 자리로 옮긴 것.
- 순서 변경은 기존 위/아래 버튼 방식 유지 (드래그 도입 안 함 — YAGNI).
- 아이콘은 `lucide-react`, 이모지 금지 (design.md §4).

## 4. 횡단 전수조사 — 실제 grep 결과

AGENTS.md §2 가 요구하는 소비처 전수조사. **아래 전부가 이 변경의 대상이다.**

**API**
| 파일 | 지점 |
|---|---|
| `api/schemas/models.py` | `InterviewGuide.questions` → `topics`, `GuideTopic` 신규 |
| `api/services/store.py:283-300` | 직렬화/역직렬화 — **호환 읽기가 여기 산다** |
| `api/routers/projects.py:341,346,352,365,512,709` | 가이드 생성 스트림·품질 로그·저장·통계 |
| `api/routers/public.py:64` | `qid` 로 질문 찾기 (2단 순회로) |
| `api/interview/nodes/strategize.py:9-11,16,34,45,47` | 상수 3개 + 강제 advance |
| `api/interview/nodes/listen.py:18,38` | `pace(asked, MAX_ASKED, ...)` — 인자 재정의 |
| `api/services/moderator.py:30,114,260` | 구엔진 `_MAX_ASKED = 12` (라이브는 graph 엔진이지만 폴백 경로) |
| `api/services/notify.py:83` | `total = len(guide.questions)` |
| `api/interview/prompts.py` | pending 블록·opening 을 주제 단위로 |
| `api/prompts/guide.py` | 가이드 생성 LLM 이 주제 구조를 내도록 |
| `api/interview/tools/pace.py`, `ledger.py` | 커버리지·페이스 산출 단위 |

**⚠️ 테스트 하네스 — 16개 파일이 `questions` 를 직접 만든다.** 여기를 빼먹으면 로컬 green ·
CI red 가 된다(AGENTS.md §2 의 명시적 경고).

```
test_bucket_classify · test_evals · test_guide_audience · test_guide_evidence
test_guide_material_injection · test_interview_graph · test_interview_ledger
test_interview_moderator · test_interview_prompts · test_interview_tools
test_knowledge_pack · test_llm_timeout · test_notify · test_pipeline_streams
test_probing · test_probing_advance
```

`test_probing_advance.py:5,13,23` 은 `Q_STREAK_CAP` 을 직접 import 한다 — 상수를 없애면
바로 깨진다.

**WEB**
| 파일 | 지점 |
|---|---|
| `web/lib/api.ts:69` | `Guide.questions` 타입 |
| `web/app/projects/[id]/guide-panel.tsx` | 15군데 (162~248, 436~564) |
| `web/app/projects/[id]/results-panel.tsx:149,191` | 스펙 B 에서 다시 손대지만 타입은 여기서 깨진다 |

## 5. 완료 기준 (DoD)

1. 새 가이드를 만들면 주제 구조로 저장되고, 기존 라이브 가이드(평면)도 **주제 1개로 정상 표시**된다.
2. 주제 2개 · 질문 각 2개 가이드로 인터뷰하면 **최대 6턴**에서 끝난다.
3. 한 주제 안에서 질문이 2개 남았는데 턴이 2턴 남으면 **꼬리질문이 나오지 않는다**(강제 advance).
4. 모든 질문의 버킷이 채워진다 — 어떤 질문도 턴 배분 때문에 미수집으로 남지 않는다.
5. `MAX_ASKED` 상수가 코드에서 사라진다(구엔진 `_MAX_ASKED` 포함).
6. CI 4종 통과 — pytest · import · `tsc --noEmit` · `next build`.

## 6. 가이드 생성 기본값

현재 프롬프트는 질문 7개를 평면으로 낸다. 새 기본값은 **주제 3개 · 주제당 질문 2~3개**
(총 6~9 질문)로 잡는다 → 인터뷰 9~12턴. 지금 12턴과 비슷한 길이라 응답자 경험이 급변하지
않으면서 주제 구조의 이점을 얻는다. 실측 후 조정한다.

## 7. 남은 위험 (구현 전 사람 확인)

- **전체 상한 부재의 안전망을 언제 다시 넣을지.** 실응답자를 받기 전에 반드시 다시 본다
  (§2.3 참고). 지금은 가이드 화면의 `최대 N턴` 표시가 유일한 방어선이다.
