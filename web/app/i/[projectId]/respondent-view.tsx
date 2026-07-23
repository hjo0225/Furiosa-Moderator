"use client";

// 응답자 화면 — 동의(R-1) → 인터뷰(R-2·R-3) → 완료(R-4). 모바일 우선.
// InAppBridge 를 최상단에 mount 한다: 카톡 등 인앱 웹뷰는 getUserMedia 가 막혀 음성 답변이
// 아예 불가능하므로, 인터뷰를 시작시키기 전에 외부 브라우저로 유도해야 한다.
import { useEffect, useState } from "react";
import { CheckCircle2, HeartHandshake } from "lucide-react";

import { InAppBridge } from "@/components/in-app-bridge";
import { InterviewFlow } from "@/components/interview-flow";
import { Button, Card } from "@/components/shared";
import {
  getPublicProject,
  screenParticipant,
  startSession,
  type PublicProject,
  type Session,
} from "@/lib/api";

// screener = 동의 후·인터뷰 전 자격 판정(F4.3). disqualified = 부적격 종료 화면.
type Stage = "consent" | "screener" | "interview" | "done" | "disqualified";

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
  // 스크리너 상태(F4.3) — {문항 id: 선택한 옵션}. 판정은 서버가 하고 여기선 답만 모은다.
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [screening, setScreening] = useState(false);
  const [screenError, setScreenError] = useState<string | null>(null);

  useEffect(() => {
    getPublicProject(projectId)
      .then(setProject)
      .catch(() => setLoadError("인터뷰를 찾을 수 없어요. 링크를 다시 확인해 주세요."));
  }, [projectId]);

  const screenerQs = project?.screener ?? [];
  // 모든 문항에 답해야 다음으로 넘어간다 — 미응답은 서버에서 부적격 처리되므로 실수로 탈락하지 않게 막는다.
  const allAnswered = screenerQs.every((q) => answers[q.id]);

  async function startInterview() {
    const s = await startSession(projectId, true, navigator.userAgent);
    setSession(s);
    setStage("interview");
  }

  async function begin() {
    if (!agreed || starting) return;
    // 스크리너가 있으면 세션을 만들기 전에 자격부터 확인한다(부적격이면 세션·집계 모수에 안 들어간다).
    if (screenerQs.length) {
      setStage("screener");
      return;
    }
    setStarting(true);
    setStartError(null);
    try {
      await startInterview();
    } catch {
      setStartError("인터뷰를 시작하지 못했어요. 잠시 후 다시 시도해 주세요.");
      setStarting(false);
    }
  }

  function pick(qid: string, opt: string) {
    setScreenError(null);
    setAnswers((a) => ({ ...a, [qid]: opt }));
  }

  async function submitScreener() {
    if (screening || !allAnswered) return;
    setScreening(true);
    setScreenError(null);
    try {
      const { qualified } = await screenParticipant(projectId, answers);
      if (!qualified) {
        setStage("disqualified");
        return;
      }
      await startInterview();   // 적격 → 바로 세션 시작
    } catch {
      setScreenError("확인 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.");
      setScreening(false);
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
        className={`mx-auto flex min-h-screen w-full flex-col px-4 py-8 sm:px-6 sm:py-14 ${
          stage === "interview" ? "max-w-3xl" : "max-w-xl"
        }`}
      >
        {loadError ? (
          <Card className="p-8 text-center">
            <p className="text-base text-ink-soft">{loadError}</p>
          </Card>
        ) : !project ? (
          <p className="animate-pulse text-center font-mono text-meta text-ink-faint">
            불러오는 중…
          </p>
        ) : project.status === "closed" ? (
          <Card className="p-8 text-center">
            <p>
              <HeartHandshake className="inline-block h-7 w-7 text-ink-soft" aria-hidden="true" />
            </p>
            <h1 className="mt-3 text-lead font-medium">마감된 인터뷰예요</h1>
            <p className="mt-2 text-meta leading-relaxed text-ink-soft">
              이 인터뷰는 모집이 끝났어요. 관심 가져주셔서 감사합니다.
            </p>
          </Card>
        ) : stage === "consent" ? (
          <section>
            <p className="eyebrow">음성 인터뷰</p>
            <h1 className="mt-4 text-title">{project.title || project.topic}</h1>
            <p className="mt-3 text-base leading-relaxed text-ink-soft">
              AI 진행자가 음성으로 질문을 드려요. 말하거나 직접 입력해서 답해 주시면 됩니다.
              5~10분 정도 걸려요.
            </p>

            {/* R-1 — 수집 목적·항목·보관기간을 명시하고, 동의 없이는 진행할 수 없다 */}
            <Card className="mt-6 p-5">
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
            </Card>

            {startError && <p className="mt-3 text-meta text-nogo">{startError}</p>}

            <Button
              type="button"
              size="lg"
              onClick={begin}
              disabled={!agreed || starting}
              className="mt-6 w-full"
            >
              {starting ? "준비 중…" : "동의하고 인터뷰 시작"}
            </Button>
            {!agreed && (
              <p className="mt-2 text-2xs text-ink-faint">
                동의해 주셔야 인터뷰를 시작할 수 있어요.
              </p>
            )}
          </section>
        ) : stage === "screener" ? (
          /* F4.3 참가 조건 — 동의 후·인터뷰 전 단일선택 자격 문항. 통과 조건은 서버만 안다. */
          <section>
            <p className="eyebrow">참가 조건 확인</p>
            <h1 className="mt-4 text-title">몇 가지만 확인할게요</h1>
            <p className="mt-3 text-base leading-relaxed text-ink-soft">
              이 인터뷰에 맞는 분인지 확인하기 위한 짧은 질문이에요. 각 문항에 하나씩 골라 주세요.
            </p>

            <div className="mt-6 space-y-4">
              {screenerQs.map((q, qi) => (
                <Card key={q.id} className="p-5">
                  <fieldset>
                    <legend className="text-base font-medium text-ink">
                      {qi + 1}. {q.text}
                    </legend>
                    <div className="mt-3 space-y-2">
                      {q.options.map((opt) => (
                        <label
                          key={opt}
                          className={`flex cursor-pointer items-center gap-3 rounded-lg bg-bg p-3 ring-1 ${
                            answers[q.id] === opt ? "ring-accent" : "ring-line"
                          }`}
                        >
                          <input
                            type="radio"
                            name={q.id}
                            value={opt}
                            checked={answers[q.id] === opt}
                            onChange={() => pick(q.id, opt)}
                            className="h-5 w-5 shrink-0 accent-[color:var(--accent-solid)]"
                          />
                          <span className="text-meta leading-relaxed text-ink">{opt}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                </Card>
              ))}
            </div>

            {screenError && <p className="mt-3 text-meta text-nogo">{screenError}</p>}

            <div className="mt-6 flex justify-center">
              <Button
                type="button"
                size="lg"
                onClick={submitScreener}
                disabled={!allAnswered || screening}
                className="w-full max-w-xs"
              >
                {screening ? "확인 중…" : "다음"}
              </Button>
            </div>
            {!allAnswered && (
              <p className="mt-2 text-center text-2xs text-ink-faint">
                모든 질문에 답해 주시면 다음으로 넘어갈 수 있어요.
              </p>
            )}
          </section>
        ) : stage === "disqualified" ? (
          /* F4.3 부적격 — 정중한 종료. 세션을 만들지 않았으므로 집계 모수에 들어가지 않는다. */
          <section className="mx-auto max-w-md rounded-2xl bg-surface p-8 text-center shadow-card ring-1 ring-line sm:p-10">
            <p>
              <HeartHandshake className="inline-block h-8 w-8 text-ink-soft" aria-hidden="true" />
            </p>
            <h1 className="mt-4 text-title">감사합니다</h1>
            <p className="mt-3 text-base leading-relaxed text-ink-soft">
              참여해 주셔서 감사하지만, 이번 조사 대상에는 해당하지 않으세요.
            </p>
            <p className="mt-4 text-meta leading-relaxed text-ink-faint">
              관심 가져주셔서 진심으로 감사드려요. 이제 창을 닫으셔도 좋아요.
            </p>
          </section>
        ) : stage === "interview" && session ? (
          <section className="flex flex-1 flex-col">
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
          <section className="mx-auto max-w-md rounded-2xl bg-surface p-8 text-center shadow-card ring-1 ring-line sm:p-10">
            <p>
              <CheckCircle2 className="inline-block h-8 w-8 text-go" aria-hidden="true" />
            </p>
            <h1 className="mt-4 text-title">제출됐어요</h1>
            <p className="mt-3 text-base leading-relaxed text-ink-soft">
              시간 내어 답변해 주셔서 감사합니다.{turnCount > 0 && ` 총 ${turnCount}개의 답변을 남겨주셨어요.`}
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
