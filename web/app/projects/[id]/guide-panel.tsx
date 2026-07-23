"use client";

// C-2 인터뷰 가이드 검토·수정 + C-3 배포(응답자 링크 발급).
import { useCallback, useEffect, useState } from "react";
import { Check, ChevronDown, ChevronUp, X } from "lucide-react";

import { Button, buttonVariants, Card, PipelineProgress, Skeleton } from "@/components/shared";
import { usePipeline } from "@/lib/pipeline";
import {
  ApiError,
  deployProject,
  getGuide,
  guideMaxTurns,
  saveBlocklist,
  saveGuide,
  saveScreener,
  type GuideQuestion,
  type GuideTopic,
  type InterviewGuide,
  type Project,
  type ResponseBucket,
  type ScreenerQuestion,
  type Stimulus,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const inputCls =
  "w-full rounded-lg bg-surface px-3 py-2 text-base text-ink ring-1 ring-line placeholder:text-ink-faint/60 focus:outline-none focus:ring-accent";

function newQuestionId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `q-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }
}

function newTopicId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `t-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }
}

/** 배포 응답의 url 을 절대 주소로 정규화 — 백엔드가 경로만 줘도 그대로 쓸 수 있게. */
function absoluteUrl(url: string, projectId: string): string {
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  if (!url) return `${origin}/i/${projectId}`;
  if (/^https?:\/\//i.test(url)) return url;
  return `${origin}${url.startsWith("/") ? "" : "/"}${url}`;
}

export function GuidePanel({
  project,
  onProjectChange,
}: {
  project: Project;
  onProjectChange: () => void;
}) {
  const [guide, setGuide] = useState<InterviewGuide | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<null | "save" | "deploy">(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const gen = usePipeline<InterviewGuide>();

  // 참가 조건 스크리너(F4.3) — 가이드와 별개로 Project 에 붙는다. 자체 dirty/저장을 둔다.
  const [screener, setScreener] = useState<ScreenerQuestion[]>(project.screener ?? []);
  const [screenerDirty, setScreenerDirty] = useState(false);
  const [savingScreener, setSavingScreener] = useState(false);
  const [screenerMsg, setScreenerMsg] = useState<string | null>(null);
  const [screenerErr, setScreenerErr] = useState<string | null>(null);

  // 지식팩 금칙어(F1.5) — 스크리너처럼 Project 에 붙는다. 자체 dirty/저장을 둔다.
  const [blocklist, setBlocklist] = useState<string[]>(project.blocklist ?? []);
  const [blocklistDirty, setBlocklistDirty] = useState(false);
  const [savingBlocklist, setSavingBlocklist] = useState(false);
  const [blocklistMsg, setBlocklistMsg] = useState<string | null>(null);
  const [blocklistErr, setBlocklistErr] = useState<string | null>(null);

  const projectId = project.id;

  useEffect(() => {
    let alive = true;
    getGuide(projectId)
      .then((g) => alive && setGuide(g))
      .catch((e) => {
        // 404 = 아직 생성 전. 에러가 아니라 "생성하기" 상태다.
        if (alive && !(e instanceof ApiError && e.status === 404)) {
          setError("가이드를 불러오지 못했어요.");
        }
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [projectId]);

  // 이미 배포된 프로젝트면 링크를 바로 보여준다(다시 배포 누를 필요 없이).
  useEffect(() => {
    if (project.status === "deployed") setLink(absoluteUrl("", projectId));
  }, [project.status, projectId]);

  const patch = useCallback((updater: (g: InterviewGuide) => InterviewGuide) => {
    setGuide((g) => (g ? updater(g) : g));
    setDirty(true);
    setMessage(null);
  }, []);

  // 가이드 생성은 문항·응답 버킷·어휘를 한 번에 만드느라 1분 안팎 걸린다. 경과초만으로는
  // 무엇을 하는 중인지 알 수 없어, 서버가 흘려보내는 실제 단계를 진행 화면으로 받는다.
  async function generate() {
    setError(null);
    setMessage(null);
    const g = await gen.run(`/api/projects/${projectId}/guide/stream`, {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic: project.topic, target: project.target }),
    });
    if (!g) return; // 실패·중단 — 에러는 진행 화면이 이미 보여준다
    setGuide(g);
    setDirty(false);
    setMessage("가이드를 새로 만들었어요. 확인하고 필요하면 고쳐 주세요.");
    gen.detach();
  }

  async function save() {
    if (!guide) return;
    setBusy("save");
    setError(null);
    try {
      const saved = await saveGuide(projectId, guide);
      setGuide(saved);
      setDirty(false);
      setMessage("저장했어요.");
    } catch {
      setError("저장에 실패했어요.");
    } finally {
      setBusy(null);
    }
  }

  async function deploy() {
    setBusy("deploy");
    setError(null);
    try {
      const res = await deployProject(projectId);
      setLink(absoluteUrl(res.url, projectId));
      setMessage("배포했어요. 아래 링크를 응답자에게 보내면 됩니다.");
      onProjectChange();
    } catch {
      setError("배포에 실패했어요.");
    } finally {
      setBusy(null);
    }
  }

  async function copyLink() {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      setCopied(false);
    }
  }

  const topics = guide?.topics ?? [];
  const questions = guide?.questions ?? [];
  // 최대 턴 = 주제별(질문수+1)의 합. 엔진에 전체 상한이 없으므로 여기가 유일하게
  // "인터뷰가 얼마나 길어지는가"를 의뢰자에게 보여주는 자리다(design.md §5).
  const maxTurns = guide ? guideMaxTurns(guide) : 0;

  /** 구조 재조립의 유일한 통로 — 평면 questions 뷰를 topics 에서 다시 파생시키고 순번을 매긴다. */
  function withTopics(g: InterviewGuide, next: GuideTopic[]): InterviewGuide {
    let n = 0;
    const renumbered = next.map((t, ti) => ({
      ...t,
      order: ti,
      questions: t.questions.map((q) => ({ ...q, order: n++ })),
    }));
    return { ...g, topics: renumbered, questions: renumbered.flatMap((t) => t.questions) };
  }

  /** 평면 인덱스 idx 의 질문 하나만 교체. 편집 핸들러들은 계속 평면 좌표로 말한다. */
  function mapQuestionAt(idx: number, fn: (q: GuideQuestion) => GuideQuestion) {
    patch((g) => {
      let n = 0;
      return withTopics(
        g,
        g.topics.map((t) => ({
          ...t,
          questions: t.questions.map((q) => (n++ === idx ? fn(q) : q)),
        })),
      );
    });
  }

  function updateQuestion(idx: number, field: keyof GuideQuestion, value: string) {
    mapQuestionAt(idx, (q) => ({ ...q, [field]: value }));
  }

  function removeQuestion(idx: number) {
    patch((g) => {
      let n = 0;
      return withTopics(
        g,
        g.topics.map((t) => ({ ...t, questions: t.questions.filter(() => n++ !== idx) })),
      );
    });
  }

  // 제시 자료(선택) — 문항 하나에 이미지/영상 URL+캡션을 붙인다. URL 을 비우면 자료 자체를 해제한다
  // (빈 액자를 응답자에게 띄우지 않으려는 것 — 백엔드도 빈 URL 을 걸러낸다).
  function setStimulusField(qi: number, field: keyof Stimulus, value: string) {
    mapQuestionAt(qi, (q) => {
      const cur: Stimulus = q.stimulus ?? { type: "image", url: "", caption: "" };
      const next: Stimulus = { ...cur, [field]: value };
      return { ...q, stimulus: field === "url" && !value.trim() ? undefined : next };
    });
  }

  function updateBucket(qi: number, bi: number, field: "label" | "definition", value: string) {
    mapQuestionAt(qi, (q) => ({
      ...q,
      response_buckets: q.response_buckets.map((b, j) => (j === bi ? { ...b, [field]: value } : b)),
    }));
  }
  function removeBucket(qi: number, bi: number) {
    mapQuestionAt(qi, (q) => ({
      ...q,
      response_buckets: q.response_buckets.filter((_, j) => j !== bi),
    }));
  }
  function addBucket(qi: number) {
    mapQuestionAt(qi, (q) => ({
      ...q,
      response_buckets: [
        ...q.response_buckets,
        {
          id: `${q.id}_b${q.response_buckets.length + 1}`,
          label: "",
          definition: "",
          is_catchall: false,
          is_negative_case: false,
        } satisfies ResponseBucket,
      ],
    }));
  }

  /** 질문 이동은 **같은 주제 안에서만** 한다 — 주제를 넘나들면 버킷이 엉뚱한 주제에 붙는다. */
  function moveQuestion(ti: number, qi: number, dir: -1 | 1) {
    patch((g) => {
      const t = g.topics[ti];
      const to = qi + dir;
      if (!t || to < 0 || to >= t.questions.length) return g;
      const qs = [...t.questions];
      [qs[qi], qs[to]] = [qs[to], qs[qi]];
      return withTopics(g, g.topics.map((x, i) => (i === ti ? { ...x, questions: qs } : x)));
    });
  }

  function addQuestion(ti: number) {
    patch((g) =>
      withTopics(
        g,
        g.topics.map((t, i) =>
          i === ti
            ? {
                ...t,
                questions: [
                  ...t.questions,
                  { id: newQuestionId(), text: "", goal: "", order: 0, response_buckets: [] },
                ],
              }
            : t,
        ),
      ),
    );
  }

  // --- 주제 편집 ------------------------------------------------------------
  function updateTopic(ti: number, field: "title" | "goal", value: string) {
    patch((g) => withTopics(g, g.topics.map((t, i) => (i === ti ? { ...t, [field]: value } : t))));
  }

  function removeTopic(ti: number) {
    patch((g) => withTopics(g, g.topics.filter((_, i) => i !== ti)));
  }

  function moveTopic(ti: number, dir: -1 | 1) {
    patch((g) => {
      const to = ti + dir;
      if (to < 0 || to >= g.topics.length) return g;
      const next = [...g.topics];
      [next[ti], next[to]] = [next[to], next[ti]];
      return withTopics(g, next);
    });
  }

  function addTopic() {
    patch((g) =>
      withTopics(g, [
        ...g.topics,
        { id: newTopicId(), title: "", goal: "", order: 0, questions: [] },
      ]),
    );
  }

  // --- 참가 조건 스크리너(F4.3) 편집 --------------------------------------
  function patchScreenerQ(qi: number, updater: (q: ScreenerQuestion) => ScreenerQuestion) {
    setScreener((qs) => qs.map((q, i) => (i === qi ? updater(q) : q)));
    setScreenerDirty(true);
    setScreenerMsg(null);
  }

  function addScreenerQuestion() {
    setScreener((qs) => [
      ...qs,
      { id: newQuestionId(), text: "", options: ["", ""], pass_options: [] },
    ]);
    setScreenerDirty(true);
    setScreenerMsg(null);
  }

  function removeScreenerQuestion(qi: number) {
    setScreener((qs) => qs.filter((_, i) => i !== qi));
    setScreenerDirty(true);
    setScreenerMsg(null);
  }

  function updateScreenerText(qi: number, value: string) {
    patchScreenerQ(qi, (q) => ({ ...q, text: value }));
  }

  function addOption(qi: number) {
    patchScreenerQ(qi, (q) => ({ ...q, options: [...q.options, ""] }));
  }

  function updateOption(qi: number, oi: number, value: string) {
    // 선택지 문자열을 바꾸면 pass_options(문자열로 보관)도 함께 갱신한다 — 안 그러면 통과 표시가 어긋난다.
    patchScreenerQ(qi, (q) => {
      const old = q.options[oi];
      return {
        ...q,
        options: q.options.map((o, i) => (i === oi ? value : o)),
        pass_options: q.pass_options.map((p) => (p === old ? value : p)),
      };
    });
  }

  function removeOption(qi: number, oi: number) {
    patchScreenerQ(qi, (q) => {
      const removed = q.options[oi];
      return {
        ...q,
        options: q.options.filter((_, i) => i !== oi),
        pass_options: q.pass_options.filter((p) => p !== removed),
      };
    });
  }

  function togglePass(qi: number, opt: string) {
    patchScreenerQ(qi, (q) => ({
      ...q,
      pass_options: q.pass_options.includes(opt)
        ? q.pass_options.filter((p) => p !== opt)
        : [...q.pass_options, opt],
    }));
  }

  async function saveScreenerCard() {
    setSavingScreener(true);
    setScreenerErr(null);
    try {
      // 저장 전에 빈 선택지·빈 문항을 정리한다. 빈 문자열 옵션·통과표시는 판정에서 무의미하다.
      const cleaned: ScreenerQuestion[] = screener
        .map((q) => {
          const options = q.options.map((o) => o.trim()).filter(Boolean);
          const pass_options = q.pass_options
            .map((p) => p.trim())
            .filter((p) => options.includes(p));
          return { ...q, text: q.text.trim(), options, pass_options };
        })
        .filter((q) => q.text && q.options.length > 0);
      const updated = await saveScreener(projectId, cleaned);
      setScreener(updated.screener ?? cleaned);
      setScreenerDirty(false);
      setScreenerMsg("참가 조건을 저장했어요.");
      onProjectChange();
    } catch {
      setScreenerErr("참가 조건 저장에 실패했어요.");
    } finally {
      setSavingScreener(false);
    }
  }

  // --- 지식팩 금칙어(F1.5) 편집 -------------------------------------------
  function addBlockword() {
    setBlocklist((ws) => [...ws, ""]);
    setBlocklistDirty(true);
    setBlocklistMsg(null);
  }

  function updateBlockword(idx: number, value: string) {
    setBlocklist((ws) => ws.map((w, i) => (i === idx ? value : w)));
    setBlocklistDirty(true);
    setBlocklistMsg(null);
  }

  function removeBlockword(idx: number) {
    setBlocklist((ws) => ws.filter((_, i) => i !== idx));
    setBlocklistDirty(true);
    setBlocklistMsg(null);
  }

  async function saveBlocklistCard() {
    setSavingBlocklist(true);
    setBlocklistErr(null);
    try {
      // 저장 전에 빈/공백 항목을 정리한다(서버도 다시 거른다 — 이중 방어).
      const cleaned = blocklist.map((w) => w.trim()).filter(Boolean);
      const updated = await saveBlocklist(projectId, cleaned);
      setBlocklist(updated.blocklist ?? cleaned);
      setBlocklistDirty(false);
      setBlocklistMsg("금칙어를 저장했어요.");
      onProjectChange();
    } catch {
      setBlocklistErr("금칙어 저장에 실패했어요.");
    } finally {
      setSavingBlocklist(false);
    }
  }

  // 생성 중이면 화면 전체를 진행 뷰로 바꾼다 — 트리거 버튼이 언마운트되므로 더블클릭
  // 방지가 비활성화가 아니라 화면 전환으로 이뤄진다(design.md §5).
  if (gen.state.running || gen.state.error) {
    return (
      <PipelineProgress
        title="가이드를 만들고 있어요"
        state={gen.state}
        onDetach={gen.detach}
        onRetry={generate}
      />
    );
  }

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!guide) {
    return (
      <Card className="p-8 text-center">
        <p className="text-base text-ink-soft">
          아직 인터뷰 가이드가 없어요. 주제를 바탕으로 초안을 만들어 드릴게요.
        </p>
        {error && <p className="mt-3 text-meta text-nogo">{error}</p>}
        <Button className="mt-5" onClick={generate}>
          가이드 생성하기
        </Button>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* 조사 목표 */}
      <Card className="p-5">
        <label className="block">
          <span className="text-meta font-medium text-ink-soft">조사 목표</span>
          <textarea
            value={guide.goal}
            onChange={(e) => patch((g) => ({ ...g, goal: e.target.value }))}
            rows={2}
            placeholder="이 인터뷰로 무엇을 알아내고 싶은가요?"
            className={cn(inputCls, "mt-1.5 resize-none")}
          />
        </label>
        <p className="mt-2 font-mono text-2xs text-ink-faint">
          v{guide.version} · 진행자는 이 목표를 기준으로 꼬리질문을 이어갑니다
        </p>
      </Card>

      {/* 문항 */}
      <Card className="p-5">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-lead font-medium">주제 {topics.length}개 · 질문 {questions.length}개</h3>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-surface px-2.5 py-1 font-mono text-2xs text-ink-soft ring-1 ring-line">
              최대 {maxTurns}턴
            </span>
            <Button size="sm" variant="secondary" onClick={generate}>
              AI로 다시 생성
            </Button>
          </div>
        </div>
        <p className="mt-1 text-meta text-ink-faint">
          진행자가 그대로 읽는 대본이 아니라, 대화에서 반드시 다뤄야 할 주제 목록이에요.
          주제마다 <b className="text-ink-soft">질문수 + 1턴</b>을 쓰고, 남는 1턴으로 파고듭니다.
        </p>

        <ul className="mt-4 space-y-4">
          {topics.map((t, ti) => (
            <li key={t.id || ti} className="rounded-xl bg-surface p-4 ring-1 ring-line">
              <div className="flex items-start gap-2">
                <span className="mt-2.5 shrink-0 font-mono text-2xs text-ink-faint">T{ti + 1}</span>
                <div className="min-w-0 flex-1 space-y-2">
                  <input
                    value={t.title}
                    onChange={(e) => updateTopic(ti, "title", e.target.value)}
                    placeholder="주제 이름 (예: 앱 선택 기준)"
                    className={cn(inputCls, "font-medium")}
                  />
                  <input
                    value={t.goal}
                    onChange={(e) => updateTopic(ti, "goal", e.target.value)}
                    placeholder="이 주제로 알아내려는 것 (선택)"
                    className={cn(inputCls, "text-meta")}
                  />
                </div>
                <div className="flex shrink-0 flex-col gap-1">
                  <button
                    type="button"
                    onClick={() => moveTopic(ti, -1)}
                    disabled={ti === 0}
                    aria-label="주제 위로"
                    className="rounded px-2 py-1 text-ink-faint hover:bg-blush disabled:opacity-30"
                  >
                    <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => moveTopic(ti, 1)}
                    disabled={ti === topics.length - 1}
                    aria-label="주제 아래로"
                    className="rounded px-2 py-1 text-ink-faint hover:bg-blush disabled:opacity-30"
                  >
                    <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => removeTopic(ti)}
                    aria-label="주제 삭제"
                    className="rounded px-2 py-1 text-ink-faint hover:bg-nogo/10 hover:text-nogo"
                  >
                    <X className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </div>
              </div>
              <p className="mt-2 pl-6 font-mono text-2xs text-ink-faint">
                질문 {t.questions.length}개 · 이 주제 {t.questions.length + 1}턴
              </p>

              <ul className="mt-3 space-y-3 pl-6">
              {t.questions.map((q, qi) => {
                const i = topics.slice(0, ti).reduce((n, x) => n + x.questions.length, 0) + qi;
                return (
            <li key={q.id || i} className="rounded-lg bg-bg p-4 ring-1 ring-line">
              <div className="flex items-start justify-between gap-2">
                <span className="mt-2.5 font-mono text-2xs text-ink-faint">Q{i + 1}</span>
                <div className="min-w-0 flex-1 space-y-2">
                  <textarea
                    value={q.text}
                    onChange={(e) => updateQuestion(i, "text", e.target.value)}
                    rows={2}
                    placeholder="질문"
                    className={cn(inputCls, "resize-none")}
                  />
                  <input
                    value={q.goal}
                    onChange={(e) => updateQuestion(i, "goal", e.target.value)}
                    placeholder="이 질문으로 알아내려는 것 (선택)"
                    className={cn(inputCls, "text-meta")}
                  />
                  <div className="mt-2 rounded-lg bg-surface p-3 ring-1 ring-line">
                    <p className="mb-2 text-2xs font-medium uppercase tracking-wide text-ink-faint">
                      응답 버킷 · {q.response_buckets.length}개
                    </p>
                    <ul className="space-y-1.5">
                      {q.response_buckets.map((b, bi) => (
                        <li key={b.id || bi} className="flex items-start gap-2">
                          <span
                            className={cn(
                              "mt-2 h-2 w-2 shrink-0 rounded-full",
                              b.is_catchall ? "bg-ink-faint" : b.is_negative_case ? "bg-pivot" : "bg-accent-solid",
                            )}
                            aria-hidden
                          />
                          <input
                            value={b.label}
                            onChange={(e) => updateBucket(i, bi, "label", e.target.value)}
                            placeholder="버킷 이름"
                            className={cn(inputCls, "text-meta min-w-0 flex-1")}
                          />
                          <input
                            value={b.definition}
                            onChange={(e) => updateBucket(i, bi, "definition", e.target.value)}
                            placeholder="1문장 정의"
                            className={cn(inputCls, "text-meta min-w-0 flex-[2]")}
                          />
                          <button
                            type="button"
                            onClick={() => removeBucket(i, bi)}
                            aria-label="버킷 삭제"
                            className="mt-1 rounded px-2 py-1 text-ink-faint hover:bg-nogo/10 hover:text-nogo"
                          >
                            <X className="h-3.5 w-3.5" aria-hidden="true" />
                          </button>
                        </li>
                      ))}
                    </ul>
                    <Button size="sm" variant="ghost" className="mt-1.5" onClick={() => addBucket(i)}>
                      + 버킷 추가
                    </Button>
                  </div>

                  {/* 자극물(선택) — 이 문항을 다룰 때 응답자 화면에 함께 띄울 이미지/영상 */}
                  <div className="mt-2 rounded-lg bg-surface p-3 ring-1 ring-line">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <p className="text-2xs font-medium uppercase tracking-wide text-ink-faint">
                        자극물 (선택)
                      </p>
                      <div className="flex items-center gap-1">
                        {(["image", "video"] as const).map((t) => (
                          <button
                            key={t}
                            type="button"
                            onClick={() => setStimulusField(i, "type", t)}
                            className={cn(
                              "rounded px-2 py-0.5 text-2xs ring-1 transition-colors",
                              (q.stimulus?.type ?? "image") === t
                                ? "bg-accent-wash text-accent ring-accent/30"
                                : "text-ink-faint ring-line hover:bg-accent-wash",
                            )}
                          >
                            {t === "image" ? "이미지" : "영상"}
                          </button>
                        ))}
                      </div>
                    </div>
                    <input
                      value={q.stimulus?.url ?? ""}
                      onChange={(e) => setStimulusField(i, "url", e.target.value)}
                      placeholder={
                        (q.stimulus?.type ?? "image") === "video"
                          ? "영상 URL (비우면 해제)"
                          : "이미지 URL (비우면 해제)"
                      }
                      className={cn(inputCls, "text-meta")}
                    />
                    <input
                      value={q.stimulus?.caption ?? ""}
                      onChange={(e) => setStimulusField(i, "caption", e.target.value)}
                      placeholder="설명 캡션 (선택)"
                      className={cn(inputCls, "text-meta mt-1.5")}
                    />
                    <p className="mt-1.5 text-2xs text-ink-faint">
                      이 문항을 물을 때 응답자 화면에 함께 보여줄 이미지·영상이에요. 비워두면 표시하지 않아요.
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 flex-col gap-1">
                  <button
                    type="button"
                    onClick={() => moveQuestion(ti, qi, -1)}
                    disabled={qi === 0}
                    aria-label="위로"
                    className="rounded px-2 py-1 text-ink-faint hover:bg-blush disabled:opacity-30"
                  >
                    <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => moveQuestion(ti, qi, 1)}
                    disabled={qi === t.questions.length - 1}
                    aria-label="아래로"
                    className="rounded px-2 py-1 text-ink-faint hover:bg-blush disabled:opacity-30"
                  >
                    <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => removeQuestion(i)}
                    aria-label="삭제"
                    className="rounded px-2 py-1 text-ink-faint hover:bg-nogo/10 hover:text-nogo"
                  >
                    <X className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </div>
              </div>
            </li>
                );
              })}
              </ul>

              <Button size="sm" variant="ghost" className="ml-6 mt-2" onClick={() => addQuestion(ti)}>
                + 질문 추가
              </Button>
            </li>
          ))}
        </ul>

        <Button size="sm" variant="ghost" className="mt-3" onClick={addTopic}>
          + 주제 추가
        </Button>
      </Card>

      {/* 참가 조건 스크리너 (F4.3) — 동의 후·인터뷰 전 자격 판정 문항 */}
      <Card className="p-5">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-lead font-medium">참가 조건(스크리너)</h3>
          <Button size="sm" variant="ghost" onClick={addScreenerQuestion}>
            + 조건 추가
          </Button>
        </div>
        <p className="mt-1 text-meta text-ink-faint">
          동의 후·인터뷰 시작 전에 물어볼 자격 질문이에요. <b className="text-ink-soft">통과</b>로 표시한 답을
          고른 사람만 인터뷰로 넘어갑니다. 비워두면 누구나 참여할 수 있어요.
        </p>

        {screener.length === 0 ? (
          <p className="mt-4 rounded-lg bg-bg p-4 text-meta text-ink-faint ring-1 ring-line">
            아직 참가 조건이 없어요. 필요하면 위 &lsquo;조건 추가&rsquo;로 만들어 주세요.
          </p>
        ) : (
          <ul className="mt-4 space-y-3">
            {screener.map((q, qi) => (
              <li key={q.id || qi} className="rounded-lg bg-bg p-4 ring-1 ring-line">
                <div className="flex items-start justify-between gap-2">
                  <span className="mt-2.5 font-mono text-2xs text-ink-faint">S{qi + 1}</span>
                  <div className="min-w-0 flex-1 space-y-2">
                    <textarea
                      value={q.text}
                      onChange={(e) => updateScreenerText(qi, e.target.value)}
                      rows={2}
                      placeholder="자격 질문 (예: 최근 3개월 내 배달앱을 이용하셨나요?)"
                      className={cn(inputCls, "resize-none")}
                    />
                    <div className="rounded-lg bg-surface p-3 ring-1 ring-line">
                      <p className="mb-2 text-2xs font-medium uppercase tracking-wide text-ink-faint">
                        선택지 · 통과 체크 = 적격
                      </p>
                      <ul className="space-y-1.5">
                        {q.options.map((opt, oi) => (
                          <li key={oi} className="flex items-center gap-2">
                            <label
                              className="flex shrink-0 cursor-pointer items-center gap-1"
                              title="이 답을 고르면 통과(적격)"
                            >
                              <input
                                type="checkbox"
                                checked={q.pass_options.includes(opt) && !!opt.trim()}
                                onChange={() => togglePass(qi, opt)}
                                disabled={!opt.trim()}
                                className="h-4 w-4 accent-[color:var(--accent-solid)] disabled:opacity-40"
                              />
                              <span className="text-2xs text-ink-faint">통과</span>
                            </label>
                            <input
                              value={opt}
                              onChange={(e) => updateOption(qi, oi, e.target.value)}
                              placeholder="선택지"
                              className={cn(inputCls, "text-meta min-w-0 flex-1")}
                            />
                            <button
                              type="button"
                              onClick={() => removeOption(qi, oi)}
                              aria-label="선택지 삭제"
                              className="rounded px-2 py-1 text-ink-faint hover:bg-nogo/10 hover:text-nogo"
                            >
                              <X className="h-3.5 w-3.5" aria-hidden="true" />
                            </button>
                          </li>
                        ))}
                      </ul>
                      <Button size="sm" variant="ghost" className="mt-1.5" onClick={() => addOption(qi)}>
                        + 선택지 추가
                      </Button>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeScreenerQuestion(qi)}
                    aria-label="조건 삭제"
                    className="mt-0.5 shrink-0 rounded px-2 py-1 text-ink-faint hover:bg-nogo/10 hover:text-nogo"
                  >
                    <X className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        {screenerMsg && <p className="mt-3 text-meta text-go">{screenerMsg}</p>}
        {screenerErr && <p className="mt-3 text-meta text-nogo">{screenerErr}</p>}

        <div className="mt-4 flex items-center gap-2">
          <Button size="sm" onClick={saveScreenerCard} disabled={savingScreener || !screenerDirty}>
            {savingScreener ? "저장 중…" : screenerDirty ? "참가 조건 저장" : "저장됨"}
          </Button>
          {screenerDirty && (
            <span className="text-2xs text-pivot">저장하지 않은 변경이 있어요.</span>
          )}
        </div>
      </Card>

      {/* 지식팩 금칙어 (F1.5) — 진행자가 먼저 꺼내면 안 되는 주제·표현 */}
      <Card className="p-5">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-lead font-medium">말하면 안 되는 것 (금칙어)</h3>
          <Button size="sm" variant="ghost" onClick={addBlockword}>
            + 금칙어 추가
          </Button>
        </div>
        <p className="mt-1 text-meta text-ink-faint">
          진행자가 어떤 형태로도 <b className="text-ink-soft">먼저</b> 꺼내면 안 되는 주제·표현이에요.
          진행자는 이 자료를 이해에만 쓰고 참가자에게 먼저 말하지 않아요. 비워두면 제약이 없어요.
        </p>

        {blocklist.length === 0 ? (
          <p className="mt-4 rounded-lg bg-bg p-4 text-meta text-ink-faint ring-1 ring-line">
            아직 금칙어가 없어요. 필요하면 위 &lsquo;금칙어 추가&rsquo;로 만들어 주세요.
          </p>
        ) : (
          <ul className="mt-4 space-y-2">
            {blocklist.map((word, i) => (
              <li key={i} className="flex items-center gap-2">
                <X className="h-3 w-3 shrink-0 text-ink-faint" aria-hidden="true" />
                <input
                  value={word}
                  onChange={(e) => updateBlockword(i, e.target.value)}
                  placeholder="예: 가격 정책 변경"
                  className={cn(inputCls, "min-w-0 flex-1")}
                />
                <button
                  type="button"
                  onClick={() => removeBlockword(i)}
                  aria-label="금칙어 삭제"
                  className="shrink-0 rounded px-2 py-1 text-ink-faint hover:bg-nogo/10 hover:text-nogo"
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}

        {blocklistMsg && <p className="mt-3 text-meta text-go">{blocklistMsg}</p>}
        {blocklistErr && <p className="mt-3 text-meta text-nogo">{blocklistErr}</p>}

        <div className="mt-4 flex items-center gap-2">
          <Button size="sm" onClick={saveBlocklistCard} disabled={savingBlocklist || !blocklistDirty}>
            {savingBlocklist ? "저장 중…" : blocklistDirty ? "금칙어 저장" : "저장됨"}
          </Button>
          {blocklistDirty && (
            <span className="text-2xs text-pivot">저장하지 않은 변경이 있어요.</span>
          )}
        </div>
      </Card>

      {message && <p className="text-meta text-go">{message}</p>}
      {error && <p className="text-meta text-nogo">{error}</p>}

      <div className="flex flex-wrap gap-2">
        <Button onClick={save} disabled={busy === "save" || !dirty}>
          {busy === "save" ? "저장 중…" : dirty ? "가이드 저장" : "저장됨"}
        </Button>
        <Button variant="secondary" onClick={deploy} disabled={busy === "deploy"}>
          {busy === "deploy"
            ? "배포 중…"
            : project.status === "deployed"
              ? "링크 다시 발급"
              : "배포하고 링크 받기"}
        </Button>
      </div>
      {dirty && (
        <p className="text-2xs text-pivot">저장하지 않은 변경이 있어요. 배포 전에 저장해 주세요.</p>
      )}

      {/* C-3 응답자 링크 */}
      {link && (
        <div className="rounded-xl bg-accent-wash p-5 ring-1 ring-accent/20">
          <p className="text-meta font-medium text-ink">응답자용 링크</p>
          <p className="mt-2 break-all rounded-lg bg-surface px-3 py-2 font-mono text-meta text-ink-soft">
            {link}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" onClick={copyLink}>
              {copied && <Check className="h-4 w-4" aria-hidden="true" />}
              {copied ? "복사됨" : "링크 복사"}
            </Button>
            <a
              href={link}
              target="_blank"
              rel="noreferrer"
              className={buttonVariants({ variant: "secondary", size: "sm" })}
            >
              새 탭에서 열기
            </a>
          </div>
          <p className="mt-3 text-2xs leading-relaxed text-ink-soft">
            카카오톡으로 보내면 응답자가 인앱 브라우저로 열게 되는데, 인앱에서는 마이크가 막혀요.
            응답 화면이 자동으로 &ldquo;외부 브라우저에서 열기&rdquo;를 안내합니다.
          </p>
        </div>
      )}
    </div>
  );
}
