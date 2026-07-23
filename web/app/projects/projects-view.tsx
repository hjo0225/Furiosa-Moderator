"use client";

// C-1 보관함 — 프로젝트 목록. 생성 폼은 /projects/new 로 분리했다.
import Link from "next/link";
import { useEffect, useState } from "react";

import { buttonVariants, Container } from "@/components/shared";
import { listProjects, type Project } from "@/lib/api";
import { cn } from "@/lib/utils";

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
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch(() => {
        setProjects([]);
        setLoadError("프로젝트 목록을 불러오지 못했어요. 백엔드가 켜져 있는지 확인해 주세요.");
      });
  }, []);

  return (
    <main className="py-10 md:py-16">
      <Container className="max-w-4xl">
        <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-title">내 프로젝트</h1>
            <p className="mt-2 text-base text-ink-soft">
              알고 싶은 주제로 인터뷰 가이드를 만들고 응답을 모아 보세요.
            </p>
          </div>
          <Link href="/projects/new" className={buttonVariants()}>
            + 새 프로젝트
          </Link>
        </div>

        {/* 목록 */}
        <section className="mt-8">
          <h2 className="text-lead font-medium">
            프로젝트 {projects ? `${projects.length}개` : ""}
          </h2>
          {loadError && <p className="mt-3 text-meta text-nogo">{loadError}</p>}
          {projects === null ? (
            <p className="mt-4 animate-pulse font-mono text-meta text-ink-faint">불러오는 중…</p>
          ) : projects.length === 0 ? (
            <p className="mt-4 rounded-xl bg-surface p-8 text-center text-base text-ink-soft shadow-card">
              아직 만든 프로젝트가 없어요.{" "}
              <Link href="/projects/new" className="text-accent underline">
                첫 프로젝트를 만들어 보세요.
              </Link>
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
