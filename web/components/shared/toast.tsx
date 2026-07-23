"use client";

// 전역 토스트 (액션 피드백) — design.md §5 "토스트".
// 성공 액션(저장·배포·내보내기 등)을 화면 어디서 눌러도 같은 자리(우하단)에서 확인하게 한다.
// 예전엔 페이지 최하단 인라인 텍스트라 스크롤 위치에 따라 놓쳤다.
//
// 성공=go(초록 체크), 에러/파괴=maroon — brand-red 는 정상 액션 색으로만(§1). 3.5초 자동 소멸.
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

type Tone = "success" | "error" | "info";
type Toast = { id: number; tone: Tone; message: string };

type ShowArgs = { tone?: Tone; message: string };
const ToastContext = createContext<((args: ShowArgs) => void) | null>(null);

const AUTO_DISMISS_MS = 3500;

const TONE: Record<Tone, { icon: typeof CheckCircle2; cls: string }> = {
  success: { icon: CheckCircle2, cls: "text-go" },
  error: { icon: AlertTriangle, cls: "text-maroon" },
  info: { icon: Info, cls: "text-charcoal" },
};

/** useToast().show({ tone: "success", message: "저장했어요" }) */
export function useToast() {
  const show = useContext(ToastContext);
  if (!show) {
    // Provider 밖에서 불려도 앱을 죽이지 않는다 — 조용히 무동작(테스트·SSR 방어).
    return { show: (_: ShowArgs) => {} };
  }
  return { show };
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const remove = useCallback((id: number) => {
    setToasts((ts) => ts.filter((t) => t.id !== id));
  }, []);

  const show = useCallback(({ tone = "info", message }: ShowArgs) => {
    const id = nextId.current++;
    setToasts((ts) => [...ts, { id, tone, message }].slice(-4)); // 최대 4개만 쌓는다
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      {/* 우하단(모바일 상단) 스택. aria-live 로 스크린리더에도 읽힌다. */}
      <div
        className="pointer-events-none fixed inset-x-0 top-3 z-[60] flex flex-col items-center gap-2 px-4 sm:inset-x-auto sm:bottom-4 sm:right-4 sm:top-auto sm:items-end sm:px-0"
        role="status"
        aria-live="polite"
      >
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onDone={() => remove(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, onDone }: { toast: Toast; onDone: () => void }) {
  const [leaving, setLeaving] = useState(false);
  const [entered, setEntered] = useState(false);
  const { icon: Icon, cls } = TONE[toast.tone];

  useEffect(() => {
    // 진입 애니메이션 트리거(다음 프레임에 entered=true)
    const raf = requestAnimationFrame(() => setEntered(true));
    const dismiss = window.setTimeout(() => setLeaving(true), AUTO_DISMISS_MS);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(dismiss);
    };
  }, []);

  // 소멸 애니메이션이 끝나면 실제 제거(150ms, exit가 enter보다 빠르게 — §7)
  useEffect(() => {
    if (!leaving) return;
    const t = window.setTimeout(onDone, 150);
    return () => window.clearTimeout(t);
  }, [leaving, onDone]);

  return (
    <div
      className={cn(
        "pointer-events-auto flex w-full max-w-sm items-start gap-2.5 rounded-lg bg-white px-3.5 py-3 shadow-card ring-1 ring-silver",
        "transition-all",
        leaving ? "duration-150" : "duration-200",
        entered && !leaving ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0",
      )}
    >
      <Icon className={cn("mt-0.5 h-4.5 w-4.5 shrink-0", cls)} aria-hidden="true" />
      <p className="min-w-0 flex-1 text-meta text-obsidian">{toast.message}</p>
      <button
        type="button"
        onClick={() => setLeaving(true)}
        aria-label="닫기"
        className="-mr-1 -mt-0.5 shrink-0 rounded p-1 text-grey hover:bg-paper hover:text-charcoal"
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}
