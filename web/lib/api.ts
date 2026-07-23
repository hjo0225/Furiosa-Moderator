// mindlens API 클라이언트 — 무인증(MVP). `_reference/survey-api.ts`(1012줄, 90% 무관)를 이식하지 않고 새로 짰다.
// 백엔드: FastAPI. 베이스 URL 은 NEXT_PUBLIC_API_BASE.

const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

/** 절대 API URL — fetch 를 직접 쓰는 곳(SSE·multipart)에서 BASE 를 다시 짜지 않게. */
export const apiUrl = (path: string) => `${BASE}${path}`;

// --- 타입 (api/schemas/models.py 와 1:1) -------------------------------------

export type ProjectStatus = "draft" | "deployed" | "closed";

// 참가 조건 스크리너(F4.3). 의뢰자 설정용 — pass_options(통과 선택지)를 포함한다.
export type ScreenerQuestion = {
  id: string;
  text: string;
  options: string[];
  pass_options: string[];
};

export type Project = {
  id: string;
  owner: string;
  title: string;
  topic: string; // 조사 목적 (UI 라벨: 조사 목적)
  target: string; // 타깃 대상
  motivation: string; // 조사 동기
  utilization: string; // 활용 방안
  material_text: string; // 업로드한 참고 자료 (가이드 생성에 주입). 비어 있으면 미첨부.
  screener: ScreenerQuestion[]; // 참가 조건 스크리너(F4.3). 비면 게이트 없음. 의뢰자 응답에만 담긴다.
  blocklist: string[]; // 지식팩 금칙어(F1.5). 진행자가 먼저 꺼내면 안 되는 주제·표현. 비면 제약 없음.
  status: ProjectStatus;
  created_at: string;
  session_count: number;
  completed_count: number;
};

/** 자료 슬롯 — api/routers/projects.py 의 검증값과 1:1. 서버에서 필수라 빠지면 422 다. */
export type MaterialAngle = "현상" | "원인" | "활용";

/** 자료 업로드 응답 (POST /api/projects/{id}/material). */
export type MaterialUploadResult = {
  project_id: string;
  chars: number;
  truncated: boolean;
  summarized?: boolean; // 긴 자료를 LLM이 요약해 저장한 경우 true (백엔드 ② 이후)
};

export type ResponseBucket = {
  id: string;
  label: string;
  definition: string;
  is_catchall: boolean;
  is_negative_case: boolean;
};
export type GuideQuestion = {
  id: string;
  text: string;
  goal: string;
  order: number;
  response_buckets: ResponseBucket[];
  // 이 문항을 다룰 때 응답자 화면에 띄울 제시 자료(선택). 미첨부면 null/undefined — 기본 단일 컬럼.
  stimulus?: Stimulus | null;
};

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
  // 이번 진행자 발화가 다루는 문항의 제시 자료(있으면). url 이 빈 것은 서버가 걸러 내려주지 않는다.
  stimulus?: Stimulus;
};

export type ThemeInsight = { theme: string; summary: string; quotes: string[]; mention_count: number };

// 문항별 AI 요약(F6.3) — 문항마다 headline(핵심 발견) + summary(2~4문장). theme 요약처럼 LLM 해석 출력.
export type QuestionSummary = { question_id: string; headline: string; summary: string };

export type Insight = {
  project_id: string;
  overall: string;
  themes: ThemeInsight[];
  sentiment: Record<string, number>;
  // 문항별 응답 버킷 분포(F6.4) — { question_id: { bucket_id: 응답자 수 } }.
  // sentiment 와 같이 DB 실측(LLM 이 세지 않음). bucket_id → 라벨은 가이드의 response_buckets 로 매핑.
  bucket_distribution: Record<string, Record<string, number>>;
  // 문항별 AI 요약(F6.3) — bucket_distribution 이 '분류·개수'라면 이건 '무엇을 말했나'의 서술 요약.
  question_summaries: QuestionSummary[];
  session_count: number;
  generated_at: string;
};

export type Dashboard = { project: Project; sessions: Session[]; insight: Insight | null };

// 응답자에게 내려오는 변형 — 어느 답이 통과인지(pass_options)는 서버가 벗겨낸다.
export type PublicScreenerQuestion = { id: string; text: string; options: string[] };

export type PublicProject = {
  id: string;
  title: string;
  topic: string;
  status: ProjectStatus;
  screener: PublicScreenerQuestion[];
};

export type SpeechVoice = { name: string; label: string };

/** 화면에 그대로 그리는 대화 한 줄 — 서버 Turn 의 표시용 축약본. */
export type TranscriptTurn = { role: TurnRole; text: string; emotion?: string };

/** 질문에 붙는 제시 자료(시안·광고·컨셉). 가이드 문항에 첨부하면 진행자가 그 문항을 다룰 때
 *  턴 응답(TurnOut.stimulus)에 실려 내려오고 응답자 화면이 2분할로 렌더한다. */
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
 *  multipart 라 JSON 헬퍼가 아니라 transcribeAudio 처럼 FormData 로 보낸다.
 *  angle 은 서버 필수값이다 — 빠지면 요청이 핸들러에 닿기도 전에 422 로 튕긴다. */
export async function uploadMaterial(
  pid: string,
  file: File,
  angle: MaterialAngle = "현상",
): Promise<MaterialUploadResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("angle", angle);
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

/** 참가 조건 스크리너 저장 (F4.3). 빈 배열이면 게이트 해제. 갱신된 프로젝트를 돌려준다. */
export const saveScreener = (pid: string, screener: ScreenerQuestion[]) =>
  request<Project>(`/api/projects/${pid}/screener`, {
    method: "PUT",
    body: JSON.stringify({ screener }),
  });

/** 지식팩 금칙어 저장 (F1.5). 빈/공백 항목은 서버가 버린다. 빈 배열이면 제약 해제. 갱신된 프로젝트를 돌려준다. */
export const saveBlocklist = (pid: string, blocklist: string[]) =>
  request<Project>(`/api/projects/${pid}/blocklist`, {
    method: "PUT",
    body: JSON.stringify({ blocklist }),
  });

export const getDashboard = (pid: string) => request<Dashboard>(`/api/projects/${pid}/dashboard`);

export const getTurns = (pid: string, sid: string) =>
  request<Turn[]>(`/api/projects/${pid}/sessions/${sid}/turns`);

/** 집계 인사이트 재생성 (C-4). */
export const regenerateInsight = (pid: string) => post<Insight>(`/api/projects/${pid}/insight`);

// --- 응답자 (무인증 공개 경로) ------------------------------------------------

export const getPublicProject = (pid: string) =>
  request<PublicProject>(`/api/public/projects/${pid}`);

/** 참가 조건 판정 (F4.3) — 동의 후·세션 시작 전. 판정은 서버가 pass_options 로 한다(클라엔 없음). */
export const screenParticipant = (pid: string, answers: Record<string, string>) =>
  post<{ qualified: boolean }>(`/api/public/projects/${pid}/screen`, { answers });

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

// --- 벤치마크 (RNGD vs GPU 손익분기, Task 7) ---------------------------------
// 계약 정본: docs/specs/2026-07-23-rngd-benchmark-instrumentation.md §1(지표 정의)·
// §2(손익분기)·§7(출력물). 측정 하네스(부하 재생기·데이터 수집)는 별도 워크스트림 —
// 이 타입·fetch 는 그 산출물을 "소비"만 한다(문서 인용: "UI(대시보드)는 §7 출력물을
// 소비만 한다").
//
// **null-우선 계약**: 실측 전 필드는 전부 null. 미측정 항목을 추정치로 채우는 것은
// 스펙 §8 "하지 말 것" 위반이므로 절대 금지 — 값이 없으면 여기서도, 화면에서도 null 그대로 둔다.

/** 결과 표(§7)의 4개 고정 구성. GPU 대조군 1 + RNGD 3(governor·prefix caching 조합). */
export type BenchmarkConfigKey =
  | "gpu_baseline"
  | "rngd_perf_cache_on"
  | "rngd_powersave_cache_on"
  | "rngd_perf_cache_off";

/** 결과 표 1행 = 구성 1개. 모든 측정치는 number|null — null 은 "아직 측정 안 함". */
export type BenchmarkRow = {
  config: BenchmarkConfigKey;
  label: string; // 표시용 라벨 (예: "GPU 대조군", "RNGD · Perf · cache on")
  hardware: "gpu" | "rngd";
  m1_sessions_per_card: number | null; // M1 — SLA 충족 동시 세션 수(세션슬롯/카드). §1: max C : turn_e2e p95 ≤ 2000ms
  cards_for_500: number | null; // 500세션 처리에 필요한 카드 수 (ceil(500 / M1))
  m2_wh_per_session: number | null; // M2 — 세션당 Wh(벽면 PDU 기준, idle 포함)
  idle_share: number | null; // idle 전력이 차지하는 비중, 0~1
  kappa: number | null; // M3 — 버킷 분류 Cohen's κ
  delta_kappa: number | null; // Δκ = κ_rngd - κ_gpu (게이트: κ<0.75 또는 Δκ<-0.05 면 M1·M2 무효)
  ttft_p95_ms: number | null; // 타이핑 인디케이터 체감 지표(M1과 함께 보고)
  turn_e2e_p50_ms: number | null;
};

/** 24h 전력 시계열(§7 차트 2) 1점. */
export type PowerTimeseriesPoint = {
  t: string; // ISO8601
  wall_power_w: number | null; // 벽면 PDU 실측(§8: 카드 센서만으로 계산 금지)
  concurrent_sessions: number | null;
};

/** 손익분기 곡선(§2·§7 차트 1) 1점. 두 비용선이 s_breakeven 세션 수에서 교차한다. */
export type BreakevenCurvePoint = {
  sessions: number;
  cost_rngd: number | null;
  cost_baseline: number | null;
};

/** 실행 메타데이터(§4 "재현성") — 재현성 기록용. 모르는 값은 null(추정 금지), 숫자도 문자열로 받는다
 *  ("측정 안 함"과 "0"을 구분할 필요가 없고, 부록은 순수 표시용이라 원문 그대로 보여주면 충분하다). */
export type BenchmarkRunMeta = {
  sdk_version: string | null;
  firmware_version: string | null;
  driver_version: string | null;
  model_id: string | null;
  quantization: string | null;
  governor: string | null;
  prefix_caching: string | null;
  tensor_parallel_size: string | null;
  corpus_hash: string | null;
  prompt_template_hash: string | null;
  cache_hit_rate: string | null;
};

export type BenchmarkResult = {
  rows: BenchmarkRow[];
  s_breakeven: number | null; // 헤드라인 S* — 월 손익분기 세션 수
  breakeven_curve: BreakevenCurvePoint[]; // 비어 있으면 뷰가 스키매틱(개념도)으로 대신 그린다
  power_timeseries: PowerTimeseriesPoint[]; // 비어 있으면 "계측 대기" 플레이스홀더
  idle_baseline_w: number | null;
  measured_at: string | null; // 마지막 측정 실행 시각. null = 아직 실행된 계측이 없음
  meta: BenchmarkRunMeta;
};

function emptyBenchmarkRow(
  config: BenchmarkConfigKey,
  label: string,
  hardware: "gpu" | "rngd",
): BenchmarkRow {
  return {
    config,
    label,
    hardware,
    m1_sessions_per_card: null,
    cards_for_500: null,
    m2_wh_per_session: null,
    idle_share: null,
    kappa: null,
    delta_kappa: null,
    ttft_p95_ms: null,
    turn_e2e_p50_ms: null,
  };
}

/** null-우선 기본값 — 계측 하네스가 아직 결과를 내놓지 않았을 때 화면이 그대로 렌더하는 값.
 *  4행 순서·라벨은 스펙 §7 결과 표와 1:1. */
export const EMPTY_BENCHMARK_RESULT: BenchmarkResult = {
  rows: [
    emptyBenchmarkRow("gpu_baseline", "GPU 대조군", "gpu"),
    emptyBenchmarkRow("rngd_perf_cache_on", "RNGD · Perf · cache on", "rngd"),
    emptyBenchmarkRow("rngd_powersave_cache_on", "RNGD · PowerSave · cache on", "rngd"),
    emptyBenchmarkRow("rngd_perf_cache_off", "RNGD · Perf · cache off", "rngd"),
  ],
  s_breakeven: null,
  breakeven_curve: [],
  power_timeseries: [],
  idle_baseline_w: null,
  measured_at: null,
  meta: {
    sdk_version: null,
    firmware_version: null,
    driver_version: null,
    model_id: null,
    quantization: null,
    governor: null,
    prefix_caching: null,
    tensor_parallel_size: null,
    corpus_hash: null,
    prompt_template_hash: null,
    cache_hit_rate: null,
  },
};

/** 벤치마크 결과 fetch. 계측 하네스(스펙 §3~§6, 별도 워크스트림)가 아직 붙지 않아
 *  백엔드에 대응 엔드포인트가 없다 — 404/네트워크 실패는 조용히 null-우선 기본값으로
 *  떨어진다(추정치를 만들어내지 않는다, 스펙 §8). 하네스가 붙으면 이 함수만 실제 파싱으로
 *  바꾸면 되고, 뷰는 이미 null 을 그릴 줄 알아서 손댈 필요 없다. */
export async function fetchBenchmarkResult(): Promise<BenchmarkResult> {
  try {
    const data = await request<Partial<BenchmarkResult>>("/api/benchmark/latest");
    return {
      ...EMPTY_BENCHMARK_RESULT,
      ...data,
      meta: { ...EMPTY_BENCHMARK_RESULT.meta, ...(data.meta ?? {}) },
    };
  } catch {
    return EMPTY_BENCHMARK_RESULT;
  }
}
