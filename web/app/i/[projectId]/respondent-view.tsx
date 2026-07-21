"use client";

// 응답자 화면 — 동의(R-1) → 인터뷰(R-2·R-3) → 완료(R-4). 모바일 우선.
// InAppBridge 를 최상단에 mount 한다: 카톡 등 인앱 웹뷰는 getUserMedia 가 막혀 음성 답변이
// 아예 불가능하므로, 인터뷰를 시작시키기 전에 외부 브라우저로 유도해야 한다.
import { useEffect, useState } from "react";

import { InAppBridge } from "@/components/in-app-bridge";
import { InterviewFlow } from "@/components/interview-flow";
import { Button } from "@/components/shared";
import {
  getPublicProject,
  startSession,
  type PublicProject,
  type Session,
} from "@/lib/api";

type Stage = "consent" | "interview" | "done";

const RETENTION = "수집일로부터 1년";

export function RespondentView({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<PublicProject | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  const [stage, setStage] = useState<Stage>("consent");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [turnCount, setTurnCount] = useState(0);

  useEffect(() => {
    getPublicProject(projectId)
      .then(setProject)
      .catch(() => setLoadError("인터뷰를 찾을 수 없어요. 링크를 다시 확인해 주세요."));
  }, [projectId]);

  async function begin() {
    if (!agreed || starting) return;
    setStarting(true);
    setStartError(null);
    try {
      const s = await startSession(projectId, true, navigator.userAgent);
      setSession(s);
      setStage("interview");
    } catch {
      setStartError("인터뷰를 시작하지 못했어요. 잠시 후 다시 시도해 주세요.");
      setStarting(false);
    }
  }

  function handleComplete(answerCount: number) {
    setTurnCount(answerCount);
    setStage("done");
  }

  return (
    <>
      <InAppBridge />
      <main
        className={`mx-auto min-h-screen w-full px-4 py-8 sm:px-6 sm:py-12 ${
          stage === "interview" ? "max-w-3xl" : "max-w-lg"
        }`}
      >
        {loadError ? (
          <div className="rounded-2xl bg-surface p-8 text-center shadow-card">
            <p className="text-base text-ink-soft">{loadError}</p>
          </div>
        ) : !project ? (
          <p className="animate-pulse text-center font-mono text-meta text-ink-faint">
            불러오는 중…
          </p>
        ) : project.status === "closed" ? (
          <div className="rounded-2xl bg-surface p-8 text-center shadow-card">
            <p className="text-2xl" aria-hidden>
              🙏
            </p>
            <h1 className="mt-3 text-lead font-medium">마감된 인터뷰예요</h1>
            <p className="mt-2 text-meta leading-relaxed text-ink-soft">
              이 인터뷰는 모집이 끝났어요. 관심 가져주셔서 감사합니다.
            </p>
          </div>
        ) : stage === "consent" ? (
          <section>
            <p className="eyebrow">음성 인터뷰</p>
            <h1 className="mt-4 text-title">{project.title || project.topic}</h1>
            <p className="mt-3 text-base leading-relaxed text-ink-soft">
              AI 진행자가 음성으로 질문을 드려요. 말하거나 직접 입력해서 답해 주시면 됩니다.
              5~10분 정도 걸려요.
            </p>

            {/* R-1 — 수집 목적·항목·보관기간을 명시하고, 동의 없이는 진행할 수 없다 */}
            <div className="mt-6 rounded-2xl bg-surface p-5 shadow-card ring-1 ring-line">
              <h2 className="text-base font-medium text-ink">개인정보 수집·이용 동의</h2>
              <dl className="mt-4 space-y-3 text-meta leading-relaxed">
                <div>
                  <dt className="font-medium text-ink">수집 목적</dt>
                  <dd className="mt-0.5 text-ink-soft">
                    &lsquo;{project.topic}&rsquo; 주제의 사용자 조사 및 결과 분석
                  </dd>
                </div>
                <div>
                  <dt className="font-medium text-ink">수집 항목</dt>
                  <dd className="mt-0.5 text-ink-soft">
                    인터뷰 대화 내용(음성에서 변환한 텍스트), 접속 브라우저 정보.
                    이름·연락처 등은 수집하지 않으며, 답변 중 개인정보로 보이는 표현은 저장 전에
                    자동으로 가려집니다.
                  </dd>
                </div>
                <div>
                  <dt className="font-medium text-ink">보관 기간</dt>
                  <dd className="mt-0.5 text-ink-soft">{RETENTION} 보관 후 파기</dd>
                </div>
                <div>
                  <dt className="font-medium text-ink">동의 거부 권리</dt>
                  <dd className="mt-0.5 text-ink-soft">
                    동의하지 않으실 수 있으며, 이 경우 인터뷰에 참여할 수 없습니다. 인터뷰 도중
                    언제든 창을 닫아 중단하실 수 있어요.
                  </dd>
                </div>
              </dl>

              <label className="mt-5 flex cursor-pointer items-start gap-3 rounded-lg bg-bg p-3 ring-1 ring-line">
                <input
                  type="checkbox"
                  checked={agreed}
                  onChange={(e) => setAgreed(e.target.checked)}
                  className="mt-0.5 h-5 w-5 shrink-0 accent-[color:var(--accent-solid)]"
                />
                <span className="text-meta leading-relaxed text-ink">
                  위 내용을 읽고 개인정보 수집·이용에 <b>동의합니다.</b>
                </span>
              </label>
            </div>

            {startError && <p className="mt-3 text-meta text-nogo">{startError}</p>}

            <Button
              type="button"
              size="lg"
              onClick={begin}
              disabled={!agreed || starting}
              className="mt-5 w-full"
            >
              {starting ? "준비 중…" : "동의하고 인터뷰 시작"}
            </Button>
            {!agreed && (
              <p className="mt-2 text-center text-2xs text-ink-faint">
                동의해 주셔야 인터뷰를 시작할 수 있어요.
              </p>
            )}
          </section>
        ) : stage === "interview" && session ? (
          <section>
            <h1 className="mb-4 text-lead font-medium">{project.title || project.topic}</h1>
            <InterviewFlow
              projectId={projectId}
              sessionId={session.id}
              onComplete={handleComplete}
            />
            <p className="mt-4 text-center text-2xs leading-relaxed text-ink-faint">
              답변은 익명으로 저장되며 개인정보는 자동으로 가려집니다.
            </p>
          </section>
        ) : (
          /* R-4 완료 */
          <section className="rounded-2xl bg-surface p-8 text-center shadow-card">
            <p className="text-3xl" aria-hidden>
              ✅
            </p>
            <h1 className="mt-4 text-title">제출됐어요</h1>
            <p className="mt-3 text-base leading-relaxed text-ink-soft">
              시간 내어 답변해 주셔서 감사합니다.
              {turnCount > 0 && ` 총 ${turnCount}개의 답변을 남겨주셨어요.`}
            </p>
            <p className="mt-4 text-meta leading-relaxed text-ink-faint">
              답변은 익명으로 저장되었고, {RETENTION} 보관 후 파기됩니다. 이제 창을 닫으셔도 좋아요.
            </p>
          </section>
        )}
      </main>
    </>
  );
}
