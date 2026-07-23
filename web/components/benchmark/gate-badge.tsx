import { cn } from "@/lib/utils";

import type { GateStatus } from "./format";

// M3 게이트 배지 — Badge(shared)의 live/draft/closed 톤은 프로젝트 상태용이라 재사용하지 않고
// 이 화면 전용 3톤(미측정/통과/무효)을 별도로 둔다. 무효는 danger 시맨틱(maroon) — brand-red 와
// 혼용 금지(design.md §1).
const STYLE: Record<GateStatus, string> = {
  unmeasured: "bg-platinum text-grey",
  pass: "bg-mint/25 text-obsidian",
  fail: "bg-maroon/10 text-maroon",
};

const LABEL: Record<GateStatus, string> = {
  unmeasured: "게이트 · 미측정",
  pass: "게이트 · 통과",
  fail: "게이트 · 무효",
};

export function GateBadge({ gate, className }: { gate: GateStatus; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex w-fit items-center rounded-md px-2 py-0.5 text-2xs font-medium",
        STYLE[gate],
        className,
      )}
    >
      {LABEL[gate]}
    </span>
  );
}
