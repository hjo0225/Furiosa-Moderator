import { Card } from "@/components/shared";
import type { BenchmarkResult, TurnStageRow } from "@/lib/api";

import { fmtPct, fmtSec } from "./format";

// M4 턴 내부 분해 — 계측 스펙 §7 "표 2".
// 대조군이 없는 상황에서 가장 실행 가능한 결론을 주는 지표라 M1·M2 와 동급이다:
// "어디서 시간을 쓰는가"가 곧 "무엇을 고칠 것인가"다.
function StageBar({ stage }: { stage: TurnStageRow }) {
  const pct = stage.share === null ? 0 : Math.round(stage.share * 100);
  const isTotal = stage.key === "total";

  return (
    <li className={isTotal ? "border-t border-silver pt-3" : ""}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span
          className={
            isTotal ? "text-meta font-semibold text-obsidian" : "text-meta font-medium text-obsidian"
          }
        >
          {stage.label}
          {stage.parallel && (
            <span className="ml-1.5 rounded bg-blush px-1.5 py-0.5 text-2xs font-normal text-red-dark">
              병렬
            </span>
          )}
        </span>
        <span className="font-telemetry text-meta text-obsidian">
          {fmtSec(stage.p50_ms)}
          <span className="ml-2 text-grey">{fmtPct(stage.share)}</span>
        </span>
      </div>
      {!isTotal && (
        <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-platinum">
          <div
            className="h-full rounded-full bg-red transition-[width]"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
      {stage.note && <p className="mt-1 text-2xs text-grey">{stage.note}</p>}
    </li>
  );
}

export function TurnBreakdown({ result }: { result: BenchmarkResult }) {
  return (
    <Card as="section" className="p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="eyebrow">M4 · 턴 내부 분해</p>
        <p className="text-2xs text-grey">
          재작성 발생률{" "}
          <span className="font-telemetry text-obsidian">{fmtPct(result.rewrite_rate)}</span>
        </p>
      </div>
      <p className="mt-2 text-meta text-charcoal">
        한 턴을 구성하는 LLM 호출을 단계로 쪼갠 것. 질문을 <b className="text-obsidian">만드는</b>{" "}
        시간과 그 질문을 <b className="text-obsidian">검사하는</b> 시간을 갈라 봐야 어디를 고칠지가
        정해진다.
      </p>
      <ul className="mt-4 space-y-3">
        {result.turn_breakdown.map((stage) => (
          <StageBar key={stage.key} stage={stage} />
        ))}
      </ul>
      <p className="mt-3 text-2xs text-grey">
        병렬 단계의 비중은 직렬 합이 아니라 벽시계 기여도다 — 합이 100%를 넘지 않도록 보정된 값이다.
      </p>
    </Card>
  );
}
