// mindlens API 클라이언트 — 무인증(MVP). `_reference/survey-api.ts`(1012줄, 90% 무관)를 이식하지 않고 새로 짰다.
// 백엔드: FastAPI. 베이스 URL 은 NEXT_PUBLIC_API_BASE.

const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

// --- 타입 (api/schemas/models.py 와 1:1) -------------------------------------

export type ProjectStatus = "draft" | "deployed" | "closed";

export type Project = {
  id: string;
  owner: string;
  title: string;
  topic: string; // 조사 목적 (UI 라벨: 조사 목적)
  target: string; // 타깃 대상
  motivation: string; // 조사 동기
  utilization: string; // 활용 방안
  material_text: string; // 업로드한 참고 자료 (가이드 생성에 주입). 비어 있으면 미첨부.
  status: ProjectStatus;
  created_at: string;
  session_count: number;
  completed_count: number;
};

/** 자료 업로드 응답 (POST /api/projects/{id}/material). */
export type MaterialUploadResult = {
  project_id: string;
  chars: number;
  truncated: boolean;
  summarized?: boolean; // 긴 자료를 LLM이 요약해 저장한 경우 true (백엔드 ② 이후)
};

export type GuideQuestion = { id: string; text: string; goal: string; order: number };

export type InterviewGuide = {
  project_id: string;
  goal: string;
  questions: GuideQuestion[];
  version: number;
  updated_at: string;
};

// pending = 진행자는 마무리했고 응답자의 제출을 기다리는 중. completed 만 '응답 1건'으로 센다.
export type SessionStatus =
  | "consented"
  | "active"
  | "pending"
  | "completed"
  | "abandoned";

export type Session = {
  id: string;
  project_id: string;
  respondent_id: string;
  status: SessionStatus;
  started_at: string;
  ended_at: string | null;
  asked: number;
  summary: string;
  covered: string[];
};

export type TurnRole = "moderator" | "respondent";

export type Turn = {
  id: string;
  session_id: string;
  role: TurnRole;
  text: string;
  emotion: string;
  emotion_confidence: number;
  is_probe: boolean;
  question_id: string;
  pii_types: string[];
  guardrail_rewritten: boolean;
  created_at: string;
};

export type TurnOut = {
  message: string;
  done: boolean;
  asked: number;
  is_probe: boolean;
  guardrail_rewritten: boolean;
  emotion: string;
};

export type ThemeInsight = { theme: string; summary: string; quotes: string[]; mention_count: number };

export type Insight = {
  project_id: string;
  overall: string;
  themes: ThemeInsight[];
  sentiment: Record<string, number>;
  session_count: number;
  generated_at: string;
};

export type Dashboard = { project: Project; sessions: Session[]; insight: Insight | null };

export type PublicProject = { id: string; title: string; topic: string; status: ProjectStatus };

export type SpeechVoice = { name: string; label: string };

/** 화면에 그대로 그리는 대화 한 줄 — 서버 Turn 의 표시용 축약본. */
export type TranscriptTurn = { role: TurnRole; text: string; emotion?: string };

/** 질문에 붙는 제시 자료(시안·광고·컨셉). Phase 1은 UI만 — 아직 API가 내려주지 않는다. */
export type Stimulus = { type: "image" | "video"; url: string; caption?: string };

// --- 코어 -------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    // 무인증이라 쿠키를 실어보내지 않는다. 빌드 타임 캐시도 끈다.
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new ApiError(res.status, `${init?.method ?? "GET"} ${path} → ${res.status}`);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });

// --- 의뢰자 (C-1 ~ C-5) ------------------------------------------------------

export const createProject = (body: {
  topic: string; // 조사 목적
  title?: string;
  target?: string; // 타깃 대상
  motivation?: string; // 조사 동기
  utilization?: string; // 활용 방안
}) => post<Project>("/api/projects", body);

export const listProjects = () => request<Project[]>("/api/projects");

export const getProject = (pid: string) => request<Project>(`/api/projects/${pid}`);

/** 가이드 자동 생성 (C-2). 인자를 비우면 프로젝트의 주제·대상을 그대로 쓴다. */
export const generateGuide = (pid: string, body?: { topic?: string; target?: string }) =>
  post<InterviewGuide>(`/api/projects/${pid}/guide`, body ?? {});

/** 참고 자료 업로드 (선택). 업로드하면 가이드 생성 시 도메인 맥락이 프롬프트에 주입된다.
 *  multipart 라 JSON 헬퍼가 아니라 transcribeAudio 처럼 FormData 로 보낸다. */
export async function uploadMaterial(pid: string, file: File): Promise<MaterialUploadResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/api/projects/${pid}/material`, { method: "POST", body: form });
  if (!res.ok) throw new ApiError(res.status, `upload material → ${res.status}`);
  return (await res.json()) as MaterialUploadResult;
}

export const getGuide = (pid: string) => request<InterviewGuide>(`/api/projects/${pid}/guide`);

export const saveGuide = (pid: string, guide: InterviewGuide) =>
  request<InterviewGuide>(`/api/projects/${pid}/guide`, {
    method: "PUT",
    body: JSON.stringify(guide),
  });

/** 배포 — 응답자 링크 발급 (C-3). */
export const deployProject = (pid: string) =>
  post<{ project_id: string; url: string }>(`/api/projects/${pid}/deploy`);

export const getDashboard = (pid: string) => request<Dashboard>(`/api/projects/${pid}/dashboard`);

export const getTurns = (pid: string, sid: string) =>
  request<Turn[]>(`/api/projects/${pid}/sessions/${sid}/turns`);

/** 집계 인사이트 재생성 (C-4). */
export const regenerateInsight = (pid: string) => post<Insight>(`/api/projects/${pid}/insight`);

// --- 응답자 (무인증 공개 경로) ------------------------------------------------

export const getPublicProject = (pid: string) =>
  request<PublicProject>(`/api/public/projects/${pid}`);

/** 동의 후 세션 생성 (R-1). */
export const startSession = (pid: string, agreed: boolean, userAgent: string) =>
  post<Session>(`/api/public/projects/${pid}/sessions`, { agreed, user_agent: userAgent });

/** 발화 1턴 → 진행자의 다음 한 마디. 첫 호출은 text 를 비워 오프닝을 받는다. */
export const sendTurn = (pid: string, sid: string, text: string, lang = "ko") =>
  post<TurnOut>(`/api/public/projects/${pid}/sessions/${sid}/turn`, { text, lang });

/** 제출 (R-4) — **이 호출이 있어야 '응답 1건'이 된다.** 진행자가 done 을 냈다고 끝난 게 아니다.
 *  서버에서 멱등하게 처리하므로 중복 클릭·재시도로 실패하지 않는다. */
export const submitSession = (pid: string, sid: string) =>
  post<Session>(`/api/public/projects/${pid}/sessions/${sid}/submit`, {});

// --- 음성 -------------------------------------------------------------------

/** STT. **200 ≠ 성공** — 빈 transcript 만으로는 무음과 엔진실패를 구별할 수 없어 백엔드가 ok 를 따로 준다.
 *  (중국어 STT 400 이 한 달간 조용히 저장된 실장애의 교훈 — PORTING.md §3) */
export async function transcribeAudio(
  blob: Blob,
  lang = "ko",
): Promise<{ text: string; ok: boolean }> {
  const form = new FormData();
  form.append("file", blob, "audio.webm");
  form.append("lang", lang);
  const res = await fetch(`${BASE}/api/speech/transcribe`, { method: "POST", body: form });
  if (!res.ok) throw new ApiError(res.status, `transcribe → ${res.status}`);
  const data = (await res.json()) as { text?: string; ok?: boolean };
  return { text: data.text ?? "", ok: data.ok !== false };
}

/** TTS — audio/mpeg 바이트를 그대로 받는다. */
export async function synthesizeSpeech(body: { text: string; voice?: string }): Promise<Blob> {
  const res = await fetch(`${BASE}/api/speech/synthesize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(res.status, `synthesize → ${res.status}`);
  return res.blob();
}

export async function fetchVoices(): Promise<SpeechVoice[]> {
  const data = await request<{ voices?: SpeechVoice[] }>("/api/speech/voices");
  return data.voices ?? [];
}
