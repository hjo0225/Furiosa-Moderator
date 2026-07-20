import type { Config } from "tailwindcss";

const PRETENDARD = [
  "Pretendard Variable",
  "Pretendard",
  "-apple-system",
  "BlinkMacSystemFont",
  "system-ui",
  "Apple SD Gothic Neo",
  "Malgun Gothic",
  "sans-serif",
];

// 단일 서체 정책 — 전 영역 Pretendard. font-mono(메타·수치 라벨)도 Pretendard 로 렌더(자간/대문자 스타일만 유지).
const MONO = PRETENDARD;

/**
 * MindLens 디자인 시스템 — DESIGN.md SSOT.
 * Indigo-tinted neutral (Linear/Vercel류 monochrome). 단일 라이트 스킴.
 * 색상 토큰은 DESIGN.md §1-1 과 1:1 매핑.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── DESIGN.md 정식 토큰 (Optimal Workshop 팔레트) ──
        // 구 indigo 복구용 값(주석): indigo #4F46E5/#4338CA/#eef2ff · violet #8B5CF6 · bg #f5f7ff
        // · ink #1e1b4b/#4b5168/#9ca3af · clay #4F46E5 · line/border #e0e4f0 · go/pivot #10b981/#f59e0b
        indigo: { DEFAULT: "#00A4DF", hover: "#0090C4", light: "#E5F2F6" }, // alias명 유지 → sky-blue
        violet: { DEFAULT: "#4785FF", hover: "#3A6FE0", light: "#E5F2F6" }, // → OW blue
        bg: "#fcfcfc",
        surface: "#ffffff",
        slate: "#25353F", // 다크 밴드(CTA)·Review 솔리드 버튼
        border: { DEFAULT: "#e6e6e6" },
        success: "#00AA64",
        warning: "#F18134",
        error: "#ef4444",

        // ── 호환 alias (기존 paper/ink/clay 클래스를 OW 팔레트로 리맵) ──
        ink: { DEFAULT: "#0D0D0D", soft: "#454545", faint: "#8a8a8a" },
        // 표면 토큰
        paper: { DEFAULT: "#fcfcfc", deep: "#ffffff", dim: "#f3f3f3" },
        // 액센트 토큰 (alias → sky/blue)
        clay: { DEFAULT: "#00A4DF", deep: "#0090C4", soft: "#4785FF", wash: "#E5F2F6" },
        // 서브브랜드 액센트 — CSS 변수(--accent*). 기본=sky, .theme-* 가 솔루션별 색 치환.
        // (DESIGN.md §1-1-a SSOT. ProductShell·솔루션 페이지가 컨텍스트에 테마 클래스 부여)
        // color-mix + <alpha-value>: var() 색상은 Tailwind v3 가 알파를 계산할 수 없어
        // bg-accent-solid/80 같은 modifier 클래스가 아예 생성되지 않는다(투명 렌더 버그).
        accent: {
          DEFAULT: "color-mix(in srgb, var(--accent) calc(<alpha-value> * 100%), transparent)",
          deep: "color-mix(in srgb, var(--accent-deep) calc(<alpha-value> * 100%), transparent)",
          soft: "color-mix(in srgb, var(--accent-soft) calc(<alpha-value> * 100%), transparent)",
          wash: "color-mix(in srgb, var(--accent-wash) calc(<alpha-value> * 100%), transparent)",
          solid: "color-mix(in srgb, var(--accent-solid) calc(<alpha-value> * 100%), transparent)", // 채운 버튼 배경
          on: "color-mix(in srgb, var(--accent-on) calc(<alpha-value> * 100%), transparent)", // 채운 버튼 위 글자색
        },
        // 라인
        line: { DEFAULT: "#e6e6e6", soft: "#f3f3f3" },
        // verdict (= success/warning/error)
        go: "#00AA64",
        pivot: "#F18134",
        nogo: "#ef4444",
      },
      fontFamily: {
        sans: PRETENDARD,
        serif: PRETENDARD, // 호환용 — 실제 serif 없음 (Pretendard)
        display: PRETENDARD,
        mono: MONO,
      },
      fontSize: {
        // DESIGN.md §1-2 — 참고사이트 타이포 "시스템" 차용(색·폰트 제외).
        // 시그니처: 거대하고 얇은(400) 타이트한 제목 + 작고 자간 넓은 본문.
        // weight 를 토큰에 내장 → text-hero/display/title 은 앱 전역에서 자동으로 light/medium.
        "2xs": ["0.625rem", { lineHeight: "1.4", letterSpacing: "0.04em" }],
        meta: ["0.8125rem", { lineHeight: "1.5", letterSpacing: "0.02em" }],
        base: ["1rem", { lineHeight: "1.65", letterSpacing: "0.01em" }],
        lead: ["1.1875rem", { lineHeight: "1.6", letterSpacing: "0.005em" }],
        title: ["1.75rem", { lineHeight: "1.2", letterSpacing: "-0.015em", fontWeight: "600" }],
        score: ["3rem", { lineHeight: "1", letterSpacing: "-0.02em", fontWeight: "600" }],
        // OW 실측(2026-06): h1 100px·w400·lh 1.0·ls -1px(-0.01em). hero 를 실측에 정합,
        // display 도 w400 으로 — "거대하고 얇은" 시그니처 강화.
        display: ["3.25rem", { lineHeight: "1.05", letterSpacing: "-0.02em", fontWeight: "400" }],
        // 좁은 컨테이너(max-w-2xl 인트로 히어로)용 중간 단계 — hero(100px)는 풀폭 랜딩 전용.
        headline: ["4rem", { lineHeight: "1.04", letterSpacing: "-0.02em", fontWeight: "400" }],
        hero: ["6.25rem", { lineHeight: "1.0", letterSpacing: "-0.01em", fontWeight: "400" }],
      },
      borderRadius: {
        sm: "0.125rem", // 2px — 배지
        DEFAULT: "0.5rem", // 8px — 버튼/입력/카드
        lg: "0.5rem",
        xl: "0.75rem", // 12px — 차트 카드/모달
      },
      boxShadow: {
        // 참고사이트 = 플랫 카드(그림자 거의 없음). 카드는 border 의존, 그림자는 미세하게만.
        card: "0 1px 2px rgba(13,13,13,0.03)",
        elevated: "0 4px 16px rgba(13,13,13,0.06)",
        // 호환 별칭 (기존 코드용)
        soft: "0 1px 2px rgba(13,13,13,0.03)",
        lift: "0 4px 16px rgba(13,13,13,0.06)",
        // 서브브랜드 액센트를 따르는 inset 링 (Validate=민트, Review/플랫폼=인디고)
        edge: "inset 0 0 0 1px color-mix(in srgb, var(--accent) 16%, transparent)",
      },
      maxWidth: { content: "76rem", prose: "42rem" },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(14px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "draw-line": { from: { transform: "scaleX(0)" }, to: { transform: "scaleX(1)" } },
        "pulse-indigo": {
          "0%,100%": { boxShadow: "0 0 0 0 rgba(0,164,223,0.0)" },
          "50%": { boxShadow: "0 0 0 6px rgba(0,164,223,0.14)" },
        },
        // 무한 마퀴 — 트랙을 동일 그룹 2개로 구성하고 한 그룹 폭(-50%)만큼 이동 → 끊김 없는 루프
        marquee: {
          from: { transform: "translateX(0)" },
          to: { transform: "translateX(-50%)" },
        },
        // 라이브 타이핑/대기 인디케이터 점 — 부드러운 펄스(불투명도+살짝 솟음). reduced-motion 시 전역 블록이 정지.
        "dot-pulse": {
          "0%,100%": { opacity: "0.35", transform: "translateY(0)" },
          "50%": { opacity: "1", transform: "translateY(-2px)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.7s cubic-bezier(0.16,1,0.3,1) both",
        "fade-in": "fade-in 0.8s ease both",
        "draw-line": "draw-line 0.9s cubic-bezier(0.16,1,0.3,1) both",
        "pulse-indigo": "pulse-indigo 2.4s ease-in-out infinite",
        "dot-pulse": "dot-pulse 1.2s ease-in-out infinite",
        marquee: "marquee 28s linear infinite",
      },
    },
  },
  plugins: [],
};
export default config;
