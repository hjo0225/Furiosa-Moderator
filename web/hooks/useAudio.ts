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

// 무음 WAV — 오디오 재생 권한을 '사용자 제스처 순간에' 확보(unlock)하는 용도로만 쓴다.
// 첫 진행자 음성은 LLM 생성이 끝난 뒤에야 play() 가 호출돼 클릭 제스처 창을 벗어난다.
// 그래서 클릭 시점에 이 무음을 같은 엘리먼트로 한 번 재생해 재생 권한을 얻어 둔다.
let _silentUrl: string | null = null;
function silentWavUrl(): string {
  if (_silentUrl) return _silentUrl;
  const rate = 8000;
  const samples = 400; // 0.05초
  const buf = new ArrayBuffer(44 + samples);
  const v = new DataView(buf);
  const put = (o: number, s: string) => {
    for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i));
  };
  put(0, "RIFF");
  v.setUint32(4, 36 + samples, true);
  put(8, "WAVE");
  put(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true); // PCM
  v.setUint16(22, 1, true); // mono
  v.setUint32(24, rate, true);
  v.setUint32(28, rate, true); // byte rate (8-bit mono = rate)
  v.setUint16(32, 1, true); // block align
  v.setUint16(34, 8, true); // 8-bit
  put(36, "data");
  v.setUint32(40, samples, true);
  for (let i = 0; i < samples; i++) v.setUint8(44 + i, 128); // 8-bit 무음 = 128
  _silentUrl = URL.createObjectURL(new Blob([buf], { type: "audio/wav" }));
  return _silentUrl;
}

export function useTts(locale: string) {
  const [voices, setVoices] = useState<SpeechVoice[]>([]);
  const [settings, setSettingsState] = useState<TtsSettings>(DEFAULT_TTS);
  const [speaking, setSpeaking] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const srcUrlRef = useRef<string | null>(null); // 현재 mp3 blob URL — 교체·언마운트 시 revoke
  const unlockedRef = useRef(false);
  // 아바타 진폭 분석용 WebAudio 그래프. 재생 오디오 → analyser → 스피커.
  const ctxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const srcNodeRef = useRef<MediaElementAudioSourceNode | null>(null);
  const levelBufRef = useRef<Uint8Array<ArrayBuffer> | null>(null);

  // 재생 엘리먼트는 하나를 재사용한다 — 매번 new Audio() 를 만들면 unlock 으로 얻은 권한이 날아간다.
  const element = useCallback(() => {
    if (!audioRef.current) audioRef.current = new Audio();
    return audioRef.current;
  }, []);

  // WebAudio 그래프 준비. AudioContext 는 자동재생 정책상 제스처 안에서 만들어야 해서 unlock 에서 부른다.
  const ensureGraph = useCallback(() => {
    if (ctxRef.current) return;
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return;
    const ctx = new Ctor();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    ctxRef.current = ctx;
    analyserRef.current = analyser;
  }, []);

  /** 사용자 제스처(클릭) 안에서 호출 — 무음을 한 번 재생해 재생 권한을, AudioContext 를 함께 확보한다. */
  const unlock = useCallback(() => {
    ensureGraph();
    void ctxRef.current?.resume();
    if (unlockedRef.current) return;
    unlockedRef.current = true; // 재진입 방지. 실패해도 speak 는 계속 시도한다.
    try {
      const audio = element();
      audio.src = silentWavUrl();
      audio.play().then(
        () => {
          audio.pause();
          audio.currentTime = 0;
        },
        () => {
          /* 제스처가 아니었거나 정책상 거부 — speak 에서 다시 시도한다 */
        },
      );
    } catch {
      /* 무시 */
    }
  }, [element, ensureGraph]);

  /** 현재 재생 음량 0~1. 아바타가 rAF 로 매 프레임 읽어 움직임을 구동한다. */
  const getLevel = useCallback(() => {
    const an = analyserRef.current;
    if (!an) return 0;
    const buf =
      levelBufRef.current ?? (levelBufRef.current = new Uint8Array(new ArrayBuffer(an.fftSize)));
    an.getByteTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) {
      const v = (buf[i] - 128) / 128; // -1~1
      sum += v * v;
    }
    return Math.min(1, Math.sqrt(sum / buf.length) * 3.2); // RMS × 게인
  }, []);

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
    // 엘리먼트는 null 로 버리지 않는다 — unlock 으로 얻은 재생 권한을 유지해야 한다.
    audioRef.current?.pause();
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
        if (srcUrlRef.current) URL.revokeObjectURL(srcUrlRef.current);
        srcUrlRef.current = url;
        const audio = element(); // 같은 엘리먼트 재사용 — unlock 권한 유지
        audio.src = url;
        audio.playbackRate = Math.min(2, Math.max(0.5, settings.speakingRate));
        audio.volume = Math.min(1, Math.pow(10, settings.volumeGainDb / 20));
        // 분석 그래프에 한 번만 연결한다. createMediaElementSource 는 엘리먼트당 평생 1회.
        // 연결하면 엘리먼트 출력이 그래프로만 가므로 analyser→destination 을 반드시 이어야 소리가 난다.
        if (ctxRef.current && analyserRef.current && !srcNodeRef.current) {
          try {
            const node = ctxRef.current.createMediaElementSource(audio);
            node.connect(analyserRef.current);
            analyserRef.current.connect(ctxRef.current.destination);
            srcNodeRef.current = node;
          } catch {
            /* 이미 연결됨 등 — 무시 */
          }
        }
        if (ctxRef.current?.state === "suspended") void ctxRef.current.resume();
        audio.onended = () => setSpeaking(false);
        audio.onerror = () => setSpeaking(false);
        await audio.play();
      } catch {
        setSpeaking(false);
      }
    },
    [settings, stop, element],
  );

  // 언마운트 시 재생 중단 + blob URL·AudioContext 정리
  useEffect(
    () => () => {
      audioRef.current?.pause();
      if (srcUrlRef.current) URL.revokeObjectURL(srcUrlRef.current);
      void ctxRef.current?.close();
    },
    [],
  );

  return {
    voices,
    settings,
    setSettings,
    speak,
    stop,
    unlock,
    getLevel,
    speaking,
    available: voices.length > 0,
  };
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
      // `audio: true` 만 주면 기기·브라우저 기본값에 맡겨진다. STT 정확도는 입력 오디오에
      // 크게 좌우되므로 명시한다:
      //  - echoCancellation: 스피커로 나가는 AI 진행자 목소리가 마이크로 되돌아오는 걸 막는다.
      //    이어폰 없이 쓰는 응답자가 대부분이라 이게 없으면 진행자 발화가 답변에 섞인다.
      //  - noiseSuppression / autoGainControl: 실사용 환경(카페·길거리)과 작게 말하는 응답자 대응.
      //  - sampleRate 16k: STT 가 내부적으로 쓰는 값. 더 높게 받아 다운샘플되느니 맞춰 준다.
      // 브라우저가 지원하지 않는 제약은 조용히 무시되므로 폴백 분기가 따로 필요 없다.
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 16000,
          channelCount: 1,
        },
      });
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
