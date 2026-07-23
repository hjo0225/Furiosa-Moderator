import { cn } from "@/lib/utils";

// 상태 배지 — design.md §5 "카드(프로젝트)": 배포됨=obsidian칩·작성중=red-wash칩·종료=grey칩.
// warm 은 응답자(웜) 표면에서 쓰는 동일 red-wash 톤(별도 시맨틱 색 아님 — 액센트 wash 재사용).
export type BadgeTone = "live" | "draft" | "closed" | "warm";

const tones: Record<BadgeTone, string> = {
  live: "bg-obsidian text-white",
  draft: "bg-blush text-red-dark",
  closed: "bg-platinum text-grey",
  warm: "bg-blush text-red-dark",
};

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
}

// 배지 라디우스 6px(design.md §3) — 토큰에 별도 항목이 없어 Tailwind 기본 스케일의
// rounded-md(0.375rem=6px)를 그대로 쓴다(tailwind.config 의 확장이 이 키를 덮지 않음).
export function Badge({ tone = "draft", className, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-2xs font-medium tabular-nums",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}
