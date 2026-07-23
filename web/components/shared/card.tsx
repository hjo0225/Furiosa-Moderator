import { cn } from "@/lib/utils";

// Furiosa 카드 = 흰 표면 + 1px silver 헤어라인 + 소프트 그림자, 10px 라디우스(design.md §3·§5 "카드(프로젝트)").
// 단일 radius. 패딩만 className 으로 조절.
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-[10px] bg-white p-5 shadow-card ring-1 ring-silver", className)}
      {...props}
    />
  );
}

// 입력 필드 공통 스타일 — <input>/<textarea> 가 cn 으로 조합해 쓴다(크기·flex 등은 호출부에서).
export function fieldClass(className?: string) {
  return cn(
    "rounded-lg bg-bg px-3 py-2 text-ink ring-1 ring-line",
    "placeholder:text-ink-faint/60 focus:outline-none focus:ring-accent disabled:opacity-60",
    className,
  );
}
