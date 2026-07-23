"use client";

// 파괴적 작업 확인 다이얼로그 — design.md §5 "확인 다이얼로그".
// 되돌릴 수 없는 작업에만 쓴다. 브라우저 confirm() 을 쓰지 않는 이유: 모달 대화상자는
// 스타일을 못 입히고, 무엇이 함께 사라지는지 같은 맥락을 담을 수 없다.
import { useEffect, useRef } from "react";
import { AlertTriangle } from "lucide-react";

import { Button } from "./button";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  /** 무엇이 사라지는지 — 되돌릴 수 없다는 사실을 여기서 분명히 말한다. */
  body: React.ReactNode;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  // 파괴적 확인창은 취소에 포커스를 준다 — 엔터 연타로 실행되면 안 된다.
  useEffect(() => {
    if (open) cancelRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-obsidian/40 px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
    >
      <div className="w-full max-w-md rounded-card bg-white p-6 shadow-lift">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-maroon/10 text-maroon">
            <AlertTriangle className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p id="confirm-dialog-title" className="text-lead font-medium text-obsidian">
              {title}
            </p>
            <div className="mt-1.5 text-meta leading-relaxed text-charcoal">{body}</div>
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <Button ref={cancelRef} variant="secondary" size="sm" onClick={onCancel} disabled={busy}>
            취소
          </Button>
          {/* 파괴적 액션은 maroon — brand red 와 섞지 않는다(design.md §1 시맨틱) */}
          <Button
            size="sm"
            onClick={onConfirm}
            disabled={busy}
            className="!bg-maroon !text-white hover:!bg-maroon/90"
          >
            {busy ? "삭제 중…" : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
