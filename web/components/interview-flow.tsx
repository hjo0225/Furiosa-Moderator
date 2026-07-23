"use client";

// 인터뷰 모드 — 카드형 1문1답. 채팅 스트림이 아니라 '질문 하나 → 답변 하나 → 다음'을 사용자가
// 직접 넘긴다. 왼쪽 진행자 아바타(말할 때 진폭 반응), 오른쪽 질문 + 녹음/입력 + 다음.
//
// 진행자는 여전히 동적이다 — '다음'을 누르면 서버(next_turn)가 직전 답변을 보고 꼬리질문(래더링)
// 이나 새 주제를 낸다. UI 만 카드형이고, 커버리지·래더링·콜백은 서버에 그대로 살아있다.
//
// [이식 수정] 세션 기반 백엔드라 이력·asked 는 서버가 들고, 클라이언트는 sendTurn 으로 직전 발화
// 한 줄만 보낸다. 함께 배선: voice-input.ts(전사 2회 실패 → 텍스트 폴백), useTts unlock/getLevel
// (자동재생 권한 확보 + 아바타 진폭).
import { useCallback, useEffect, useRef, useState } from "react";
import { Circle, Mic, Square, Volume2 } from "lucide-react";

import { InterviewStimulus } from "@/components/interview-stimulus";
import { ModeratorAvatar } from "@/components/moderator-avatar";
import { Button, Card, fieldClass } from "@/components/shared";
import { useRecorder, useTts } from "@/hooks/useAudio";
import { sendTurn, submitSession, transcribeAudio, type Stimulus } from "@/lib/api";
import { initialVoiceInput, reduceVoiceInput, type VoiceInputState } from "@/lib/voice-input";
import { cn } from "@/lib/utils";

// idle       = 시작 전(자동재생 정책상 첫 진행자 음성은 클릭 제스처가 있어야 재생된다)
// asking     = 진행자의 다음 질문 생성 중
// answering  = 질문이 나왔고 답변 대기(녹음/타이핑). input 이 차 있으면 '다음' 가능
// recording  / transcribing = 음성 답변 처리
// review     = 진행자가 마무리(done) → 제출 대기
// done       = 제출 완료
type Phase =
  | "idle"
  | "asking"
  | "answering"
  | "recording"
  | "transcribing"
  | "review"
  | "done";

export function InterviewFlow({
  projectId,
  sessionId,
  locale = "ko",
  en = false,
  stimulus: initialStimulus,
  onComplete,
}: {
  projectId: string;
  sessionId: string;
  locale?: string;
  en?: boolean;
  stimulus?: Stimulus; // 초기값(선택). 실질 소스는 매 턴 응답(out.stimulus) — 문항마다 달라진다.
  onComplete: (answerCount: number) => void;
}) {
  const tts = useTts(locale);
  const recorder = useRecorder();
  const [phase, setPhase] = useState<Phase>("idle");
  const [question, setQuestion] = useState("");
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [voiceInput, setVoiceInput] = useState<VoiceInputState>(initialVoiceInput);
  const [answerCount, setAnswerCount] = useState(0);
  const [mainQ, setMainQ] = useState(0); // 프로빙 제외 '본 질문' 번호 (PRD F5.3: 프로빙은 진행률 미반영)
  const [voiceFilled, setVoiceFilled] = useState(false); // 방금 답변이 음성 전사에서 왔나(확인 안내용)
  const [submitting, setSubmitting] = useState(false);
  // 제시 자료는 문항마다 다르다 — 매 턴 응답(out.stimulus)이 실질 소스다. 초기값만 프롭에서 받는다.
  const [stimulus, setStimulus] = useState<Stimulus | undefined>(initialStimulus);
  const started = useRef(false);

  // 녹음 미지원이면 즉시 텍스트로 폴백(편도).
  useEffect(() => {
    if (!recorder.supported) setVoiceInput((s) => reduceVoiceInput(s, { type: "unsupported" }));
  }, [recorder.supported]);

  /** 진행자의 다음 한 마디를 받아온다. text 가 빈 문자열이면 오프닝 요청. */
  const advance = useCallback(
    async (text: string) => {
      setPhase("asking");
      setError(null);
      try {
        const out = await sendTurn(projectId, sessionId, text, en ? "en" : "ko");
        setStimulus(out.stimulus ?? undefined); // 이번 문항의 제시 자료로 교체(없으면 단일 컬럼으로 복귀)
        const msg = (out.message ?? "").trim();
        if (msg && !out.done && !out.is_probe) setMainQ((n) => n + 1); // 오프닝·본 질문만 카운트, 프로빙 제외
        if (text) setAnswerCount((n) => n + 1); // 방금 전달된 답변을 센다(성공 시에만)
        setInput("");
        setVoiceFilled(false);
        // 진행자 발화가 비면(LLM 히컵) 지금까지 답한 건 제출할 가치가 있으니 마무리 단계로.
        if (!msg) {
          setQuestion(en ? "Thank you for your time." : "말씀 감사합니다.");
          setPhase("review");
          return;
        }
        setQuestion(msg);
        if (tts.available) void tts.speak(msg);
        setPhase(out.done ? "review" : "answering");
      } catch {
        // 실패해도 답변(input)은 지우지 않는다 — 재시도할 수 있게. 오프닝 실패면 시작 화면으로.
        setError(en ? "Something went wrong. Please try again." : "문제가 생겼어요. 다시 시도해 주세요.");
        if (!question) {
          started.current = false;
          setPhase("idle");
        } else {
          setPhase("answering");
        }
      }
    },
    [projectId, sessionId, tts, en, question],
  );

  // 자동 시작하지 않는다 — '인터뷰 시작' 클릭(제스처) 안에서 오디오 권한을 확보하고 오프닝을 받는다.
  const begin = useCallback(() => {
    if (started.current) return;
    started.current = true;
    tts.unlock(); // 첫 발화 play() 는 LLM 생성 뒤라 제스처 창을 벗어난다 — 여기서 미리 깨워 둔다.
    void advance("");
  }, [advance, tts]);

  /** '다음' — 지금 답변을 서버에 보내고 다음 질문을 받는다. */
  const goNext = useCallback(() => {
    const t = input.trim();
    if (!t || phase === "asking" || phase === "recording" || phase === "transcribing") return;
    void advance(t);
  }, [input, phase, advance]);

  /** 제출해야 비로소 '응답 1건'이 된다. 실패하면 화면을 넘기지 않고 재시도를 남긴다. */
  const submit = useCallback(async () => {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await submitSession(projectId, sessionId);
      setPhase("done");
      onComplete(answerCount);
    } catch {
      setError(en ? "Submission failed. Please try again." : "제출에 실패했어요. 다시 시도해 주세요.");
    } finally {
      setSubmitting(false);
    }
  }, [projectId, sessionId, answerCount, onComplete, submitting, en]);

  const toggleRecord = useCallback(async () => {
    if (phase === "recording") {
      const blob = await recorder.stop(); // 절대 reject 하지 않는다 — recorder-session.ts 계약
      setPhase("transcribing");
      if (!blob) {
        setPhase("answering");
        return;
      }
      try {
        // 200 ≠ 성공. ok=false 는 엔진 실패, ok=true+빈 텍스트는 무음/미인식 — 다르게 안내한다.
        const { text, ok } = await transcribeAudio(blob, locale);
        if (ok && text.trim()) {
          setVoiceInput((s) => reduceVoiceInput(s, { type: "transcribe_ok" }));
          setInput(text.trim()); // 카드에 채워 확인·수정·재녹음할 수 있게 (바로 넘기지 않는다)
          setVoiceFilled(true);
          setPhase("answering");
          return;
        }
        setVoiceInput((s) => reduceVoiceInput(s, { type: "transcribe_failed" }));
        setError(
          ok
            ? en
              ? "Couldn't catch that. Please type your answer or try recording again."
              : "음성을 알아듣지 못했어요. 직접 입력하거나 다시 녹음해 주세요."
            : en
              ? "Speech recognition failed. Please type your answer."
              : "음성 인식에 실패했어요. 직접 입력해 주세요.",
        );
        setPhase("answering");
      } catch {
        setVoiceInput((s) => reduceVoiceInput(s, { type: "transcribe_failed" }));
        setError(en ? "Transcription failed." : "음성 인식에 실패했어요.");
        setPhase("answering");
      }
    } else if (phase === "answering") {
      const ok = await recorder.start();
      if (ok) setPhase("recording");
      else {
        setVoiceInput((s) => reduceVoiceInput(s, { type: "permission_denied" }));
        setError(en ? "Microphone unavailable." : "마이크를 사용할 수 없어요. 직접 입력해 주세요.");
      }
    }
  }, [phase, recorder, locale, en]);

  const canType = phase === "answering";
  const canNext = phase === "answering" && !!input.trim();
  const busy = phase === "asking";

  // --- 시작 전 화면 --------------------------------------------------------
  if (phase === "idle") {
    return (
      <Card className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center gap-6 rounded-xl p-8 text-center ring-warm-border sm:p-10">
        <p className="eyebrow">{en ? "Voice interview" : "음성 인터뷰"}</p>
        <p className="max-w-md text-lead leading-relaxed text-warm-ink-soft">
          {en
            ? "A moderator will guide the interview by voice. Answer by speaking or typing, then press Next."
            : "진행자가 음성으로 질문을 드립니다. 말하거나 입력해 답한 뒤 ‘다음’을 눌러 주세요."}
        </p>
        <Button type="button" size="lg" onClick={begin} className="w-full max-w-xs">
          {en ? "Start interview" : "인터뷰 시작"}
        </Button>
        {error && <p className="text-meta text-nogo">{error}</p>}
        {!tts.available && (
          <p className="text-2xs text-warm-ink-soft">
            {en ? "(Voice playback unavailable — text only)" : "(음성 재생 비활성 — 텍스트로 진행)"}
          </p>
        )}
      </Card>
    );
  }

  // --- 인터뷰 화면 (센터 컬럼) ---------------------------------------------
  const qaProps = {
    en, busy, question, tts, phase, input, setInput, goNext,
    toggleRecord, recorder, voiceFilled, voiceInput, canType, canNext, error,
  };
  return (
    <Card className="mx-auto flex w-full max-w-3xl flex-1 flex-col overflow-hidden rounded-xl p-0 ring-warm-border">
      {/* 상단 — 진행자 오브 + 진행률 (프로빙 미반영) */}
      <div className="flex items-center justify-between gap-3 border-b border-warm-border px-5 py-3 sm:px-6">
        <p className="flex items-center gap-2 font-mono text-2xs uppercase tracking-wider text-warm-ink-soft">
          <ModeratorAvatar speaking={tts.speaking} size={22} />
          {en ? "Moderator" : "진행자"}
        </p>
        {phase !== "review" && phase !== "done" && mainQ > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-2xs font-medium text-warm-ink-soft">
              {en ? `Question ${mainQ}` : `질문 ${mainQ}`}
            </span>
            <span className="h-1 w-24 overflow-hidden rounded-full bg-warm-border">
              <span
                className="block h-full rounded-full bg-red transition-[width] duration-500"
                style={{ width: `${Math.min(90, mainQ * 14)}%` }}
              />
            </span>
          </div>
        )}
      </div>

      <div className="flex flex-1 flex-col p-5 sm:p-8">
        {phase === "review" || phase === "done" ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
            <p className="text-title text-ink">{question}</p>
            {phase === "done" ? (
              <p className="text-meta text-warm-ink-soft">{en ? "Submitted. Thank you!" : "제출됐어요. 감사합니다!"}</p>
            ) : (
              <>
                <p className="text-meta text-warm-ink-soft">
                  {en
                    ? "That's the end of the interview. Submit to send your answers."
                    : "인터뷰가 끝났어요. 제출해야 답변이 전달됩니다."}
                </p>
                <Button type="button" size="lg" onClick={() => void submit()} disabled={submitting} className="w-full max-w-xs">
                  {submitting ? (en ? "Submitting…" : "제출 중…") : en ? "Submit answers" : "답변 제출하기"}
                </Button>
                <p className="text-2xs text-warm-ink-soft">
                  {en ? "Your answers are only counted once submitted." : "제출하지 않고 창을 닫으면 답변이 집계되지 않아요."}
                </p>
                {error && <p className="text-meta text-nogo">{error}</p>}
              </>
            )}
          </div>
        ) : stimulus ? (
          // 자극물 모드 — 2분할(방향 3): 왼쪽 자극물, 오른쪽 질문+답변
          <div className="grid flex-1 gap-5 md:grid-cols-[1.4fr_1fr]">
            <div className="min-h-[16rem] md:min-h-0">
              <InterviewStimulus stimulus={stimulus} />
            </div>
            <div className="flex min-h-0 flex-col md:border-l md:border-warm-border md:pl-6">
              <QuestionAndAnswer {...qaProps} />
            </div>
          </div>
        ) : (
          // 기본 — 센터 컬럼(방향 1). 카드 폭을 그대로 써서 화면을 채운다
          <div className="flex w-full flex-1 flex-col">
            <QuestionAndAnswer {...qaProps} />
          </div>
        )}
      </div>
    </Card>
  );
}

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
            <span className="animate-pulse text-warm-ink-soft">
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
          className="mt-3 inline-flex items-center gap-1.5 self-start text-meta font-medium text-red"
        >
          <Volume2 className="h-4 w-4" aria-hidden="true" />
          {en ? "Replay" : "다시 듣기"}
        </button>
      )}

      {/* 답변 */}
      <div className="mt-auto pt-6">
        {voiceFilled && canType && (
          <p className="mb-2 text-2xs text-warm-ink-soft">
            {en ? "Here's what we heard — edit it or re-record, then press Next." : "이렇게 들었어요 — 고치거나 다시 녹음한 뒤 ‘다음’을 눌러 주세요."}
          </p>
        )}
        {voiceInput.mode === "text" && recorder.supported && (
          <p className="mb-2 text-2xs text-warm-ink-soft">
            {en ? "Switched to typing. The mic still works if you want to try again." : "키보드 입력으로 전환했어요. 마이크는 계속 쓸 수 있어요."}
          </p>
        )}
        {phase === "recording" && (
          <p className="mb-2 flex items-center gap-1.5 text-meta font-medium text-red">
            <Circle className="h-2.5 w-2.5 animate-pulse" fill="currentColor" aria-hidden="true" />
            {en ? "Recording" : "녹음 중"} <span className="font-mono tabular-nums">{recorder.elapsedSec}s</span>
          </p>
        )}
        {phase === "transcribing" && (
          <p className="mb-2 text-meta text-warm-ink-soft">{en ? "Transcribing…" : "음성 인식 중…"}</p>
        )}
        {error && <p className="mb-2 text-meta text-nogo">{error}</p>}

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
          placeholder={en ? "Type or speak your answer" : "답변을 입력하거나 마이크로 말하세요"}
          className={fieldClass("min-h-[7rem] w-full resize-none text-lead ring-warm-border")}
        />
        {/* 컨트롤 — 마이크·다음 모두 공유 Button(동일 h-14 pill)으로 통일 */}
        <div className="mt-3 flex items-center gap-2">
          {recorder.supported && (
            <Button
              type="button"
              variant="secondary"
              size="lg"
              onClick={() => void toggleRecord()}
              disabled={busy || phase === "transcribing"}
              aria-label={en ? "Record answer" : "음성으로 답하기"}
              className={cn(
                "w-14 shrink-0 !px-0 !bg-blush !text-red-dark !ring-warm-border hover:!bg-blush/70",
                phase === "recording" &&
                  "!bg-red !text-white !ring-red hover:!bg-red-dark animate-pulse-indigo",
              )}
            >
              {phase === "recording" ? (
                <Square className="h-5 w-5" fill="currentColor" aria-hidden="true" />
              ) : (
                <Mic className="h-5 w-5" aria-hidden="true" />
              )}
            </Button>
          )}
          <Button type="button" size="lg" onClick={goNext} disabled={!canNext} className="flex-1">
            {en ? "Next" : "다음"}
          </Button>
        </div>
      </div>
    </>
  );
}
