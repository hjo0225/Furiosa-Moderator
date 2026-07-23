import { Info } from "lucide-react";

import { Card } from "@/components/shared";
import type { BenchmarkResult } from "@/lib/api";

import { isUnmeasured } from "./format";

// 정직성 배너 — design.md §5 "벤치마크": 이 뷰를 읽기 전에 먼저 알아야 하는 계약.
// 문구는 계측 스펙 §0·§1·§9 를 그대로 반영한다(즉흥 카피 금지).
export function HonestyBanner({ result }: { result: BenchmarkResult }) {
  return (
    <Card className="border border-silver bg-paper p-4 shadow-none ring-0">
      <div className="flex items-start gap-3">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-grey" aria-hidden="true" />
        <div className="space-y-1.5 text-meta text-charcoal">
          <p>
            <strong className="font-semibold text-obsidian">대조군이 없습니다.</strong> 이 화면은
            &ldquo;몇 배 빠른가&rdquo;가 아니라{" "}
            <strong className="font-semibold text-obsidian">지연과 에너지가 어디서 나오는지</strong>를
            분해해 보여줍니다.
          </p>
          <p>
            전력은 <strong className="font-semibold text-obsidian">카드 센서 기준 하한값</strong>입니다 —
            CPU·NIC·팬·전원 손실이 빠져 있어 실제 벽면 소비는 이보다 큽니다. 전기요금 계산이나 타
            플랫폼 비교에 쓰지 않습니다.
          </p>
          {isUnmeasured(result) ? (
            <p>
              <strong className="font-semibold text-obsidian">아직 실행된 계측이 없습니다.</strong>{" "}
              모든 수치가 &ldquo;—&rdquo;로 표시됩니다 — 예시로 채운 숫자는 없습니다.
            </p>
          ) : (
            <p>
              측정되지 않은 값은 &ldquo;—&rdquo;로 둡니다. 못 잰 항목과 사유는 아래{" "}
              <strong className="font-semibold text-obsidian">범위 밖</strong> 표에 있습니다.
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}
