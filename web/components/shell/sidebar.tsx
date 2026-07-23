"use client";

// 의뢰자 앱 셸 — 좌측 사이드바. design.md §5 "앱 셸(의뢰자)".
// 무인증 MVP: 워크스페이스 전환·계정 메뉴·유저 아바타 없음. 대신 푸터에
// "로그인 없이, 링크만 공유" 안내를 둬서 무인증을 특징으로 드러낸다.
import type { LucideIcon } from "lucide-react";
import { Cpu, Folder, Link as LinkIcon, Menu, Plus, Search, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { cn } from "@/lib/utils";

export type SidebarActive = "projects" | "benchmark";

interface NavItem {
  key: SidebarActive;
  href: string;
  label: string;
  icon: LucideIcon;
}

// 실존 화면만 올린다(design.md §5) — 아직 없는 화면(설정 등)은 네비에 안 넣는다.
const NAV_ITEMS: NavItem[] = [
  { key: "projects", href: "/projects", label: "프로젝트", icon: Folder },
  { key: "benchmark", href: "/projects/benchmark", label: "성능 · 벤치마크", icon: Cpu },
];

/**
 * `active` 를 안 주면 현재 경로로 유추한다(`/projects/benchmark` 이하만 benchmark,
 * 그 외 `/projects/*` 는 projects). 레이아웃이 서버 컴포넌트로 남을 수 있도록
 * pathname 유추는 이 컴포넌트 안에서 끝낸다.
 */
export function Sidebar({ active }: { active?: SidebarActive }) {
  const pathname = usePathname();
  const resolvedActive: SidebarActive =
    active ?? (pathname?.startsWith("/projects/benchmark") ? "benchmark" : "projects");
  const [mobileOpen, setMobileOpen] = useState(false);

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
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-60 shrink-0 flex-col border-r border-silver bg-canvas transition-transform duration-200",
          "md:sticky md:top-0 md:h-screen md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
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
              <Link
                key={key}
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
            );
          })}
        </nav>

        <div className="px-3 pb-4">
          <Link
            href="/projects/new"
            onClick={() => setMobileOpen(false)}
            className="flex items-center justify-center gap-1.5 rounded-lg bg-red px-3 py-2.5 text-base font-medium text-white transition-colors hover:bg-red-dark active:translate-y-px"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            새 프로젝트
          </Link>
        </div>

        {/* 푸터 — 계정 메뉴가 아니다. 무인증 MVP 안내(design.md §5). */}
        <div className="flex items-center gap-2 border-t border-silver px-5 py-4 text-meta text-grey">
          <LinkIcon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>로그인 없이, 링크만 공유</span>
        </div>
      </aside>
    </>
  );
}
