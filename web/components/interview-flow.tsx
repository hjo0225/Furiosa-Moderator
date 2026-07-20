"use client";

// 인터뷰 모드 — 모더레이터 주도 자유 인터뷰(채팅형). 진행자가 질문을 던지고(TTS 읽기),
// 응답자가 음성/타이핑으로 답하면 다음 발화를 생성한다. done:true 면 onComplete(전사).
//
// [이식 수정] 원본은 `interviewTurn(goal, history, asked, lang)` — **대화 이력을 클라이언트가 통째로**
// 매 턴 올려보내는 stateless 계약이었다. 새 백엔드는 세션 기반이라 이력·asked 를 서버가 들고 있고,
// 클라이언트는 `sendTurn(projectId, sessionId, text)` 로 **직전 발화 한 줄만** 보낸다.
// 그래서 next(history, askedN) → advance(text) 로 바꿨다. turns/asked 는 이제 렌더 전용 로컬 상태다.
// 함께 배선한 것: voice-input.ts(전사 2회 실패 → 텍스트 폴백), use-stick-to-bottom(바닥 고정).
import { useCallback, useEffect, useRef, useState } from "react";

import { useRecorder, useTts } from "@/hooks/useAudio";
import { useStickToBottom } from "@/hooks/use-stick-to-bottom";
import { sendTurn, transcribeAudio, type TranscriptTurn } from "@/lib/api";
import { initialVoiceInput, reduceVoiceInput, type VoiceInputState } from "@/lib/voice-input";
import { cn } from "@/lib/utils";

// idle = 시작 전(브라우저 자동재생 정책상 첫 진행자 음성은 사용자 클릭 제스처가 있어야 재생된다)
type Phase = "idle" | "thinking" | "awaiting" | "recording" | "transcribing" | "done";

export function InterviewFlow({
  projectId,
  sessionId,
  locale = "ko",
  en = false,
  onComplete,
}: {
  projectId: string;
  sessionId: string;
  locale?: string;
  en?: boolean;
  onComplete: (transcript: TranscriptTurn[]) => void;
}) {
  const tts = useTts(locale);
  const recorder = useRecorder();
  const [turns, setTurns] = useState<TranscriptTurn[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [voiceInput, setVoiceInput] = useState<VoiceInputState>(initialVoiceInput);
  const started = useRef(false);
  const { streamRef, follow, resumeLatest } = useStickToBottom([turns, phase]);

  // 녹음 미지원이면 즉시 텍스트로 폴백(편도) — 마이크 버튼이 아예 없는 화면에서 헤매지 않게.
  useEffect(() => {
    if (!recorder.supported) setVoiceInput((s) => reduceVoiceInput(s, { type: "unsupported" }));
  }, [recorder.supported]);

  /** 응답자 발화 한 줄(빈 문자열이면 오프닝 요청) → 진행자의 다음 한 마디. */
  const advance = useCallback(
    async (history: TranscriptTurn[], text: string) => {
      setPhase("thinking");
      setError(null);
      try {
        const out = await sendTurn(projectId, sessionId, text, en ? "en" : "ko");
        const msg = (out.message ?? "").trim();
        // 진행자 발화가 비면(LLM 히컵) 빈 말풍선·빈 TTS 대신 인터뷰를 정리하고 종료한다.
        if (!msg) {
          setPhase("done");
          onComplete(history);
          return;
        }
        const withMod: TranscriptTurn[] = [
          ...history,
          { role: "moderator", text: msg, emotion: out.emotion },
        ];
        setTurns(withMod);
        if (tts.available) void tts.speak(msg);
        if (out.done) {
          setPhase("done");
          onComplete(withMod);
        } else {
          setPhase("awaiting");
        }
      } catch {
        setError(en ? "Interview failed. Please try again." : "인터뷰 진행에 실패했어요. 다시 시도해 주세요.");
        setPhase("awaiting");
      }
    },
    [projectId, sessionId, tts, onComplete, en],
  );

  // 자동 시작하지 않는다 — 사용자가 '인터뷰 시작'을 눌러야(제스처) 첫 진행자 음성이 재생된다.
  const begin = useCallback(() => {
    if (started.current) return;
    started.current = true;
    void advance([], ""); // 빈 text = 오프닝 요청
  }, [advance]);

  const sendAnswer = useCallback(
    async (text: string) => {
      const t = text.trim();
      if (!t || phase === "thinking" || phase === "done") return;
      const updated: TranscriptTurn[] = [...turns, { role: "respondent", text: t }];
      setTurns(updated);
      setInput("");
      await advance(updated, t);
    },
    [turns, phase, advance],
  );

  const toggleRecord = useCallback(async () => {
    if (phase === "recording") {
      const blob = await recorder.stop(); // 절대 reject 하지 않는다 — recorder-session.ts 계약
      setPhase("transcribing");
      if (!blob) {
        setPhase("awaiting");
        return;
      }
      try {
        // 200 ≠ 성공. ok=false 는 엔진 실패, ok=true+빈 텍스트는 무음/미인식 — 다르게 안내한다.
        const { text, ok } = await transcribeAudio(blob, locale);
        if (ok && text.trim()) {
          setVoiceInput((s) => reduceVoiceInput(s, { type: "transcribe_ok" }));
          await sendAnswer(text);
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
        setPhase("awaiting");
      } catch {
        setVoiceInput((s) => reduceVoiceInput(s, { type: "transcribe_failed" }));
        setError(en ? "Transcription failed." : "음성 인식에 실패했어요.");
        setPhase("awaiting");
      }
    } else if (phase === "awaiting") {
      const ok = await recorder.start();
      if (ok) setPhase("recording");
      else {
        setVoiceInput((s) => reduceVoiceInput(s, { type: "permission_denied" }));
        setError(en ? "Microphone unavailable." : "마이크를 사용할 수 없어요. 직접 입력해 주세요.");
      }
    }
  }, [phase, recorder, locale, sendAnswer, en]);

  const canType = phase === "awaiting";

  if (phase === "idle") {
    return (
      <div className="flex min-h-[26rem] flex-col items-center justify-center gap-4 rounded-2xl bg-surface p-8 text-center shadow-card">
        <p className="text-2xl" aria-hidden>
          🎙
        </p>
        <p className="max-w-sm text-base leading-relaxed text-ink-soft">
          {en
            ? "A moderator will guide the interview by voice. Answer by speaking or typing."
            : "진행자가 음성으로 인터뷰를 이끕니다. 말하거나 직접 입력해 답하면 됩니다."}
        </p>
        <button
          type="button"
          onClick={begin}
          className="rounded-full bg-accent-solid px-6 py-3 text-base font-medium text-accent-on shadow-card"
        >
          {en ? "Start interview" : "인터뷰 시작"}
        </button>
        {!tts.available && (
          <p className="text-2xs text-ink-faint">
            {en ? "(Voice playback unavailable — text only)" : "(음성 재생 비활성 — 텍스트로 진행)"}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="flex min-h-[26rem] flex-col rounded-2xl bg-surface p-4 shadow-card sm:p-5">
      <div ref={streamRef} className="relative max-h-[60vh] flex-1 space-y-3 overflow-y-auto">
        {turns.map((t, i) => (
          <div key={i} className={t.role === "respondent" ? "text-right" : "text-left"}>
            {t.role === "moderator" && (
              <p className="mb-0.5 font-mono text-2xs uppercase text-accent">
                🎙 {en ? "Moderator" : "진행자"}
              </p>
            )}
            <span
              className={cn(
                "inline-block max-w-[85%] rounded-2xl px-3.5 py-2 text-base leading-relaxed",
                t.role === "respondent" ? "bg-accent-solid text-accent-on" : "bg-bg text-ink shadow-edge",
              )}
            >
              {t.text}
            </span>
            {t.role === "moderator" && tts.available && (
              <button
                type="button"
                onClick={() => void tts.speak(t.text)}
                className="ml-2 align-middle text-2xs text-accent underline"
              >
                {en ? "Replay" : "다시 듣기"}
              </button>
            )}
          </div>
        ))}
        {phase === "thinking" && (
          <p className="text-meta text-ink-faint">
            {en ? "Moderator is thinking…" : "진행자가 생각 중…"}
          </p>
        )}
        {phase === "recording" && (
          <p className="text-right text-meta text-nogo">
            ● {en ? "Recording" : "녹음 중"} {recorder.elapsedSec}s
          </p>
        )}
        {phase === "transcribing" && (
          <p className="text-right text-meta text-ink-faint">
            {en ? "Transcribing…" : "음성 인식 중…"}
          </p>
        )}
        {error && <p className="text-meta text-nogo">{error}</p>}
      </div>

      {!follow && (
        <button
          type="button"
          onClick={resumeLatest}
          className="mx-auto mt-2 rounded-full bg-bg px-3 py-1 text-2xs text-ink-soft ring-1 ring-line"
        >
          {en ? "Jump to latest" : "최신 대화로"}
        </button>
      )}

      {phase === "done" ? (
        <p className="mt-3 text-center text-meta text-ink-soft">
          {en ? "Interview complete. Saving…" : "인터뷰가 끝났어요. 저장 중…"}
        </p>
      ) : (
        <>
          {voiceInput.mode === "text" && recorder.supported && (
            <p className="mt-3 text-center text-2xs text-ink-faint">
              {en
                ? "Switched to typing. The mic still works if you want to try again."
                : "키보드 입력으로 전환했어요. 마이크는 계속 쓸 수 있어요."}
            </p>
          )}
          <div className="mt-3 flex items-end gap-2">
            {recorder.supported && (
              <button
                type="button"
                onClick={() => void toggleRecord()}
                disabled={phase === "thinking" || phase === "transcribing"}
                aria-label={en ? "Record answer" : "음성으로 답하기"}
                className={cn(
                  "shrink-0 rounded-full px-3 py-2 text-meta font-medium transition-colors disabled:opacity-40",
                  phase === "recording"
                    ? "bg-nogo/10 text-nogo"
                    : "bg-bg text-ink-soft ring-1 ring-line hover:bg-accent-wash",
                )}
              >
                {phase === "recording" ? (en ? "■ Stop" : "■ 정지") : "🎤"}
              </button>
            )}
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                // IME 조합 중(한국어 입력 확정)의 Enter 는 전송하지 않는다.
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  void sendAnswer(input);
                }
              }}
              rows={1}
              disabled={!canType}
              placeholder={en ? "Type or speak your answer" : "답변을 입력하거나 🎤로 말하세요"}
              className="flex-1 resize-none rounded-lg bg-bg px-3 py-2 text-base text-ink ring-1 ring-line placeholder:text-ink-faint/60 focus:outline-none focus:ring-accent disabled:opacity-60"
            />
            <button
              type="button"
              onClick={() => void sendAnswer(input)}
              disabled={!canType || !input.trim()}
              className="shrink-0 rounded-lg bg-accent-solid px-4 py-2 text-base font-medium text-accent-on disabled:opacity-40"
            >
              {en ? "Send" : "전송"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
