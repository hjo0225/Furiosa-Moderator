"use client";

// 진행 이벤트 소비 훅 — 서버(api/services/progress.py)가 보내는 4종 이벤트를 화면 상태로 접는다.
// 수치는 전부 서버 실측을 그대로 쓴다. 경과 타이머만 클라이언트 벽시계다(추정이 아니다).
import { useCallback, useEffect, useRef, useState } from "react";

import { apiUrl } from "./api";
import { streamSse } from "./sse";

/** 서버는 wait 를 보내지 않는다 — 아직 안 온 단계라 클라이언트에만 있는 상태다. */
export type StepStatus = "wait" | "run" | "done" | "skip" | "error";

export type StepView = {
  key: string;
  label: string;
  status: StepStatus;
  ms?: number;
  detail?: Record<string, unknown>;
};

type ServerEvent =
  | { steps: { key: string; label: string }[] }
  | {
      step: string;
      status: "start" | "done" | "skip" | "error";
      ms?: number;
      error?: string;
      detail?: Record<string, unknown>;
    }
  | { result: unknown }
  | { error: string };

export type PipelineState = {
  running: boolean;
  steps: StepView[];
  elapsedMs: number;
  tokens: number;
  error: string | null;
};

const IDLE: PipelineState = { running: false, steps: [], elapsedMs: 0, tokens: 0, error: null };

const SERVER_TO_VIEW: Record<string, StepStatus> = {
  start: "run",
  done: "done",
  skip: "skip",
  error: "error",
};

export function usePipeline<T>() {
  const [state, setState] = useState<PipelineState>(IDLE);
  const abortRef = useRef<AbortController | null>(null);
  const startedAtRef = useRef(0);

  // 경과 타이머 — 진행 중에만 돈다.
  useEffect(() => {
    if (!state.running) return;
    const id = window.setInterval(
      () => setState((s) => ({ ...s, elapsedMs: Date.now() - startedAtRef.current })),
      100,
    );
    return () => window.clearInterval(id);
  }, [state.running]);

  // 언마운트되면 스트림을 붙잡고 있지 않는다.
  useEffect(() => () => abortRef.current?.abort(), []);

  const detach = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setState(IDLE);
  }, []);

  const run = useCallback(async (path: string, init: RequestInit = {}): Promise<T | null> => {
    const ac = new AbortController();
    abortRef.current = ac;
    startedAtRef.current = Date.now();
    setState({ ...IDLE, running: true });

    let result: T | null = null;
    try {
      await streamSse<ServerEvent>(
        apiUrl(path),
        { method: "POST", ...init },
        (ev) => {
          if ("steps" in ev) {
            // 선언 이벤트 — 아직 안 온 단계까지 회색으로 미리 그린다.
            setState((s) => ({
              ...s,
              steps: ev.steps.map((d) => ({ key: d.key, label: d.label, status: "wait" })),
            }));
            return;
          }
          if ("result" in ev) {
            result = ev.result as T;
            return;
          }
          if (!("step" in ev)) {
            // 단계에 붙지 않은 전역 에러.
            setState((s) => ({ ...s, error: ev.error }));
            return;
          }

          const next = SERVER_TO_VIEW[ev.status] ?? "run";
          const tokens = Number(ev.detail?.tokens ?? 0);
          setState((s) => ({
            ...s,
            tokens: s.tokens + (ev.status === "done" && Number.isFinite(tokens) ? tokens : 0),
            error: ev.status === "error" ? (ev.error ?? "작업에 실패했어요.") : s.error,
            steps: s.steps.map((st) =>
              st.key === ev.step
                ? { ...st, status: next, ms: ev.ms ?? st.ms, detail: ev.detail ?? st.detail }
                : st,
            ),
          }));
        },
        ac.signal,
      );
    } catch (e) {
      // 사용자가 백그라운드로 두면 abort 가 뜬다 — 실패가 아니다.
      if ((e as Error)?.name !== "AbortError") {
        setState((s) => ({ ...s, running: false, error: "작업 중 연결이 끊겼어요." }));
      }
      return null;
    }
    setState((s) => ({ ...s, running: false }));
    return result;
  }, []);

  return { state, run, detach };
}
