"use client";

// 작업 진행 화면 — design.md §5 "작업 진행(파이프라인) 화면".
// 프레젠테이션 전용이다: 스스로 fetch 하지 않고 usePipeline 이 접어 준 상태만 그린다.
// 수치는 서버 실측만 쓴다. 값이 없으면 "—" (추정치를 실측처럼 보여주지 않는다).
import { AlertTriangle, Check, Circle, Loader2, Minus, RotateCw } from "lucide-react";

import type { PipelineState, StepView } from "@/lib/pipeline";
import { cn } from "@/lib/utils";

import { Button } from "./button";

function clock(ms: number): string {
  const total = Math.floor(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function StepIcon({ status }: { status: StepView["status"] }) {
  const base = "h-4 w-4 shrink-0";
  if (status === "done") return <Check className={cn(base, "text-go")} aria-hidden="true" />;
  if (status === "run")
    return <Loader2 className={cn(base, "animate-spin text-red")} aria-hidden="true" />;
  if (status === "skip") return <Minus className={cn(base, "text-ink-faint")} aria-hidden="true" />;
  if (status === "error")
    return <AlertTriangle className={cn(base, "text-maroon")} aria-hidden="true" />;
  return <Circle className={cn(base, "text-ink-faint/40")} aria-hidden="true" />;
}

/** 단계가 실제로 무엇을 했는지 — 서버가 보낸 detail 만 쓴다. */
function StepDetail({ step }: { step: StepView }) {
  const d = step.detail ?? {};
  const done = typeof d.done === "number" ? d.done : null;
  const total = typeof d.total === "number" ? d.total : null;
  const model = typeof d.model === "string" ? d.model : "";
  const reason = typeof d.reason === "string" ? d.reason : "";
  const samples = Array.isArray(d.samples)
    ? (d.samples as { text?: string; source?: string }[])
    : [];

  return (
    <>
      {done !== null && total !== null && (
        <p className="mt-0.5 font-mono text-2xs text-ink-faint">
          {done}/{total}
        </p>
      )}
      {model && <p className="mt-0.5 font-mono text-2xs text-ink-faint">└ RNGD · {model}</p>}
      {reason && <p className="mt-0.5 text-2xs text-ink-faint">└ {reason}</p>}
      {samples.map((s, i) => (
        <p key={i} className="mt-0.5 text-2xs leading-relaxed text-ink-soft">
          &ldquo;{s.text ?? ""}&rdquo;
          {s.source ? <span className="text-ink-faint"> — {s.source}</span> : null}
        </p>
      ))}
    </>
  );
}

export interface PipelineProgressProps {
  /** 무엇을 하는 중인지 — "가이드를 만들고 있어요" */
  title: string;
  state: PipelineState;
  onDetach: () => void;
  onRetry?: () => void;
}

export function PipelineProgress({ title, state, onDetach, onRetry }: PipelineProgressProps) {
  const settled = state.steps.filter((s) => s.status !== "wait" && s.status !== "run").length;

  return (
    <div className="flex flex-col items-center px-6 py-16">
      <h2 className="text-title text-ink">{title}</h2>
      <p className="mt-1 font-mono text-lead text-ink-faint" aria-live="polite">
        {clock(state.elapsedMs)}
      </p>

      <ul className="mt-8 w-full max-w-md space-y-3">
        {state.steps.map((step) => (
          <li key={step.key} className="flex items-start gap-3">
            <span className="mt-1">
              <StepIcon status={step.status} />
            </span>
            <div className="min-w-0 flex-1">
              <p
                className={cn(
                  "text-base",
                  step.status === "wait" ? "text-ink-faint" : "text-ink",
                  step.status === "error" && "text-maroon",
                )}
              >
                {step.label}
              </p>
              <StepDetail step={step} />
            </div>
            {/* 실측 소요 시간만 쓴다. 아직 안 끝났거나 서버가 안 보냈으면 "—". */}
            <span className="mt-0.5 shrink-0 font-mono text-2xs text-ink-faint">
              {step.status === "done" && step.ms !== undefined
                ? `${(step.ms / 1000).toFixed(1)}s`
                : "—"}
            </span>
          </li>
        ))}
      </ul>

      <div className="mt-8 w-full max-w-md border-t border-line pt-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="font-mono text-2xs text-ink-faint">
            {settled}/{state.steps.length} 단계
            {state.tokens > 0 ? ` · 토큰 ${state.tokens.toLocaleString()}` : ""}
          </p>
          {state.running && (
            // "취소"가 아니다 — 이미 떠난 NPU 호출은 못 죽인다(design.md §5).
            <Button size="sm" variant="ghost" onClick={onDetach}>
              백그라운드로 두기
            </Button>
          )}
        </div>
        {state.error && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <p className="text-meta text-maroon">{state.error}</p>
            {onRetry && (
              <Button size="sm" variant="secondary" onClick={onRetry} className="gap-1.5">
                <RotateCw className="h-4 w-4" aria-hidden="true" />
                다시 시도
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
