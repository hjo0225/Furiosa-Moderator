import { Card } from "@/components/shared";
import type { LatencyRow } from "@/lib/api";

import { fmtNum, fmtPct, fmtSec } from "./format";

// 지연 곡선 — 계측 스펙 §7 "표 1". 동시 세션 슬롯별 지연 + M1-b(슬롯≠생성).
// 넓은 표는 자체 overflow-x:auto(design.md §6) — 본문은 절대 가로 스크롤하지 않는다.
export function LatencyTable({ rows }: { rows: LatencyRow[] }) {
  return (
    <Card as="section" className="p-6">
      <p className="eyebrow">M1 · 지연 곡선</p>
      <p className="mt-2 text-meta text-charcoal">
        슬롯을 4배로 올려도 p95가 따라 오르지 않는다면 병목은 카드 용량이 아니다. 그 판단의 근거가
        오른쪽 <b className="text-obsidian">동시 생성</b> 두 열이다 — 참가자 사고시간 때문에 슬롯
        수보다 훨씬 적은 수만 실제로 생성 중이다.
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[680px] border-collapse text-left text-meta">
          <thead>
            <tr className="border-b border-silver text-2xs uppercase tracking-wide text-grey">
              <th className="py-2 pr-4 font-medium">세션 슬롯</th>
              <th className="py-2 pr-4 font-medium">턴 수</th>
              <th className="py-2 pr-4 font-medium">실패</th>
              <th className="py-2 pr-4 font-medium">p50</th>
              <th className="py-2 pr-4 font-medium">p95</th>
              <th className="py-2 pr-4 font-medium">ttft p95</th>
              <th className="py-2 pr-4 font-medium">평균 동시 생성</th>
              <th className="py-2 font-medium">카드 점유율</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.slots} className="border-b border-platinum last:border-0">
                <td className="py-2.5 pr-4">
                  <span className="inline-flex items-center gap-1.5 font-medium text-obsidian">
                    <span className="h-2 w-2 shrink-0 rounded-full bg-red" aria-hidden="true" />
                    {r.slots}
                  </span>
                </td>
                <td className="py-2.5 pr-4 font-telemetry text-obsidian">{fmtNum(r.turns)}</td>
                <td className="py-2.5 pr-4 font-telemetry text-obsidian">{fmtNum(r.failures)}</td>
                <td className="py-2.5 pr-4 font-telemetry text-obsidian">{fmtSec(r.p50_ms)}</td>
                <td className="py-2.5 pr-4 font-telemetry text-obsidian">{fmtSec(r.p95_ms)}</td>
                <td className="py-2.5 pr-4 font-telemetry text-obsidian">
                  {fmtSec(r.ttft_p95_ms)}
                </td>
                <td className="py-2.5 pr-4 font-telemetry text-obsidian">
                  {fmtNum(r.avg_concurrent_generating, { digits: 2 })}
                </td>
                <td className="py-2.5 font-telemetry text-obsidian">{fmtPct(r.occupancy)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-2xs text-grey">
        평균 동시 생성 = 처리량 × 평균 턴 지연(Little의 법칙). 원자료로 검증할 수 없는 &ldquo;순간
        최대 동시 생성&rdquo;은 보고하지 않는다(스펙 §8).
      </p>
    </Card>
  );
}
