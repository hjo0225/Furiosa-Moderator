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
 * MindLens 디자인 시스템 — design.md SoT (Furiosa 팔레트, 2026-07-23 리디자인).
 * 색상 토큰은 design.md §1 과 1:1 매핑. 기존 클래스명(ink/paper/clay/accent/line/go/pivot/nogo 등)은
 * 유지하고 값만 Furiosa 로 리맵한다 — 컴포넌트는 이 태스크에서 손대지 않는다(점진 교체 전략).
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── Furiosa 브랜드 코어 (design.md §1 실측) — 신규 토큰명. 후속 태스크가 직접 참조. ──
        red: { DEFAULT: "#E21500", dark: "#BC1302" },
        obsidian: "#151515",
        charcoal: "#444444",
        grey: "#7F7F7F",
        silver: "#D4D4D4",
        platinum: "#E1E1E1",
        canvas: "#FFFFFF",
        // 응답자 웜 표면
        cream: "#FFFBF6",
        blush: "#FFF3EE",
        "warm-border": "#F0E6DC",
        "warm-ink-soft": "#8A6F5F",
        // 시맨틱 — 액센트(red)와 분리, 카운트로 세지 않는 상태색(design.md §1)
        maroon: "#6F2020",
        // 데이터 · 바이브런트 (차트/센티먼트 카테고리 — furiosa.ai 실측, design.md §1)
        mint: "#70E697",
        cyan: "#76D6FF",
        peach: "#FEC2A0",
        lilac: "#CDBBFF",
        lemon: "#FFFA82",
        orange: "#FF9A52",

        // ── 호환 alias (기존 클래스명 유지, 값만 Furiosa 로 리맵) ──
        indigo: { DEFAULT: "#E21500", hover: "#BC1302", light: "#FBEBE9" }, // 구 sky-blue alias → red
        bg: "#FFFFFF", // → canvas
        surface: "#FFFFFF", // → canvas
        slate: "#151515", // 다크 밴드(CTA)·Review 솔리드 버튼 → obsidian
        border: { DEFAULT: "#E1E1E1" }, // → platinum
        success: "#00AA64",
        warning: "#FF9A52", // design.md §1 시맨틱 warning = orange 실측치
        error: "#6F2020", // design.md §1: brand-red 와 충돌 방지 위해 maroon. 구 #ef4444 폐기

        ink: { DEFAULT: "#151515", soft: "#444444", faint: "#7F7F7F" }, // → obsidian/charcoal/grey
        // 표면 토큰
        paper: { DEFAULT: "#FAF9F7", deep: "#FFFFFF", dim: "#E1E1E1" }, // → paper/canvas/platinum
        // 액센트 토큰 (alias → red)
        clay: { DEFAULT: "#E21500", deep: "#BC1302", soft: "#FEC2A0", wash: "#FBEBE9" },
        // 서브브랜드 액센트 — CSS 변수(--accent*). design.md §0: 서브테마 폐기, 항상 red.
        // (.theme-* 는 하위호환용으로 남아있지만 전부 동일한 red 값으로 통일됨 — globals.css 참고)
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
        // 라인 — design.md §3: 1px silver/platinum 헤어라인
        line: { DEFAULT: "#D4D4D4", soft: "#E1E1E1" },
        // verdict (= success/warning/error)
        go: "#00AA64",
        pivot: "#FF9A52",
        nogo: "#6F2020",
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
        DEFAULT: "0.5rem", // 8px — 버튼/입력/카드 (design.md §3, 유지)
        lg: "0.5rem",
        card: "0.625rem", // 10px — 의뢰자 카드 <Card> 전용 토큰(design.md §3)
        xl: "0.875rem", // 14px — 응답자(웜) 카드. design.md §3: 웜 카드 12–16px 범위 중간값
      },
      boxShadow: {
        // 참고사이트 = 플랫 카드(그림자 거의 없음). 카드는 border 의존, 그림자는 미세하게만.
        card: "0 1px 2px rgba(13,13,13,0.03)",
        elevated: "0 4px 16px rgba(13,13,13,0.06)",
        // 호환 별칭 (기존 코드용)
        soft: "0 1px 2px rgba(13,13,13,0.03)",
        lift: "0 4px 16px rgba(13,13,13,0.06)",
        // accent(red) 기반 inset 링. design.md §0: 서브테마 폐기, 단일 red.
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
        // 미사용(alias명 유지) — 구 sky-blue 펄스 → red 로 리맵. 인터뷰 진행자 오브 등 후속 태스크가 재사용 가능.
        "pulse-indigo": {
          "0%,100%": { boxShadow: "0 0 0 0 rgba(226,21,0,0.0)" },
          "50%": { boxShadow: "0 0 0 6px rgba(226,21,0,0.14)" },
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
