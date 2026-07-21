"use client";

// C-2 인터뷰 가이드 검토·수정 + C-3 배포(응답자 링크 발급).
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/shared";
import {
  ApiError,
  deployProject,
  generateGuide,
  getGuide,
  saveGuide,
  type GuideQuestion,
  type InterviewGuide,
  type Project,
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
  const [busy, setBusy] = useState<null | "generate" | "save" | "deploy">(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

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

  async function generate() {
    setBusy("generate");
    setError(null);
    setMessage(null);
    try {
      const g = await generateGuide(projectId, { topic: project.topic, target: project.target });
      setGuide(g);
      setDirty(false);
      setMessage("가이드를 새로 만들었어요. 확인하고 필요하면 고쳐 주세요.");
    } catch {
      setError("가이드 생성에 실패했어요. 잠시 후 다시 시도해 주세요.");
    } finally {
      setBusy(null);
    }
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

  const questions = guide?.questions ?? [];

  function updateQuestion(idx: number, field: keyof GuideQuestion, value: string) {
    patch((g) => ({
      ...g,
      questions: g.questions.map((q, i) => (i === idx ? { ...q, [field]: value } : q)),
    }));
  }

  function removeQuestion(idx: number) {
    patch((g) => ({
      ...g,
      questions: g.questions.filter((_, i) => i !== idx).map((q, i) => ({ ...q, order: i })),
    }));
  }

  function moveQuestion(idx: number, dir: -1 | 1) {
    const to = idx + dir;
    patch((g) => {
      if (to < 0 || to >= g.questions.length) return g;
      const next = [...g.questions];
      [next[idx], next[to]] = [next[to], next[idx]];
      return { ...g, questions: next.map((q, i) => ({ ...q, order: i })) };
    });
  }

  function addQuestion() {
    patch((g) => ({
      ...g,
      questions: [
        ...g.questions,
        { id: newQuestionId(), text: "", goal: "", order: g.questions.length },
      ],
    }));
  }

  if (loading) {
    return <p className="animate-pulse font-mono text-meta text-ink-faint">불러오는 중…</p>;
  }

  if (!guide) {
    return (
      <div className="rounded-xl bg-surface p-8 text-center shadow-card ring-1 ring-line">
        <p className="text-base text-ink-soft">
          아직 인터뷰 가이드가 없어요. 주제를 바탕으로 초안을 만들어 드릴게요.
        </p>
        {error && <p className="mt-3 text-meta text-nogo">{error}</p>}
        <Button className="mt-5" onClick={generate} disabled={busy === "generate"}>
          {busy === "generate" ? "만드는 중…" : "가이드 생성하기"}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 조사 목표 */}
      <div className="rounded-xl bg-surface p-5 shadow-card ring-1 ring-line">
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
      </div>

      {/* 문항 */}
      <div className="rounded-xl bg-surface p-5 shadow-card ring-1 ring-line">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-lead font-medium">질문 {questions.length}개</h3>
          <Button size="sm" variant="outline" onClick={generate} disabled={busy === "generate"}>
            {busy === "generate" ? "생성 중…" : "AI로 다시 생성"}
          </Button>
        </div>
        <p className="mt-1 text-meta text-ink-faint">
          진행자가 그대로 읽는 대본이 아니라, 대화에서 반드시 다뤄야 할 주제 목록이에요.
        </p>

        <ul className="mt-4 space-y-3">
          {questions.map((q, i) => (
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
                </div>
                <div className="flex shrink-0 flex-col gap-1">
                  <button
                    type="button"
                    onClick={() => moveQuestion(i, -1)}
                    disabled={i === 0}
                    aria-label="위로"
                    className="rounded px-2 py-1 text-meta text-ink-faint hover:bg-accent-wash disabled:opacity-30"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    onClick={() => moveQuestion(i, 1)}
                    disabled={i === questions.length - 1}
                    aria-label="아래로"
                    className="rounded px-2 py-1 text-meta text-ink-faint hover:bg-accent-wash disabled:opacity-30"
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    onClick={() => removeQuestion(i)}
                    aria-label="삭제"
                    className="rounded px-2 py-1 text-meta text-ink-faint hover:bg-nogo/10 hover:text-nogo"
                  >
                    ✕
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>

        <Button size="sm" variant="ghost" className="mt-3" onClick={addQuestion}>
          + 질문 추가
        </Button>
      </div>

      {message && <p className="text-meta text-go">{message}</p>}
      {error && <p className="text-meta text-nogo">{error}</p>}

      <div className="flex flex-wrap gap-2">
        <Button onClick={save} disabled={busy === "save" || !dirty}>
          {busy === "save" ? "저장 중…" : dirty ? "가이드 저장" : "저장됨"}
        </Button>
        <Button variant="outline" onClick={deploy} disabled={busy === "deploy"}>
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
              {copied ? "✓ 복사됨" : "링크 복사"}
            </Button>
            <a
              href={link}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-9 items-center rounded-full px-4 text-meta font-medium text-accent underline"
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
