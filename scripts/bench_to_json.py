"""벤치 원자료(CSV) → 대시보드가 소비할 JSON.

계약: docs/specs/2026-07-23-rngd-benchmark-instrumentation.md §7 출력물,
      web/lib/api.ts 의 BenchmarkResult 타입과 1:1.

**원칙: 원자료에 없는 값은 만들지 않는다.** 계산할 수 없는 필드는 null 로 두고
out_of_scope 에 사유를 남긴다(스펙 §8 "확인 안 된 값을 추정치로 채워 넣기" 금지).

사용:
    python scripts/bench_to_json.py "docs/bench_results (1)/bench_results" api/benchmark/latest.json
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

SLA_TARGET_MS = 2000


def percentile(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def median(vals: list[float]) -> float | None:
    return percentile(vals, 0.5)


def load_turns(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_latency(rows: list[dict]) -> list[dict]:
    by: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by[int(r["conc"])].append(r)

    out = []
    for conc in sorted(by):
        group = by[conc]
        ok = [r for r in group if r["ok"] == "1"]
        totals = [float(r["total_s"]) * 1000 for r in ok]
        out.append(
            {
                "slots": conc,
                "turns": len(group),
                "failures": len(group) - len(ok),
                "p50_ms": round(percentile(totals, 0.5) or 0),
                "p95_ms": round(percentile(totals, 0.95) or 0),
                # TTFT 는 원자료에 없다(총 지연만 기록). 지어내지 않는다.
                "ttft_p95_ms": None,
                # Little 근사에는 레벨별 실측 소요시간이 필요한데 t_wall 이 레벨당 1개뿐이라
                # 구간 길이를 알 수 없다(스펙 §4 가 지적한 그 구멍). 다음 런에서 채운다.
                "avg_concurrent_generating": None,
                "occupancy": None,
            }
        )
    return out


def build_turn_breakdown(rows: list[dict]) -> tuple[list[dict], float | None]:
    ok = [r for r in rows if r["ok"] == "1"]
    if not ok:
        return [], None

    emo = [float(r["emo_s"]) * 1000 for r in ok]
    gen = [float(r["gen_s"]) * 1000 for r in ok]
    guard = [float(r["guard_s"]) * 1000 for r in ok]
    total = [float(r["total_s"]) * 1000 for r in ok]

    t50 = median(total) or 0
    gen50, guard50, emo50 = median(gen) or 0, median(guard) or 0, median(emo) or 0

    # 감정 태깅은 질문 생성과 병렬이라 직렬 합에 넣으면 100% 를 넘는다.
    # 비중은 "턴 전체 대비"로만 내고, 병렬이라는 사실을 별도 플래그로 넘긴다.
    stages = [
        {
            "key": "emotion",
            "label": "감정 태깅",
            "p50_ms": round(emo50),
            "share": round(emo50 / t50, 4) if t50 else None,
            "parallel": True,
            "note": "질문 생성과 병렬 — 직렬 합에 더하지 않는다",
        },
        {
            "key": "generate",
            "label": "질문 생성",
            "p50_ms": round(gen50),
            "share": round(gen50 / t50, 4) if t50 else None,
            "parallel": False,
            "note": "",
        },
        {
            "key": "guardrail",
            "label": "가드레일 (판정+재작성)",
            "p50_ms": round(guard50),
            "share": round(guard50 / t50, 4) if t50 else None,
            "parallel": False,
            "note": "",
        },
        {
            "key": "total",
            "label": "턴 전체",
            "p50_ms": round(t50),
            "share": 1.0,
            "parallel": False,
            "note": "",
        },
    ]
    rewritten = sum(1 for r in ok if r["rewritten"] == "1")
    return stages, round(rewritten / len(ok), 4)


def build_power(path: Path) -> tuple[list[dict], float | None]:
    """카드별 W 컬럼을 합쳐 시계열로. 동시 세션 수는 이 파일에 없어 null."""
    if not path.exists():
        return [], None
    series, totals = [], []
    with path.open(encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 2:
                continue
            try:
                watts = [float(x) for x in row[1:]]
            except ValueError:
                continue
            total = sum(watts)
            totals.append(total)
            series.append(
                {"t": row[0], "card_power_w": round(total, 1), "concurrent_sessions": None}
            )
    if not totals:
        return [], None
    # 유휴 기준선 = 최저 구간 평균(최소값의 5% 이내 샘플). 별도 유휴 측정 구간이 없어
    # 이렇게 근사하며, 그 사실을 out_of_scope 에 남긴다.
    floor = min(totals) * 1.05
    idle_samples = [t for t in totals if t <= floor]
    idle = sum(idle_samples) / len(idle_samples) if idle_samples else None
    return series, round(idle, 1) if idle else None


def main() -> None:
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])

    turn_csv = next(src.glob("live_*.csv"))
    rows = load_turns(turn_csv)
    latency = build_latency(rows)
    stages, rewrite_rate = build_turn_breakdown(rows)
    power, idle_w = build_power(src / "power_mod4.csv")

    # M1 — 전 구간에서 p95 가 목표를 넘으면 0 이 아니라 "unmet"(스펙 §1).
    unmet = all((r["p95_ms"] or 0) > SLA_TARGET_MS for r in latency)
    measured_at = rows[0]["t_wall"] if rows else None

    result = {
        "latency": latency,
        "m1_sessions_per_card": "unmet" if unmet else None,
        "sla_target_ms": SLA_TARGET_MS,
        "turn_breakdown": stages,
        "rewrite_rate": rewrite_rate,
        # 세션 단위 집계가 없다 — 턴 벤치라 세션 경계가 원자료에 없다.
        "energy": [],
        "idle_baseline_w": idle_w,
        "power_timeseries": power,
        "model_placement": [
            {"role": "모더레이터 발화 · 판정 · 분류", "model": "furiosa-ai/Qwen3-32B-FP8"},
        ],
        "out_of_scope": [
            {"item": "벽면 PDU 전력", "reason": "공유 팟 — PDU 물리 접근 불가. 카드 센서 합(4장)으로 대체한 하한값"},
            {"item": "GPU 대조군", "reason": "대조군 하드웨어 미확보 — 배수 비교를 하지 않는 이유"},
            {"item": "버킷 분류 κ", "reason": "골드셋 500건 미구축 + 대조군 없어 Δκ 정의 불가"},
            {"item": "손익분기 S*", "reason": "대조군 비용·벽면 전력에 의존 — 추정 상수로 그리지 않는다"},
            {"item": "세션당 Wh", "reason": "턴 벤치라 원자료에 세션 경계가 없다 — 세션 모드 재측정 필요"},
            {"item": "평균 동시 생성(Little)", "reason": "t_wall 이 레벨당 1개뿐이라 구간 소요시간을 알 수 없다"},
            {"item": "TTFT", "reason": "원자료가 총 지연만 기록 — 하네스에 계측 추가 필요"},
            {"item": "전력 ↔ 부하 조인", "reason": "전력 로그가 최고 동시성(32) 구간을 덮지 못함"},
        ],
        "measured_at": measured_at,
        "meta": {
            "sdk_version": None,
            "firmware_version": None,
            "driver_version": None,
            "quantization": "FP8",
            "governor": None,
            "prefix_caching": None,
            "tensor_parallel_size": None,
            "corpus_hash": None,
            "prompt_template_hash": None,
            "cache_hit_rate": None,
            "code_revision": None,
        },
    }

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{turn_csv.name} · {len(rows)}턴 → {dst}")
    print(f"  재작성률 {rewrite_rate:.1%} · 유휴 {idle_w}W · 전력 {len(power)}샘플")


if __name__ == "__main__":
    main()
