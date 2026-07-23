"use client";

// C-1 보관함 — 프로젝트 목록. 생성 폼은 /projects/new 로 분리했다.
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { FolderOpen, Plus } from "lucide-react";

import {
  Badge,
  type BadgeTone,
  buttonVariants,
  Container,
  EmptyState,
  ErrorState,
  Skeleton,
} from "@/components/shared";
import { listProjects, type Project } from "@/lib/api";

const STATUS_LABEL: Record<Project["status"], string> = {
  draft: "작성 중",
  deployed: "배포됨",
  closed: "종료",
};

// design.md §5 "카드(프로젝트)": 배포됨=obsidian칩·작성중=red-wash칩·종료=grey칩 → Badge 톤 매핑.
// (Badge 는 draft/warm 을 같은 red-wash 로 그려 obsidian 칩 요구를 못 채우므로 live 를 배포됨에 쓴다.)
const STATUS_TONE: Record<Project["status"], BadgeTone> = {
  draft: "draft",
  deployed: "live",
  closed: "closed",
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
}

export function ProjectsView() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [loadError, setLoadError] = useState(false);

  const load = useCallback(() => {
    setLoadError(false);
    listProjects()
      .then(setProjects)
      .catch(() => setLoadError(true));
  }, []);

  useEffect(load, [load]);

  return (
    <main className="py-10 md:py-16">
      <Container className="max-w-4xl">
        <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-title text-obsidian">내 프로젝트</h1>
            <p className="mt-2 text-base text-charcoal">
              알고 싶은 주제로 인터뷰 가이드를 만들고 응답을 모아 보세요.
            </p>
          </div>
          <Link href="/projects/new" className={buttonVariants()}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            새 프로젝트
          </Link>
        </div>

        {/* 목록 */}
        <section className="mt-8">
          {projects !== null && !loadError && projects.length > 0 && (
            <h2 className="text-lead font-medium text-obsidian">프로젝트 {projects.length}개</h2>
          )}

          {loadError ? (
            <ErrorState
              className="mt-4"
              title="프로젝트 목록을 불러오지 못했어요"
              body="백엔드가 켜져 있는지 확인해 주세요."
              onRetry={load}
            />
          ) : projects === null ? (
            <div className="mt-4 space-y-3">
              <Skeleton className="h-[92px] w-full" />
              <Skeleton className="h-[92px] w-full" />
              <Skeleton className="h-[92px] w-full" />
            </div>
          ) : projects.length === 0 ? (
            <EmptyState
              className="mt-4"
              icon={FolderOpen}
              title="아직 프로젝트가 없어요"
              body="주제만 정해주시면 인터뷰 가이드를 만들어 드릴게요."
              action={
                <Link href="/projects/new" className={buttonVariants({ size: "sm" })}>
                  첫 프로젝트 만들기
                </Link>
              }
            />
          ) : (
            <ul className="mt-4 space-y-3">
              {projects.map((p) => {
                // 완료율 — '응답'(제출 완료) 기준. 진행중(발화만 한) 세션은 분모엔 잡히되 완료로 세지 않는다.
                const pct =
                  p.session_count > 0 ? Math.round((p.completed_count / p.session_count) * 100) : 0;
                return (
                  <li key={p.id}>
                    <Link
                      href={`/projects/${p.id}`}
                      className="block rounded-card bg-white p-5 shadow-card ring-1 ring-silver transition-colors hover:bg-paper"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-base font-medium text-obsidian">
                          {p.title || p.topic}
                        </span>
                        <Badge tone={STATUS_TONE[p.status]}>{STATUS_LABEL[p.status]}</Badge>
                      </div>
                      <p className="mt-1 text-meta text-charcoal">{p.topic}</p>
                      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                        {/* '응답'은 제출 완료 기준이다. session_count 는 발화한 세션이라
                            둘의 차가 아직 제출하지 않은 진행중 인원이 된다. 응답자 아바타 스택은
                            안 쓴다(익명) — 카운트/완료율 시각화로 대신한다(design.md §5). */}
                        <p className="font-mono text-2xs text-grey">
                          {formatDate(p.created_at)} · 응답 {p.completed_count}건
                          {p.session_count > p.completed_count &&
                            ` · 진행중 ${p.session_count - p.completed_count}건`}
                        </p>
                        {p.session_count > 0 && (
                          <div className="flex items-center gap-1.5">
                            <span className="h-1.5 w-16 overflow-hidden rounded-full bg-platinum">
                              <span
                                className="block h-full rounded-full bg-red transition-[width]"
                                style={{ width: `${pct}%` }}
                              />
                            </span>
                            <span className="font-mono text-2xs text-grey">완료율 {pct}%</span>
                          </div>
                        )}
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </Container>
    </main>
  );
}
