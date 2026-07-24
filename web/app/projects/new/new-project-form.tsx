"use client";

// C-1 새 프로젝트 — 조사 브리프(목적·대상·동기·활용)와 참고 자료를 한곳에서 입력한다.
// 제출 시 프로젝트를 만들고, 자료가 있으면 그 프로젝트에 업로드한 뒤 상세로 이동한다.
//
// 브리프 AI 정제는 걷어냈다 — 정제본이 원문보다 나을 때가 드물어 오히려 나쁜 문장을
// 적용하게 만들었다. 브리프는 의뢰자가 쓴 그대로 가이드 생성에 들어간다.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, buttonVariants, Container } from "@/components/shared";
import { createProject, uploadMaterial } from "@/lib/api";
import { cn } from "@/lib/utils";

const inputCls =
  "w-full rounded-lg bg-white px-3 py-2.5 text-base text-obsidian ring-1 ring-silver placeholder:text-grey/60 focus:outline-none focus:ring-red";

export function NewProjectForm() {
  const router = useRouter();
  const [purpose, setPurpose] = useState(""); // 조사 목적 — 백엔드 topic 필드에 저장
  const [target, setTarget] = useState("");
  const [motivation, setMotivation] = useState("");
  const [utilization, setUtilization] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // 조사 목적·타깃 대상·동기·활용 방안은 모두 필수. 참고 자료만 선택.
  const canSubmit =
    purpose.trim() !== "" &&
    target.trim() !== "" &&
    motivation.trim() !== "" &&
    utilization.trim() !== "";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || creating) return;
    setCreating(true);
    setFormError(null);
    try {
      const p = await createProject({
        topic: purpose.trim(),
        target: target.trim(),
        motivation: motivation.trim(),
        utilization: utilization.trim(),
      });
      if (file) {
        try {
          await uploadMaterial(p.id, file);
        } catch {
          // 프로젝트는 이미 생성됨 — 자료 업로드만 실패. 상세로 이동해 이어가게 두되,
          // 조용히 삼키지 않는다. 삼킨 탓에 angle 누락 422 를 한참 못 봤다.
          setFormError("프로젝트는 만들었지만 자료 업로드에 실패했어요. 상세에서 다시 올려 주세요.");
        }
      }
      // ?created=1 로 도착지(project-view)에 성공 토스트를 캐리오버한다.
      router.push(`/projects/${p.id}?created=1`);
    } catch {
      setFormError("프로젝트를 만들지 못했어요. 잠시 후 다시 시도해 주세요.");
      setCreating(false);
    }
  }

  return (
    <main className="py-10 md:py-16">
      <Container className="max-w-2xl">
        <h1 className="text-title text-obsidian">새 프로젝트</h1>
        <p className="mt-2 text-base text-charcoal">
          알고 싶은 것을 적으면 인터뷰 가이드를 만들어 드려요. 참고 자료를 올리면 도메인을 반영해요.
        </p>

        <form
          onSubmit={submit}
          className="mt-8 rounded-card bg-white p-5 shadow-card ring-1 ring-silver"
        >
          <div className="space-y-3">
            <label className="block">
              <span className="text-meta font-medium text-charcoal">
                조사 목적 <span className="text-red">*</span>
              </span>
              <input
                value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
                placeholder="예: 20대 직장인이 아침 식사를 거르는 이유를 알고 싶어요"
                className={cn(inputCls, "mt-1.5")}
                required
              />
            </label>
            <label className="block">
              <span className="text-meta font-medium text-charcoal">
                타깃 대상 <span className="text-red">*</span>
              </span>
              <input
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder="예: 수도권 거주 25~34세 직장인"
                className={cn(inputCls, "mt-1.5")}
                required
              />
            </label>
            <label className="block">
              <span className="text-meta font-medium text-charcoal">
                동기 <span className="text-red">*</span>
              </span>
              <input
                value={motivation}
                onChange={(e) => setMotivation(e.target.value)}
                placeholder="예: 아침 대용식 신제품 기획을 준비 중이에요"
                className={cn(inputCls, "mt-1.5")}
                required
              />
            </label>
            <label className="block">
              <span className="text-meta font-medium text-charcoal">
                활용 방안 <span className="text-red">*</span>
              </span>
              <input
                value={utilization}
                onChange={(e) => setUtilization(e.target.value)}
                placeholder="예: 제품 컨셉과 메시지 방향을 정하는 데 쓸 거예요"
                className={cn(inputCls, "mt-1.5")}
                required
              />
            </label>
          </div>

          <div className="mt-4 space-y-3">
            {/* 참고 자료 — 입력 필드와 한곳에서 */}
            <div className="pt-1">
              <span className="text-meta font-medium text-charcoal">
                참고 자료 <span className="font-normal text-grey">(선택)</span>
              </span>
              <p className="mt-0.5 text-2xs text-grey">
                도메인 자료(.txt · .md · .pdf)를 올리면 그 용어·맥락을 반영해 질문을 만들어요. 긴 파일은 자동 요약돼요.
              </p>
              <label className="mt-2 inline-flex cursor-pointer items-center rounded-full bg-blush px-4 py-2 text-meta font-medium text-red ring-1 ring-red/20 transition-colors hover:bg-red/10">
                <input
                  type="file"
                  accept=".txt,.md,.pdf"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="hidden"
                />
                {file ? "파일 바꾸기" : "파일 선택"}
              </label>
              {file && <span className="ml-2 text-meta text-charcoal">{file.name}</span>}
            </div>
          </div>

          {formError && <p className="mt-3 text-meta text-maroon">{formError}</p>}
          <div className="mt-4 flex flex-wrap gap-2">
            <Button type="submit" disabled={!canSubmit || creating}>
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
