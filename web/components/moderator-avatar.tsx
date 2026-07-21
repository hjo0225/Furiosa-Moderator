"use client";

// 진행자 아바타 — 목소리 크기에 반응하는 오브. useTts 의 getLevel(0~1) 을 rAF 로 매 프레임
// 읽어 CSS 변수 --level 에 쓴다(React 리렌더 없이 DOM 직접 갱신). 색은 테마 토큰(--accent)을 따른다.
// prefers-reduced-motion 이면 진폭 구동을 끈다(전역 CSS 도 애니메이션을 죽인다).
//
// 지금은 단순 오브지만, 진짜 '말하는 아바타'로 바꿀 때도 배선은 동일하다 — speaking/getLevel 만
// 그대로 받아 그림만 교체하면 된다.
import { useEffect, useRef } from "react";

export function ModeratorAvatar({
  speaking,
  getLevel,
}: {
  speaking: boolean;
  getLevel: () => number;
}) {
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (!speaking || reduce) {
      root.style.setProperty("--level", "0");
      return;
    }
    let raf = 0;
    const tick = () => {
      root.style.setProperty("--level", getLevel().toFixed(3));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [speaking, getLevel]);

  return (
    <div
      ref={rootRef}
      className={`mod-orb${speaking ? " is-speaking" : ""}`}
      aria-hidden
    >
      <span className="mod-orb__ring mod-orb__ring--2" />
      <span className="mod-orb__ring mod-orb__ring--1" />
      <span className="mod-orb__core" />
      <style>{`
        .mod-orb {
          --level: 0;
          position: relative;
          display: grid;
          place-items: center;
          width: 100%;
          max-width: 200px;
          aspect-ratio: 1;
          margin: 0 auto;
        }
        .mod-orb__core,
        .mod-orb__ring {
          position: absolute;
          border-radius: 9999px;
          transform-origin: center;
        }
        .mod-orb__core {
          width: 46%;
          height: 46%;
          background: var(--accent-solid);
          box-shadow: 0 10px 34px color-mix(in srgb, var(--accent) 45%, transparent);
          transform: scale(calc(1 + var(--level) * 0.18));
          transition: transform 70ms linear;
          animation: mod-breath 3.4s ease-in-out infinite;
        }
        .mod-orb.is-speaking .mod-orb__core {
          animation: none; /* 말하는 동안엔 진폭이 대신 구동 */
        }
        .mod-orb__ring {
          border: 2px solid var(--accent);
        }
        .mod-orb__ring--1 {
          width: 64%;
          height: 64%;
          opacity: calc(0.14 + var(--level) * 0.72);
          transform: scale(calc(1 + var(--level) * 0.34));
          transition: opacity 70ms linear, transform 70ms linear;
        }
        .mod-orb__ring--2 {
          width: 84%;
          height: 84%;
          opacity: calc(0.05 + var(--level) * 0.48);
          transform: scale(calc(1 + var(--level) * 0.52));
          transition: opacity 90ms linear, transform 90ms linear;
        }
        @keyframes mod-breath {
          0%, 100% { transform: scale(1); }
          50% { transform: scale(1.04); }
        }
        @media (prefers-reduced-motion: reduce) {
          .mod-orb__core { animation: none; transition: none; }
          .mod-orb__ring { transition: none; }
        }
      `}</style>
    </div>
  );
}
