import { forwardRef } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md" | "lg";

// Furiosa 버튼 = pill(rounded-full) 폐기 → 8px 라운드 렉트(rounded). design.md §3·§5.
const base =
  "inline-flex items-center justify-center gap-2 font-medium rounded transition-all duration-200 " +
  "focus-visible:outline-red disabled:opacity-50 disabled:pointer-events-none select-none whitespace-nowrap";

// 서브테마 폐기, 단일 red 액센트(design.md §0·§5) — primary=red 채움 · secondary=흰+silver 링 · ghost=투명+charcoal.
const variants: Record<Variant, string> = {
  // Primary — brand-red 배경/흰 글자, hover red-dark
  primary: "bg-red text-white hover:bg-red-dark active:translate-y-px",
  // Secondary — 흰 배경/obsidian 글자, 1px silver 링
  secondary:
    "bg-white text-obsidian ring-1 ring-silver hover:bg-paper active:translate-y-px",
  ghost: "bg-transparent text-charcoal hover:bg-blush",
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
  /** true 면 앞에 회전 스피너(파이프라인의 loader-2 관용구와 통일)를 붙이고 자동 비활성화한다.
   *  자식 텍스트("저장 중…")는 그대로 두어 무슨 작업인지 읽히게 한다. */
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, disabled, children, ...props }, ref) => (
    <button
      ref={ref}
      className={buttonVariants({ variant, size, className })}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />}
      {children}
    </button>
  ),
);
Button.displayName = "Button";
