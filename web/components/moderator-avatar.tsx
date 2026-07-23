"use client";

// 진행자 아바타 — 웜 오브(peach→red 라디얼, design.md §5 "인터뷰(응답자, 웜)"). 말하는 동안
// **실제 목소리 진폭으로** 오브가 출렁여 "지금 말하고 있다"를 화면에 보여준다. 이모지 아님(§4).
//
// getLevel 이 있으면(useTts().getLevel) rAF 루프로 매 프레임 진폭을 읽어 scale·글로우를
// 실시간 구동한다. 없으면(또는 reduced-motion) 고정 맥동(.animate-moderator-pulse)으로 폴백.
//
// prefers-reduced-motion: CSS animation 은 globals.css 전역 규칙이 끄지만 rAF 는 못 끄므로
// 이 컴포넌트 안에서 matchMedia 로 직접 확인해 진폭 루프를 돌리지 않는다(정적 오브로 폴백).
//
// 순수 장식 그래픽이라 aria-hidden — 실제 레이블은 이 컴포넌트를 쓰는 쪽의 인접 텍스트가 맡는다.
import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

export function ModeratorAvatar({
  speaking = false,
  size = 40,
  getLevel,
}: {
  /** 진행자가 말하는 중인가 — true 면 오브가 반응한다. */
  speaking?: boolean;
  /** 오브 지름(px). */
  size?: number;
  /** 현재 재생 음량 0~1(useTts().getLevel). 있으면 진폭 구동, 없으면 고정 맥동. */
  getLevel?: () => number;
}) {
  const orbRef = useRef<HTMLSpanElement | null>(null);
  const glowRef = useRef<HTMLSpanElement | null>(null);
  const rafRef = useRef<number | null>(null);

  const reduced =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  // 진폭 구동 — speaking && getLevel && !reduced 일 때만 rAF 루프를 돈다.
  const amplitudeDriven = speaking && !!getLevel && !reduced;

  useEffect(() => {
    if (!amplitudeDriven || !getLevel) return;
    let alive = true;
    // 부드럽게 따라가도록 지수 평활(급격한 떨림 방지).
    let smooth = 0;
    const tick = () => {
      if (!alive) return;
      const level = getLevel(); // 0~1
      smooth += (level - smooth) * 0.35;
      const scale = 1 + smooth * 0.14; // 최대 +14%
      if (orbRef.current) orbRef.current.style.transform = `scale(${scale.toFixed(3)})`;
      if (glowRef.current) {
        const spread = 6 + smooth * 18;
        const alpha = (0.22 + smooth * 0.4).toFixed(3);
        glowRef.current.style.boxShadow = `0 2px ${spread.toFixed(0)}px rgba(226, 21, 0, ${alpha})`;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      alive = false;
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      // 루프 종료 시 원상 복구
      if (orbRef.current) orbRef.current.style.transform = "";
      if (glowRef.current) glowRef.current.style.boxShadow = "";
    };
  }, [amplitudeDriven, getLevel]);

  return (
    <span
      aria-hidden="true"
      className="relative inline-flex shrink-0 items-center justify-center rounded-full"
      style={{ width: size, height: size }}
    >
      {/* 소프트 링 — 오브 밖으로 은은하게 번지는 테두리(design.md §5: 압도하지 않게) */}
      <span
        className={cn(
          "absolute inset-0 rounded-full ring-2 transition-colors duration-300",
          speaking ? "ring-red/35" : "ring-red/15",
        )}
      />
      {/* 오브 본체 — peach→red 라디얼. 진폭 구동이면 rAF 가 transform 을 세팅, 아니면 CSS 맥동 폴백. */}
      <span
        ref={(el) => {
          orbRef.current = el;
          glowRef.current = el;
        }}
        className={cn(
          "absolute inset-[3px] rounded-full will-change-transform",
          speaking && !amplitudeDriven && "animate-moderator-pulse",
        )}
        style={{
          background: "radial-gradient(circle at 38% 32%, #FEC2A0, #E21500 90%)",
          boxShadow: "0 2px 10px rgba(226, 21, 0, 0.22)",
        }}
      />
    </span>
  );
}
