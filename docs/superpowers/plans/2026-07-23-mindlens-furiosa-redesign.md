# mindlens Furiosa 리디자인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** mindlens 3개 표면(의뢰자·응답자·랜딩)을 Furiosa 디자인 시스템으로 리스킨하고, 신규 벤치마크 뷰를 추가한다.

**Architecture:** 토큰 레이어(globals.css `@theme` + tailwind)를 먼저 Furiosa로 리맵 → 공통 컴포넌트/아이콘/상태 → 셸 → 표면별 리스킨 → 벤치마크·랜딩. 구조는 현행 유지, 색·아이콘·상태만 교체(계약 §0.1 불변).

**Tech Stack:** Next.js 14 App Router · TypeScript strict · Tailwind(@theme) · lucide-react · recharts.

## Global Constraints

- 정본 = `design.md`(2026-07-23 Furiosa). 토큰 변경 시 design.md·globals.css·tailwind 동시 갱신.
- **아이콘 = `lucide-react`, 제품 시각 UI 이모지 금지**(하네스 §2).
- **에러색 = maroon `#6F2020`**(brand-red `#E21500`와 분리). 기존 `#ef4444` 폐기.
- **이원화:** 의뢰자/벤치마크 = 정통(화이트·obsidian·red·8–10px). 응답자/인터뷰 = 웜(cream `#FFFBF6`·blush·red·12–16px). 블랙 그라운드 금지.
- 폰트 Pretendard + `tabular-nums`. 시스템 mono는 **벤치마크 텔레메트리 전용**.
- **계약 불변(§0.1):** 집계=DB 실측 · PII 저장경로 마스킹 · transcribe `(전사,성공)`. 리스킨은 UI만.
- 검증(웹): `cd web && npm run typecheck` · `npm run build` · `npm run lint` · UI 스크린샷 · `/design-review`. (파이썬 무변경 — pytest 불필요, 단 회귀 시 `pytest api/tests -q`.)
- 하드게이트: 브랜치 커밋·PR 초안 자율, **머지=배포는 사람 승인**(§1).

---

### Task 1: 디자인 토큰 — Furiosa 리맵

**Files:**
- Modify: `web/styles/globals.css` (`:root` 토큰 · `.theme-*` 블록)
- Modify: `web/tailwind.config.ts` (colors · borderRadius · fontFeatureSettings)

**Interfaces:**
- Produces: Tailwind 클래스 `bg-red / text-red / border-silver / bg-cream / text-obsidian / bg-blush / text-maroon` 등과 CSS 변수 `--red --obsidian --silver --cream --blush --maroon` + 데이터 팔레트 리터럴(문서화).

- [ ] **Step 1:** `globals.css` `:root`의 sky-blue 계열(`--indigo/--accent*`)을 Furiosa로 치환:
```css
:root{
  --red:#E21500; --red-dark:#BC1302;
  --obsidian:#151515; --charcoal:#444; --grey:#7F7F7F; --silver:#D4D4D4; --platinum:#E1E1E1;
  --canvas:#ffffff; --paper:#FAF9F7;
  --cream:#FFFBF6; --blush:#FFF3EE; --warm-border:#F0E6DC; --warm-ink-soft:#8A6F5F;
  --maroon:#6F2020;
  /* 하위호환: 기존 --accent* 를 red 로 매핑 (컴포넌트 점진 교체용) */
  --accent:#E21500; --accent-deep:#BC1302; --accent-wash:#FBEBE9;
  --accent-solid:#E21500; --accent-on:#ffffff; --accent-soft:#FEC2A0;
}
```
`.theme-validate/survey/prediction/review` 블록은 제거하거나 red 단색으로 통일(솔루션별 테마 미사용 — design.md §0).
- [ ] **Step 2:** `tailwind.config.ts` `colors`에 Furiosa 팔레트 추가(`red`,`obsidian`,`charcoal`,`grey`,`silver`,`platinum`,`cream`,`blush`,`maroon`,데이터 `mint/cyan/peach/lilac/lemon/orange`), 기존 `nogo/error`를 `maroon`으로. `borderRadius.DEFAULT` = `0.5rem`(8px) 유지, 웜용 `xl:0.875rem(14px)` 추가.
- [ ] **Step 3:** 본문 `font-variant-numeric` 유틸 확인(`tabular-nums`), mono 스택은 벤치마크 전용 클래스 `.font-telemetry`(시스템 monospace) 신설.
- [ ] **Step 4:** `npm run build` → 통과(클래스 미해결 에러 없음). Expected: PASS.
- [ ] **Step 5:** Commit `git commit -am "디자인 토큰을 Furiosa 팔레트로 리맵한다"`.

### Task 2: 공통 컴포넌트 (Button·Card·Badge·상태)

**Files:**
- Modify: `web/components/shared/button.tsx` · `card.tsx`
- Create: `web/components/shared/states.tsx`(`Skeleton`,`EmptyState`,`ErrorState`) · `web/components/shared/badge.tsx`
- Modify: `web/components/shared/index.ts`(export)

**Interfaces:**
- Produces: `<Button variant="primary|secondary|ghost" size>`(red 8px, **pill 제거 → rounded rect**), `<EmptyState icon title body action>`, `<ErrorState onRetry>`, `<Skeleton className>`, `<Badge tone="live|draft|closed|warm">`.

- [ ] **Step 1:** 실패 없는 정적 컴포넌트라 검증=타입/빌드. `button.tsx`의 `rounded-full`→`rounded`(8px), variants를 red 기반으로(`primary: bg-red text-white hover:bg-red-dark`, `secondary: bg-white text-obsidian ring-1 ring-silver`, `ghost: text-charcoal`).
- [ ] **Step 2:** `states.tsx` 작성 — `Skeleton`(시머 애니), `EmptyState`(lucide 아이콘+제목+본문+CTA), `ErrorState`(maroon+`RotateCw` 재시도). `badge.tsx` — tone별 색.
- [ ] **Step 3:** `index.ts`에 export 추가.
- [ ] **Step 4:** `npm run typecheck && npm run build` → PASS.
- [ ] **Step 5:** Commit `공통 컴포넌트에 Furiosa 버튼·배지·상태 화면을 추가한다`.

### Task 3: lucide 아이콘 + 이모지 횡단 교체 + 진행자 오브

**Files:**
- Modify (package): `web/package.json`(`lucide-react` 추가) · `npm i lucide-react`
- Modify: `web/components/interview-flow.tsx` · `web/app/i/[projectId]/respondent-view.tsx` · `web/app/projects/[id]/results-panel.tsx`(이모지 사용 3파일 — grep 확인)
- Create: `web/components/moderator-avatar.tsx`(웜 오브, `prefers-reduced-motion` 존중)

**Interfaces:**
- Consumes: 없음. Produces: `<ModeratorAvatar speaking?>`.

- [ ] **Step 1:** `cd web && npm i lucide-react`.
- [ ] **Step 2:** 3파일의 이모지 교체 — 🎤→`<Mic/>` · 🔊→`<Volume2/>` · ●녹음→`<Circle fill/>` · 정지→`<Square/>` · ✅→`<CheckCircle2/>` · 🙏→`<HeartHandshake/>` · 🎙→`<Mic/>`(또는 ModeratorAvatar). results-panel의 🎙(전사 헤더)도.
- [ ] **Step 3:** `moderator-avatar.tsx` 작성(peach→red 라디얼 오브, speaking 시 맥동).
- [ ] **Step 4:** 검증 — `grep -rP "🎤|🔊|✅|🙏|🎙" web/ ` → **0건**. `npm run typecheck && npm run build` → PASS.
- [ ] **Step 5:** Commit `제품 UI 이모지를 lucide 아이콘으로 교체하고 진행자 오브를 추가한다`.

### Task 4: 앱 셸 — 좌측 사이드바 (무인증) + 로고

**Files:**
- Create: `web/components/shell/sidebar.tsx`
- Create/Modify: `web/app/projects/layout.tsx`(사이드바 래핑)
- Modify: `web/app/projects/projects-view.tsx` · `project-view.tsx`(BackLink 제거, 셸 내부로)
- Asset: `web/public/mindlens-logo.svg`(V3, 이미 저장) · `web/app/icon.svg`(favicon을 red 마크로 갱신)

**Interfaces:**
- Produces: `<Sidebar active="projects|benchmark">` — 로고(logo.svg)+검색(⌘K, 시각만)+네비(프로젝트·성능/벤치마크)+새 프로젝트+무인증 푸터. **계정/워크스페이스 없음.**

- [ ] **Step 1:** `sidebar.tsx` 작성 — design.md §5. 로고는 `<img src="/mindlens-logo.svg">` 또는 인라인.
- [ ] **Step 2:** `app/projects/layout.tsx`로 사이드바 + 콘텐츠 헤더바 래핑. 기존 뷰들의 `<BackLink>` 제거.
- [ ] **Step 3:** `app/icon.svg`를 red 마크로 교체(favicon).
- [ ] **Step 4:** `npm run build` → PASS. 스크린샷(사이드바 렌더·로고).
- [ ] **Step 5:** Commit `무인증 좌측 사이드바 셸과 서비스 로고를 배선한다`.

### Task 5: 의뢰자 화면 리스킨 (정통)

**Files:** `web/app/projects/projects-view.tsx` · `projects/[id]/project-view.tsx` · `guide-panel.tsx` · `results-panel.tsx`

**Interfaces:** Consumes Task 1·2·4. 로직·API·집계 계약 불변 — **클래스/상태 렌더만 교체.**

- [ ] **Step 1:** 프로젝트 리스트를 카드형(배지·익명 카운트·완료율)으로, 로딩=`<Skeleton>`·빈=`<EmptyState>`·에러=`<ErrorState>`로 교체("불러오는 중…" 텍스트 제거).
- [ ] **Step 2:** `results-panel.tsx` recharts 색을 Furiosa 데이터 팔레트로(ACCENT→`#E21500`, SENTIMENT_COLOR→mint/silver/orange/red). 진행바 `bg-accent-solid`→red.
- [ ] **Step 3:** `guide-panel`·탭·버튼 red/silver로.
- [ ] **Step 4:** `npm run typecheck && npm run build` → PASS. `pytest api/tests -q`(무변경 확인). 스크린샷.
- [ ] **Step 5:** Commit `의뢰자 대시보드를 Furiosa 정통 스킨으로 리스킨한다`.

### Task 6: 응답자 화면 리스킨 (웜)

**Files:** `web/app/i/[projectId]/respondent-view.tsx`(consent·screener·done) · `web/components/interview-flow.tsx` · `interview-stimulus.tsx`

**Interfaces:** Consumes Task 1·2·3. **현행 인터뷰 구조 불변** — cream 캔버스·웜 카드·red 액센트·`ModeratorAvatar`로 스킨만.

- [ ] **Step 1:** respondent-view 전 스테이지(동의·스크리너·완료)를 cream/blush·warm-border·12–16px로. 완료 ✅→`CheckCircle2`.
- [ ] **Step 2:** interview-flow 상단 진행자 라벨을 `<ModeratorAvatar>`로, 마이크/다음 red, 진행바 red, 녹음/전사 상태 아이콘화. 자극물 2분할 유지.
- [ ] **Step 3:** `npm run typecheck && npm run build` → PASS. 모바일 폭 스크린샷.
- [ ] **Step 4:** Commit `응답자 인터뷰 여정을 Furiosa 웜 스킨으로 리스킨한다`.

### Task 7: 벤치마크 뷰 (신규, 정통)

**Files:**
- Create: `web/components/benchmark/benchmark-view.tsx`(+하위: KPI·결과표·손익분기·전력시계열)
- Create: `web/app/projects/benchmark/page.tsx` 또는 프로젝트 내 탭(라우팅은 셸 네비와 정합)
- (데이터) `web/lib/api.ts`에 벤치마크 fetch 스텁 — **미측정=null 계약**

**Interfaces:** design.md §5·`docs/specs/2026-07-23-rngd-benchmark-instrumentation.md §7`. M1/M2/M3 + S* + 결과표(4구성) + 24h 시계열. **null-우선**(값 없으면 `—`), 텔레메트리=`.font-telemetry` mono.

- [ ] **Step 1:** 데이터 계약 타입 정의(`BenchmarkResult` — 모든 필드 `number|null`). fetch는 없으면 null 반환.
- [ ] **Step 2:** `benchmark-view.tsx` — 보드 아티팩트 레이아웃 이식(KPI·표·차트 recharts, NPU=red/GPU=grey). 추정치 렌더 금지(null→`—`).
- [ ] **Step 3:** 셸 네비 "성능·벤치마크"와 라우팅 연결.
- [ ] **Step 4:** `npm run typecheck && npm run build` → PASS. 스크린샷(null 상태).
- [ ] **Step 5:** Commit `NPU 손익분기 벤치마크 뷰를 추가한다(미측정 null 상태)`.

### Task 8: 랜딩 = 스플래시 (시작하기 → 서비스)

**Files:** `web/app/page.tsx`(전면 교체 — 기존 히어로/4스텝/프리뷰/푸터 **제거**)

**Interfaces:** Consumes Task 1·4(로고). **최소 스플래시**: 로고 + 워드마크 + 한 줄 태그라인 + 단일 `시작하기` 버튼 → `/projects`(실제 서비스 진입).

- [ ] **Step 1:** `page.tsx`를 스플래시로 교체 — 뷰포트 중앙 정렬, 로고(`/mindlens-logo.svg`)+워드마크 "mindlens", 한 줄 태그라인("설문으로는 안 나오던 진짜 이유를 듣습니다"), primary `시작하기`(`<Link href="/projects">`), 서브 "가입 없이 바로 · 링크만 공유". 라이트 그라운드, 잔여 sky-blue(`section-ice/glow`) 제거. 마케팅 섹션(4스텝·프리뷰·푸터) 없음.
- [ ] **Step 2:** `npm run build` → PASS. 스크린샷(모바일·데스크톱).
- [ ] **Step 3:** Commit `랜딩을 시작하기 스플래시로 교체한다`.

---

## Self-Review
- **Spec 커버리지:** 스펙 §2 결정 1–9 → Task 1(색·타이포)·2(상태·버튼)·3(아이콘)·4(셸·무인증·로고)·5(의뢰자)·6(인터뷰 웜)·7(벤치마크)·8(랜딩). 전 항목 매핑됨.
- **횡단(§2):** 이모지 교체=Task 3 grep 0건 게이트. 토큰 리네임=Task 1 하위호환 alias로 점진 교체(빌드 게이트).
- **계약 보존:** Task 5·6에 "로직·집계·API 불변, 스킨만" 명시. pytest 회귀 확인 스텝 포함.
- **타입 일관성:** `Button` variant명(primary/secondary/ghost) 전 Task 공유. 상태 컴포넌트 시그니처 Task 2에서 확정 후 5·6 소비.
- **미측정 정직성:** Task 7 null-우선(스펙 §8) 명시.
- **의존:** Task 1 → 2 → (3·4 병렬 가능) → 5·6·8 → 7. 순서 준수.
