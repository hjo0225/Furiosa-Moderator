"use client";

// 인터뷰 전사 뷰어 (C-4).
// [이식 수정] 원본 response-viewer.tsx 에서 **전사 렌더 블록(L163-186)만** 남겼다. 제거한 것:
//  · 6-Lens 소비자 에이전트 생성(L51-64, L155-162) — 이 제품에 없는 기능
//  · 답변별 관리자 메모 저장(L93-104) — MVP 범위 밖
//  · 문항 단위 그룹핑(groupAnswersByQuestion) — 인터뷰는 문항-답변이 아니라 대화라 성립하지 않는다
// 추가한 것: 감정 태그(M-3)·꼬리질문·PII 마스킹 배지 — 새 Turn 스키마가 주는 정보라 버리면 아깝다.

import { cn } from "@/lib/utils";
import type { Turn } from "@/lib/api";

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return ""; // 잘못된 날짜 문자열 → NaN:NaN 표시 방지
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function TranscriptView({ turns }: { turns: Turn[] }) {
  if (turns.length === 0) {
    return <p className="text-meta text-ink-soft">아직 대화 기록이 없어요.</p>;
  }

  return (
    <div className="space-y-2">
      {turns.map((t, i) => (
        <div key={t.id || i} className={t.role === "respondent" ? "text-right" : "text-left"}>
          <span
            className={cn(
              "inline-block max-w-[85%] rounded-xl px-3 py-2 text-meta leading-relaxed",
              t.role === "respondent"
                ? "bg-accent-wash text-ink"
                : "bg-bg text-ink-soft ring-1 ring-line",
            )}
          >
            <span className="font-mono text-2xs text-ink-faint">
              {t.role === "moderator" ? "진행자" : "응답자"}
              {t.created_at ? ` · ${formatTime(t.created_at)}` : ""} ·{" "}
            </span>
            {t.text}
          </span>
          <div
            className={cn(
              "mt-1 flex flex-wrap gap-1.5",
              t.role === "respondent" ? "justify-end" : "justify-start",
            )}
          >
            {t.emotion && (
              <span className="rounded-sm bg-accent-wash px-1.5 py-0.5 font-mono text-2xs text-accent">
                {t.emotion}
                {t.emotion_confidence > 0 && ` ${Math.round(t.emotion_confidence * 100)}%`}
              </span>
            )}
            {t.is_probe && (
              <span className="rounded-sm bg-paper-dim px-1.5 py-0.5 font-mono text-2xs text-ink-faint">
                꼬리질문
              </span>
            )}
            {t.guardrail_rewritten && (
              <span className="rounded-sm bg-pivot/10 px-1.5 py-0.5 font-mono text-2xs text-pivot">
                중립성 교정됨
              </span>
            )}
            {t.pii_types?.length > 0 && (
              <span className="rounded-sm bg-nogo/10 px-1.5 py-0.5 font-mono text-2xs text-nogo">
                마스킹: {t.pii_types.join(", ")}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
