import { forwardRef } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "outline" | "ghost";
type Size = "sm" | "md" | "lg";

// OW 버튼 = pill(rounded-full) + 플랫 솔리드
const base =
  "inline-flex items-center justify-center gap-2 font-medium rounded-full transition-all duration-200 " +
  "focus-visible:outline-accent disabled:opacity-50 disabled:pointer-events-none select-none whitespace-nowrap";

// 서브브랜드 액센트를 따른다 (theme-* 가 --accent* 주입) — Validate=그린·Survey=블루·Prediction=시안·Review=오렌지(솔리드는 slate)
const variants: Record<Variant, string> = {
  // Primary — 채운 액센트 배경 + 대비 글자색(--accent-on), 플랫
  primary:
    "bg-accent-solid text-accent-on hover:brightness-[0.97] active:translate-y-px",
  // Secondary — 투명 + 액센트 테두리·글자
  outline:
    "bg-surface text-accent ring-1 ring-accent/40 hover:bg-accent-wash active:translate-y-px",
  ghost: "bg-transparent text-ink-soft hover:text-ink hover:bg-accent-wash",
};

const sizes: Record<Size, string> = {
  sm: "h-9 px-4 text-meta",
  md: "h-11 px-6 text-base",
  lg: "h-14 px-8 text-lead",
};

/** 버튼 스타일 — 링크(<a>/<Link>)에도 재사용 */
export function buttonVariants({
  variant = "primary",
  size = "md",
  className,
}: { variant?: Variant; size?: Size; className?: string } = {}) {
  return cn(base, variants[variant], sizes[size], className);
}

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={buttonVariants({ variant, size, className })} {...props} />
  ),
);
Button.displayName = "Button";
