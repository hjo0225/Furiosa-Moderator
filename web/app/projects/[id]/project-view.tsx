"use client";

// 프로젝트 상세 — 가이드 검토·수정(C-2) + 배포(C-3) | 결과 대시보드(C-4) + 내보내기(C-5).
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Container } from "@/components/shared";
import { getProject, type Project } from "@/lib/api";
import { cn } from "@/lib/utils";

import { GuidePanel } from "./guide-panel";
import { ResultsPanel } from "./results-panel";

type Tab = "guide" | "results";

const STATUS_LABEL: Record<Project["status"], string> = {
  draft: "작성 중",
  deployed: "배포됨",
  closed: "종료",
};

export function ProjectView({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("guide");

  const reload = useCallback(() => {
    getProject(projectId)
      .then(setProject)
      .catch(() => setError("프로젝트를 불러오지 못했어요. 백엔드가 켜져 있는지 확인해 주세요."));
  }, [projectId]);

  useEffect(reload, [reload]);

  // 이미 응답이 쌓여 있으면 결과 탭을 먼저 보여준다.
  // 제출 완료 기준이다 — 진행중인 세션으로 열면 아무것도 없는 결과 화면이 첫 화면이 된다.
  useEffect(() => {
    if (project && project.completed_count > 0) setTab("results");
  }, [project]);

  return (
    <main className="py-10 md:py-16">
      <Container className="max-w-5xl">
        <Link href="/projects" className="font-mono text-2xs uppercase text-ink-faint">
          ← 내 프로젝트
        </Link>

        {error && <p className="mt-4 text-meta text-nogo">{error}</p>}

        {!project ? (
          <p className="mt-4 animate-pulse font-mono text-meta text-ink-faint">불러오는 중…</p>
        ) : (
          <>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <h1 className="text-title">{project.title || project.topic}</h1>
              <span
                className={cn(
                  "rounded-sm px-1.5 py-0.5 font-mono text-2xs",
                  project.status === "deployed"
                    ? "bg-go/10 text-go"
                    : project.status === "closed"
                      ? "bg-paper-dim text-ink-faint"
                      : "bg-accent-wash text-accent",
                )}
              >
                {STATUS_LABEL[project.status]}
              </span>
            </div>
            <p className="mt-1 text-base text-ink-soft">{project.topic}</p>
            {project.target && (
              <p className="mt-0.5 text-meta text-ink-faint">대상 · {project.target}</p>
            )}
            <p className="mt-2 font-mono text-2xs text-ink-faint">
              응답 {project.completed_count}건
              {project.session_count > project.completed_count &&
                ` · 진행중 ${project.session_count - project.completed_count}건`}
            </p>

            {/* 탭 */}
            <div className="mt-8 flex gap-1 border-b border-line" role="tablist">
              {(
                [
                  ["guide", "인터뷰 가이드"],
                  ["results", "결과"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  role="tab"
                  aria-selected={tab === key}
                  onClick={() => setTab(key)}
                  className={cn(
                    "-mb-px border-b-2 px-4 py-2.5 text-base font-medium transition-colors",
                    tab === key
                      ? "border-accent text-accent"
                      : "border-transparent text-ink-faint hover:text-ink-soft",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="mt-6">
              {tab === "guide" ? (
                <GuidePanel project={project} onProjectChange={reload} />
              ) : (
                <ResultsPanel projectId={projectId} />
              )}
            </div>
          </>
        )}
      </Container>
    </main>
  );
}
