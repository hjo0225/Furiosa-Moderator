import type { LucideIcon } from "lucide-react";
import { AlertTriangle, RotateCw } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "./button";

// 상태 화면 3종 — design.md §5 "상태 화면": 데모 티("불러오는 중…" 텍스트) 제거.
// prefers-reduced-motion 은 globals.css 전역 규칙(모든 animation-duration→0.01ms)이 처리하므로
// 여기서 시머/펄스를 별도로 끌 필요가 없다.

/** 로딩 — 텍스트 없이 시머 블록만. 크기/모양은 className 으로 지정(예: "h-4 w-32"). */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-platinum/70", className)} aria-hidden="true" />;
}

export interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  body?: string;
  action?: React.ReactNode;
  className?: string;
}

/** 빈 상태 — lucide 아이콘(연한 red-wash 원) + 제목 + 본문 + 선택 CTA. */
export function EmptyState({ icon: Icon, title, body, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center gap-3 px-6 py-16 text-center", className)}>
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-blush text-red-dark">
        <Icon className="h-6 w-6" strokeWidth={1.75} aria-hidden="true" />
      </div>
      <div className="space-y-1">
        <p className="text-base font-semibold text-obsidian">{title}</p>
        {body ? <p className="max-w-sm text-meta text-charcoal">{body}</p> : null}
      </div>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export interface ErrorStateProps {
  title?: string;
  body?: string;
  onRetry?: () => void;
  className?: string;
}

// 에러는 brand-red 와 절대 섞지 않는다 — maroon 전용(design.md §1 시맨틱: red 충돌 회피).
export function ErrorState({
  title = "문제가 발생했어요",
  body,
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div className={cn("flex flex-col items-center gap-3 px-6 py-16 text-center", className)}>
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-maroon/10 text-maroon">
        <AlertTriangle className="h-6 w-6" strokeWidth={1.75} aria-hidden="true" />
      </div>
      <div className="space-y-1">
        <p className="text-base font-semibold text-obsidian">{title}</p>
        {body ? <p className="max-w-sm text-meta text-charcoal">{body}</p> : null}
      </div>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry} className="mt-2 gap-1.5">
          <RotateCw className="h-4 w-4" aria-hidden="true" />
          다시 시도
        </Button>
      ) : null}
    </div>
  );
}
