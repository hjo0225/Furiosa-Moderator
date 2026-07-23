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

/** 프로젝트 삭제 (C-6). 가이드·세션·턴·인사이트·자료가 **함께 사라진다. 되돌릴 수 없다.**
 *  반환의 sessions 는 같이 지워진 세션 수 — 확인 문구·로그에 쓴다. */
export const deleteProject = (pid: string) =>
  request<{ deleted: boolean; project_id: string; sessions: number }>(
    `/api/projects/${pid}`,
    { method: "DELETE" },
  );

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

// --- 벤치마크 (RNGD 단독 계측) -----------------------------------------------
// 계약 정본: docs/specs/2026-07-23-rngd-benchmark-instrumentation.md §1(지표)·§7(출력물)·
// §9(범위 밖). 측정 하네스는 별도 워크스트림 — 이 타입·fetch 는 산출물을 "소비"만 한다.
//
// **대조군이 없다.** GPU 대조군·벽면 PDU 전력·Cohen's κ·손익분기 S* 는 환경 제약으로
// 측정 불가라 스펙 §9 로 내려갔다. 그래서 여기에도 대응 필드를 두지 않는다 — 영원히
// null 로 남을 칸을 만들면 화면이 "아직 안 함"처럼 보이지만 실제로는 "못 함"이다.
// 그 구분은 outOfScope 로 사유와 함께 싣는다.
//
// **null-우선 계약**: 실측 전 필드는 전부 null. 미측정을 추정치로 채우는 것은 스펙 §8
// "하지 말 것" 위반이므로 절대 금지 — 값이 없으면 여기서도, 화면에서도 null 그대로 둔다.

/** M1 지연 곡선 1행 = 동시 세션 슬롯 1수준. */
export type LatencyRow = {
  slots: number; // 세션 슬롯 수 C ("생성 중인 요청 수"가 아님)
  turns: number | null;
  failures: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  ttft_p95_ms: number | null;
  /** M1-b — Little의 법칙 산출. 사고시간 때문에 slots 보다 훨씬 작다. */
  avg_concurrent_generating: number | null;
  /** 카드 점유율 0~1 = avg_concurrent_generating / slots */
  occupancy: number | null;
};

/** M4 턴 내부 분해 1행 = 단계 1개. */
export type TurnStageRow = {
  key: "emotion" | "generate" | "guardrail" | "total";
  label: string;
  p50_ms: number | null;
  /** 턴 전체 대비 비중 0~1. 병렬 단계는 벽시계 기여도. */
  share: number | null;
  /** 병렬로 도는 단계면 true — 직렬 합과 다르다는 표시 */
  parallel: boolean;
  note: string;
};

/** M2 에너지 1행 = 하루 세션 수 1수준. 카드 센서 기준(벽면 아님). */
export type EnergyRow = {
  sessions_per_day: number;
  active_wh: number | null;
  idle_wh: number | null;
  wh_per_session: number | null;
  /** idle 이 총 에너지에서 차지하는 비중 0~1 — 이 화면의 헤드라인 */
  idle_share: number | null;
};

/** 전력 시계열 1점. 카드 센서 기준(§1 M2). */
export type PowerTimeseriesPoint = {
  t: string; // ISO8601
  card_power_w: number | null;
  concurrent_sessions: number | null;
};

/** 스펙 §9 — 못 잰 항목과 사유. 빈 칸이 아니라 사유가 정보다. */
export type OutOfScopeItem = {
  item: string;
  reason: string;
};

/** 역할별 모델 배치(§5). 배치가 다르면 수치를 비교할 수 없어 화면에 항상 적는다. */
export type ModelPlacement = {
  role: string;
  model: string;
};

/** 실행 메타데이터(§4 "재현성"). 모르는 값은 null(추정 금지), 숫자도 문자열로 받는다. */
export type BenchmarkRunMeta = {
  sdk_version: string | null;
  firmware_version: string | null;
  driver_version: string | null;
  quantization: string | null;
  governor: string | null;
  prefix_caching: string | null;
  tensor_parallel_size: string | null;
  corpus_hash: string | null;
  prompt_template_hash: string | null;
  cache_hit_rate: string | null;
  /** 어떤 커밋의 파이프라인을 쟀는지 — 재작성률 해석을 좌우한다 */
  code_revision: string | null;
};

export type BenchmarkResult = {
  latency: LatencyRow[];
  /** M1 판정. null=미측정, "unmet"=전 구간 SLA 미달(0 과 다르다), number=충족 최대 C */
  m1_sessions_per_card: number | "unmet" | null;
  sla_target_ms: number;
  turn_breakdown: TurnStageRow[];
  /** 가드레일 재작성 발생률 0~1 — M4 의 핵심 관전 포인트 */
  rewrite_rate: number | null;
  energy: EnergyRow[];
  idle_baseline_w: number | null;
  power_timeseries: PowerTimeseriesPoint[];
  model_placement: ModelPlacement[];
  out_of_scope: OutOfScopeItem[];
  measured_at: string | null; // null = 아직 실행된 계측이 없음
  meta: BenchmarkRunMeta;
};

function emptyLatencyRow(slots: number): LatencyRow {
  return {
    slots,
    turns: null,
    failures: null,
    p50_ms: null,
    p95_ms: null,
    ttft_p95_ms: null,
    avg_concurrent_generating: null,
    occupancy: null,
  };
}

function emptyStage(
  key: TurnStageRow["key"],
  label: string,
  parallel = false,
  note = "",
): TurnStageRow {
  return { key, label, p50_ms: null, share: null, parallel, note };
}

function emptyEnergyRow(sessions_per_day: number): EnergyRow {
  return {
    sessions_per_day,
    active_wh: null,
    idle_wh: null,
    wh_per_session: null,
    idle_share: null,
  };
}

/** null-우선 기본값 — 계측 하네스가 아직 결과를 내놓지 않았을 때 화면이 그대로 렌더하는 값.
 *  행 구성은 스펙 §7 출력물과 1:1. out_of_scope 는 §9 를 그대로 옮긴 것이라 측정 여부와
 *  무관하게 항상 채워져 있다 — "못 재는 이유"는 측정 전에도 이미 아는 사실이다. */
export const EMPTY_BENCHMARK_RESULT: BenchmarkResult = {
  latency: [emptyLatencyRow(8), emptyLatencyRow(16), emptyLatencyRow(32)],
  m1_sessions_per_card: null,
  sla_target_ms: 2000,
  turn_breakdown: [
    emptyStage("emotion", "감정 태깅", true, "질문 생성과 병렬"),
    emptyStage("generate", "질문 생성"),
    emptyStage("guardrail", "가드레일 (판정+재작성)"),
    emptyStage("total", "턴 전체"),
  ],
  rewrite_rate: null,
  energy: [
    emptyEnergyRow(50),
    emptyEnergyRow(200),
    emptyEnergyRow(500),
    emptyEnergyRow(1000),
  ],
  idle_baseline_w: null,
  power_timeseries: [],
  model_placement: [],
  out_of_scope: [
    { item: "벽면 PDU 전력", reason: "공유 팟 — PDU 물리 접근 불가. 카드 센서로 대체(하한값)" },
    { item: "GPU 대조군", reason: "대조군 하드웨어 미확보 — 배수 비교를 하지 않는 이유" },
    { item: "버킷 분류 κ", reason: "골드셋 500건 미구축 + 대조군 없어 Δκ 정의 불가" },
    { item: "손익분기 S*", reason: "대조군 비용·벽면 전력에 의존 — 추정 상수로 그리지 않는다" },
    { item: "프리픽스 캐시 히트율", reason: "서버 로그 파서 미구현" },
  ],
  measured_at: null,
  meta: {
    sdk_version: null,
    firmware_version: null,
    driver_version: null,
    quantization: null,
    governor: null,
    prefix_caching: null,
    tensor_parallel_size: null,
    corpus_hash: null,
    prompt_template_hash: null,
    cache_hit_rate: null,
    code_revision: null,
  },
};

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
