"use client";

// C-1 의뢰자 대시보드 — 프로젝트 목록 + 생성 폼.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button, Container } from "@/components/shared";
import { createProject, listProjects, type Project } from "@/lib/api";
import { cn } from "@/lib/utils";

const inputCls =
  "w-full rounded-lg bg-surface px-3 py-2.5 text-base text-ink ring-1 ring-line placeholder:text-ink-faint/60 focus:outline-none focus:ring-accent";

const STATUS_LABEL: Record<Project["status"], string> = {
  draft: "작성 중",
  deployed: "배포됨",
  closed: "종료",
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
}

export function ProjectsView() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [topic, setTopic] = useState("");
  const [title, setTitle] = useState("");
  const [target, setTarget] = useState("");
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch(() => {
        setProjects([]);
        setLoadError("프로젝트 목록을 불러오지 못했어요. 백엔드가 켜져 있는지 확인해 주세요.");
      });
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!topic.trim() || creating) return;
    setCreating(true);
    setFormError(null);
    try {
      const p = await createProject({
        topic: topic.trim(),
        title: title.trim(),
        target: target.trim(),
      });
      router.push(`/projects/${p.id}`);
    } catch {
      setFormError("프로젝트를 만들지 못했어요. 잠시 후 다시 시도해 주세요.");
      setCreating(false);
    }
  }

  return (
    <main className="py-10 md:py-16">
      <Container className="max-w-4xl">
        <Link href="/" className="font-mono text-2xs uppercase text-ink-faint">
          ← mindlens
        </Link>
        <h1 className="mt-3 text-title">내 프로젝트</h1>
        <p className="mt-2 text-base text-ink-soft">
          알고 싶은 주제를 적으면 인터뷰 가이드를 만들어 드려요.
        </p>

        {/* 생성 폼 */}
        <form onSubmit={submit} className="mt-8 rounded-xl bg-surface p-5 shadow-card ring-1 ring-line">
          <h2 className="text-lead font-medium">새 프로젝트</h2>
          <div className="mt-4 space-y-3">
            <label className="block">
              <span className="text-meta font-medium text-ink-soft">
                주제 <span className="text-nogo">*</span>
              </span>
              <input
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="예: 20대 직장인이 아침 식사를 거르는 이유"
                className={cn(inputCls, "mt-1.5")}
                required
              />
            </label>
            <label className="block">
              <span className="text-meta font-medium text-ink-soft">제목</span>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="비워두면 주제를 제목으로 씁니다"
                className={cn(inputCls, "mt-1.5")}
              />
            </label>
            <label className="block">
              <span className="text-meta font-medium text-ink-soft">대상 조건</span>
              <input
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder="예: 수도권 거주 25~34세 직장인"
                className={cn(inputCls, "mt-1.5")}
              />
            </label>
          </div>
          {formError && <p className="mt-3 text-meta text-nogo">{formError}</p>}
          <Button type="submit" className="mt-4 w-full sm:w-auto" disabled={!topic.trim() || creating}>
            {creating ? "만드는 중…" : "프로젝트 만들기"}
          </Button>
        </form>

        {/* 목록 */}
        <section className="mt-10">
          <h2 className="text-lead font-medium">
            프로젝트 {projects ? `${projects.length}개` : ""}
          </h2>
          {loadError && <p className="mt-3 text-meta text-nogo">{loadError}</p>}
          {projects === null ? (
            <p className="mt-4 animate-pulse font-mono text-meta text-ink-faint">불러오는 중…</p>
          ) : projects.length === 0 ? (
            <p className="mt-4 rounded-xl bg-surface p-8 text-center text-base text-ink-soft shadow-card">
              아직 만든 프로젝트가 없어요. 위에서 첫 프로젝트를 만들어 보세요.
            </p>
          ) : (
            <ul className="mt-4 space-y-2">
              {projects.map((p) => (
                <li key={p.id}>
                  <Link
                    href={`/projects/${p.id}`}
                    className="block rounded-xl bg-surface p-5 shadow-card ring-1 ring-line transition-colors hover:bg-accent-wash"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-base font-medium text-ink">{p.title || p.topic}</span>
                      <span
                        className={cn(
                          "rounded-sm px-1.5 py-0.5 font-mono text-2xs",
                          p.status === "deployed"
                            ? "bg-go/10 text-go"
                            : p.status === "closed"
                              ? "bg-paper-dim text-ink-faint"
                              : "bg-accent-wash text-accent",
                        )}
                      >
                        {STATUS_LABEL[p.status]}
                      </span>
                    </div>
                    <p className="mt-1 text-meta text-ink-soft">{p.topic}</p>
                    <p className="mt-2 font-mono text-2xs text-ink-faint">
                      {/* '응답'은 제출 완료 기준이다. session_count 는 발화한 세션이라
                          둘의 차가 아직 제출하지 않은 진행중 인원이 된다. */}
                      {formatDate(p.created_at)} · 응답 {p.completed_count}건
                      {p.session_count > p.completed_count &&
                        ` · 진행중 ${p.session_count - p.completed_count}건`}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </Container>
    </main>
  );
}
