import { Card } from "@/components/shared";
import type { BenchmarkResult } from "@/lib/api";

import { fmtM1, fmtNum, fmtPct, fmtSec } from "./format";

// M1 / M2 / M4 — design.md §5·계측 스펙 §1. 손익분기 S* 와 κ 카드는 뺐다(스펙 §9 범위 밖):
// 영원히 "—" 로 남을 칸을 헤드라인에 두면 "아직 안 함"으로 읽히는데, 실제로는 이 환경에서
// 측정 자체가 불가능한 항목이라 아래 "범위 밖" 표에서 사유와 함께 말하는 게 맞다.
export function MetricCards({ result }: { result: BenchmarkResult }) {
  // 헤드라인 idle 비중 = 가장 낮은 가동률 구간. "적게 쓸수록 세션당 에너지가 나쁘다"가 논점이라
  // 최악 구간을 대표로 보여주고, 곡선 전체는 아래 에너지 패널이 맡는다.
  const lowestLoad = result.energy.length > 0 ? result.energy[0] : null;
  const guardrail = result.turn_breakdown.find((s) => s.key === "guardrail") ?? null;
  const total = result.turn_breakdown.find((s) => s.key === "total") ?? null;
  const idlePct =
    lowestLoad?.idle_share === null || lowestLoad?.idle_share === undefined
      ? null
      : Math.round(lowestLoad.idle_share * 100);

  return (
    <div className="grid gap-4 md:grid-cols-3">
      {/* M1 — 지연 */}
      <Card className="flex flex-col">
        <p className="eyebrow">M1</p>
        <p className="mt-2 text-meta font-medium text-obsidian">SLA 충족 동시 세션</p>
        <p className="mt-3 font-telemetry text-title text-red">
          {fmtM1(result.m1_sessions_per_card)}
        </p>
        <p className="mt-1 text-2xs text-grey">
          max C : turn_e2e p95 ≤ {fmtNum(result.sla_target_ms, { unit: "ms" })}
        </p>
        {result.m1_sessions_per_card === "unmet" && (
          <p className="mt-2 text-2xs leading-relaxed text-charcoal">
            전 구간에서 p95가 목표를 넘었습니다. 카드 용량이 아니라 파이프라인이 원인이라는 뜻이며,
            근거는 아래 <b className="text-obsidian">동시 생성 수</b>입니다.
          </p>
        )}
        <span className="mt-3 inline-flex w-fit items-center rounded-md bg-blush px-2 py-0.5 text-2xs font-medium text-red-dark">
          세션 슬롯 ≠ 동시 생성
        </span>
      </Card>

      {/* M2 — 에너지 */}
      <Card className="flex flex-col">
        <p className="eyebrow">M2</p>
        <p className="mt-2 text-meta font-medium text-obsidian">
          세션당 Wh
          <span className="ml-1 font-normal text-grey">
            (하루 {fmtNum(lowestLoad?.sessions_per_day ?? null)}세션)
          </span>
        </p>
        <p className="mt-3 font-telemetry text-title text-red">
          {fmtNum(lowestLoad?.wh_per_session, { digits: 1 })}
          <span className="ml-1 font-sans text-meta font-normal text-grey">Wh/세션</span>
        </p>
        <div className="mt-3 border-t border-platinum pt-3">
          <div className="flex items-center justify-between text-2xs text-grey">
            <span>idle 비중</span>
            <span className="font-telemetry text-obsidian">
              {idlePct === null ? "—" : `${idlePct}%`}
            </span>
          </div>
          <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-platinum">
            <div
              className="h-full rounded-full bg-grey transition-[width]"
              style={{ width: `${idlePct ?? 0}%` }}
            />
          </div>
        </div>
        <p className="mt-2 text-2xs text-grey">카드 센서 기준 하한값 · CPU/NIC/팬 미포함</p>
      </Card>

      {/* M4 — 턴 내부 분해 */}
      <Card className="flex flex-col">
        <p className="eyebrow">M4</p>
        <p className="mt-2 text-meta font-medium text-obsidian">가드레일이 턴에서 차지하는 비중</p>
        <p className="mt-3 font-telemetry text-title text-red">
          {fmtPct(guardrail?.share)}
        </p>
        <dl className="mt-3 grid grid-cols-2 gap-2 border-t border-platinum pt-3 text-2xs">
          <div>
            <dt className="text-grey">가드레일 p50</dt>
            <dd className="font-telemetry text-obsidian">{fmtSec(guardrail?.p50_ms)}</dd>
          </div>
          <div>
            <dt className="text-grey">턴 전체 p50</dt>
            <dd className="font-telemetry text-obsidian">{fmtSec(total?.p50_ms)}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-grey">재작성 발생률</dt>
            <dd className="font-telemetry text-obsidian">{fmtPct(result.rewrite_rate)}</dd>
          </div>
        </dl>
      </Card>
    </div>
  );
}
