# 응답자 UI 리디자인 (Outset풍 · Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 응답자 인터뷰 UI(동의 → 인터뷰 → 완료)를 진행자 아바타 없는 단일 컬럼 중심의 Outset풍으로, 우리 색상 시스템 그대로, 데스크톱 웹 기준(모바일 반응형 유지)으로 리디자인한다. 자극물(stimulus)은 이번엔 **UI 자리만 예약**(2분할 모드 스캐폴딩)하고 백엔드 연동은 하지 않는다.

**Architecture:** 순수 프론트엔드 변경. `web/components/interview-flow.tsx`의 렌더만 재구성하고(상태·음성·IME 로직 전부 보존), `web/app/i/[projectId]/respondent-view.tsx`의 동의/완료 화면을 같은 결로 맞춘다. 진행자 아바타는 제거하고 `moderator-avatar.tsx`를 삭제한다. 질문에 선택적 `stimulus` prop이 있으면 2분할, 없으면 센터 컬럼으로 갈라지는 어댑티브 레이아웃을 만들되, Phase 1에서 `stimulus`는 항상 `undefined`다.

**Tech Stack:** Next.js 14 App Router · TypeScript(strict) · Tailwind + `web/styles/globals.css`의 CSS 변수 토큰(SSOT).

**시각 스펙(픽셀 기준):** 목업 아트팩트 <https://claude.ai/code/artifact/cddebc7a-d3ba-469a-a6c1-1098b8eb0901> — "1번 Centered Column"이 인터뷰 기본, "자극물 붙이면 3번 2분할", 맨 아래 "동의 화면"이 R-1 기준. 이 문서의 클래스 값은 목업을 코드로 옮긴 것이며, 최종 여백·크기는 Task 6 시각 QA에서 아트팩트와 대조해 확정한다.

## Global Constraints

- **깨면 안 되는 계약(무관하지만 준수):** 이 작업은 UI만 건드린다 — 집계(DB 실측)·PII 마스킹·`transcribe (전사,성공여부)`·NPU 전용·provider 설정값 판별·Qwen3 thinking off 경로는 **손대지 않는다.** (`CLAUDE.md`)
- **디자인 토큰 SSOT = `web/styles/globals.css`의 CSS 변수.** 새 색·타이포·radii를 컴포넌트에 하드코딩하지 않고 기존 토큰 클래스(`text-ink`/`text-ink-soft`/`text-ink-faint`/`bg-surface`/`bg-bg`/`text-accent`/`bg-accent-solid`/`text-accent-on`/`ring-line`/`bg-accent-wash`/`text-title`/`text-lead`/`text-meta` 등)를 쓴다. 응답자 라우트는 `theme-*` 클래스가 없어 기본 액센트 = sky-blue `#00a4df`.
- **커밋 메시지: 한국어 현재형 서술** ("무엇을 한다"). 예: `응답자 인터뷰 화면에서 진행자 아바타를 걷어낸다`.
- **웹 검증 사이클(유닛 러너 없음):** 각 Task 종료 시 `cd web && npm run typecheck` (tsc --noEmit) → `cd web && npm run build` → `cd web && npm run lint` 3종을 통과시키고, 렌더 변경은 헤드리스 시각 QA(`/qa` 또는 `/browse`)로 확인한다. 이 repo에는 JS 컴포넌트 테스트 프레임워크가 없으므로 **새로 도입하지 않는다**(범위 밖).
- **한국어 IME 계약 보존:** `interview-flow.tsx`의 Enter 전송 시 `e.nativeEvent.isComposing` 가드를 절대 제거하지 않는다(조합 중 확정 Enter가 전송되면 안 됨).
- **음성 계약 보존:** `recorder.stop()`은 "절대 reject 하지 않는다", `transcribeAudio`는 `{text, ok}`를 돌려주고 `ok=false`(엔진실패)와 `ok=true`+빈텍스트(무음)를 다르게 안내한다 — 이 분기 로직을 유지한다.

---

### Task 1: 진행자 아바타 제거

**Files:**
- Modify: `web/components/interview-flow.tsx` (import 라인 14, 사용처 184·209 및 감싸는 2단 그리드)
- Delete: `web/components/moderator-avatar.tsx` (interview-flow 외 사용처 없음 — grep 확인됨)

**Interfaces:**
- Consumes: 없음
- Produces: 아바타 없는 `interview-flow.tsx` (Task 2가 이어서 레이아웃을 재구성)

- [ ] **Step 1: 아바타 import·사용 제거**

`web/components/interview-flow.tsx` 상단 import에서 다음 줄을 삭제:
```tsx
import { ModeratorAvatar } from "@/components/moderator-avatar";
```
idle 화면(현재 182-201)의 아바타 블록 삭제:
```tsx
        <div className="w-32">
          <ModeratorAvatar speaking={false} getLevel={tts.getLevel} />
        </div>
```
인터뷰 화면(현재 206-211)의 왼쪽 아바타 컬럼 전체 삭제:
```tsx
      {/* 왼쪽 — 진행자 아바타 */}
      <div className="flex flex-col items-center gap-3">
        <ModeratorAvatar speaking={tts.speaking} getLevel={tts.getLevel} />
        <p className="font-mono text-2xs uppercase text-accent">🎙 {en ? "Moderator" : "진행자"}</p>
      </div>
```
그리고 그 아바타 컬럼을 담던 2단 그리드(현재 206 `<Card className="grid gap-5 p-5 sm:p-6 md:grid-cols-[minmax(0,13rem)_1fr] md:items-center">`)를 단일 컬럼 카드로 바꾼다 — 정확한 마크업은 Task 2에서 확정하므로, 이 Task에서는 우선 `md:grid-cols-[...]`를 제거해 세로 스택으로만 만든다:
```tsx
    <Card className="mx-auto w-full max-w-2xl p-5 sm:p-6">
```
(오른쪽 컬럼을 감싸던 `<div className="flex min-h-[20rem] flex-col">`는 그대로 둔다 — Task 2에서 다듬는다.)

- [ ] **Step 2: 고아가 된 avatar 컴포넌트 삭제**

```bash
rm web/components/moderator-avatar.tsx
```
`getLevel`(진폭)은 아바타 전용이었다. `useTts`의 `getLevel`은 이제 호출되지 않지만 훅 인터페이스는 그대로 두어도 무방하다(다른 파일이 쓸 수 있음). 훅은 수정하지 않는다.

- [ ] **Step 3: 검증**

Run: `cd web && npm run typecheck`
Expected: PASS (ModeratorAvatar 참조가 모두 사라져 미해결 import 없음)

Run: `cd web && npm run build`
Expected: 빌드 성공

- [ ] **Step 4: 커밋**

```bash
git add web/components/interview-flow.tsx
git rm web/components/moderator-avatar.tsx
git commit -m "응답자 인터뷰 화면에서 진행자 아바타를 걷어낸다"
```

---

### Task 2: 인터뷰 화면을 센터 컬럼(방향 1)으로 재구성 + 진행률

**Files:**
- Modify: `web/components/interview-flow.tsx` (렌더 전체 + 진행률 상태 추가)

**Interfaces:**
- Consumes: 기존 상태/콜백(`phase`,`question`,`input`,`advance`,`goNext`,`submit`,`toggleRecord`,`tts`,`recorder`,`voiceInput`,`voiceFilled`,`error`) — **전부 보존**
- Produces: 아바타 없는 센터 컬럼 인터뷰 렌더 + `mainQ` 진행률(프로빙 미포함). Task 4가 이 렌더에 `stimulus` 분기를 추가한다.

- [ ] **Step 1: 진행률 상태 추가 (프로빙은 세지 않음)**

`interview-flow.tsx`의 상태 선언부(현재 `const [answerCount, setAnswerCount] = useState(0);` 부근)에 추가:
```tsx
  const [mainQ, setMainQ] = useState(0); // 프로빙 제외 '본 질문' 번호 (PRD F5.3: 프로빙은 진행률 미반영)
```
`advance()` 안에서 진행자 발화를 받은 직후(현재 `const msg = (out.message ?? "").trim();` 다음 줄)에 추가:
```tsx
      if (msg && !out.done && !out.is_probe) setMainQ((n) => n + 1); // 오프닝·본 질문만 카운트, 프로빙 제외
```
(`out.is_probe`는 `TurnOut`에 이미 존재한다. `lib/api.ts` 확인 — 없으면 `sendTurn` 반환 타입에 `is_probe: boolean`이 있는지 점검하고, `TurnOut`을 그대로 쓴다.)

- [ ] **Step 2: idle 화면 렌더 교체 (센터, 아바타 없음)**

현재 idle 블록(`if (phase === "idle") { return ( ... ) }`)의 `return` 내용을 교체:
```tsx
    return (
      <Card className="mx-auto flex min-h-[24rem] w-full max-w-2xl flex-col items-center justify-center gap-6 p-8 text-center sm:p-10">
        <p className="eyebrow">{en ? "Voice interview" : "음성 인터뷰"}</p>
        <p className="max-w-md text-lead leading-relaxed text-ink-soft">
          {en
            ? "A moderator will guide the interview by voice. Answer by speaking or typing, then press Next."
            : "진행자가 음성으로 질문을 드립니다. 말하거나 입력해 답한 뒤 ‘다음’을 눌러 주세요."}
        </p>
        <Button type="button" size="lg" onClick={begin}>
          {en ? "Start interview" : "인터뷰 시작"}
        </Button>
        {error && <p className="text-meta text-nogo">{error}</p>}
        {!tts.available && (
          <p className="text-2xs text-ink-faint">
            {en ? "(Voice playback unavailable — text only)" : "(음성 재생 비활성 — 텍스트로 진행)"}
          </p>
        )}
      </Card>
    );
```

- [ ] **Step 3: 인터뷰 화면 렌더 교체 (센터 컬럼 + 상단 진행률)**

인터뷰 `return (...)`를 아래로 교체. 질문이 주인공(큰 타이포), 답변 바는 아래. 상태별(진행 중 / review / done) 분기는 기존 그대로 유지하되 2단 그리드를 없앤다:
```tsx
  return (
    <Card className="mx-auto w-full max-w-2xl overflow-hidden p-0">
      {/* 상단 — 진행률 (프로빙 미반영) */}
      <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3 sm:px-6">
        <p className="font-mono text-2xs uppercase tracking-wider text-ink-faint">
          🎙 {en ? "Moderator" : "진행자"}
        </p>
        {phase !== "review" && phase !== "done" && mainQ > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-2xs font-medium text-ink-faint">
              {en ? `Question ${mainQ}` : `질문 ${mainQ}`}
            </span>
            <span className="h-1 w-24 overflow-hidden rounded-full bg-line">
              <span
                className="block h-full rounded-full bg-accent-solid transition-[width] duration-500"
                style={{ width: `${Math.min(90, mainQ * 14)}%` }}
              />
            </span>
          </div>
        )}
      </div>

      <div className="flex min-h-[22rem] flex-col p-5 sm:p-8">
        {phase === "review" || phase === "done" ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
            <p className="text-title text-ink">{question}</p>
            {phase === "done" ? (
              <p className="text-meta text-ink-soft">{en ? "Submitted. Thank you!" : "제출됐어요. 감사합니다!"}</p>
            ) : (
              <>
                <p className="text-meta text-ink-soft">
                  {en
                    ? "That's the end of the interview. Submit to send your answers."
                    : "인터뷰가 끝났어요. 제출해야 답변이 전달됩니다."}
                </p>
                <Button type="button" size="lg" onClick={() => void submit()} disabled={submitting}>
                  {submitting ? (en ? "Submitting…" : "제출 중…") : en ? "Submit answers" : "답변 제출하기"}
                </Button>
                <p className="text-2xs text-ink-faint">
                  {en ? "Your answers are only counted once submitted." : "제출하지 않고 창을 닫으면 답변이 집계되지 않아요."}
                </p>
                {error && <p className="text-meta text-nogo">{error}</p>}
              </>
            )}
          </div>
        ) : (
          <QuestionAndAnswer
            en={en}
            busy={busy}
            question={question}
            tts={tts}
            phase={phase}
            input={input}
            setInput={setInput}
            goNext={goNext}
            toggleRecord={toggleRecord}
            recorder={recorder}
            voiceFilled={voiceFilled}
            voiceInput={voiceInput}
            canType={canType}
            canNext={canNext}
            error={error}
          />
        )}
      </div>
    </Card>
  );
```

- [ ] **Step 4: 질문+답변 블록을 `QuestionAndAnswer` 프리젠테이션 컴포넌트로 추출**

같은 파일 하단(export 함수 밖)에 추가. 여기가 Task 4에서 자극물 2분할이 얹히는 지점이라 미리 분리한다. 마크업은 현재 245-336의 질문/답변 로직을 **동작 그대로** 옮긴 것(replay, 녹음 상태, transcribing, error, 마이크 버튼, textarea+IME 가드, 다음 버튼):
```tsx
function QuestionAndAnswer(p: {
  en: boolean; busy: boolean; question: string; tts: ReturnType<typeof useTts>;
  phase: Phase; input: string; setInput: (v: string) => void; goNext: () => void;
  toggleRecord: () => void; recorder: ReturnType<typeof useRecorder>;
  voiceFilled: boolean; voiceInput: VoiceInputState; canType: boolean; canNext: boolean;
  error: string | null;
}) {
  const { en, busy, question, tts, phase, input, setInput, goNext, toggleRecord, recorder, voiceFilled, voiceInput, canType, canNext, error } = p;
  return (
    <>
      {/* 질문 — 화면의 주인공 */}
      <div className="flex items-start gap-3">
        <p className="flex-1 text-[1.6rem] font-medium leading-snug tracking-tight text-ink [text-wrap:balance]">
          {busy ? (
            <span className="animate-pulse text-ink-faint">
              {en ? "Moderator is thinking…" : "진행자가 다음 질문을 준비 중…"}
            </span>
          ) : (
            question
          )}
        </p>
      </div>
      {!busy && tts.available && question && (
        <button
          type="button"
          onClick={() => void tts.speak(question)}
          className="mt-3 inline-flex items-center gap-1.5 self-start text-meta font-medium text-accent"
        >
          🔊 {en ? "Replay" : "다시 듣기"}
        </button>
      )}

      {/* 답변 */}
      <div className="mt-auto pt-6">
        {voiceFilled && canType && (
          <p className="mb-2 text-2xs text-ink-faint">
            {en ? "Here's what we heard — edit it or re-record, then press Next." : "이렇게 들었어요 — 고치거나 다시 녹음한 뒤 ‘다음’을 눌러 주세요."}
          </p>
        )}
        {voiceInput.mode === "text" && recorder.supported && (
          <p className="mb-2 text-2xs text-ink-faint">
            {en ? "Switched to typing. The mic still works if you want to try again." : "키보드 입력으로 전환했어요. 마이크는 계속 쓸 수 있어요."}
          </p>
        )}
        {phase === "recording" && (
          <p className="mb-2 text-meta text-nogo">● {en ? "Recording" : "녹음 중"} {recorder.elapsedSec}s</p>
        )}
        {phase === "transcribing" && (
          <p className="mb-2 text-meta text-ink-faint">{en ? "Transcribing…" : "음성 인식 중…"}</p>
        )}
        {error && <p className="mb-2 text-meta text-nogo">{error}</p>}

        <div className="flex items-end gap-2">
          {recorder.supported && (
            <button
              type="button"
              onClick={() => void toggleRecord()}
              disabled={busy || phase === "transcribing"}
              aria-label={en ? "Record answer" : "음성으로 답하기"}
              className={cn(
                "flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-meta font-medium transition-colors disabled:opacity-40",
                phase === "recording" ? "bg-nogo/10 text-nogo" : "bg-accent-wash text-accent-deep ring-1 ring-line hover:bg-accent-wash/70",
              )}
            >
              {phase === "recording" ? (en ? "■" : "■") : "🎤"}
            </button>
          )}
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                goNext();
              }
            }}
            rows={3}
            disabled={!canType}
            placeholder={en ? "Type or speak your answer" : "답변을 입력하거나 🎤로 말하세요"}
            className={fieldClass("min-h-12 flex-1 resize-none text-lead")}
          />
          <button
            type="button"
            onClick={goNext}
            disabled={!canNext}
            className="h-12 shrink-0 rounded-xl bg-accent-solid px-5 text-base font-medium text-accent-on disabled:opacity-40"
          >
            {en ? "Next" : "다음"}
          </button>
        </div>
      </div>
    </>
  );
}
```
`cn`,`fieldClass`,`Button`,`Card`,`useTts`,`useRecorder`,`VoiceInputState`,`Phase` import는 이미 파일 상단에 있다(그대로 유지).

- [ ] **Step 5: 검증**

Run: `cd web && npm run typecheck` → Expected: PASS
Run: `cd web && npm run build` → Expected: 성공
시각 확인(로컬 dev 또는 배포된 테스트 프로젝트 `p_293daf165c5d`): idle → 인터뷰 진행 중 화면이 아바타 없이 센터 컬럼으로 뜨고, 본 질문에서만 "질문 N"이 오르는지(프로빙 턴에선 안 오름) 확인.

- [ ] **Step 6: 커밋**

```bash
git add web/components/interview-flow.tsx
git commit -m "인터뷰 화면을 아바타 없는 센터 컬럼으로 재구성하고 진행률을 붙인다"
```

---

### Task 3: 자극물 타입과 렌더 컴포넌트 (데이터 없이 UI만)

**Files:**
- Modify: `web/lib/api.ts` (Stimulus 타입 export 추가)
- Create: `web/components/interview-stimulus.tsx`

**Interfaces:**
- Consumes: 없음
- Produces: `type Stimulus = { type: "image" | "video"; url: string; caption?: string }` · `<InterviewStimulus stimulus={...} />`. Task 4가 이 둘을 인터뷰 화면에 배선한다.

- [ ] **Step 1: Stimulus 타입 추가**

`web/lib/api.ts` 하단(타입 선언 구역)에 추가:
```ts
/** 질문에 붙는 제시 자료(시안·광고·컨셉). Phase 1은 UI만 — 아직 API가 내려주지 않는다. */
export type Stimulus = { type: "image" | "video"; url: string; caption?: string };
```

- [ ] **Step 2: 렌더 컴포넌트 작성**

Create `web/components/interview-stimulus.tsx`:
```tsx
"use client";

import type { Stimulus } from "@/lib/api";

// 질문에 붙는 제시 자료. 이미지/영상만. 접근성: 이미지는 caption 을 alt 로.
export function InterviewStimulus({ stimulus }: { stimulus: Stimulus }) {
  return (
    <figure className="flex h-full flex-col gap-2">
      <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-2xl border border-line bg-line-soft">
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
        <figcaption className="text-center text-2xs text-ink-faint">{stimulus.caption}</figcaption>
      )}
    </figure>
  );
}
```
(배경은 `bg-line-soft`(#f3f3f3) — tailwind config에 `bg-alt` 토큰은 없고 `line.soft`가 옅은 회색이다. 확인됨.)

- [ ] **Step 3: 검증**

Run: `cd web && npm run typecheck` → Expected: PASS
Run: `cd web && npm run build` → Expected: 성공 (아직 아무 데서도 import 안 하므로 tree-shaking으로 빠질 수 있음 — 정상)

- [ ] **Step 4: 커밋**

```bash
git add web/lib/api.ts web/components/interview-stimulus.tsx
git commit -m "제시 자료(stimulus) 타입과 렌더 컴포넌트를 추가한다"
```

---

### Task 4: 어댑티브 레이아웃 — 자극물 있으면 2분할(방향 3), 없으면 센터 컬럼

**Files:**
- Modify: `web/components/interview-flow.tsx` (optional `stimulus` prop + 조건부 2분할)

**Interfaces:**
- Consumes: `Stimulus`, `<InterviewStimulus>` (Task 3), `QuestionAndAnswer` (Task 2)
- Produces: 자극물 유무로 갈리는 인터뷰 본문. Phase 1에선 `stimulus`가 항상 `undefined`라 센터 컬럼으로만 렌더되지만, prop을 주면 즉시 2분할로 전환된다(v2 준비 완료).

- [ ] **Step 1: prop 추가**

`interview-flow.tsx` import에 추가:
```tsx
import { InterviewStimulus } from "@/components/interview-stimulus";
import { sendTurn, submitSession, transcribeAudio, type Stimulus } from "@/lib/api";
```
(기존 `import { sendTurn, submitSession, transcribeAudio } from "@/lib/api";`를 위 한 줄로 교체.)

`InterviewFlow` props 타입과 구조분해에 optional `stimulus` 추가:
```tsx
export function InterviewFlow({
  projectId,
  sessionId,
  locale = "ko",
  en = false,
  stimulus,
  onComplete,
}: {
  projectId: string;
  sessionId: string;
  locale?: string;
  en?: boolean;
  stimulus?: Stimulus; // Phase 1: 항상 undefined. 주어지면 2분할로 렌더.
  onComplete: (answerCount: number) => void;
}) {
```

- [ ] **Step 2: 인터뷰 본문을 조건부 레이아웃으로**

Task 2 Step 3에서 만든 인터뷰 `return`의 본문 컨테이너(`<div className="flex min-h-[22rem] flex-col p-5 sm:p-8"> ... </div>`)에서, **진행 중(질문/답변) 분기만** 자극물 유무로 가른다. review/done은 그대로 센터 유지. 진행 중 렌더를 다음으로 교체:
```tsx
        ) : stimulus ? (
          // 자극물 모드 — 2분할(방향 3): 왼쪽 자극물, 오른쪽 질문+답변
          <div className="grid flex-1 gap-5 md:grid-cols-[1.4fr_1fr]">
            <div className="min-h-[16rem] md:min-h-0">
              <InterviewStimulus stimulus={stimulus} />
            </div>
            <div className="flex min-h-0 flex-col md:border-l md:border-line md:pl-6">
              <QuestionAndAnswer {...qaProps} />
            </div>
          </div>
        ) : (
          // 기본 — 센터 컬럼(방향 1)
          <div className="mx-auto flex w-full max-w-xl flex-1 flex-col">
            <QuestionAndAnswer {...qaProps} />
          </div>
        )}
```
`qaProps`는 Task 2 Step 3에서 `<QuestionAndAnswer .../>`에 넘기던 props 객체를 렌더 직전에 한 번만 만들어 재사용:
```tsx
    const qaProps = {
      en, busy, question, tts, phase, input, setInput, goNext,
      toggleRecord, recorder, voiceFilled, voiceInput, canType, canNext, error,
    };
```
(이 `const qaProps`는 `return (` 바로 위, 컴포넌트 함수 본문 안에 둔다.)

- [ ] **Step 3: 2분할이 실제로 뜨는지 임시 확인 후 되돌리기**

Phase 1엔 자극물 데이터가 없으므로, `respondent-view.tsx`가 `stimulus`를 안 넘겨 센터 컬럼만 렌더된다. 2분할 렌더를 눈으로 확인하려면 `interview-flow.tsx` 진행 중 분기 위에 임시 목 데이터를 잠깐 넣어 확인:
```tsx
// 임시 확인용 — 확인 후 반드시 삭제
const stimulus: Stimulus | undefined = { type: "image", url: "https://picsum.photos/600/400", caption: "신제품 패키지 시안 A" };
```
`cd web && npm run dev`로 인터뷰 화면이 2분할로 뜨는지 확인한 뒤 **위 임시 줄을 삭제**하고 prop 기반으로 되돌린다.

- [ ] **Step 4: 검증**

Run: `cd web && npm run typecheck` → Expected: PASS (미사용 `stimulus` prop 경고 없음 — 렌더에서 사용)
Run: `cd web && npm run build` → Expected: 성공
시각 확인: 임시 목 제거 후 기본 인터뷰가 센터 컬럼으로 뜨는지(자극물 없음) 재확인.

- [ ] **Step 5: 커밋**

```bash
git add web/components/interview-flow.tsx
git commit -m "질문에 자극물이 붙으면 2분할, 없으면 센터 컬럼으로 갈리게 한다"
```

---

### Task 5: 동의(R-1)·완료(R-4) 화면을 같은 결로 맞춘다

**Files:**
- Modify: `web/app/i/[projectId]/respondent-view.tsx` (consent 섹션 · done 섹션 · 스테이지 폭)

**Interfaces:**
- Consumes: 없음(기존 상태/콜백 보존)
- Produces: 데스크톱 중심 + 반응형으로 정렬된 동의·완료 화면. `InterviewFlow`에 `stimulus`를 넘기지 않는다(Phase 1).

- [ ] **Step 1: 스테이지 폭 — 데스크톱 중심 + 반응형**

`<main>` 폭 로직(현재 `stage === "interview" ? "max-w-3xl" : "max-w-lg"`)을 유지하되 인터뷰는 카드가 `max-w-2xl`를 자체적으로 가지므로 컨테이너는 넉넉히:
```tsx
      <main
        className={`mx-auto min-h-screen w-full px-4 py-8 sm:px-6 sm:py-14 ${
          stage === "interview" ? "max-w-3xl" : "max-w-xl"
        }`}
      >
```

- [ ] **Step 2: 동의 화면 정렬(우리 토큰 유지, 여백만 Outset결)**

consent 섹션의 헤더/인트로/동의 카드/CTA는 기능 그대로 두고 간격만 다듬는다. 현재 `<section>`(consent)에서 eyebrow·제목·설명은 유지하고, 동의 카드(`<Card className="mt-6 p-5">`)와 CTA 사이 여백을 통일:
```tsx
          <section>
            <p className="eyebrow">{"음성 인터뷰"}</p>
            <h1 className="mt-4 text-title">{project.title || project.topic}</h1>
            <p className="mt-3 text-base leading-relaxed text-ink-soft">
              AI 진행자가 음성으로 질문을 드려요. 말하거나 직접 입력해서 답해 주시면 됩니다. 5~10분 정도 걸려요.
            </p>
            {/* 동의 카드(R-1): 기존 dl/label 마크업 그대로 유지 */}
            {/* ... 현재 93-134 블록 변경 없음 ... */}
            {startError && <p className="mt-3 text-meta text-nogo">{startError}</p>}
            <Button type="button" size="lg" onClick={begin} disabled={!agreed || starting} className="mt-6 w-full sm:w-auto">
              {starting ? "준비 중…" : "동의하고 인터뷰 시작"}
            </Button>
            {!agreed && (
              <p className="mt-2 text-2xs text-ink-faint">동의해 주셔야 인터뷰를 시작할 수 있어요.</p>
            )}
          </section>
```
(동의 항목 dl 블록 자체는 법적 문구라 문구·구조를 바꾸지 않는다. `RETENTION` 상수도 유지.)

- [ ] **Step 3: 인터뷰 스테이지 — 제목 제거(카드 상단바가 대체)·stimulus 미전달**

interview 스테이지(현재 154-164)에서 중복 제목(`<h1 className="mb-4 ...">`)을 제거하고 카드만 중앙에:
```tsx
        ) : stage === "interview" && session ? (
          <section>
            <InterviewFlow
              projectId={projectId}
              sessionId={session.id}
              onComplete={handleComplete}
            />
            <p className="mt-4 text-center text-2xs leading-relaxed text-ink-faint">
              답변은 익명으로 저장되며 개인정보는 자동으로 가려집니다.
            </p>
          </section>
```
(`stimulus`는 넘기지 않는다 — Phase 1은 데이터 없음.)

- [ ] **Step 4: 완료 화면 정렬**

done 섹션(현재 166-179)은 문구 유지, 카드 정렬만 통일:
```tsx
          <section className="mx-auto max-w-md rounded-2xl bg-surface p-8 text-center shadow-card ring-1 ring-line sm:p-10">
            <p className="text-3xl" aria-hidden>✅</p>
            <h1 className="mt-4 text-title">제출됐어요</h1>
            <p className="mt-3 text-base leading-relaxed text-ink-soft">
              시간 내어 답변해 주셔서 감사합니다.{turnCount > 0 && ` 총 ${turnCount}개의 답변을 남겨주셨어요.`}
            </p>
            <p className="mt-4 text-meta leading-relaxed text-ink-faint">
              답변은 익명으로 저장되었고, {RETENTION} 보관 후 파기됩니다. 이제 창을 닫으셔도 좋아요.
            </p>
          </section>
```

- [ ] **Step 5: 검증**

Run: `cd web && npm run typecheck` → PASS
Run: `cd web && npm run build` → 성공
시각 확인: 동의 → (테스트 프로젝트로) 인터뷰 → 완료가 데스크톱·모바일 폭에서 일관된 결로 흐르는지.

- [ ] **Step 6: 커밋**

```bash
git add web/app/i/[projectId]/respondent-view.tsx
git commit -m "동의·완료 화면을 인터뷰와 같은 결로 정렬한다"
```

---

### Task 6: 전체 흐름 시각 QA + lint + 최종 확인

**Files:** 없음(검증·미세 조정)

- [ ] **Step 1: 헤드리스 시각 QA**

`/qa` (또는 `/browse`) 스킬로 응답자 라우트를 데스크톱(≥1024px)과 모바일(375px) 두 폭에서 확인한다. 대상: 로컬 `npm run dev` 또는 배포된 테스트 프로젝트 `https://mindlens-web-128792069861.asia-northeast3.run.app/i/p_293daf165c5d`. 아트팩트 목업(방향 1 + 동의)과 대조해 여백·타이포·정렬 차이를 잡는다.

- [ ] **Step 2: 발견된 시각 이슈 수정**

QA에서 나온 차이(간격·줄바꿈·버튼 높이 등)를 해당 Task의 클래스에서 조정한다. 로직은 건드리지 않는다.

- [ ] **Step 3: lint·typecheck·build 최종 통과**

```bash
cd web && npm run lint && npm run typecheck && npm run build
```
Expected: 3종 모두 통과 (CI `test.yml`이 도는 것과 동일)

- [ ] **Step 4: 커밋(수정이 있었다면)**

```bash
git add web
git commit -m "응답자 리디자인 시각 QA 피드백을 반영한다"
```

---

## 이후 로드맵 (이 계획 범위 밖 — 참고)

PRD(`AI-Moderated-Interview-PRD.md`)를 mindlens에 얹는 순서. 각 Phase는 자체 spec → plan 사이클을 별도로 돈다.

- **Phase 2 — 응답 버킷(코드북):** 가이드 생성(F2.3)에 질문별 MECE 버킷 + 정의 + 캐치올 추가, 실시간 분류/확신도(F6.1) 도입, 프로빙을 버킷 확신도로 구동(F5.1). PRD의 핵심 차별점. (백엔드 중심 — 스키마·프롬프트·그래프)
- **Phase 3 — 분석 대시보드:** 질문-컬럼 그리드(F6.2), 버킷 분포·근거 스팬 drill·수동 교정(F6.4). (의뢰자 웹)
- **Phase 4 — 지식팩 3계층:** 브리핑 RAG를 pin·읽기전용·발화금지·blocklist·leak-rate 게이트로 승격(F1.5). 안전 핵심. leak rate 0%가 릴리즈 게이트.
- **Phase 5+ — 스크리너·쿼터·부정탐지(F4), CI evals(F8), (v2) 자극물 데이터 연동·다국어.** 이번 Task 3·4가 자극물 UI를 이미 준비해 둠 → v2에서 백엔드만 붙이면 된다.

---

## Self-Review

- **Spec 커버리지:** 이 계획은 PRD **F5.3(참가자 UI)** 중 이번 범위(리디자인·아바타 제거·데스크톱+반응형·진행률 프로빙 미반영·자극물 UI 예약)를 Task 1~6이 모두 덮는다. F5.3의 "재진입 이어하기(세션토큰 24h)"는 기능이라 이번 범위에서 제외 → 로드맵 Phase 5로 이월(명시). 자극물 **데이터/모더레이터 연동**은 의도적으로 v2(로드맵)로 분리.
- **플레이스홀더 스캔:** 각 Task에 실제 JSX/TS 코드와 정확한 파일·명령·기대결과를 담았다. "적절히 스타일" 류 없음. 단, 픽셀 최종값은 Task 6 시각 QA에서 아트팩트와 대조해 확정한다고 명시(웹 유닛러너 부재라 repo의 실제 검증 방식).
- **타입 일관성:** `Stimulus`(Task 3) → `InterviewFlow`의 `stimulus?: Stimulus` prop(Task 4) → `InterviewStimulus`(Task 3) 이름·필드 일치. `QuestionAndAnswer`(Task 2) props와 `qaProps`(Task 4) 키 일치.
- **가정 확인 완료:** `TurnOut.is_probe`(`web/lib/api.ts:83`) 존재 확인 → 진행률 로직 유효. `bg-line-soft`(#f3f3f3) 토큰 존재 확인 → 자극물 배경 유효. `bg-alt` 토큰은 없음(사용 안 함).
