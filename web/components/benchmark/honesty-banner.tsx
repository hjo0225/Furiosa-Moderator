import { Info } from "lucide-react";

import type { BenchmarkResult } from "@/lib/api";

import { gateStatus } from "./format";
import { GateBadge } from "./gate-badge";

// 정직성 배너 — design.md §5 "벤치마크": 이 뷰 전체를 읽기 전에 먼저 봐야 하는 3가지 계약.
// 문구는 task-7-brief.md·계측 스펙 §1·§8 을 그대로 반영한다(즉흥 카피 금지).
export function HonestyBanner({ result }: { result: BenchmarkResult }) {
  const gate = gateStatus(result);

  return (
    <div className="rounded-[10px] border border-silver bg-paper p-4">
      <div className="flex items-start gap-3">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-grey" aria-hidden="true" />
        <div className="space-y-1.5 text-meta text-charcoal">
          <p>
            <strong className="font-semibold text-obsidian">실측 전에는 전부 &ldquo;—&rdquo;</strong>
            입니다 — 예시로 채운 숫자는 없습니다.
          </p>
          <p>
            전력 수치는 카드 센서가 아니라 <strong className="font-semibold text-obsidian">벽면 PDU 실측</strong>{" "}
            기준입니다(CPU·NIC·팬 포함, 카드 센서만으로 계산한 값과 다를 수 있어요).
          </p>
          <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
            <span>
              <strong className="font-semibold text-obsidian">M3 게이트</strong>: κ &lt; 0.75 또는
              Δκ &lt; −0.05 면 M1·M2 결과는 무효 처리됩니다.
            </span>
            <GateBadge gate={gate} />
          </p>
        </div>
      </div>
    </div>
  );
}
