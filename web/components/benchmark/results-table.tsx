import type { BenchmarkRow } from "@/lib/api";

import { fmtNum, fmtPct } from "./format";

// 결과 표 — 계측 스펙 §7 "결과 표(1장)" 그대로: 4 구성 x 6열. 넓은 표는 자체
// overflow-x:auto(design.md §6) — 본문은 절대 가로 스크롤하지 않는다.
export function ResultsTable({ rows }: { rows: BenchmarkRow[] }) {
  return (
    <section className="rounded-[10px] bg-white p-6 shadow-card ring-1 ring-silver">
      <p className="eyebrow">결과 표</p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-left text-meta">
          <thead>
            <tr className="border-b border-silver text-2xs uppercase tracking-wide text-grey">
              <th className="py-2 pr-4 font-medium">구성</th>
              <th className="py-2 pr-4 font-medium">M1 세션/카드</th>
              <th className="py-2 pr-4 font-medium">500세션 카드</th>
              <th className="py-2 pr-4 font-medium">M2 Wh/세션</th>
              <th className="py-2 pr-4 font-medium">idle 비중</th>
              <th className="py-2 pr-4 font-medium">κ</th>
              <th className="py-2 font-medium">Δκ</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.config} className="border-b border-platinum last:border-0">
                <td className="py-2.5 pr-4">
                  <span className="inline-flex items-center gap-1.5 font-medium text-obsidian">
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ background: r.hardware === "rngd" ? "#E21500" : "#7F7F7F" }}
                      aria-hidden="true"
                    />
                    {r.label}
                  </span>
                </td>
                <td className="py-2.5 pr-4 font-telemetry text-obsidian">
                  {fmtNum(r.m1_sessions_per_card)}
                </td>
                <td className="py-2.5 pr-4 font-telemetry text-obsidian">
                  {fmtNum(r.cards_for_500)}
                </td>
                <td className="py-2.5 pr-4 font-telemetry text-obsidian">
                  {fmtNum(r.m2_wh_per_session, { digits: 2 })}
                </td>
                <td className="py-2.5 pr-4 font-telemetry text-obsidian">{fmtPct(r.idle_share)}</td>
                <td className="py-2.5 pr-4 font-telemetry text-obsidian">
                  {fmtNum(r.kappa, { digits: 2 })}
                </td>
                <td className="py-2.5 font-telemetry text-obsidian">
                  {fmtNum(r.delta_kappa, { digits: 2, signed: true })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
