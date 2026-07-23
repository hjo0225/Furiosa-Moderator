"use client";

// C-1 새 프로젝트 — 조사 브리프(목적·대상·동기·활용)와 참고 자료를 한곳에서 입력한다.
// 제출 시 프로젝트를 만들고, 자료가 있으면 그 프로젝트에 업로드한 뒤 상세로 이동한다.
//
// AI 정제(C-1): 급히 적은 네 칸을 NPU 가 명확한 문장으로 다듬고, **원문 vs 정제본**을 나란히
// 보여준 뒤 항목별로 적용한다. LLM 은 표현만 다듬고 내용을 지어내지 않는다(api/prompts/refine.py).
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Check, RotateCcw, Sparkles, X } from "lucide-react";

import { Button, buttonVariants, Container } from "@/components/shared";
import { createProject, refineBrief, uploadMaterial, type BriefRefine } from "@/lib/api";
import { cn } from "@/lib/utils";

const inputCls =
  "w-full rounded-lg bg-white px-3 py-2.5 text-base text-obsidian ring-1 ring-silver placeholder:text-grey/60 focus:outline-none focus:ring-red";

// 폼 네 필드의 키 — 정제 결과와 1:1 매핑에 쓴다.
type FieldKey = "topic" | "target" | "motivation" | "utilization";
const FIELD_LABEL: Record<FieldKey, string> = {
  topic: "조사 목적",
  target: "타깃 대상",
  motivation: "동기",
  utilization: "활용 방안",
};

export function NewProjectForm() {
  const router = useRouter();
  const [purpose, setPurpose] = useState(""); // 조사 목적 — 백엔드 topic 필드에 저장
  const [target, setTarget] = useState("");
  const [motivation, setMotivation] = useState("");
  const [utilization, setUtilization] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // AI 정제 상태
  const [refining, setRefining] = useState(false);
  const [refined, setRefined] = useState<BriefRefine | null>(null);
  const [refineError, setRefineError] = useState<string | null>(null);
  const [applied, setApplied] = useState<Set<FieldKey>>(new Set()); // 이미 적용한 항목(중복 방지·표시)

  const values: Record<FieldKey, string> = {
    topic: purpose,
    target,
    motivation,
    utilization,
  };
  const setters: Record<FieldKey, (v: string) => void> = {
    topic: setPurpose,
    target: setTarget,
    motivation: setMotivation,
    utilization: setUtilization,
  };

  // 조사 목적·타깃 대상·동기·활용 방안은 모두 필수. 참고 자료만 선택.
  const canSubmit =
    purpose.trim() !== "" &&
    target.trim() !== "" &&
    motivation.trim() !== "" &&
    utilization.trim() !== "";

  const hasAnyInput = (Object.values(values) as string[]).some((v) => v.trim() !== "");

  async function refine() {
    if (!hasAnyInput || refining) return;
    setRefining(true);
    setRefineError(null);
    setRefined(null);
    setApplied(new Set());
    try {
      const out = await refineBrief({
        topic: purpose.trim(),
        target: target.trim(),
        motivation: motivation.trim(),
        utilization: utilization.trim(),
      });
      setRefined(out);
    } catch {
      setRefineError("다듬기에 실패했어요. 잠시 후 다시 시도해 주세요.");
    } finally {
      setRefining(false);
    }
  }

  /** 정제본을 폼에 반영. 원문 대비 실제로 달라진 항목만 나온다(applyChangedOnly 계산). */
  function applyField(key: FieldKey) {
    if (!refined) return;
    setters[key](refined[key].text);
    setApplied((prev) => new Set(prev).add(key));
  }
  function applyAll() {
    if (!refined) return;
    changedKeys.forEach((k) => setters[k](refined[k].text));
    setApplied(new Set(changedKeys));
  }

  // 정제본이 원문과 실제로 다른 항목만 비교로 보여준다(빈 항목·무변경은 숨김).
  const changedKeys: FieldKey[] = refined
    ? (Object.keys(FIELD_LABEL) as FieldKey[]).filter((k) => {
        const r = refined[k].text.trim();
        return r !== "" && r !== values[k].trim();
      })
    : [];

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
      router.push(`/projects/${p.id}`);
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

            {/* AI 정제 — 급히 적은 브리프를 NPU 가 명확하게 다듬는다. 원문과 나란히 비교. */}
            <div className="pt-1">
              <button
                type="button"
                onClick={refine}
                disabled={!hasAnyInput || refining}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full px-3.5 py-2 text-meta font-medium transition-colors",
                  "bg-blush text-red ring-1 ring-red/20 hover:bg-red/10",
                  "disabled:opacity-40 disabled:cursor-not-allowed",
                )}
              >
                <Sparkles className={cn("h-3.5 w-3.5", refining && "animate-pulse")} aria-hidden="true" />
                {refining ? "다듬는 중…" : "AI로 다듬기"}
              </button>
              <p className="mt-1 text-2xs text-grey">
                급히 적어도 괜찮아요. AI가 명확한 문장으로 다듬고, 원문과 비교해 보여드려요.
              </p>
              {refineError && <p className="mt-1 text-2xs text-maroon">{refineError}</p>}
            </div>
          </div>

          {/* 정제 결과 — 원문 vs 정제본 비교. 실제로 달라진 항목만 나온다. */}
          {refined && (
            <div className="mt-4 rounded-card bg-blush/40 p-4 ring-1 ring-red/15">
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5 text-meta font-semibold text-red">
                  <Sparkles className="h-4 w-4" aria-hidden="true" />
                  AI가 다듬었어요
                </span>
                <button
                  type="button"
                  onClick={() => setRefined(null)}
                  aria-label="비교 닫기"
                  className="rounded p-1 text-grey hover:bg-white/60 hover:text-charcoal"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>

              {changedKeys.length === 0 ? (
                <p className="mt-3 text-meta text-charcoal">
                  이미 충분히 명확해요. 다듬을 곳을 찾지 못했어요.
                </p>
              ) : (
                <>
                  <ul className="mt-3 space-y-3">
                    {changedKeys.map((k) => {
                      const isApplied = applied.has(k);
                      return (
                        <li key={k} className="rounded-lg bg-white p-3 ring-1 ring-silver">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-2xs font-semibold uppercase tracking-wide text-grey">
                              {FIELD_LABEL[k]}
                            </span>
                            {refined[k].note && (
                              <span className="text-2xs text-grey">{refined[k].note}</span>
                            )}
                          </div>
                          <p className="mt-1.5 text-meta text-grey line-through decoration-grey/40">
                            {values[k].trim() || "(비어 있음)"}
                          </p>
                          <p className="mt-1 text-base text-obsidian">{refined[k].text}</p>
                          <div className="mt-2">
                            {isApplied ? (
                              <span className="inline-flex items-center gap-1 text-2xs font-medium text-go">
                                <Check className="h-3.5 w-3.5" aria-hidden="true" />
                                적용됨 — 위 입력칸에서 더 고칠 수 있어요
                              </span>
                            ) : (
                              <button
                                type="button"
                                onClick={() => applyField(k)}
                                className="inline-flex items-center gap-1 rounded-md bg-red px-2.5 py-1 text-2xs font-medium text-white transition-colors hover:bg-red-dark"
                              >
                                <Check className="h-3.5 w-3.5" aria-hidden="true" />
                                이 문장으로 바꾸기
                              </button>
                            )}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button
                      type="button"
                      size="sm"
                      onClick={applyAll}
                      disabled={changedKeys.every((k) => applied.has(k))}
                    >
                      모두 적용
                    </Button>
                    <button
                      type="button"
                      onClick={refine}
                      disabled={refining}
                      className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "gap-1.5")}
                    >
                      <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                      다시 다듬기
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

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
