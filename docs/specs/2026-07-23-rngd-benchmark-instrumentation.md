# RNGD 벤치마크 계측 스펙 (코딩 에이전트용)

> 출처: 사용자 제공(2026-07-23). mindlens 성능·벤치마크 워크스트림의 정본 계측 스펙.
> UI(대시보드)는 §7 출력물을 소비만 한다. 이 문서는 **측정 하네스**(부하 재생기·데이터 수집·지표 산출)의 스펙이며 UI 구현과 별개 워크스트림이다.

| 항목 | 내용 |
|---|---|
| 목적 | AI 중재 인터뷰 플랫폼의 추론 워크로드를 RNGD / GPU 대조군에서 측정 |
| 산출물 | 지표 3종 + 손익분기 세션 수 1개 |
| 대상 SDK | Furiosa SDK 2026.3.0 (furiosa-llm, furiosa-smi, furiosa-metrics-exporter) |
| 비목표 | tok/s, tok/s/W, TDP 비교, 랙 단위 시뮬레이션, TCO 곡선 — **구현하지 말 것** |

---

## 0. 한 줄 요약

> 이 벤치마크는 "누가 토큰을 빨리 뽑나"가 아니라 **"저부하·긴 컨텍스트·짧은 출력 구간에서 월 몇 세션부터 유리해지는가"**를 구한다.

---

## 1. 지표 정의

### M1. 카드당 SLA 충족 동시 세션 수

```
M1 = max{ C : turn_e2e_p95(C) <= 2000ms }
```

- `C` = 동시 진행 세션 수 (카드 1장 기준)
- `turn_e2e` = 참가자 답변 수신 시각 → 모더레이터 발화 **마지막 토큰** 시각 (ms)
- 탐색: 이분 탐색. 하한 1, 상한은 첫 위반 지점의 2배. 해상도 ±4 세션
- 각 `C`마다 워밍업 3분 제외 후 10분 측정
- **함께 기록**: `ttft_p95` (타이핑 인디케이터 체감 지표라 별도 보고), `turn_e2e_p50`

> **주의**: `C`는 "생성 중인 요청 수"가 아니라 "세션 슬롯 수"다. 참가자 사고 시간 때문에 실제 동시 생성은 훨씬 적다. 이 차이가 이 벤치마크의 핵심이므로 절대 혼동하지 말 것.

### M2. 세션당 Wh (벽면, idle 포함)

```
E_total   = ∫ P_wall(t) dt           over 24h window   [Wh]
Wh_session = E_total / completed_sessions

# 분해 (보고 필수)
E_idle    = P_idle_measured * 24h * N_cards
E_active  = E_total - E_idle
```

- `P_wall` = PDU 실측 (W). 카드 센서(`furiosa_npu_hw_power`)는 **보조 기록만**, 보고는 벽면 기준
- `P_idle_measured` = 부하 0, 서버 프로세스 기동 상태에서 10분 측정 평균
- 24h 윈도우는 실시간 대기 없이 **가속 리플레이 금지** — 유휴 시간이 지표의 본질이므로 실시간으로 돌릴 것. 단축이 불가피하면 최소 6h 후 선형 외삽하고 그 사실을 결과에 명시

### M3. 버킷 분류 Cohen's κ

```
κ_rngd  = cohen_kappa(gold_labels, rngd_predictions)
κ_gpu   = cohen_kappa(gold_labels, gpu_predictions)
Δκ      = κ_rngd - κ_gpu
```

- 골드셋 500건 (PRD 8.3 기준, 인간 코더 이중 라벨링)
- 동일 입력·동일 프롬프트·동일 샘플링 파라미터(`temperature=0`)로 양쪽 실행
- **기각 조건**: `κ_rngd < 0.75` 또는 `Δκ < -0.05` → M1, M2 결과 무효 처리하고 중단

---

## 2. 헤드라인: 손익분기 세션 수

```python
# 월 세션 수 S에 대한 총비용
N_cards = ceil(peak_concurrent_sessions / M1)

def cost_rngd(S):
    fixed = N_cards * (card_amort_monthly
                       + P_idle * HOURS_PER_MONTH * PRICE_KWH / 1000)
    var   = S * Wh_active_per_session * PRICE_KWH / 1000
    return fixed + var

def cost_baseline(S):
    # 모드 A: 클라우드 API   -> S * price_per_session
    # 모드 B: GPU 온프렘     -> cost_rngd와 동일 구조, GPU 파라미터
    ...

S_breakeven = solve(cost_rngd(S) == cost_baseline(S))
```

상수는 전부 설정 파일로 분리 (`HOURS_PER_MONTH=730`, `PRICE_KWH`, `card_amort_monthly`, `peak_concurrent_sessions`).

**출력 형태**: `S*` 단일 값 + 민감도 표 (전기요금 ±30%, 감가상각 기간 3/5년)

---

## 3. 부하 재생기 요구사항

### 세션 구조 (부록 A 기준)

```
세션 시작
  → 인사/동의
  → Q1..Q7 (Q5는 척도형)
      각 질문마다 프로빙 0~3회 (max_probes는 질문별 상이)
  → 클로징
세션 종료
  → 버킷 분류 (세션 전체 답변)
  → 세션 요약
```

- 모더레이터 발화 턴 수: 세션당 18~25
- 출력 길이: 턴당 60~100 토큰

### 컨텍스트 구성 — **캐시 히트를 좌우하므로 순서 고정 필수**

```
[고정 프리픽스 — 캐시 대상]
  1. 시스템 프롬프트 (바이트 단위 고정)
  2. 모더레이터 페르소나
  3. 인터뷰 가이드 JSON
  4. 동결된 지식 팩
[가변 — 캐시 미스 구간]
  5. 누적 트랜스크립트
  6. 참가자 ID / 타임스탬프 등 세션 고유값
```

> **구현 규칙**: 세션마다 달라지는 값은 반드시 5번 이후에 배치한다. Furiosa-LLM의 prefix caching은 토큰 단위 정확 일치라 구두점·공백 하나만 달라져도 프리픽스 전체가 미스 처리된다. 프롬프트 템플릿은 문자열 포매팅이 아니라 **사전 렌더링된 상수**로 관리할 것.

### 도착·지연 분포

| 파라미터 | 분포 | 비고 |
|---|---|---|
| 세션 도착 | 포아송 | λ는 목표 동시 세션 수에서 역산 |
| 참가자 사고+타이핑 지연 | 로그노멀 (median 25s) | 10~12분 / 20턴에서 역산 |
| 답변 길이 | 실제 트랜스크립트 코퍼스에서 샘플링 | 합성 금지 |

### 코퍼스 고정 (필수)

부록 A 가이드 + 실제 테스트 인터뷰 트랜스크립트를 **한 번 생성해 파일로 동결**하고, 하드웨어를 바꿔가며 동일 코퍼스를 리플레이한다. 매 실행마다 새로 생성하면 하드웨어 차이인지 입력 차이인지 구분 불가.

---

## 4. 데이터 수집

| 소스 | 수집 항목 | 주기 |
|---|---|---|
| PDU (SNMP/HTTP) | 벽면 전력 W | 1s |
| `furiosa-metrics-exporter` → Prometheus | `furiosa_npu_hw_power{label="rms"}`, `furiosa_npu_core_utilization`, `furiosa_npu_core_frequency`, `furiosa_npu_throttling_events_count` | 1s (`--interval 1`) |
| furiosa-llm `/metrics` | running/waiting requests, KV cache usage | 1s |
| furiosa-llm 서버 로그 | prefix cache hit ratio | 파싱 |
| 부하 재생기 | 턴 단위 타임스탬프 | 이벤트 |

**시각 동기**: 모든 소스에 NTP 동기 필수. 전력 시계열과 턴 이벤트를 조인해야 하므로 오차 100ms 이내.

### 턴 레코드 스키마

```json
{
  "run_id": "str",
  "session_id": "str",
  "turn_idx": "int",
  "role": "moderator_utterance | probe_judge | bucket_classify | summary",
  "t_request": "iso8601",
  "t_first_token": "iso8601",
  "t_last_token": "iso8601",
  "prompt_tokens": "int",
  "cached_prefix_tokens": "int",
  "output_tokens": "int",
  "ttft_ms": "float",
  "e2e_ms": "float"
}
```

### 실행 메타데이터 (재현성 — 결과와 함께 반드시 저장)

```json
{
  "hardware": "rngd | gpu_baseline",
  "n_cards": "int",
  "sdk_version": "str",
  "firmware_version": "str",
  "driver_version": "str",
  "model_id": "str",
  "quantization": "FP8 | INT8 | BF16 | ...",
  "governor": "Performance | PowerSave",
  "prefix_caching": "on | off",
  "tensor_parallel_size": "int",
  "corpus_hash": "sha256",
  "prompt_template_hash": "sha256"
}
```

---

## 5. 실험 매트릭스

| 축 | 수준 |
|---|---|
| 하드웨어 | RNGD / GPU 대조군 |
| governor | Performance / PowerSave |
| prefix caching | on / off (`--no-enable-prefix-caching`) |
| 동시 세션 | 이분 탐색 (M1 산출용) |
| 역할 | 모더레이터 발화 / 프로빙 판정 / 버킷 분류 |

**축소 지침**: 전조합을 돌리지 말 것. M1은 `governor=Performance, cache=on`에서만 구하고, governor·cache 축은 **고정 부하(M1의 70%)에서 전력 비교용으로만** 사용한다.

### 모델 배치 (SDK 검증 등급 기준)

| 역할 | 1순위 | 비고 |
|---|---|---|
| 모더레이터 발화 (한국어) | `furiosa-ai/EXAONE-4.0-32B-FP8` | Performance ✅ |
| 프로빙 판정 / 버킷 분류 | `furiosa-ai/Llama-3.1-8B-Instruct` | Performance ✅ |
| 대안 (버킷 분류) | `furiosa-ai/Qwen3-8B-FP8` | Performance 🟡 — 결과에 등급 명시 |

가이드 생성·종합 요약은 측정 대상에서 **제외** (저빈도, 이관 대상 아님).

---

## 6. 측정 프로토콜

1. 워밍업 3분 → 폐기
2. 본 측정 10분 × 3회 반복
3. 보고: 중앙값 + p95 + 표준편차
4. `furiosa_npu_throttling_events_count`가 증가한 구간이 있으면 해당 회차 무효 처리 후 재측정
5. idle 베이스라인은 매 실행 전후로 각각 측정 (드리프트 확인)

---

## 7. 출력물

### 결과 표 (1장)

| 구성 | M1 (세션/카드) | 500세션 필요 카드 | M2 (Wh/세션) | idle 비중 | κ | Δκ |
|---|---|---|---|---|---|---|
| GPU 대조군 | | | | | | |
| RNGD, Perf, cache on | | | | | | |
| RNGD, PowerSave, cache on | | | | | | |
| RNGD, Perf, cache off | | | | | | |

### 차트 (2장)

1. **손익분기 곡선** — x축 월 세션 수, y축 월 총비용. 두 곡선의 교차점에 `S*` 라벨
2. **24h 전력 시계열** — 상단 벽면 W, 하단 동시 세션 수. idle 바닥선 표시

### 부록 (자동 생성)

실행 메타데이터 전량 + 캐시 히트율 + 측정 회차별 원자료 경로

---

## 8. 구현 시 하지 말 것

- 카드 센서 전력만으로 M2 계산 (CPU·NIC·팬 누락 → 실측 전기료와 불일치)
- 24h 윈도우를 가속 리플레이 (유휴 시간이 지표의 본질)
- 매 실행마다 코퍼스 재생성
- 프롬프트를 런타임 문자열 포매팅으로 조립 (캐시 파괴)
- κ 미달 상태에서 M1·M2 보고
- 확인 안 된 값을 추정치로 채워 넣기 — 미측정 항목은 `null`로 남기고 사유 기록
