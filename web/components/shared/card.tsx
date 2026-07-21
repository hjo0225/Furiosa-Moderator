import { cn } from "@/lib/utils";

// OW 카드 = 흰 표면 + 1px 헤어라인 + 미세 그림자, 단일 radius(rounded-xl=12px).
// 화면마다 rounded-xl/2xl 이 뒤섞이던 걸 하나로 모은다. 패딩만 className 으로 조절.
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-xl bg-surface p-5 shadow-card ring-1 ring-line", className)}
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
