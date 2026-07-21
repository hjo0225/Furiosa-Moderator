# Qwen3 자율 tool choice 실측 (TICKET-0 게이트)

- 모델: furiosa-ai/Qwen3-32B-FP8 · thinking=on · 시나리오 10종 × 3회
- **게이트 판정: ❌ 미달 — 폴백(도구 선택 구조화 출력 강제) 채택**

| 지표 | 결과 | 기준 |
|---|---|---|
| 도구 시나리오 정확도 | 57% | ≥ 80% |
| 무도구 오발동률 | 11% | ≤ 20% |
| 인자 JSON 유효율 | 100% | = 100% |
| 지연 mean / p95 | 4.41s / 4.72s | (참고) |

## 시행 상세

| 시나리오 | 회 | 호출 | 기대 | 판정 | 지연 | 응답 앞부분 |
|---|---|---|---|---|---|---|
| brand-unknown | 1 | brief | brief | PASS | 5.26s |  |
| brand-unknown | 2 | brief | brief | PASS | 4.02s |  |
| brand-unknown | 3 | brief | brief | PASS | 3.67s |  |
| client-jargon | 1 | brief | brief | PASS | 4.08s |  |
| client-jargon | 2 | brief | brief | PASS | 3.98s |  |
| client-jargon | 3 | brief | brief | PASS | 3.79s |  |
| shallow-answer | 1 | - | playbook | FAIL | 4.54s |  |
| shallow-answer | 2 | - | playbook | FAIL | 4.51s |  |
| shallow-answer | 3 | - | playbook | FAIL | 4.66s |  |
| contradiction | 1 | - | playbook 또는 - | PASS | 4.62s |  |
| contradiction | 2 | - | playbook 또는 - | PASS | 4.67s | <tool_call> {"name": "playbook", "argume |
| contradiction | 3 | - | playbook 또는 - | PASS | 4.59s | <tool_call> {"name": "playbook", "argume |
| coverage-check | 1 | ledger_report | ledger_report | PASS | 3.65s |  |
| coverage-check | 2 | - | ledger_report | FAIL | 4.53s |  |
| coverage-check | 3 | ledger_report | ledger_report | PASS | 3.99s |  |
| pace-check | 1 | - | pace | FAIL | 4.57s | <tool_call> {" |
| pace-check | 2 | - | pace | FAIL | 4.71s |  |
| pace-check | 3 | pace | pace | PASS | 4.55s |  |
| smalltalk | 1 | - | - | PASS | 4.71s |  |
| smalltalk | 2 | playbook | - | FAIL | 3.39s |  |
| smalltalk | 3 | - | - | PASS | 4.51s | 안녕하세요, 반갑습니다! 카페를 이용하시는 데 있어 평소 어떤 요소를 가 |
| clear-story | 1 | - | - | PASS | 4.72s |  |
| clear-story | 2 | - | - | PASS | 4.55s |  |
| clear-story | 3 | - | - | PASS | 4.59s |  |
| multi-brief-pace | 1 | - | brief,pace 또는 brief | FAIL | 4.83s |  |
| multi-brief-pace | 2 | - | brief,pace 또는 brief | FAIL | 4.37s |  |
| multi-brief-pace | 3 | - | brief,pace 또는 brief | FAIL | 4.58s |  |
| common-term-trap | 1 | - | - | PASS | 4.49s | "로켓배송 서비스를 통해 다음날 새벽에 물건을 받으셨는데, 배송 과정에서 |
| common-term-trap | 2 | - | - | PASS | 4.55s |  |
| common-term-trap | 3 | - | - | PASS | 4.56s |  |

## 임베딩 (Task 2 Step 5 결과 — 수동 기입)

- 기본 차원: (기입)
- dimensions=1024 지원 여부: (기입) → §11 결정 재료
