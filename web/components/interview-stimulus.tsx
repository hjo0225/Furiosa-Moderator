"use client";

import type { Stimulus } from "@/lib/api";

// 질문에 붙는 제시 자료. 이미지/영상만. 접근성: 이미지는 caption 을 alt 로.
export function InterviewStimulus({ stimulus }: { stimulus: Stimulus }) {
  return (
    <figure className="flex h-full flex-col gap-2">
      <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-2xl border border-warm-border bg-blush">
        {stimulus.type === "image" ? (
          <img
            src={stimulus.url}
            alt={stimulus.caption ?? "제시 자료"}
            className="max-h-full max-w-full object-contain"
          />
        ) : (
          <video src={stimulus.url} controls className="max-h-full max-w-full" />
        )}
      </div>
      {stimulus.caption && (
        <figcaption className="text-center text-2xs text-warm-ink-soft">{stimulus.caption}</figcaption>
      )}
    </figure>
  );
}
