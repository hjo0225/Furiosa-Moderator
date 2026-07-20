"use client";

// 음성 훅 — 구버전 mindlens_backend useAudio 이식.
//  useTts: 문항/안내문 읽어주기(음성·속도·볼륨 설정, localStorage 영속).
//  useRecorder: 주관식 음성 답변 녹음(MediaRecorder) → Blob.
//    [T-AUDIO-APPEND] pause/resume 단일 세션 지원 — phase(idle|recording|paused)·경과초·
//    pauseSupported(iOS 사파리 감지). start/stop 계약은 보존(미지원 폴백·인터뷰 플로우용).
// 둘 다 graceful — TTS 음성 목록이 비면(미설정) 읽어주기 비활성, 녹음 미지원이면 버튼 숨김.
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchVoices, synthesizeSpeech, type SpeechVoice } from "@/lib/api";
import {
  elapsedSeconds,
  initialTimer,
  recorderSupportsPause,
  stopRecording,
  timerPause,
  timerStart,
  type ElapsedTimer,
} from "@/lib/recorder-session";

export type TtsSettings = {
  voiceName: string;
  speakingRate: number; // 0.5 ~ 2.0
  volumeGainDb: number; // -10 ~ +10
};

const TTS_KEY = "mindlens:ttsSettings";
const DEFAULT_TTS: TtsSettings = { voiceName: "", speakingRate: 1, volumeGainDb: 0 };

export function useTts(locale: string) {
  const [voices, setVoices] = useState<SpeechVoice[]>([]);
  const [settings, setSettingsState] = useState<TtsSettings>(DEFAULT_TTS);
  const [speaking, setSpeaking] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // 설정 복원(최초 1회)
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(TTS_KEY);
      if (raw) setSettingsState({ ...DEFAULT_TTS, ...JSON.parse(raw) });
    } catch {
      /* 무시 */
    }
  }, []);

  const setSettings = useCallback((patch: Partial<TtsSettings>) => {
    setSettingsState((prev) => {
      const next = { ...prev, ...patch };
      try {
        window.localStorage.setItem(TTS_KEY, JSON.stringify(next));
      } catch {
        /* 무시 */
      }
      return next;
    });
  }, []);

  // 음성 목록 갱신(미설정/실패면 빈 목록 → 읽어주기 비활성).
  // [이식 수정] 새 백엔드의 GET /api/speech/voices 는 언어 인자를 받지 않는다.
  // locale 은 언어 전환 시 재조회 트리거로만 남긴다(엔진이 언어별 목록을 주도록 바뀌어도 그대로 동작).
  useEffect(() => {
    let alive = true;
    fetchVoices()
      .then((v) => alive && setVoices(v))
      .catch(() => alive && setVoices([]));
    return () => {
      alive = false;
    };
  }, [locale]);

  const stop = useCallback(() => {
    audioRef.current?.pause();
    audioRef.current = null;
    setSpeaking(false);
  }, []);

  const speak = useCallback(
    async (text: string) => {
      if (!text.trim()) return;
      stop();
      setSpeaking(true);
      try {
        // [이식 수정] 새 백엔드는 {text, voice?} 만 받는다(속도·볼륨 파라미터 없음).
        // 기능을 버리지 않고 재생 측에서 적용한다 — 설정 UI·localStorage 영속은 그대로 살아있다.
        const blob = await synthesizeSpeech({
          text,
          voice: settings.voiceName || undefined,
        });
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audio.playbackRate = Math.min(2, Math.max(0.5, settings.speakingRate));
        audio.volume = Math.min(1, Math.pow(10, settings.volumeGainDb / 20));
        audioRef.current = audio;
        const cleanup = () => {
          setSpeaking(false);
          URL.revokeObjectURL(url);
        };
        audio.onended = cleanup;
        audio.onerror = cleanup;
        await audio.play();
      } catch {
        setSpeaking(false);
      }
    },
    [settings, stop],
  );

  // 언마운트 시 재생 중단
  useEffect(() => () => stop(), [stop]);

  return { voices, settings, setSettings, speak, stop, speaking, available: voices.length > 0 };
}

export type RecorderPhase = "idle" | "recording" | "paused";

export function useRecorder() {
  // 세션 상태 — idle → recording ⇄ paused → (stop) idle. 최종 블롭은 stop 에서 1개로 조립.
  const [phase, setPhase] = useState<RecorderPhase>("idle");
  const [elapsedSec, setElapsedSec] = useState(0);
  const recRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ElapsedTimer>(initialTimer);
  const supported =
    typeof window !== "undefined" &&
    typeof window.MediaRecorder !== "undefined" &&
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices;
  // iOS 사파리 등 pause 미지원 — 호출부가 이 값으로 현행(정지=조각 전사) 폴백 분기를 태운다.
  const pauseSupported = supported && recorderSupportsPause(window.MediaRecorder.prototype);

  const start = useCallback(async (): Promise<boolean> => {
    if (!supported || recRef.current) return false;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recRef.current = rec;
      rec.start();
      timerRef.current = timerStart(initialTimer, Date.now());
      setElapsedSec(0);
      setPhase("recording");
      return true;
    } catch {
      return false;
    }
  }, [supported]);

  // 일시정지 — 세션은 유지(마이크 트랙도 유지), 경과 타이머만 멈춘다.
  const pause = useCallback(() => {
    const rec = recRef.current;
    if (!rec || rec.state !== "recording") return;
    rec.pause();
    timerRef.current = timerPause(timerRef.current, Date.now());
    setElapsedSec(elapsedSeconds(timerRef.current, Date.now()));
    setPhase("paused");
  }, []);

  const resume = useCallback(() => {
    const rec = recRef.current;
    if (!rec || rec.state !== "paused") return;
    rec.resume();
    timerRef.current = timerStart(timerRef.current, Date.now());
    setPhase("recording");
  }, []);

  // [T-VOICE-STOP-DEADLOCK] 정지는 stopRecording 에 위임한다 — **절대 reject 하지 않는다.**
  // 예전엔 rec.stop() 의 InvalidStateError(마이크를 뺏겨 이미 inactive)가 promise reject 로 새어
  // 호출부의 상태 정리를 통째로 건너뛰게 만들었다 → 다음·제출 버튼 영구 잠금.
  const stop = useCallback(async (): Promise<Blob | null> => {
    const rec = recRef.current;
    if (!rec) return null;
    const blob = await stopRecording(rec, chunksRef.current);
    timerRef.current = timerPause(timerRef.current, Date.now());
    setPhase("idle");
    recRef.current = null; // 어느 경로로든 좀비를 남기지 않는다(다음 start() 가 가짜 실패하지 않게)
    return blob;
  }, []);

  // 경과초 표시 틱 — 녹음 진행 중에만(일시정지 중엔 고정값 유지).
  useEffect(() => {
    if (phase !== "recording") return;
    const id = window.setInterval(
      () => setElapsedSec(elapsedSeconds(timerRef.current, Date.now())),
      500,
    );
    return () => window.clearInterval(id);
  }, [phase]);

  // 녹음 중 컴포넌트 언마운트(중간 이탈) 시 마이크 트랙을 정리 — 안 그러면 마이크가 계속 켜진다.
  useEffect(() => {
    return () => {
      const rec = recRef.current;
      if (!rec) return;
      try {
        if (rec.state !== "inactive") rec.stop();
      } catch {
        /* 무시 */
      }
      rec.stream.getTracks().forEach((t) => t.stop());
      recRef.current = null;
    };
  }, []);

  return {
    recording: phase === "recording",
    phase,
    elapsedSec,
    start,
    pause,
    resume,
    stop,
    supported,
    pauseSupported,
  };
}
