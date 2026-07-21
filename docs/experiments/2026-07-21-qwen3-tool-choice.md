# Qwen3 자율 tool choice 실측 (TICKET-0 게이트)

- 모델: furiosa-ai/Qwen3-32B-FP8 · thinking=off(프로덕션 설정) · 시나리오 10종 × 3회
- **게이트 판정: ❌ 미달 — 폴백(도구 선택 구조화 출력 강제) 채택**

| 지표 | 결과 | 기준 |
|---|---|---|
| 도구 시나리오 정확도 | 71% | ≥ 80% |
| 무도구 오발동률 | 0% | ≤ 20% |
| 인자 JSON 유효율 | 100% | = 100% |
| 지연 mean / p95 | 1.16s / 1.48s | (참고) |

## 시행 상세

| 시나리오 | 회 | 호출 | 기대 | 판정 | 지연 | 응답 앞부분 |
|---|---|---|---|---|---|---|
| brand-unknown | 1 | brief | brief | PASS | 8.12s | "배민클럽"이라는 용어가 의뢰자 도메인 내에서 어떤 의미를 가지는지 파악 |
| brand-unknown | 2 | - | brief | FAIL | 0.79s | "배민클럽"이라는 용어의 의미와 배달앱 전환과의 연관성을 더 자세히 설명 |
| brand-unknown | 3 | - | brief | FAIL | 2.33s | "배민클럽"이라는 기능이나 제도가 다른 배달앱으로 전환하는 데 영향을 주 |
| client-jargon | 1 | brief | brief | PASS | 0.72s |  |
| client-jargon | 2 | - | brief | FAIL | 0.76s | "멤버스딜"이란 것이 무엇인지 간략히 설명해 주시겠어요? |
| client-jargon | 3 | brief | brief | PASS | 0.69s |  |
| shallow-answer | 1 | playbook | playbook | PASS | 1.37s |  |
| shallow-answer | 2 | playbook | playbook | PASS | 1.04s |  |
| shallow-answer | 3 | playbook | playbook | PASS | 0.92s |  |
| contradiction | 1 | playbook | playbook 또는 - | PASS | 1.2s |  |
| contradiction | 2 | playbook | playbook 또는 - | PASS | 1.18s |  |
| contradiction | 3 | playbook | playbook 또는 - | PASS | 1.05s |  |
| coverage-check | 1 | ledger_report | ledger_report | PASS | 0.39s |  |
| coverage-check | 2 | ledger_report | ledger_report | PASS | 0.39s |  |
| coverage-check | 3 | ledger_report | ledger_report | PASS | 0.41s |  |
| pace-check | 1 | pace | pace | PASS | 0.38s |  |
| pace-check | 2 | pace | pace | PASS | 0.37s |  |
| pace-check | 3 | pace | pace | PASS | 0.36s |  |
| smalltalk | 1 | - | - | PASS | 1.01s | 좋습니다, 오늘은 카페 이용에 대한 이야기를 나눠볼게요. 평소에 카페를  |
| smalltalk | 2 | - | - | PASS | 0.97s | 좋은 아침이세요! 오늘은 카페 이용에 대한 경험과 생각을 나누는 시간을  |
| smalltalk | 3 | - | - | PASS | 0.86s | 좋은 아침입니다! 카페를 이용하시는 빈도에 대해 간단히 소개해 주실 수  |
| clear-story | 1 | - | - | PASS | 1.12s | 그렇군요, 반품 절차가 편리해서 만족하셨다니 다행입니다. 혹시 반품 과정 |
| clear-story | 2 | - | - | PASS | 1.24s | 그렇군요, 반품 절차가 편리하게 느껴지셨다니 다행입니다. 혹시 반품 과정 |
| clear-story | 3 | - | - | PASS | 0.82s | 좋은 경험을 해주셨다니 다행이네요. 앱을 통한 반품 절차는 전체적으로 얼 |
| multi-brief-pace | 1 | playbook | brief,pace 또는 brief | FAIL | 1.18s |  |
| multi-brief-pace | 2 | playbook | brief,pace 또는 brief | FAIL | 1.39s |  |
| multi-brief-pace | 3 | playbook | brief,pace 또는 brief | FAIL | 1.07s |  |
| common-term-trap | 1 | - | - | PASS | 0.64s | 다음날 새벽까지 배송이 도착한 경험은 어떤 점에서 만족스러우셨나요? |
| common-term-trap | 2 | - | - | PASS | 1.48s | 그렇군요, 로켓배송 서비스를 이용하셨는데 다음날 새벽에 배송이 도착하셨다 |
| common-term-trap | 3 | - | - | PASS | 0.64s | 다음날 새벽에 배송이 도착한 경험에 대해, 어떤 점이 특히 만족스러웠나요 |

## 임베딩 실측 (Task 2 Step 5)

- 기본 차원: **4096** (furiosa-ai/Qwen3-Embedding-8B)
- dimensions=1024: **서버 네이티브 지원** (1024차원 반환) → §11 결정: 1024 MRL 채택 가능, 클라이언트 절단 불필요

## 판정 및 후속 방향

- **게이트 미달 — 폴백 확정.** 도구 선택은 자율(tool_choice="auto")이 아니라 **구조화 출력으로 강제**한다 (계획 §8 폴백).
- 실패 패턴: brief 계열 집중 — 모르는 용어(배민클럽·프로여관러)를 아는 척 넘어가거나(무호출), 상황을 playbook 으로 오분류(multi-brief-pace 0/3). 나머지 도구(playbook·ledger_report·pace) 12/12, 무도구 판단 9/9(오발동 0%)는 완벽.
- thinking=on 비교([별도 문서](./2026-07-21-qwen3-tool-choice-thinking.md)): 정확도 57% · 오발동 11% · 지연 4.4s — 전 지표 악화. 프로덕션 설정(off) 유지.
- TICKET-5 반영: generate 의 tool-loop 는 "쓸 도구를 상위 노드의 구조화 출력이 지정 → 결정론 실행" 형태로 설계. 인자 JSON 유효율 100%는 긍정 신호 — 도구 **실행**은 신뢰 가능, 도구 **선택**만 강제하면 된다.
