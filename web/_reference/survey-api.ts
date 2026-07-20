// 솔루션2 Survey API 클라이언트 — /surveys, /survey-ai 호출(Firebase 토큰 첨부).
import { onAuthStateChanged, type User } from "firebase/auth";
import { errorDetail } from "@/lib/api-error";
import { auth } from "@/lib/firebase";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// ── 타입 (apps/api/schemas/survey.py 와 camelCase 1:1) ──
export type QuestionOption = {
  id: string;
  text: string;
  textEn?: string;
  textJa?: string;
  textZh?: string;
  disqualify?: boolean;
};

/** 자극물(미디어) — 문항에 붙는 텍스트/이미지/유튜브 (구버전 MediaModel 대응) */
export type QuestionContent = {
  id: string;
  type: "text" | "photo" | "youtube";
  /** text=본문, youtube=영상 URL, photo=GCS 객체 경로(ref) 또는 외부 URL */
  value: string;
  valueEn?: string;
  valueJa?: string;
  valueZh?: string;
  /** photo 의 재발급 서명 URL(렌더용) — 서버 출력 전용. 저장 안 함 */
  valueUrl?: string;
};

export type FollowupTheme = "why" | "how" | "what_if" | "vs";

export type QuestionMode = "interview" | "survey" | "agent";

export type SurveyQuestion = {
  id: string;
  type: "choice" | "subjective";
  title: string;
  titleEn?: string;
  titleJa?: string;
  titleZh?: string;
  topic: string;
  options: QuestionOption[];
  contents: QuestionContent[];
  isRequired: boolean;
  /** 복수응답(객관식 다중 선택) 허용 — 서버는 선택지마다 답변 1행으로 저장한다 */
  allowMultiple?: boolean;
  /** 인구통계 태그(나이|성별|국적|커스텀) — 대시보드 응답자 분포(레이더) 키. ''=일반 문항 */
  demographicTag?: string;
  parentQuestionId: string | null;
  showIfOptionIds: string[];
  followupThemeType: string;
  depth: number;
  order: number;
  /** '에이전트 생성' 유형 — 6-Lens input_key(응답→채점 역매핑). 일반 문항은 미설정 */
  lensKey?: string | null;
};

export type SurveyListItem = {
  id: string;
  name: string;
  description: string;
  isPublic: boolean;
  status: string; // draft | under_review | final
  questionMode: string; // survey | interview (분류 유형)
  audience: string; // domestic | foreign (분류 대상)
  questionCount: number;
  responseCount: number;
  createdAt: string | null;
};

export type SurveyDetail = {
  id: string;
  name: string;
  description: string;
  instruction: string;
  isPublic: boolean;
  status: string; // draft | under_review | final
  finalizedAt?: string | null;
  questionMode: QuestionMode;
  audience: string; // domestic | foreign (A-S1 분류)
  // 보상·대상·모집(운영자 설정) — 편집 화면 현재값
  rewardAmount: number;
  targetNationality: string | null;
  /** 다중 국가 타깃(T-NATIONALITY-EXPAND) — ISO2/토큰 리스트. 있으면 단일 targetNationality 보다 우선 */
  targetNationalities: string[] | null;
  targetGender: string | null;
  targetAgeMin: number | null;
  targetAgeMax: number | null;
  targetHeadcount: number | null;
  /** 대상 언어(foreign) — 실제로 번역·노출할 언어. `languages`(번역본 존재)와 다른 개념 */
  targetLanguages: string[];
  /** 국적별 응답 쿼터 — 예 {CN: 5, JP: 5}. 없는 국적은 제한 없음 */
  quotas: Record<string, number> | null;
  nameEn: string;
  descriptionEn: string;
  instructionEn: string;
  /** 번역본 존재 언어(en/ja/zh) — 대시보드·백오피스 체크표시용(본문은 한글만 표시) */
  languages: string[];
  research: Record<string, string> | null;
  questions: SurveyQuestion[];
  createdAt: string | null;
};

export type SurveyPublic = {
  id: string;
  name: string;
  description: string;
  instruction: string;
  nameEn: string;
  descriptionEn: string;
  instructionEn: string;
  nameJa?: string;
  descriptionJa?: string;
  instructionJa?: string;
  nameZh?: string;
  descriptionZh?: string;
  instructionZh?: string;
  /** 번역본 존재 언어(en/ja/zh) — foreign 응답 페이지의 언어 선택지 */
  languages?: string[];
  questionMode: QuestionMode;
  audience: string; // domestic | foreign — foreign 이면 언어 선택(en/ja/zh) 노출
  /** 다중 국가 타깃(T-NATIONALITY-EXPAND) — 공개 응답 페이지 표시용 */
  targetNationalities?: string[] | null;
  /** 모집 마감(정원 도달) — 문항을 보여주기 전에 차단(T-QUOTA-ENTRY-GATE) */
  closed?: boolean;
  /** 한도에 도달한 국적 키(예 ["CN"]) — 무인증 조회라 서버가 내 국적을 모른다.
      클라가 내 프로필 국적과 대조해 조기 차단한다. 카운트는 안 준다. */
  quotaClosedNationalities?: string[];
  /** 마감된 국적 → 정원(상한) — 마감 화면 "○○ 정원 N명" 숫자용(찬 버킷 상한만, 진행 카운트 비공개). */
  quotaClosedLimits?: Record<string, number>;
  currentCount?: number;
  targetHeadcount?: number | null;
  research: Record<string, string> | null;
  questions: SurveyQuestion[];
};

export type TranscriptTurn = { role: "moderator" | "respondent"; text: string };

export type TopicItem = { id: string; title: string };

export type QuestionGroup = {
  topicId: string;
  topic: string;
  questionDirection: string;
  questions: SurveyQuestion[];
};

export type ResearchInput = {
  background: string;
  purpose: string;
  motivation: string;
  utilization: string;
  target: string;
  size: string;
  additionalConditions: string;
};

export type OptionCount = { optionId: string; text: string; count: number };

export type QuestionStats = {
  questionId: string;
  title: string;
  type: "choice" | "subjective";
  totalAnswers: number;
  optionCounts: OptionCount[];
  textAnswers: string[];
  latestSummary: string;
  demographicTag: string;
};

export type SurveyAnalytics = {
  surveyId: string;
  totalResponses: number;
  averageDuration: number;
  questions: QuestionStats[];
};

export type AnswerIn = {
  questionId: string;
  answerText?: string;
  answerOptionId?: string | null;
  /** 고른 선택지 전부(복수응답). 서버가 선택지마다 답변 1행으로 저장한다 */
  answerOptionIds?: string[];
  /** 음성 답변 오디오 ref(/speech/transcribe 가 반환) */
  url?: string;
  duration?: number;
};

export type AnswerOut = {
  id: string;
  questionId: string;
  answerText: string;
  answerOptionId: string | null;
  /** 음성 답변 오디오 재생용 서명 URL(조회 시 재발급) */
  url: string;
  duration: number;
  memo: string;
};

export type SpeechVoice = { name: string; languageCode: string; gender: string };

export type ResponseOut = {
  id: string;
  duration: number;
  createdAt: string | null;
  answers: AnswerOut[];
  transcript?: TranscriptTurn[];
};

export type SummaryHistoryItem = { summary: string; prompt: string; createdAt: string | null };

export type QuestionSummary = {
  questionId: string;
  summary: string;
  prompt: string;
  history: SummaryHistoryItem[];
};

export type DemographicCondition = { tag: string; generationHint: string };

export type InfographicDataset = { label: string; data: number[] };
export type Infographic = {
  ok: boolean;
  type: "bar" | "pie" | "line";
  labels: string[];
  datasets: InfographicDataset[];
  note: string;
};

// Firebase 세션 복원 대기 — 페이지 직진입 직후 currentUser 가 null 인 동안 요청하면
// Authorization 없이 나가 401(첫 클릭 무반응의 근본 원인). 최초 onAuthStateChanged 1회를
// 캐시해 두 번째 호출부터는 즉시 resolve 된다.
let authReadyPromise: Promise<User | null> | null = null;

export function authReady(): Promise<User | null> {
  if (!authReadyPromise) {
    authReadyPromise = new Promise((resolve) => {
      const unsubscribe = onAuthStateChanged(auth, (user) => {
        unsubscribe();
        resolve(user);
      });
    });
  }
  return authReadyPromise;
}

async function authHeaders(forceRefresh = false): Promise<Record<string, string>> {
  await authReady(); // 세션 복원 완료 후의 라이브 값(currentUser)을 읽는다(재로그인 대응)
  const token = await auth.currentUser?.getIdToken(forceRefresh);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// 인증 fetch 공통부 — 401 이면 토큰 강제 갱신 후 정확히 1회 재시도.
async function authedFetch(
  path: string,
  init: RequestInit = {},
  json = true,
): Promise<Response> {
  const attempt = async (forceRefresh: boolean) =>
    fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(json ? { "Content-Type": "application/json" } : {}),
        ...(await authHeaders(forceRefresh)),
        ...(init.headers ?? {}),
      },
    });
  let res = await attempt(false);
  if (res.status === 401) res = await attempt(true);
  return res;
}

async function authedJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await authedFetch(path, init);
  if (!res.ok) throw new Error(String(res.status));
  return (await res.json()) as T;
}

// ── 설문 CRUD ──
export const listSurveys = () => authedJson<SurveyListItem[]>("/surveys");

export const getSurvey = (id: string) => authedJson<SurveyDetail>(`/surveys/${id}`);

export function createSurvey(body: {
  name: string;
  description: string;
  instruction: string;
  isPublic: boolean;
  questionMode: QuestionMode;
  audience: string; // domestic | foreign (A-S1 분류)
  research: Record<string, string> | null;
  questions: Partial<SurveyQuestion>[];
}) {
  // 발행(P1b) — 실패 시 서버 detail(번역 실패 등)을 화면에 노출. 공유 authedJson 은 건드리지 않는다.
  return createWithDetail(body);
}

async function createWithDetail(body: unknown): Promise<SurveyDetail> {
  const res = await authedFetch("/surveys", { method: "POST", body: JSON.stringify(body) });
  if (!res.ok) throw new Error(await errorDetail(res, "설문 발행에 실패했어요"));
  return (await res.json()) as SurveyDetail;
}

export function patchSurvey(
  id: string,
  body: Partial<{ name: string; description: string; instruction: string; isPublic: boolean }>,
) {
  return authedJson<SurveyDetail>(`/surveys/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

// 빌더 영어 미리보기 — 미저장 초안을 번역해 영어판만 받는다(읽기 전용, 저장 없음). 키 미설정 503·실패 502.
export type TranslatePreview = {
  nameEn: string;
  descriptionEn: string;
  instructionEn: string;
  questions: {
    id: string;
    titleEn: string;
    options: { id: string; textEn: string }[];
    contents: { id: string; valueEn: string }[];
  }[];
};

export function translatePreview(body: {
  name: string;
  description?: string;
  instruction?: string;
  questions: {
    id: string;
    title: string;
    options?: { id: string; text: string }[];
    contents?: { id: string; type: string; value: string }[];
  }[];
}): Promise<TranslatePreview> {
  return authedJson<TranslatePreview>("/survey-ai/translate-preview", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function deleteSurvey(id: string): Promise<void> {
  const res = await authedFetch(`/surveys/${id}`, { method: "DELETE" }, false);
  if (!res.ok && res.status !== 204) throw new Error(String(res.status));
}

export const getAnalytics = (id: string) => authedJson<SurveyAnalytics>(`/surveys/${id}/analytics`);

// ── WS3 보상(기프티콘) 매핑·일괄 발송 (백오피스) ──
export type AdminSurveyRow = {
  id: string;
  name: string;
  ownerEmail: string;
  /** 소유자 이름(User.name) — ''=미저장(이메일만 표시) */
  ownerName?: string;
  status: string; // draft | under_review | final
  responseCount: number;
  audience: string; // domestic | foreign — 언어 배지 노출 조건
  languages: string[]; // 번역본 존재 언어(en/ja/zh) 체크표시
};
export type RespondentRow = {
  responseId: string;
  name: string;
  email: string;
  phone: string;
  rewardStatus: string; // none|sent|failed
  rewardAmount: number; // 제출 시 스냅샷
  consented: boolean;
  createdAt: string | null;
};
export type RespondentListOut = {
  items: RespondentRow[];
  amountSent: number; // Σ 지급완료
  amountPending: number; // Σ 정산예정(none+failed)
  totalSent: number;
  totalPending: number;
};
export type RewardSendResult = { responseId: string; status: string };

export const adminListSurveys = (q: string, status?: string) => {
  const p = new URLSearchParams();
  if (q.trim()) p.set("q", q.trim());
  if (status) p.set("status", status);
  const qs = p.toString();
  return authedJson<AdminSurveyRow[]>(`/admin/surveys${qs ? `?${qs}` : ""}`);
};

// ── 솔루션2 검수 워크플로우 ──
/** 사용자: 검수 요청(under_review). phone=완료 알림 받을 번호. */
export const submitSurveyForReview = (id: string, phone?: string) =>
  authedJson<SurveyDetail>(`/surveys/${id}/submit-review`, {
    method: "POST",
    body: JSON.stringify({ phone: phone || null }),
  });

/** 운영자: 검수용 설문 상세(임의 소유자). */
export const adminGetSurvey = (id: string) => authedJson<SurveyDetail>(`/admin/surveys/${id}`);

/** 운영자: 제자리 문항 편집 저장. */
export const adminSaveSurveyQuestions = (id: string, questions: SurveyQuestion[]) =>
  authedJson<SurveyQuestion[]>(`/admin/surveys/${id}/questions`, {
    method: "POST",
    body: JSON.stringify(questions),
  });

/** 소유자: 프로젝트 컨텍스트(research) 저장 — 최종 확정(final) 후에는 409. */
export const saveSurveyResearch = (id: string, research: ResearchInput) =>
  authedJson<{ ok: boolean; research: Record<string, string> }>(`/surveys/${id}/research`, {
    method: "PUT",
    body: JSON.stringify(research),
  });

/** 운영자: 프로젝트 컨텍스트(research) 저장 — 7필드 교체(여분 키는 서버가 보존). */
export const adminSaveSurveyResearch = (id: string, research: ResearchInput) =>
  authedJson<{ ok: boolean; research: Record<string, string> }>(`/admin/surveys/${id}/research`, {
    method: "PUT",
    body: JSON.stringify(research),
  });

/** 운영자: 검수 완료(reviewed) + 소유자 SMS. 자동 발행 아님 — 신청자 최종 발행 대기. */
export const adminFinalizeSurvey = (id: string) =>
  authedJson<{ ok: boolean; status: string; sms: string }>(`/admin/surveys/${id}/finalize`, {
    method: "POST",
  });

/** 소유자: 발행(reviewed→final) — 검수 결과 최종 확인 후 수집 시작(is_public=true). */
export const publishSurvey = (id: string) =>
  authedJson<SurveyDetail>(`/surveys/${id}/publish`, { method: "POST" });

/** 운영자: 대행 발행(reviewed→final+공개) — 이미 final 이면 멱등, reviewed 아니면 409. (T-BO-BULK-PUBLISH) */
export const adminPublishSurvey = (id: string) =>
  authedJson<{ ok: boolean; status: string }>(`/admin/surveys/${id}/publish`, { method: "POST" });

/** 운영자: 반려(draft 로 되돌림). */
export const adminReopenSurvey = (id: string) =>
  authedJson<{ ok: boolean; status: string }>(`/admin/surveys/${id}/reopen`, { method: "POST" });

export const listRespondents = (surveyId: string) =>
  authedJson<RespondentListOut>(`/surveys/${surveyId}/respondents`);

// ── 응답자별 조회(T-BO-RESPONDENT-LOOKUP) — 읽기 전용. 발송은 여전히 프로젝트별이다. ──
export type RespondentLookupItem = {
  surveyId: string;
  surveyName: string;
  ownerEmail: string; // 원가 귀속 — 누구의 프로젝트 비용인지
  questionMode: string;
  participatedAt: string | null;
  amount: number;
  status: "paid" | "pending";
  rewardStatus: string; // none | sent | failed
};

export type RespondentLookup = {
  phoneKey: string;
  realName: string;
  nationality: string;
  gender: string;
  birthYear: number | null;
  paidTotal: number;
  pendingTotal: number;
  responseCount: number;
  items: RespondentLookupItem[];
};

/** 운영자: 전화번호로 한 사람의 **전 프로젝트** 참여·누적 지급 조회. */
export const adminLookupRespondent = (phone: string) =>
  authedJson<RespondentLookup>(`/admin/respondents/lookup?phone=${encodeURIComponent(phone)}`);

export type SurveyTarget = {
  targetNationality: string | null;
  targetGender: string | null;
  targetAgeMin: number | null;
  targetAgeMax: number | null;
};

/** 작성자: 대상 조건(국적/성별/나이) 저장(제안) — 최종 확정 후 409(D17). */
export const saveSurveyTarget = (id: string, target: Partial<SurveyTarget>) =>
  authedJson<{ ok: boolean }>(`/surveys/${id}/targeting`, {
    method: "PUT",
    body: JSON.stringify(target),
  });

/** 운영자: 보상금액·대상·모집목표 설정(부분·확정) — 수집 시작(final) 후 409. */
export const adminSaveSurveySettings = (
  id: string,
  settings: Partial<
    SurveyTarget & {
      rewardAmount: number;
      targetHeadcount: number | null;
      targetLanguages: string[] | null;
      quotas: Record<string, number> | null;
      /** 다중 국가 타깃(T-NATIONALITY-EXPAND) — ISO2/토큰 리스트. 있으면 단일보다 우선 */
      targetNationalities: string[] | null;
    }
  >,
) =>
  authedJson<{ ok: boolean }>(`/admin/surveys/${id}/settings`, {
    method: "PATCH",
    body: JSON.stringify(settings),
  });

/** 보상 일괄 발송 — 코드(문자열) 또는 이미지(ref) 중 하나 이상. 국내=MMS 첨부, 해외=수령 링크(서버 분기). */
export const sendRewards = (
  surveyId: string,
  items: { responseId: string; code: string; imageRef?: string }[],
) =>
  authedJson<{ results: RewardSendResult[] }>(`/surveys/${surveyId}/rewards/send`, {
    method: "POST",
    body: JSON.stringify({ items }),
  });

export const listResponses = (id: string) => authedJson<ResponseOut[]>(`/surveys/${id}/responses`);

// ── 문항별 AI 요약 ──
export const getQuestionSummary = (surveyId: string, questionId: string) =>
  authedJson<QuestionSummary>(`/surveys/${surveyId}/questions/${questionId}/summary`);

export const generateQuestionSummary = (surveyId: string, questionId: string, prompt: string) =>
  authedJson<QuestionSummary>(`/surveys/${surveyId}/questions/${questionId}/summary`, {
    method: "POST",
    body: JSON.stringify({ prompt }),
  });

// ── 답변 메모(관리자) ──
export const patchAnswerMemo = (
  surveyId: string,
  responseId: string,
  answerId: string,
  memo: string,
) =>
  authedJson<AnswerOut>(`/surveys/${surveyId}/responses/${responseId}/answers/${answerId}/memo`, {
    method: "PATCH",
    body: JSON.stringify({ memo }),
  });

// ── 문항별 AI 인포그래픽(차트 설정 생성) ──
export const generateInfographic = (surveyId: string, questionId: string) =>
  authedJson<Infographic>(`/surveys/${surveyId}/questions/${questionId}/infographic`, {
    method: "POST",
  });

// ── 결과 PDF 리포트 다운로드 ──
export async function downloadReport(id: string, name: string): Promise<void> {
  const res = await authedFetch(`/surveys/${id}/report.pdf`, {}, false);
  if (!res.ok) throw new Error(String(res.status));
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `mindlens-survey-${name}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function downloadCsv(id: string, name: string): Promise<void> {
  const res = await authedFetch(`/surveys/${id}/responses.csv`, {}, false);
  if (!res.ok) throw new Error(String(res.status));
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `mindlens-survey-${name}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

/** 운영자: 검수용 설문 문서(DOCX) — 컨텍스트 + 설문지 전문. 만든 사람과 상의용. */
export async function downloadSurveyDocx(id: string, name: string): Promise<void> {
  const res = await authedFetch(`/admin/surveys/${id}/document.docx`, {}, false);
  if (!res.ok) throw new Error(String(res.status));
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${name}_설문지.docx`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── 음성(TTS/STT) — 응답자(로그인) 토큰으로 호출 ──
export const fetchVoices = (languageCode: string) =>
  authedJson<SpeechVoice[]>(`/speech/voices?language_code=${encodeURIComponent(languageCode)}`);

export async function synthesizeSpeech(body: {
  text: string;
  voiceName?: string;
  languageCode?: string;
  speakingRate?: number;
  volumeGainDb?: number;
}): Promise<Blob> {
  const res = await authedFetch("/speech/synthesize", {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(String(res.status));
  return res.blob();
}

// 음성 답변 오디오 → { transcript(받아쓴 텍스트), ref(저장용 객체경로), url(즉시 재생), sttOk }
//
// [T-STT-FAILURE-SILENT] sttOk 는 **STT 엔진이 실제로 성공했는가**. 빈 transcript 로는
// 무음 녹음(성공)과 엔진 실패(400·권한·쿼터)를 구별할 수 없어, 서버가 실패를 200+빈 전사로
// 삼키던 시절엔 폴백이 영원히 발동하지 않았다. 구버전 서버는 이 필드를 안 주므로 기본 true.
export async function transcribeAudio(
  audio: Blob,
  languageCode = "ko-KR",
): Promise<{ transcript: string; ref: string; url: string; sttOk: boolean }> {
  const fd = new FormData();
  fd.append("file", audio, "answer.webm");
  fd.append("language_code", languageCode);
  const res = await authedFetch("/speech/transcribe", { method: "POST", body: fd }, false);
  if (!res.ok) throw new Error(String(res.status));
  const body = (await res.json()) as {
    transcript: string;
    ref: string;
    url: string;
    sttOk?: boolean;
  };
  return { ...body, sttOk: body.sttOk !== false };
}

// ── 공개 응답 (무인증) ──
export async function getPublicSurvey(id: string): Promise<SurveyPublic> {
  const res = await fetch(`${API_BASE}/surveys/${id}/public`);
  if (!res.ok) throw new Error(String(res.status));
  return (await res.json()) as SurveyPublic;
}

// 응답자 허브(A-S6) — 모든 프로젝트의 공개·확정 설문/인터뷰. 구글 로그인 필요(authedJson).
export type AvailableSurvey = {
  id: string;
  name: string;
  description: string;
  questionMode: string;
  answered: boolean;
  /** 내 국적 버킷이 마감됐는지(서버 판정 — 허브는 인증 경로) */
  quotaClosed?: boolean;
  /** 내 국적 정원 진행(count/limit) — 서버가 **본인 국적만** 계산(다른 국적 비공개).
      국적 쿼터가 없거나 내 국적에 제한이 없으면 null. 카드 "○○ N/M명" 표시용. */
  myQuotaCount?: number | null;
  myQuotaLimit?: number | null;
  supportsEn: boolean; // (구) 영어 번역 존재 — languages 로 대체, 호환 유지
  languages: string[]; // 응답 가능 번역 언어(en/ja/zh) — 허브 언어 배지
  audience: string; // domestic | foreign (A-S1 분류 — 허브 필터·배지)
  // 카드 라벨(T-HUB-CARDS-A) — 대상 조건 null=전원
  rewardAmount: number; // 1건당 보상(₩)
  targetNationality: string | null; // KR | CN | JP | foreign
  /** 다중 국가 타깃(T-NATIONALITY-EXPAND) — ISO2/토큰 리스트. 있으면 단일보다 우선 */
  targetNationalities: string[] | null;
  targetGender: string | null; // M | F
  targetAgeMin: number | null;
  targetAgeMax: number | null;
  currentCount: number; // 현재 참여수
  targetHeadcount: number | null; // 모집 목표(null=무제한)
  questionCount: number;
  estimatedMinutes: number; // 예상 소요(ⓑ)
};

export type AvailableSurveysResponse = {
  rewardCount: number; // 받은 보상 수(A-S3)
  items: AvailableSurvey[];
};

export function listAvailableSurveys(): Promise<AvailableSurveysResponse> {
  return authedJson<AvailableSurveysResponse>("/surveys/available");
}

// ── 응답자 프로필 (로그인 직후 온보딩, T-RESP-PROFILE) ──
export type RespondentProfile = {
  exists: boolean;
  realName?: string;
  phone?: string;
  nationality?: string; // KR | CN | JP | OTHER
  gender?: string; // M | F
  birthYear?: number;
  phoneVerified?: boolean;
};

export type RespondentProfileInput = {
  realName: string;
  phone: string;
  nationality?: string; // 응답자가 직접 선택(ISO2 또는 OTHER). 전화 인증과 별개 축(T-NAT-SELECT).
  gender: string;
  birthYear: number;
  consent: boolean;
};

/** 이 번호가 이미 다른 계정에 연결됐는지 + 그 계정 힌트(서버가 마스킹). (T-PHONE-IN-USE)
 *  이메일 원문은 절대 내려오지 않는다 — 번호로 주인을 캐내는 통로가 되면 안 된다. */
export function getPhoneOwner(e164: string): Promise<{ exists: boolean; hint: string }> {
  return authedJson<{ exists: boolean; hint: string }>(
    `/respondent/phone-owner?phone=${encodeURIComponent(e164)}`,
  );
}

export function getRespondentProfile(): Promise<RespondentProfile> {
  return authedJson<RespondentProfile>("/respondent/profile");
}

// PUT 은 consent=false·국적/성별 오류 시 400 → Error("400") throw(폼이 catch 해 안내).
export async function putRespondentProfile(body: RespondentProfileInput): Promise<void> {
  const res = await authedFetch("/respondent/profile", {
    method: "PUT",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(String(res.status));
}

// ── 내 적립 (T-MY-EARNINGS) ──
export type EarningItem = {
  surveyId: string;
  surveyName: string;
  questionMode: string;
  participatedAt: string | null;
  amount: number;
  status: string; // paid | pending
};

export type RespondentEarnings = {
  paidTotal: number;
  pendingTotal: number;
  responseCount: number;
  items: EarningItem[];
};

export function getRespondentEarnings(): Promise<RespondentEarnings> {
  return authedJson<RespondentEarnings>("/respondent/earnings");
}

// 중복 응답 방지 — 브라우저 단위 client_id(localStorage). 서버가 (survey, client) 중복 제출을
// 409 로 거절한다. 시크릿 모드/다른 브라우저 우회는 막지 못하는 보조 가드(IP 차단은 캠퍼스
// NAT 오탐, 개인별 토큰은 배포 플로우 변경이 커서 보류 — plan 참조).
const CLIENT_ID_KEY = "ml-survey-client-id";
const submittedKey = (surveyId: string) => `ml-survey-submitted:${surveyId}`;

export function surveyClientId(): string {
  if (typeof window === "undefined") return "";
  try {
    let id = window.localStorage.getItem(CLIENT_ID_KEY);
    if (!id) {
      id = crypto.randomUUID();
      window.localStorage.setItem(CLIENT_ID_KEY, id);
    }
    return id;
  } catch {
    return ""; // 저장 불가 환경(시크릿 등) — 서버 가드 없이 제출 허용
  }
}

export function hasSubmittedSurvey(surveyId: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(submittedKey(surveyId)) === "1";
  } catch {
    return false;
  }
}

export function markSurveySubmitted(surveyId: string): void {
  try {
    window.localStorage.setItem(submittedKey(surveyId), "1");
  } catch {
    /* 저장 실패는 무시 — 서버 가드가 남는다 */
  }
}

// 응답 제출 — 구글 로그인 필수(전 설문). authedFetch 가 Firebase 토큰을 첨부하고,
// 서버가 토큰 claims 에서 응답자 식별(uid/email/name)을 가져온다. 전화·동의는 본문.
export async function submitResponse(
  id: string,
  body: {
    answers: AnswerIn[];
    transcript?: TranscriptTurn[];
    duration: number;
    clientId?: string;
    phone?: string;
    consent?: boolean;
  },
): Promise<void> {
  const res = await authedFetch(`/surveys/${id}/responses`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    // 409 는 3종(중복/정원 마감/국적 쿼터 마감) — detail 을 실어 호출부가 구분하게 한다.
    // 전부 "이미 응답"으로 처리하면 마감 레이스 패자가 오인 + localStorage 오염(P0, T-SUBMIT-409).
    let detail = "";
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? "";
    } catch {
      /* 본문 없음 */
    }
    const err = new Error(String(res.status)) as Error & { detail?: string };
    err.detail = detail;
    throw err;
  }
}

/** 인터뷰 모드 모더레이터 — 조사 목표 + 대화이력 → 다음 진행자 발화 + 종료 여부. lang=en 이면 진행자도 영어. */
export function interviewTurn(
  goal: string,
  history: TranscriptTurn[],
  asked: number,
  lang: "ko" | "en" = "ko",
) {
  return authedJson<{ message: string; done: boolean }>("/survey-ai/interview-turn", {
    method: "POST",
    body: JSON.stringify({ goal, history, asked, lang }),
  });
}

// ── AI 보조 ──
export function aiExpand(body: Pick<ResearchInput, "background" | "purpose" | "motivation" | "utilization">) {
  return authedJson<Pick<ResearchInput, "background" | "purpose" | "motivation" | "utilization">>(
    "/survey-ai/expand",
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function aiTopics(body: ResearchInput) {
  return authedJson<{ topics: TopicItem[] }>("/survey-ai/topics", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** 타겟 자유텍스트 → 스크리닝(자격확인) 질문 1개(탈락 선택지 포함). */
export function generateScreening(target: string) {
  return authedJson<SurveyQuestion>("/survey-ai/screening", {
    method: "POST",
    body: JSON.stringify({ target }),
  });
}

/** 소유자: 생성 후 문항 전체 교체(재편집 저장). */
export const saveSurveyQuestions = (id: string, questions: SurveyQuestion[]) =>
  authedJson<SurveyQuestion[]>(`/surveys/${id}/questions`, {
    method: "POST",
    body: JSON.stringify(questions),
  });

export function aiQuestions(body: ResearchInput & { topics: TopicItem[]; questionMode: QuestionMode }) {
  return authedJson<{ groups: QuestionGroup[] }>("/survey-ai/questions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function aiRefine(body: { content: string; editRequest: string; section: string }) {
  return authedJson<{ editSummary: string; content: string; improvedContent: string }>(
    "/survey-ai/refine",
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function aiDemographics(body: { purpose: string; conditions: DemographicCondition[] }) {
  return authedJson<{ topic: string; questionDirection: string; questions: SurveyQuestion[] }>(
    "/survey-ai/demographics",
    { method: "POST", body: JSON.stringify(body) },
  );
}

// ── WS1 리서치 챗봇 + 질문지 업로드 ──
export type ResearchChatMsg = { role: "user" | "assistant"; content: string };

export function aiResearchChat(body: { messages: ResearchChatMsg[]; research: ResearchInput }) {
  return authedJson<{ message: string; research: ResearchInput; complete: boolean }>(
    "/survey-ai/research-chat",
    { method: "POST", body: JSON.stringify(body) },
  );
}

// 질문지 파일 업로드 → 문항 추출(주제 단계 스킵용) + 리서치 개요 추출(6필드 프리필, UPLOAD ⓐ).
export async function aiImportFile(
  file: File,
): Promise<{ summary: string; questions: SurveyQuestion[]; research: Record<string, string> }> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await authedFetch("/survey-ai/import-file", { method: "POST", body: fd }, false);
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? String(res.status));
  }
  const body = (await res.json()) as { summary: string; questions: SurveyQuestion[]; research?: Record<string, string> };
  return { ...body, research: body.research ?? {} };
}

// 문항 자극물 이미지 업로드 → { url(즉시 미리보기 서명 URL), ref(문항에 저장할 객체 경로) }.
export async function uploadMedia(file: File): Promise<{ url: string; ref: string }> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await authedFetch("/surveys/media/upload", { method: "POST", body: fd }, false);
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? String(res.status));
  }
  return (await res.json()) as { url: string; ref: string };
}

export function aiInstruction(body: {
  name: string;
  description: string;
  purpose: string;
  background: string;
  target: string;
}) {
  return authedJson<{ instruction: string }>("/survey-ai/instruction", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function aiFollowups(body: {
  parentQuestion: SurveyQuestion;
  selectedOptionIds: string[];
  themeType: FollowupTheme;
  followupsPerOption?: number;
  researchContext?: string;
}) {
  return authedJson<{ followups: SurveyQuestion[] }>("/survey-ai/followups", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ── '에이전트 생성' 유형 — 6-Lens 트윈 ──
export type AgentQuestion = {
  type: "choice" | "subjective";
  title: string;
  options: { id: string; text: string }[];
  lensKey: string;
  responseFormat: "choice" | "numeric" | "text";
};

export type RespondentAgent = {
  id: string;
  responseId: string;
  displayName: string | null;
  personaParams: Record<string, number> | null;
};

export type RespondentAgentDetail = RespondentAgent & {
  personaPrompt: string;
  qualitative: Record<string, string> | null;
};

/** 연구자 의도 → 관련 6-Lens 척도 선별 + 출제 문항 생성. */
export function generateAgentQuestions(intent: string) {
  return authedJson<{ questions: AgentQuestion[]; scaleIds: string[] }>(
    "/survey-ai/agent-questions",
    { method: "POST", body: JSON.stringify({ intent }) },
  );
}

/** 응답 1건 → 소비자 에이전트 생성(소유자). */
export function createRespondentAgent(surveyId: string, responseId: string) {
  return authedJson<RespondentAgentDetail>(
    `/surveys/${surveyId}/responses/${responseId}/agent`,
    { method: "POST" },
  );
}

export function listRespondentAgents(surveyId: string) {
  return authedJson<RespondentAgent[]>(`/surveys/${surveyId}/agents`);
}

/** 에이전트와 1:1 채팅 — 한 번에 한 메시지(응답 텍스트 반환). */
export function chatRespondentAgent(surveyId: string, agentId: string, message: string) {
  return authedJson<{ reply: string }>(
    `/surveys/${surveyId}/agents/${agentId}/chat`,
    { method: "POST", body: JSON.stringify({ message }) },
  );
}

/** 1:1 채팅 스트리밍 — 응답 델타를 onChunk 로 흘린다(NDJSON {type:chunk|end|error}). */
export async function chatRespondentAgentStream(
  surveyId: string,
  agentId: string,
  message: string,
  onChunk: (text: string) => void,
): Promise<void> {
  const res = await authedFetch(`/surveys/${surveyId}/agents/${agentId}/chat/stream`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
  if (!res.ok || !res.body) throw new Error(String(res.status));
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const ev = JSON.parse(line) as { type: string; text?: string };
      if (ev.type === "chunk" && ev.text) onChunk(ev.text);
      else if (ev.type === "error") throw new Error("stream-error");
    }
  }
}

/** 인터뷰 모드 AI 모더레이터 — 직전 질문+답변으로 후속질문 1개 생성(키 미설정 시 503). lang=en 이면 영어. */
export function interviewFollowup(question: string, answer: string, lang: "ko" | "en" = "ko") {
  return authedJson<{ followup: string }>("/survey-ai/interview-followup", {
    method: "POST",
    body: JSON.stringify({ question, answer, lang }),
  });
}
