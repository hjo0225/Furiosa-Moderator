import type { BenchmarkResult } from "@/lib/api";

import { fmtNum, gateStatus, primaryRow } from "./format";
import { GateBadge } from "./gate-badge";

// M1/M2/M3 — design.md §5·계측 스펙 §1. 세 카드 모두 "기준 행"(governor=Performance·
// cache=on, primaryRow())을 대표값으로 쓴다 — 스펙 §5: M1 은 그 조합에서만 산출하므로
// 헤드라인 카드가 다른 조합(예: PowerSave) 값을 섞어 보이면 오해를 부른다. 4구성 전체
// 비교는 아래 결과 표가 맡는다.
export function MetricCards({ result }: { result: BenchmarkResult }) {
  const row = primaryRow(result);
  const gate = gateStatus(result);
  const idlePct = row?.idle_share === null || row?.idle_share === undefined
    ? null
    : Math.round(row.idle_share * 100);

  return (
    <div className="grid gap-4 md:grid-cols-3">
      {/* M1 */}
      <div className="flex flex-col rounded-[10px] bg-white p-5 shadow-card ring-1 ring-silver">
        <p className="eyebrow">M1</p>
        <p className="mt-2 text-meta font-medium text-obsidian">
          SLA 충족 동시 세션(세션슬롯/카드)
        </p>
        <p className="mt-3 font-telemetry text-title text-red">
          {fmtNum(row?.m1_sessions_per_card)}
          <span className="ml-1 font-sans text-meta font-normal text-grey">세션/카드</span>
        </p>
        <p className="mt-1 text-2xs text-grey">max C : turn_e2e p95 ≤ 2000ms</p>
        <dl className="mt-3 grid grid-cols-2 gap-2 border-t border-platinum pt-3 text-2xs">
          <div>
            <dt className="text-grey">ttft p95</dt>
            <dd className="font-telemetry text-obsidian">
              {fmtNum(row?.ttft_p95_ms, { unit: "ms" })}
            </dd>
          </div>
          <div>
            <dt className="text-grey">turn e2e p50</dt>
            <dd className="font-telemetry text-obsidian">
              {fmtNum(row?.turn_e2e_p50_ms, { unit: "ms" })}
            </dd>
          </div>
        </dl>
        <span className="mt-3 inline-flex w-fit items-center rounded-md bg-blush px-2 py-0.5 text-2xs font-medium text-red-dark">
          세션 슬롯 ≠ 동시 생성
        </span>
      </div>

      {/* M2 */}
      <div className="flex flex-col rounded-[10px] bg-white p-5 shadow-card ring-1 ring-silver">
        <p className="eyebrow">M2</p>
        <p className="mt-2 text-meta font-medium text-obsidian">세션당 Wh(벽면·idle 포함)</p>
        <p className="mt-3 font-telemetry text-title text-red">
          {fmtNum(row?.m2_wh_per_session, { digits: 2 })}
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
      </div>

      {/* M3 */}
      <div className="flex flex-col rounded-[10px] bg-white p-5 shadow-card ring-1 ring-silver">
        <p className="eyebrow">M3</p>
        <p className="mt-2 text-meta font-medium text-obsidian">버킷 분류 κ</p>
        <p className="mt-3 font-telemetry text-title text-red">
          {fmtNum(row?.kappa, { digits: 2 })}
        </p>
        <p className="mt-1 text-2xs text-grey">
          Δκ <span className="font-telemetry text-charcoal">{fmtNum(row?.delta_kappa, { digits: 2, signed: true })}</span>
        </p>
        <GateBadge gate={gate} className="mt-3" />
      </div>
    </div>
  );
}
