"use client";

// C-1 새 프로젝트 생성 폼 — 보관함(/projects)에서 분리했다. 제출하면 상세로 이동.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, buttonVariants, Container } from "@/components/shared";
import { createProject } from "@/lib/api";
import { cn } from "@/lib/utils";

const inputCls =
  "w-full rounded-lg bg-surface px-3 py-2.5 text-base text-ink ring-1 ring-line placeholder:text-ink-faint/60 focus:outline-none focus:ring-accent";

export function NewProjectForm() {
  const router = useRouter();
  const [topic, setTopic] = useState("");
  const [title, setTitle] = useState("");
  const [target, setTarget] = useState("");
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

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
      <Container className="max-w-2xl">
        <Link href="/projects" className="font-mono text-2xs uppercase text-ink-faint">
          ← 내 프로젝트
        </Link>
        <h1 className="mt-3 text-title">새 프로젝트</h1>
        <p className="mt-2 text-base text-ink-soft">
          알고 싶은 주제를 적으면 인터뷰 가이드를 만들어 드려요.
        </p>

        <form
          onSubmit={submit}
          className="mt-8 rounded-xl bg-surface p-5 shadow-card ring-1 ring-line"
        >
          <div className="space-y-3">
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
          <div className="mt-4 flex flex-wrap gap-2">
            <Button type="submit" disabled={!topic.trim() || creating}>
              {creating ? "만드는 중…" : "프로젝트 만들기"}
            </Button>
            <Link href="/projects" className={buttonVariants({ variant: "ghost" })}>
              취소
            </Link>
          </div>
        </form>
      </Container>
    </main>
  );
}
