"use client";

// 의뢰자 콘텐츠 헤더바 — `/projects/*` 전 라우트 공통(design.md §5 "콘텐츠 헤더바").
// 사이드바 네비가 `프로젝트` 하나뿐이라 상세 화면에 들어가면 돌아갈 동선이 없었다
// (원래 있던 BackLink 가 사이드바 셸 도입 때 빠졌다) — 이 바가 그 자리를 메운다.
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Skeleton } from "@/components/shared";
import { getProject } from "@/lib/api";

type Crumb = { label: string; href?: string };

/**
 * 경로별 표시:
 * - `/projects`      → "프로젝트" (뒤로 없음)
 * - `/projects/new`  → ← 프로젝트 / 새 프로젝트
 * - `/projects/[id]` → ← 프로젝트 / {제목} — 제목은 getProject 로 fetch, 로딩=스켈레톤,
 *   실패 시 원문 id 대신 "프로젝트"로 대체.
 */
export function ContentHeader() {
  const pathname = usePathname() ?? "";
  const segments = pathname.split("/").filter(Boolean); // ["projects", ...]
  const section = segments[1]; // undefined | "new" | {id}
  const isProjectDetail = section !== undefined && section !== "new";
  const projectId = isProjectDetail ? section : null;

  const [title, setTitle] = useState<string | null>(null);
  const [titleFailed, setTitleFailed] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    setTitle(null);
    setTitleFailed(false);
    getProject(projectId)
      .then((p) => {
        if (!cancelled) setTitle(p.title || p.topic);
      })
      .catch(() => {
        if (!cancelled) setTitleFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const backHref = section === "new" || isProjectDetail ? "/projects" : null;

  const crumbs: Crumb[] = [];
  let showTitleSkeleton = false;

  if (!section) {
    crumbs.push({ label: "프로젝트" });
  } else if (section === "new") {
    crumbs.push({ label: "프로젝트", href: "/projects" });
    crumbs.push({ label: "새 프로젝트" });
  } else {
    crumbs.push({ label: "프로젝트", href: "/projects" });
    if (title !== null) {
      crumbs.push({ label: title });
    } else if (titleFailed) {
      crumbs.push({ label: "프로젝트" });
    } else {
      showTitleSkeleton = true;
    }
  }

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-1 border-b border-silver bg-canvas px-4 md:px-6">
      {backHref && (
        <Link
          href={backHref}
          aria-label="뒤로"
          className="-ml-2 flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-charcoal transition-colors hover:bg-paper"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        </Link>
      )}
      <nav aria-label="이동 경로" className="flex min-w-0 items-center gap-1.5">
        {crumbs.map((c, i) => (
          <span key={i} className="flex min-w-0 items-center gap-1.5">
            {i > 0 && (
              <span className="text-grey" aria-hidden="true">
                /
              </span>
            )}
            {c.href ? (
              <Link
                href={c.href}
                className="shrink-0 text-base font-medium text-charcoal transition-colors hover:text-obsidian"
              >
                {c.label}
              </Link>
            ) : (
              <span className="min-w-0 truncate text-base font-semibold text-obsidian">
                {c.label}
              </span>
            )}
          </span>
        ))}
        {showTitleSkeleton && (
          <span className="flex items-center gap-1.5">
            <span className="text-grey" aria-hidden="true">
              /
            </span>
            <Skeleton className="h-4 w-32" />
          </span>
        )}
      </nav>
    </header>
  );
}
