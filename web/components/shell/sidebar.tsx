"use client";

// 의뢰자 앱 셸 — 좌측 사이드바. design.md §5 "앱 셸(의뢰자)".
// 무인증 MVP: 워크스페이스 전환·계정 메뉴·유저 아바타 없음. 대신 푸터에
// "로그인 없이, 링크만 공유" 안내를 둬서 무인증을 특징으로 드러낸다.
import type { LucideIcon } from "lucide-react";
import { Folder, Link as LinkIcon, Menu, Search, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Skeleton } from "@/components/shared";
import { listProjects, type Project } from "@/lib/api";
import { cn } from "@/lib/utils";

export type SidebarActive = "projects";

interface NavItem {
  key: SidebarActive;
  href: string;
  label: string;
  icon: LucideIcon;
}

// 실존 화면만 올린다(design.md §5) — 아직 없는 화면(설정 등)은 네비에 안 넣는다.
const NAV_ITEMS: NavItem[] = [
  { key: "projects", href: "/projects", label: "프로젝트", icon: Folder },
];

// 서브리스트 상태 점 — 카드(design.md §5)의 배지 톤과 동일 매핑을 점으로 축약.
const STATUS_DOT: Record<Project["status"], string> = {
  draft: "bg-red",
  deployed: "bg-obsidian",
  closed: "bg-grey",
};

const SUBNAV_MAX = 8;

/**
 * `프로젝트` 네비 아래 최근 프로젝트 목록(design.md §5). 상세로 들어간 뒤 다른
 * 프로젝트로 건너뛸 동선이 없던 문제를 여기서 메운다.
 * pathname 이 바뀔 때마다 다시 불러와 방금 만든 프로젝트도 반영한다(가벼운 GET).
 */
function ProjectSubNav({
  activeProjectId,
  onNavigate,
}: {
  activeProjectId: string | null;
  onNavigate: () => void;
}) {
  const pathname = usePathname();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listProjects()
      .then((ps) => {
        if (cancelled) return;
        setProjects(ps);
        setLoadError(false);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  // 보조 내비일 뿐이다 — 실패해도 사이드바 본체(네비·검색·푸터)는 그대로 둔다.
  if (loadError) return null;

  if (projects === null) {
    return (
      <div className="mt-1 space-y-1 pb-1 pl-8 pr-2">
        <Skeleton className="h-7 w-full" />
        <Skeleton className="h-7 w-full" />
        <Skeleton className="h-7 w-4/5" />
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <p className="mt-1 pb-1 pl-8 pr-3 text-meta text-grey">아직 프로젝트가 없어요</p>
    );
  }

  const shown = projects.slice(0, SUBNAV_MAX);
  const hasMore = projects.length > SUBNAV_MAX;

  return (
    <div className="mt-1 space-y-0.5 pb-1 pl-8 pr-2">
      {shown.map((p) => {
        const isActive = p.id === activeProjectId;
        return (
          <Link
            key={p.id}
            href={`/projects/${p.id}`}
            onClick={onNavigate}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-md px-2 py-1.5 text-meta transition-colors",
              isActive ? "bg-blush text-red font-medium" : "text-charcoal hover:bg-paper",
            )}
          >
            <span
              className={cn("h-2 w-2 shrink-0 rounded-full", STATUS_DOT[p.status])}
              aria-hidden="true"
            />
            <span className="min-w-0 flex-1 truncate">{p.title || p.topic}</span>
          </Link>
        );
      })}
      {hasMore && (
        <Link
          href="/projects"
          onClick={onNavigate}
          className="block px-2 py-1.5 text-meta font-medium text-grey transition-colors hover:text-charcoal"
        >
          전체 보기
        </Link>
      )}
    </div>
  );
}

/**
 * `active` 는 현재 네비가 하나뿐이라 항상 projects 로 떨어진다 — 화면이 늘어날 때
 * 다시 경로로 유추한다. 레이아웃이 서버 컴포넌트로 남을 수 있도록 pathname 을 읽는
 * 일은 이 컴포넌트 안에서 끝낸다.
 */
export function Sidebar({ active }: { active?: SidebarActive }) {
  const pathname = usePathname();
  const resolvedActive: SidebarActive = active ?? "projects";
  // 서브리스트 활성 강조용 — /projects/{id} 형태일 때만 id, /projects/new 은 제외.
  const pathSegments = pathname?.split("/").filter(Boolean) ?? [];
  const activeProjectId =
    pathSegments[0] === "projects" && pathSegments[1] && pathSegments[1] !== "new"
      ? pathSegments[1]
      : null;
  const [mobileOpen, setMobileOpen] = useState(false);
  // md 이상은 항상 보이는 고정 사이드바라 아래 "닫힘" a11y 잠금을 절대 걸면 안 된다.
  // 뷰포트를 직접 추적해서, md 미만 + 닫힘일 때만 잠근다(md: 로는 aria/inert 를
  // 조건부로 못 걸므로 matchMedia 로 판별). 초기값 false(=잠그지 않음)로 두어
  // SSR·데스크톱 첫 페인트에서 실수로 데스크톱 사이드바를 잠그지 않는다.
  const [isMobileViewport, setIsMobileViewport] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia("(max-width: 767px)");
    const update = () => setIsMobileViewport(mql.matches);
    update();
    mql.addEventListener("change", update);
    return () => mql.removeEventListener("change", update);
  }, []);

  // 모바일 드로어가 열려 있는 동안 Escape 로 닫는다(다이얼로그 표준 동작).
  useEffect(() => {
    if (!mobileOpen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setMobileOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  const mobileDialogOpen = isMobileViewport && mobileOpen;
  const mobileClosed = isMobileViewport && !mobileOpen;
  // inert 는 @types/react 18.3 에 아직 타입이 없어 캐스팅으로 우회한다 — 붙이면 포커스 가능한
  // 하위 요소 전부와 접근성 트리에서 자동으로 빠진다(개별 tabIndex 관리보다 안전).
  const inertProps = mobileClosed
    ? ({ inert: "" } as unknown as React.HTMLAttributes<HTMLElement>)
    : {};

  return (
    <>
      {/* 모바일 상단 바 — md 이상에서는 고정 사이드바가 대신하므로 숨긴다. */}
      <div className="flex items-center justify-between border-b border-silver bg-canvas px-4 py-3 md:hidden">
        <Link href="/projects" className="flex items-center gap-2">
          <img src="/mindlens-logo.svg" alt="mindlens" width={24} height={24} />
          <span className="text-base font-semibold text-obsidian">mindlens</span>
        </Link>
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="flex h-11 w-11 items-center justify-center rounded text-charcoal hover:bg-blush"
          aria-label="메뉴 열기"
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>

      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-obsidian/30 md:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside
        {...inertProps}
        role={mobileDialogOpen ? "dialog" : undefined}
        aria-modal={mobileDialogOpen ? true : undefined}
        aria-label={mobileDialogOpen ? "메뉴" : undefined}
        aria-hidden={mobileClosed ? true : undefined}
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-60 shrink-0 flex-col border-r border-silver bg-canvas transition-transform duration-200",
          "md:sticky md:top-0 md:h-screen md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          mobileClosed && "pointer-events-none",
        )}
      >
        <div className="flex items-center justify-between px-5 pb-5 pt-6">
          <Link href="/projects" className="flex items-center gap-2">
            <img src="/mindlens-logo.svg" alt="mindlens" width={24} height={24} />
            <span className="text-lead font-semibold tracking-tight text-obsidian">mindlens</span>
          </Link>
          <button
            type="button"
            onClick={() => setMobileOpen(false)}
            className="flex h-11 w-11 items-center justify-center rounded text-charcoal hover:bg-blush md:hidden"
            aria-label="메뉴 닫기"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {/* 검색 — 시각만(⌘K 힌트 칩 포함), 핸들러는 후속 태스크. */}
        <div className="px-4">
          <div className="flex items-center gap-2 rounded-lg border border-silver bg-paper px-3 py-2">
            <Search className="h-4 w-4 shrink-0 text-grey" aria-hidden="true" />
            <span className="flex-1 text-meta text-grey">프로젝트 검색</span>
            <span className="rounded border border-platinum bg-canvas px-1.5 py-0.5 font-mono text-2xs text-grey">
              ⌘K
            </span>
          </div>
        </div>

        <nav className="mt-6 flex-1 space-y-1 px-3">
          {NAV_ITEMS.map(({ key, href, label, icon: Icon }) => {
            const isActive = resolvedActive === key;
            return (
              <div key={key}>
                <Link
                  href={href}
                  onClick={() => setMobileOpen(false)}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-base font-medium transition-colors",
                    isActive ? "bg-blush text-red" : "text-charcoal hover:bg-paper",
                  )}
                >
                  <Icon
                    className={cn("h-4 w-4", isActive ? "text-red" : "text-grey")}
                    aria-hidden="true"
                  />
                  {label}
                </Link>
                {/* 프로젝트 네비 아래 최근 프로젝트 서브리스트(design.md §5) — 상세로 들어간
                    뒤에도 다른 프로젝트로 바로 건너뛸 동선을 준다. */}
                {key === "projects" && (
                  <ProjectSubNav
                    activeProjectId={activeProjectId}
                    onNavigate={() => setMobileOpen(false)}
                  />
                )}
              </div>
            );
          })}
        </nav>

        {/* '새 프로젝트' CTA 는 각 페이지 헤더에만 둔다 — 사이드바에도 두면 첫 화면에
            같은 버튼이 두 개 보인다(종합 리뷰 지적). */}

        {/* 푸터 — 계정 메뉴가 아니다. 무인증 MVP 안내(design.md §5). */}
        <div className="flex items-center gap-2 border-t border-silver px-5 py-4 text-meta text-grey">
          <LinkIcon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>로그인 없이, 링크만 공유</span>
        </div>
      </aside>
    </>
  );
}
