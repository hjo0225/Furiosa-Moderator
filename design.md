# Boram 디자인 시스템 스펙

> 라이트 캔버스 기반 디자인 시스템. 흰 캔버스 + navy ink + 단일 electric blue 액센트,
> 넉넉한 여백과 soft-rounded 카드가 특징이다.
> **Boram은 이 시스템의 토큰을 채택했다** — 적용 현황과 의도적 차이는 아래 참고.

## Boram 적용 노트

토큰(색·타이포·radii·spacing)은 `apps/web/app/globals.css`의 `@theme`에 반영돼 있다.
값을 고칠 때는 이 문서가 아니라 **`globals.css`가 SSOT**다(이 문서는 스펙 보존용).

**의도적으로 원본과 다르게 간 것 3가지** — 근거는 `globals.css` 상단 주석에 있다.

| # | 원본 | Boram | 이유 |
|---|------|-------|------|
| 1 | 원본 스펙의 독점 sans | **Pretendard** | 원본 서체는 독점이고 한글이 없다. 이 문서가 스스로 "Inter-class geometric grotesque"라 밝히는데 Pretendard가 그 계열의 한글 지원 폰트다 |
| 2 | `rounded.lg = 14px` | 이름 유지, 값만 한 칸씩 상향 | 원본의 `lg`(14px)를 그대로 넣으면 코드 전체의 `rounded-lg`가 말없이 의미가 달라진다(기존 10px). 리네임 0건으로 "soft-rounded 10–20px" 무드를 얻는다 |
| 3 | `typography.body = 16px` | 앱 기본 **14px/1.6** | 원본 body 16px는 마케팅 여백을 전제한다. Boram 앱은 데이터 밀도가 높고, 한글은 14px가 본문 하한선이다(13px는 가독성이 급격히 나빠진다) |

**⚠️ 적용 범위 주의** — 아래 `components:` 섹션은 **전부 마케팅 사이트 컴포넌트**다
(top-nav · hero-media-frame · feature-card · stat-card · testimonial-card · cta-band · footer …).
Boram 앱 13개 화면이 쓰는 sidebar · modal · table · tabs · toast · chip 등의 스펙은 **여기 없다**.
그래서 앱은 **기존 컴포넌트 구조를 유지하고 토큰만 갈아입혔다.** 랜딩 페이지만 이 컴포넌트
스펙을 실제로 따른다.

## 디자인 토큰

```yaml
description: "A bright, friendly light-canvas B2B SaaS marketing system built on a pure white canvas (#ffffff), near-black navy ink (#0b1220), and a single confident electric royal blue (#2c5cff) — 'Primary Blue' — carried on primary CTAs, links, active tabs, and the brand mark. The mood is optimistic-professional 'revenue software that people love': generous whitespace, soft-rounded cards (10–20px), thin neutral hairlines, and full-bleed product UI screenshots framed in light panels. Section rhythm alternates a white canvas with a very light blue-gray band (#f6f8fc) to separate feature stories, and closes on an inverse near-navy CTA band. Type is set in a modern geometric grotesque (Inter-class fallback) at 600–700 for headlines with tight negative tracking, dropping to 400 for body. A secondary AI-indigo (#6d5ef6) appears only on AI/agent surfaces (AI/agent surfaces). One vivid green (#12a150) marks positive proof-points (+25% win rate). The system reads warm and human — rounded corners, emoji social proof (💙), and a playful blue mascot — while staying enterprise-credible via security/compliance badges and clean data-dense screenshots."

colors:
  primary: "#2c5cff"
  on-primary: "#ffffff"
  primary-hover: "#1e4de0"
  primary-pressed: "#1840bd"
  primary-focus: "#2c5cff"
  primary-subtle: "#eaf0ff"
  primary-subtle-2: "#dbe6ff"
  primary-border: "#c3d4ff"
  ai-indigo: "#6d5ef6"
  ai-indigo-subtle: "#efedff"
  ink: "#0b1220"
  ink-muted: "#39415a"
  ink-subtle: "#5b6478"
  ink-tertiary: "#8a93a6"
  ink-disabled: "#b4bccb"
  canvas: "#ffffff"
  surface-1: "#f6f8fc"
  surface-2: "#eef1f8"
  surface-3: "#e5e9f2"
  surface-inverse: "#0b1220"
  surface-inverse-2: "#141b2e"
  on-inverse: "#ffffff"
  on-inverse-muted: "#aab2c5"
  hairline: "#e7eaf1"
  hairline-strong: "#d6dbe6"
  hairline-inverse: "#232b40"
  semantic-success: "#12a150"
  semantic-success-subtle: "#e6f6ed"
  semantic-warning: "#e0951b"
  semantic-danger: "#e5484d"
  overlay: "#0b1220"

typography:
  display-xl:
    fontFamily: Pretendard
    fontSize: 72px
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: -2.4px
  display-lg:
    fontFamily: Pretendard
    fontSize: 56px
    fontWeight: 700
    lineHeight: 1.08
    letterSpacing: -1.8px
  display-md:
    fontFamily: Pretendard
    fontSize: 40px
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: -1.2px
  headline:
    fontFamily: Pretendard
    fontSize: 32px
    fontWeight: 600
    lineHeight: 1.18
    letterSpacing: -0.8px
  section-title:
    fontFamily: Pretendard
    fontSize: 26px
    fontWeight: 600
    lineHeight: 1.22
    letterSpacing: -0.5px
  card-title:
    fontFamily: Pretendard
    fontSize: 20px
    fontWeight: 600
    lineHeight: 1.30
    letterSpacing: -0.3px
  subhead:
    fontFamily: Pretendard
    fontSize: 19px
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: -0.1px
  body-lg:
    fontFamily: Pretendard
    fontSize: 18px
    fontWeight: 400
    lineHeight: 1.60
    letterSpacing: 0
  body:
    fontFamily: Pretendard
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.60
    letterSpacing: 0
  body-sm:
    fontFamily: Pretendard
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: 0
  caption:
    fontFamily: Pretendard
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: 0
  button:
    fontFamily: Pretendard
    fontSize: 15px
    fontWeight: 600
    lineHeight: 1.20
    letterSpacing: -0.1px
  eyebrow:
    fontFamily: Pretendard
    fontSize: 13px
    fontWeight: 600
    lineHeight: 1.30
    letterSpacing: 0.6px
  stat:
    fontFamily: Pretendard
    fontSize: 44px
    fontWeight: 700
    lineHeight: 1.0
    letterSpacing: -1.4px
  mono:
    fontFamily: mono
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: 0

rounded:
  xs: 6px
  sm: 8px
  md: 10px
  lg: 14px
  xl: 20px
  xxl: 28px
  pill: 9999px
  full: 9999px

spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
  xxl: 48px
  xxxl: 72px
  section: 120px

components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button}"
    rounded: "{rounded.sm}"
    padding: 12px 20px
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button}"
    rounded: "{rounded.sm}"
    padding: 12px 20px
  button-primary-pressed:
    backgroundColor: "{colors.primary-pressed}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button}"
    rounded: "{rounded.sm}"
    padding: 12px 20px
  button-secondary:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.sm}"
    padding: 12px 20px
  button-secondary-hover:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.sm}"
    padding: 12px 20px
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-muted}"
    typography: "{typography.button}"
    rounded: "{rounded.sm}"
    padding: 12px 16px
  button-inverse:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.sm}"
    padding: 12px 20px
  top-nav:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.xs}"
    height: 68px
  mega-menu:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.lg}"
    padding: 24px
  hero-media-frame:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.xl}"
    padding: 16px
  feature-card:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.lg}"
    padding: 28px
  product-screenshot-card:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.xl}"
    padding: 24px
  stat-card:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.ink}"
    typography: "{typography.stat}"
    rounded: "{rounded.lg}"
    padding: 28px
  testimonial-card:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-lg}"
    rounded: "{rounded.lg}"
    padding: 28px
  logo-tile:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink-subtle}"
    typography: "{typography.caption}"
    rounded: "{rounded.xs}"
    padding: 16px 24px
  product-tab-default:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.ink-subtle}"
    typography: "{typography.button}"
    rounded: "{rounded.pill}"
    padding: 8px 18px
  product-tab-selected:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button}"
    rounded: "{rounded.pill}"
    padding: 8px 18px
  ai-prompt-chip:
    backgroundColor: "{colors.ai-indigo-subtle}"
    textColor: "{colors.ai-indigo}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.pill}"
    padding: 8px 14px
  ai-panel:
    backgroundColor: "{colors.surface-inverse}"
    textColor: "{colors.on-inverse}"
    typography: "{typography.body}"
    rounded: "{rounded.xl}"
    padding: 32px
  template-card:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.lg}"
    padding: 20px
  integration-card:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.lg}"
    padding: 24px
  security-badge:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.ink-muted}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.md}"
    padding: 16px 20px
  proof-pill:
    backgroundColor: "{colors.semantic-success-subtle}"
    textColor: "{colors.semantic-success}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.pill}"
    padding: 4px 12px
  category-tab:
    backgroundColor: "transparent"
    textColor: "{colors.ink-subtle}"
    typography: "{typography.button}"
    rounded: "{rounded.pill}"
    padding: 8px 16px
  text-input:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: 12px 14px
  text-input-focused:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: 12px 14px
  cta-band:
    backgroundColor: "{colors.surface-inverse}"
    textColor: "{colors.on-inverse}"
    typography: "{typography.headline}"
    rounded: "{rounded.xxl}"
    padding: 64px
  footer:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink-subtle}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.xs}"
    padding: 72px 32px
```

---

## Overview

The marketing canvas is a **pure white surface** (`{colors.canvas}` #ffffff) carrying near-black navy ink (`{colors.ink}` #0b1220). It is the opposite of a dark developer tool: bright, spacious, and human. Hierarchy is built by alternating the white canvas with a **very light blue-gray band** (`{colors.surface-1}` #f6f8fc) that separates each feature story, and by lifting content into soft-rounded cards with thin neutral hairlines (`{colors.hairline}` #e7eaf1).

The single chromatic anchor is **Primary Blue** `{colors.primary}` (#2c5cff) — a confident electric royal blue used on the primary CTA ("Start for Free →"), text links, the active product tab, form focus, and the brand mark. It darkens to `{colors.primary-hover}` (#1e4de0) on hover and `{colors.primary-pressed}` (#1840bd) when pressed, and thins to `{colors.primary-subtle}` (#eaf0ff) for tinted highlight backgrounds. Blue is used with restraint — it signals action and brand, never fills whole sections.

A **secondary AI-indigo** `{colors.ai-indigo}` (#6d5ef6) is reserved exclusively for AI/agent surfaces — AI surface, the AI 에이전트 표면, AI prompt chips — so "the AI part" reads as its own quiet sub-language rather than a competing brand color. One **proof green** `{colors.semantic-success}` (#12a150) marks quantified wins (+25% win rate, +22% deals closed) so numbers pop without shouting.

The page rhythm is **product UI screenshots as the protagonist.** Every feature section (per product feature) leads with a high-fidelity product capture framed in a light `{colors.surface-1}` panel with `{rounded.xl}` 20px corners. Marketing chrome stays deliberately light so the screenshots do the persuading. Social proof is warm and literal — an emoji-tabbed social-proof section (💙 / 💰 / 🧠 / 🤝) with quote cards and a friendly blue mascot. The page closes on an **inverse near-navy CTA band** (`{colors.surface-inverse}` #0b1220), the one moment the system goes dark.

**Key Characteristics:**
- **Light-canvas marketing system** — `{colors.canvas}` (#ffffff) is the anchor; the dark CTA band is the single inversion.
- **One electric-blue accent** (`{colors.primary}` #2c5cff) for CTAs, links, active tabs, brand, and mascot — used scarcely, never as a section fill.
- **AI-indigo sub-language** (`{colors.ai-indigo}` #6d5ef6) isolated to AI surface / agent surfaces.
- **Alternating white ↔ #f6f8fc bands** carry section rhythm instead of borders or shadows.
- Cards use `{rounded.lg}` 14px – `{rounded.xl}` 20px soft corners with 1px `{colors.hairline}` borders and low-blur shadows.
- **Product UI screenshots dominate** every feature story; chrome is a light frame for the app.
- **Warm human proof** — emoji social proof, a friendly mascot, green proof pills — balanced by trust/compliance badges.

## Colors

> Source pages: 원본 마케팅 사이트 (home), and the observable brand system across /pricing, /product/*, /solutions/*, /templates. Values are curated from publicly observable patterns (see Known Gaps).

### Brand & Accent
- **Primary Blue** ({colors.primary}): The signature accent — primary CTA, text links, active product tab, form focus ring, brand mark (#2c5cff).
- **Blue Hover** ({colors.primary-hover}): One step darker (#1e4de0) — hovered primary CTA and links.
- **Blue Pressed** ({colors.primary-pressed}): Deepest state (#1840bd) — active/pressed CTA.
- **Blue Subtle** ({colors.primary-subtle}): Pale tint (#eaf0ff) — highlighted callout backgrounds, selected-row wash, icon chips.
- **Blue Subtle 2** ({colors.primary-subtle-2}): Slightly deeper tint (#dbe6ff) — hovered subtle surfaces, chart fills.
- **Blue Border** ({colors.primary-border}): (#c3d4ff) — 1px border on tinted callouts and selected cards.

### AI Surfaces
- **AI Indigo** ({colors.ai-indigo}): Reserved for AI/agent moments only (#6d5ef6) — AI surface accents, agent surfaces, prompt-chip text.
- **AI Indigo Subtle** ({colors.ai-indigo-subtle}): Pale indigo (#efedff) — AI prompt chip fill, AI callout wash.

### Surface
- **Canvas** ({colors.canvas}): Default page background — pure white #ffffff.
- **Surface 1** ({colors.surface-1}): The alternating light blue-gray section band (#f6f8fc) — also the fill behind product-screenshot frames.
- **Surface 2** ({colors.surface-2}): One step deeper (#eef1f8) — inactive tab pills, nested tiles, table zebra.
- **Surface 3** ({colors.surface-3}): (#e5e9f2) — pressed tiles, deeper nesting.
- **Surface Inverse** ({colors.surface-inverse}): Near-navy (#0b1220) — the closing CTA band and AI panels.
- **Surface Inverse 2** ({colors.surface-inverse-2}): (#141b2e) — lifted cards inside inverse sections.
- **Hairline** ({colors.hairline}): 1px card borders and dividers on light (#e7eaf1).
- **Hairline Strong** ({colors.hairline-strong}): Stronger 1px borders / input outlines (#d6dbe6).
- **Hairline Inverse** ({colors.hairline-inverse}): 1px borders inside inverse sections (#232b40).

### Text
- **Ink** ({colors.ink}): Headlines and emphasized body — near-black navy #0b1220.
- **Ink Muted** ({colors.ink-muted}): Default body copy (#39415a).
- **Ink Subtle** ({colors.ink-subtle}): Secondary/meta type, inactive labels (#5b6478).
- **Ink Tertiary** ({colors.ink-tertiary}): Captions, footnotes, placeholder (#8a93a6).
- **Ink Disabled** ({colors.ink-disabled}): Disabled labels (#b4bccb).
- **On Inverse** ({colors.on-inverse}): White text on the dark CTA band (#ffffff).
- **On Inverse Muted** ({colors.on-inverse-muted}): Muted text on dark (#aab2c5).

### Semantic
- **Success Green** ({colors.semantic-success}): Quantified proof-points (+25% win rate), success states (#12a150).
- **Success Subtle** ({colors.semantic-success-subtle}): Proof-pill background (#e6f6ed).
- **Warning** ({colors.semantic-warning}): Caution states (#e0951b).
- **Danger** ({colors.semantic-danger}): Errors, destructive (#e5484d).
- **Overlay** ({colors.overlay}): Navy scrim for modals and video lightboxes (#0b1220 at ~55% opacity).

## Typography

### Font Family

- **Pretendard** — a modern geometric grotesque display+text sans. Recommended fallback stack: `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`. Carries the entire hierarchy from display-xl down to caption.
- **mono** — monospace for code/tokens inside product screenshots and API/doc contexts. Fallback: `ui-monospace, "SF Mono", "JetBrains Mono", Menlo, monospace`.

The marketing surface uses a **single sans voice** across headlines and body — weight and tracking do the work, not family swaps.

### Hierarchy

| Token | Size | Weight | Line Height | Letter Spacing | Use |
|---|---|---|---|---|---|
| `{typography.display-xl}` | 72px | 700 | 1.05 | -2.4px | Hero headline |
| `{typography.display-lg}` | 56px | 700 | 1.08 | -1.8px | Major section openers |
| `{typography.display-md}` | 40px | 700 | 1.12 | -1.2px | Feature-story headlines |
| `{typography.headline}` | 32px | 600 | 1.18 | -0.8px | Sub-section headlines, CTA-band heading |
| `{typography.section-title}` | 26px | 600 | 1.22 | -0.5px | "Why revenue teams are switching" style titles |
| `{typography.card-title}` | 20px | 600 | 1.30 | -0.3px | Feature/template card titles |
| `{typography.subhead}` | 19px | 400 | 1.55 | -0.1px | Hero subhead, section intro paragraph |
| `{typography.body-lg}` | 18px | 400 | 1.60 | 0 | Lead paragraphs, testimonial quotes |
| `{typography.body}` | 16px | 400 | 1.60 | 0 | Default body copy |
| `{typography.body-sm}` | 14px | 400 | 1.55 | 0 | Card body, nav links, footer columns |
| `{typography.caption}` | 13px | 400 | 1.45 | 0 | Meta, labels, logo captions |
| `{typography.button}` | 15px | 600 | 1.20 | -0.1px | All button labels |
| `{typography.eyebrow}` | 13px | 600 | 1.30 | +0.6px | Section eyebrow ("Client Workspaces", "AI surface") — uppercase or small-caps |
| `{typography.stat}` | 44px | 700 | 1.0 | -1.4px | Big proof numbers (+25%, 2 hours) |
| `{typography.mono}` | 13px | 400 | 1.55 | 0 | Code / tokens in product screenshots |

### Principles

- **Bold display, tight tracking.** Headlines run weight 700 with aggressive negative letter-spacing (-2.4px at 72px ≈ 3.3% of size); body relaxes to 400 at 0 tracking.
- **Eyebrows use positive tracking** (+0.6px), typically uppercased, to read as section taxonomy against the tight-tracked headlines below them.
- **Generous line-height on body** (1.60) keeps the light, airy, readable feel — this is a copy-forward marketing site, not a dense dashboard.
- **Numbers get their own scale.** The `stat` token (44px/700) makes proof-points a visual anchor, often paired with a green `proof-pill`.
- **Single family, no serif.** The system stays entirely in one grotesque sans — friendliness comes from roundness and blue, not from a type mix.

### Note on Font Substitutes

The marketing typeface reads as a rounded geometric grotesque. If the exact face is unavailable, **Inter** (weights 400 / 600 / 700) is the closest free substitute and the recommended default fallback. **Geist Sans** or **General Sans** are viable alternates for a slightly more geometric feel. For mono, **JetBrains Mono** or **Geist Mono** at 400 approximates mono.

## Layout

### Spacing System

- **Base unit**: 4px.
- **Tokens**: `{spacing.xxs}` 4 · `{spacing.xs}` 8 · `{spacing.sm}` 12 · `{spacing.md}` 16 · `{spacing.lg}` 24 · `{spacing.xl}` 32 · `{spacing.xxl}` 48 · `{spacing.xxxl}` 72 · `{spacing.section}` 120.
- Feature-card interior padding: `{spacing.xl}` 28–32px.
- Product-screenshot frame padding: `{spacing.md}`–`{spacing.lg}` 16–24px (the frame is a thin light mat around the capture).
- Primary button padding: 12px vertical · 20px horizontal.
- Vertical section spacing: `{spacing.section}` 120px between major stories on desktop; `{spacing.xxxl}` 72px on tablet.

### Grid & Container

- Max content width ~1200–1280px, centered, with ~24px gutters.
- Feature-card grids run 3-up at desktop → 2-up at tablet → 1-up at mobile.
- The homepage feature stories use an **asymmetric split**: headline + copy column (~40%) beside a product-screenshot panel (~60%), sides alternating down the page.
- Product tab groups sit as a **pill row above one shared screenshot frame** that swaps on tab select.
- Logo marquee runs 6-up desktop → 3-up mobile.
- The social-proof grid uses a masonry / multi-column quote-card grid (3-up desktop).

### Whitespace Philosophy

Whitespace is the primary structural device. Sections separate not by rules but by **alternating white and `{colors.surface-1}` bands** with 96–120px vertical breathing room. Within a section, `{spacing.lg}` 24px gaps between blocks. The airy rhythm is intentional: the layout itself embodies calm and "less busywork."

## Elevation & Depth

| Level | Treatment | Use |
|---|---|---|
| 0 (flat) | No shadow, no border | Body copy, hero text, section bands |
| 1 (hairline card) | `{colors.canvas}` fill on `{colors.surface-1}` band, 1px `{colors.hairline}` border | Default feature/template/integration cards |
| 2 (soft lift) | White fill + 1px `{colors.hairline}` + shadow `0 4px 16px rgba(11,18,32,0.06)` | Testimonial cards, hovered cards, mega-menu |
| 3 (raised media) | Product screenshot in `{colors.surface-1}` frame + shadow `0 12px 40px rgba(11,18,32,0.10)` | Hero product panel, feature screenshots |
| 4 (focus ring) | 3px `{colors.primary}` outline at ~30% opacity + 1px `{colors.primary}` border | Focused input, focused button |

Depth here is **low-blur, low-opacity soft shadows on white** plus hairline borders — never harsh drop shadows. Elevation reads as gentle floating, matching the friendly tone.

### Decorative Depth

- **Product UI screenshots** are the dominant decorative element — framed, lightly shadowed, sometimes tilted or partially bled off a section edge.
- **A mascot or illustration** may sit near social-proof and empty-state moments for warmth (optional).
- **Subtle blue glow / gradient wash** may sit behind the hero product panel (very light `{colors.primary-subtle}` radial) — used once, softly.
- No neon, no atmospheric dark gradients, no glassmorphism.

## Shapes

### Border Radius Scale

| Token | Value | Use |
|---|---|---|
| `{rounded.xs}` | 6px | Small chips, logo tiles, nav items |
| `{rounded.sm}` | 8px | Buttons, form inputs |
| `{rounded.md}` | 10px | Icon chips, security badges, inline tags |
| `{rounded.lg}` | 14px | Feature cards, testimonial cards, template cards |
| `{rounded.xl}` | 20px | Product-screenshot frames, hero media frame, AI panel |
| `{rounded.xxl}` | 28px | The closing CTA band |
| `{rounded.pill}` | 9999px | Product-tab pills, proof pills, AI prompt chips, category tabs |
| `{rounded.full}` | 9999px | Avatars, mascot bubble, round icon buttons |

### Photography & Illustration Geometry

- Product UI screenshots sit in `{rounded.xl}` 20px frames with a thin `{colors.surface-1}` mat and soft shadow; captures keep their native aspect and never crop awkwardly.
- Customer logos render as flat monochrome / brand-color SVGs on white, ~28–32px tall, no border.
- Testimonial avatars use `{rounded.full}` circles at 40–48px, paired with a small source badge (Slack / G2 / LinkedIn / Product Hunt).
- If a mascot is used, keep it soft, rounded and low-detail — and use it sparingly.

## Components

### Buttons

**`button-primary`** — Primary Blue CTA. The default primary across the site ("Start for Free →", "Request Demo").
- Background `{colors.primary}`, text `{colors.on-primary}`, type `{typography.button}`, padding 12px 20px, rounded `{rounded.sm}` 8px.
- Hover → `button-primary-hover` (#1e4de0); pressed → `button-primary-pressed` (#1840bd).
- Often carries a trailing "→" arrow glyph.

**`button-secondary`** — White outline button. Paired left of the primary ("Request Demo" beside "Start for Free").
- Background `{colors.canvas}`, text `{colors.ink}`, 1px `{colors.hairline-strong}` border, type `{typography.button}`, padding 12px 20px, rounded `{rounded.sm}`.
- Hover → `button-secondary-hover` (fill shifts to `{colors.surface-1}`).

**`button-ghost`** — Plain text button for tertiary actions / nav ("Log in").
- Transparent background, text `{colors.ink-muted}`, type `{typography.button}`, padding 12px 16px.

**`button-inverse`** — White button on the dark CTA band.
- Background `{colors.canvas}`, text `{colors.ink}`, type `{typography.button}`, rounded `{rounded.sm}`, padding 12px 20px.

### Navigation

**`top-nav`** — Sticky white bar, 68px tall. Left: wordmark. Center: nav items (Product, Pricing, Customers, Resources) with hover mega-menus. Right: `button-ghost` ("Log in") + `button-secondary` ("Request Demo") + `button-primary` ("Start for Free").
- Background `{colors.canvas}`, text `{colors.ink}`, type `{typography.body-sm}`, 1px `{colors.hairline}` bottom border on scroll.

**`mega-menu`** — Dropdown panel grouping products by category (Collaboration / Content / Learning / AI & Integrations).
- Background `{colors.canvas}`, rounded `{rounded.lg}`, padding 24px, level-2 soft shadow, column headers in `{typography.eyebrow}` `{colors.ink-subtle}`.

### Hero & Media

**`hero-media-frame`** — The framed product panel dominating the hero, often with a pill row of feature labels above it (product tabs / AI 에이전트 표면 / AI Documents / …).
- Background `{colors.surface-1}`, rounded `{rounded.xl}`, padding 16px, level-3 shadow, optional faint `{colors.primary-subtle}` radial glow behind.

**`product-screenshot-card`** — The recurring framed app capture in each feature story.
- Background `{colors.surface-1}`, text `{colors.ink}`, type `{typography.body}`, rounded `{rounded.xl}`, padding 24px, level-3 shadow.

### Product Tabs

**`product-tab-default`** + **`product-tab-selected`** — Pill toggles that swap the shared screenshot (e.g. per-feature tabs).
- Default: `{colors.surface-2}` fill, `{colors.ink-subtle}` text, rounded `{rounded.pill}`, padding 8px 18px.
- Selected: `{colors.primary}` fill, `{colors.on-primary}` text — the active tab goes full Primary Blue.

### Cards & Containers

**`feature-card`** — Generic feature/benefit tile (Integrations "Connect your CRM", "Embed anything").
- Background `{colors.canvas}`, text `{colors.ink}`, type `{typography.body}`, rounded `{rounded.lg}`, padding 28px, 1px `{colors.hairline}` border.

**`stat-card`** — Proof-point tile ("+25% win rate", "2 hours saved").
- Background `{colors.surface-1}`, big number in `{typography.stat}` `{colors.ink}`, label in `{typography.body-sm}` `{colors.ink-subtle}`, rounded `{rounded.lg}`, padding 28px; number may carry a green `proof-pill`.

**`testimonial-card`** — Social-proof quote card: quote in `{typography.body-lg}`, avatar circle, name + role + company, source badge, optional mascot.
- Background `{colors.canvas}`, rounded `{rounded.lg}`, padding 28px, level-2 shadow, 1px `{colors.hairline}` border.

**`template-card`** — Starter-template tile.
- Background `{colors.canvas}`, thumbnail on top, title `{typography.card-title}`, category tag in `{colors.ink-subtle}`, rounded `{rounded.lg}`, padding 20px.

**`integration-card`** — Third-party integration tile with logo lockups.
- Background `{colors.canvas}`, rounded `{rounded.lg}`, padding 24px, 1px `{colors.hairline}` border.

**`logo-tile`** — Customer logo in the customer-logo marquee.
- Background `{colors.canvas}`, monochrome/brand SVG ~28px tall, no border, padding 16px 24px.

### AI Surfaces

**`ai-panel`** — Dark panel showcasing the AI / agent chat surface.
- Background `{colors.surface-inverse}`, text `{colors.on-inverse}`, rounded `{rounded.xl}`, padding 32px, accents in `{colors.ai-indigo}`.

**`ai-prompt-chip`** — Selectable prompt suggestion ("Deal review", "Product FAQ", "Draft emails").
- Background `{colors.ai-indigo-subtle}`, text `{colors.ai-indigo}`, type `{typography.body-sm}`, rounded `{rounded.pill}`, padding 8px 14px.

### Proof & Social

**`proof-pill`** — Small green pill wrapping a metric.
- Background `{colors.semantic-success-subtle}`, text `{colors.semantic-success}`, type `{typography.body-sm}`, rounded `{rounded.pill}`, padding 4px 12px.

**`category-tab`** — Emoji-labeled social-proof filter tabs.
- Transparent default, `{colors.ink-subtle}` text; selected gains `{colors.primary}` text + `{colors.primary}` underline or `{colors.primary-subtle}` fill.

### Trust & Security

**`security-badge`** — Security / compliance badge row.
- Background `{colors.surface-1}`, text `{colors.ink-muted}`, badge icon left, type `{typography.body-sm}`, rounded `{rounded.md}`, padding 16px 20px.

### Inputs & Forms

**`text-input`** + **`text-input-focused`** — Demo-request and signup fields.
- Background `{colors.canvas}`, text `{colors.ink}`, 1px `{colors.hairline-strong}` border, rounded `{rounded.sm}`, padding 12px 14px.
- Focused: border shifts to `{colors.primary}` with a 3px `{colors.primary}` ring at ~30% opacity.

### Closing CTA

**`cta-band`** — The one dark section near page bottom (closing conversion copy).
- Background `{colors.surface-inverse}`, text `{colors.on-inverse}`, heading `{typography.headline}`, rounded `{rounded.xxl}` 28px (as an inset rounded block, not full-bleed), padding 64px; CTA uses `button-inverse` + `button-primary`.

### Footer

**`footer`** — Dense multi-column link grid on white, grouped (Product / Getting started / Resources / General / Support & Legal), with the 워드마크 and social links.
- Background `{colors.canvas}`, text `{colors.ink-subtle}`, type `{typography.body-sm}`, padding 72px 32px, 1px `{colors.hairline}` top border.

## Do's and Don'ts

### Do

- Keep `{colors.canvas}` white as the anchor and use `{colors.surface-1}` (#f6f8fc) bands to separate sections.
- Reserve `{colors.primary}` Primary Blue for: primary CTA, links, active tab, focus, brand mark, mascot. Keep it scarce.
- Confine `{colors.ai-indigo}` to AI/agent surfaces only.
- Lead every feature story with a framed product UI screenshot.
- Use bold 700 display with tight negative tracking; keep body at 400 / 1.60 line-height for airiness.
- Wrap proof metrics in a green `proof-pill` and set the number in the `stat` scale.
- Use soft low-opacity shadows (`rgba(11,18,32,0.06–0.10)`) with hairline borders — never harsh shadows.
- Round buttons/inputs to 8px and cards to 14–20px.
- Let emoji and the mascot carry warmth in social-proof zones; balance with trust/compliance badges.

### Don't

- Don't ship a dark marketing page — the only dark moments are the AI panel and the closing CTA band.
- Don't fill whole sections with Primary Blue or use blue as a body background.
- Don't introduce a third brand accent (green and indigo are semantic/AI, not decorative).
- Don't mix in a serif or a second display family — stay in one grotesque sans.
- Don't use pill-shaped primary CTAs; primary buttons are 8px-rounded rectangles (pills are reserved for tabs/chips).
- Don't crop or heavily overlay product screenshots — they are the proof and must stay legible.
- Don't use heavy borders or high-contrast drop shadows; keep the surface calm and light.
- Don't over-tilt or 3D-transform the app captures; a slight lift is enough.

## Responsive Behavior

### Breakpoints

| Name | Width | Key Changes |
|---|---|---|
| Desktop-XL | 1440px | Default; asymmetric split stories, 3-up card grids |
| Desktop | 1200px | Container maxes out; 3-up grids maintained |
| Tablet | 1024px | Feature split stacks (copy above screenshot); grids 3-up → 2-up |
| Mobile-Lg | 768px | Nav collapses to hamburger; section spacing 120px → 72px; logo marquee 6-up → 3-up |
| Mobile | 480px | Single column; `display-xl` 72px scales toward `display-md` ~36–40px; CTA band padding shrinks |

### Touch Targets

- Primary/secondary CTAs hold ≥44px tap height on touch.
- Product-tab and category pills grow to ≥40px height on touch viewports.
- Form inputs hold ≥44px tap target.
- Nav hamburger and menu rows hold ≥44px.

### Collapsing Strategy

- **Top nav**: full nav + mega-menus collapse to a hamburger drawer below 768px; CTAs move into the drawer, keeping one `button-primary` visible in the bar.
- **Feature stories**: the copy/screenshot split stacks vertically — copy first, screenshot below — at 1024px.
- **Product tabs**: pill row may wrap or become a horizontal scroll strip on mobile; the shared screenshot spans full width.
- **Social-proof grid**: masonry collapses 3-up → 2-up → 1-up; category tabs become a scrollable row.
- **Footer**: multi-column grid collapses to 2-up then 1-up accordion-style groups.

### Image Behavior

- Product screenshots keep aspect ratio and scale to full container width on mobile; never letterbox-crop.
- Customer logos in the marquee reflow from 6-up to 3-up; keep uniform optical height (~28px).
- Testimonial avatars and source badges stay fixed size and never crop to non-circles.

## Iteration Guide

1. Focus on ONE component at a time and reference it by its `components:` token name.
2. When adding a section, first decide its band: white `{colors.canvas}` or light `{colors.surface-1}` — alternate down the page.
3. Default body to `{typography.body}` (16 / 400 / 1.60); reserve 700 + tight tracking for display.
4. Treat `{colors.primary}` as scarce — CTA, link, active tab, focus, brand, mascot only.
5. Put anything "AI" in the AI sub-language: `{colors.ai-indigo}`, `ai-prompt-chip`, `ai-panel`.
6. Lead each feature story with a `product-screenshot-card`; keep the copy column tight.
7. Wrap every metric in a `proof-pill` + `stat` pairing.
8. Keep shadows soft and low-opacity; prefer hairlines over heavy borders.
9. Add new variants as separate component entries rather than overloading existing ones.

## Known Gaps

- **Token derivation.** The source site is a Webflow build; the exact production CSS custom properties were not machine-extracted for this file. The hex values, radii, spacing, and type scale here are curated from publicly observable brand patterns (electric royal-blue accent on white canvas, alternating light bands, soft-rounded cards, product-screenshot rhythm, mascot, emoji social proof, dark closing CTA). Before shipping, run a live inspector on the source and reconcile `{colors.primary}`, `{colors.surface-1}`, and the exact display typeface against the real CSS variables, then `lint` the file.
- **Exact display typeface** is treated as "Pretendard" with an `Inter` fallback; the real marketing face may be a proprietary or licensed grotesque. Inter 400/600/700 is a safe substitute.
- **AI-indigo scope.** #6d5ef6 is inferred as the AI sub-accent from the AI/agent sections; confirm whether the source uses a distinct AI hue a distinct AI hue or simply reuses Primary Blue on dark.
- **Dark surfaces.** Only the AI panel and closing CTA band are documented as dark; a fuller dark palette (in-product theming) is out of scope for the marketing analysis.
- **In-product UI.** This file analyzes the marketing site. The product's actual in-app UI and white-label theming — where customers override logo, button, background, and accent colors — use a broader, tenant-configurable token set not captured here.
- **Motion.** Hover transitions, tab-swap animation, and scroll reveals are observable but not quantified; assume ~150–200ms ease-out for hovers and ~250ms for tab/media swaps as a starting point.
