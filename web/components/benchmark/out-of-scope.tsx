import { Minus } from "lucide-react";

import { Card } from "@/components/shared";
import type { OutOfScopeItem } from "@/lib/api";

// 범위 밖 — 계측 스펙 §9. 이 표의 항목은 "아직 안 했다"가 아니라 "이 환경에서는 못 한다"다.
// 빈 칸으로 두면 전자로 읽히는데, 사유가 곧 정보다(왜 배수 비교를 안 하는지 등).
// design.md §5: minus 아이콘 + ink-faint. 실패(maroon)가 아니다 — 잘못된 게 아니라 범위 밖이다.
export function OutOfScopePanel({ items }: { items: OutOfScopeItem[] }) {
  if (items.length === 0) return null;

  return (
    <Card as="section" className="p-6">
      <p className="eyebrow">범위 밖 — 재지 않는 것</p>
      <p className="mt-2 text-meta text-charcoal">
        아래는 측정을 안 한 게 아니라 <b className="text-obsidian">이 환경에서 못 하는</b> 것들이다.
        빈 칸 대신 사유를 남긴다.
      </p>
      <ul className="mt-4 space-y-2.5">
        {items.map((it) => (
          <li key={it.item} className="flex items-start gap-2.5">
            <Minus className="mt-1 h-3.5 w-3.5 shrink-0 text-grey" aria-hidden="true" />
            <div className="min-w-0">
              <p className="text-meta font-medium text-charcoal">{it.item}</p>
              <p className="text-2xs leading-relaxed text-grey">{it.reason}</p>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
