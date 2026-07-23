"use client";

// 프로젝트 상세 — 가이드 검토·수정(C-2) + 배포(C-3) | 결과 대시보드(C-4) + 내보내기(C-5).
import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Trash2 } from "lucide-react";

import {
  Badge,
  type BadgeTone,
  Button,
  ConfirmDialog,
  Container,
  ErrorState,
  Skeleton,
  useToast,
} from "@/components/shared";
import { deleteProject, getProject, type Project } from "@/lib/api";
import { cn } from "@/lib/utils";

import { GuidePanel } from "./guide-panel";
import { ResultsPanel } from "./results-panel";

type Tab = "guide" | "results";

const TABS: Tab[] = ["guide", "results"];

const STATUS_LABEL: Record<Project["status"], string> = {
  draft: "작성 중",
  deployed: "배포됨",
  closed: "종료",
};

const STATUS_TONE: Record<Project["status"], BadgeTone> = {
  draft: "draft",
  deployed: "live",
  closed: "closed",
};

export function ProjectView({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState(false);
  // 탭은 URL 이 소유한다 — 공유·뒤로가기·새로고침이 동작해야 한다(design.md §5 / ui-ux-pro-max Deep Linking).
  // 예전엔 useState 라 결과 화면 링크를 보내도 상대는 가이드 탭을 봤다.
  const search = useSearchParams();
  const tabParam = search?.get("tab");
  const urlTab = TABS.includes(tabParam as Tab) ? (tabParam as Tab) : null;
  // URL 에 tab 이 없을 때만 '응답 있으면 결과부터' 기본값이 적용된다.
  const [autoTab, setAutoTab] = useState<Tab>("guide");
  const tab: Tab = urlTab ?? autoTab;

  const setTab = useCallback(
    (next: Tab) => {
      setAutoTab(next);
      const qs = new URLSearchParams(Array.from(search?.entries() ?? []));
      qs.set("tab", next);
      if (next !== "results") qs.delete("view");   // 결과 하위 탭은 결과 탭에서만 의미가 있다
      router.replace(`?${qs.toString()}`, { scroll: false });
    },
    [router, search],
  );
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const { show: toast } = useToast();

  const reload = useCallback(() => {
    getProject(projectId)
      .then((p) => {
        setProject(p);
        setError(false);
      })
      .catch(() => setError(true));
  }, [projectId]);

  useEffect(reload, [reload]);

  // 생성 직후 캐리오버(new-project-form 이 ?created=1 로 보낸다) — 도착지에서 1회 토스트.
  // URL 은 바로 정리해 공유·새로고침 때 다시 뜨지 않게 한다.
  useEffect(() => {
    if (search?.get("created") !== "1") return;
    toast({ tone: "success", message: "프로젝트를 만들었어요. 가이드를 생성해 보세요." });
    const qs = new URLSearchParams(Array.from(search?.entries() ?? []));
    qs.delete("created");
    router.replace(qs.toString() ? `?${qs.toString()}` : window.location.pathname, { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 이미 응답이 쌓여 있으면 결과 탭을 먼저 보여준다.
  // 제출 완료 기준이다 — 진행중인 세션으로 열면 아무것도 없는 결과 화면이 첫 화면이 된다.
  useEffect(() => {
    if (!urlTab && project && project.completed_count > 0) setAutoTab("results");
  }, [project, urlTab]);

  // 최초 로드부터 실패 — 보여줄 프로젝트가 아예 없으니 전면 에러 화면.
  if (error && !project) {
    return (
      <main className="py-10 md:py-16">
        <Container className="max-w-5xl">
          <ErrorState
            title="프로젝트를 불러오지 못했어요"
            body="백엔드가 켜져 있는지 확인해 주세요."
            onRetry={reload}
          />
        </Container>
      </main>
    );
  }

  return (
    <main className="py-10 md:py-16">
      <Container className="max-w-5xl">
        {/* 이미 프로젝트를 보여준 뒤(예: 저장 후 reload) 새로고침만 실패한 경우 —
            화면을 통째로 지우지 않고 이전 상태 위에 알림만 얹는다. */}
        {error && project && (
          <p className="mt-4 text-meta text-maroon">
            방금 새로고침에 실패했어요. 아래는 이전에 불러온 내용이에요.
          </p>
        )}

        {!project ? (
          <div className="mt-3 space-y-3">
            <Skeleton className="h-8 w-72" />
            <Skeleton className="h-4 w-48" />
            <Skeleton className="mt-6 h-10 w-full max-w-xs" />
            <Skeleton className="h-64 w-full" />
          </div>
        ) : (
          <>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <h1 className="text-title text-obsidian">{project.title || project.topic}</h1>
              <Badge tone={STATUS_TONE[project.status]}>{STATUS_LABEL[project.status]}</Badge>
              {/* 파괴적 액션은 제목 줄 끝에 조용히 둔다 — 눈에 띄되 먼저 눌리지 않게 ghost. */}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setConfirmDelete(true)}
                className="ml-auto gap-1.5 text-grey hover:text-maroon"
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
                삭제
              </Button>
            </div>
            {deleteError && <p className="mt-1 text-meta text-maroon">{deleteError}</p>}
            <p className="mt-1 text-base text-charcoal">{project.topic}</p>
            {project.target && (
              <p className="mt-0.5 text-meta text-grey">대상 · {project.target}</p>
            )}
            <p className="mt-2 font-mono text-2xs text-grey">
              응답 {project.completed_count}건
              {project.session_count > project.completed_count &&
                ` · 진행중 ${project.session_count - project.completed_count}건`}
            </p>

            {/* 탭 — 활성 = red 밑줄(design.md §0·§5 단일 red 액센트) */}
            <div className="mt-8 flex gap-1 border-b border-silver" role="tablist">
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
                      ? "border-red text-red"
                      : "border-transparent text-grey hover:text-charcoal",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>

            {/* key={tab} 로 remount → 짧은 페이드(탭 전환이 탁 바뀌지 않게, design.md §7). */}
            <div key={tab} className="mt-6 animate-fade-in">
              {tab === "guide" ? (
                <GuidePanel project={project} onProjectChange={reload} />
              ) : (
                <ResultsPanel projectId={projectId} />
              )}
            </div>
            <ConfirmDialog
              open={confirmDelete}
              busy={deleting}
              title="이 프로젝트를 삭제할까요?"
              body={
                <>
                  <b className="text-obsidian">{project.title || project.topic}</b> 와 함께{" "}
                  <b className="text-obsidian">응답 {project.completed_count}건</b>
                  {project.session_count > project.completed_count &&
                    ` · 진행중 ${project.session_count - project.completed_count}건`}
                  , 인터뷰 가이드, 분석 결과, 업로드한 자료가 모두 지워집니다.{" "}
                  <b className="text-maroon">되돌릴 수 없어요.</b>
                </>
              }
              confirmLabel="삭제"
              onCancel={() => setConfirmDelete(false)}
              onConfirm={async () => {
                setDeleting(true);
                setDeleteError(null);
                try {
                  await deleteProject(projectId);
                  toast({ tone: "success", message: "프로젝트를 삭제했어요." });
                  router.push("/projects");
                } catch {
                  setDeleteError("삭제하지 못했어요. 잠시 후 다시 시도해 주세요.");
                  toast({ tone: "error", message: "삭제하지 못했어요." });
                  setDeleting(false);
                  setConfirmDelete(false);
                }
              }}
            />
          </>
        )}
      </Container>
    </main>
  );
}
