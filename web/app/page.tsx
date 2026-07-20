import Link from "next/link";
import { Container } from "@/components/shared";
import { buttonVariants } from "@/components/shared/button";

const STEPS = [
  {
    no: "01",
    title: "주제를 적습니다",
    body: "알고 싶은 것 한 줄이면 충분해요. AI가 인터뷰 가이드 초안을 만들어 드립니다.",
  },
  {
    no: "02",
    title: "링크를 뿌립니다",
    body: "가이드를 확인하고 배포하면 응답자용 링크가 바로 발급돼요. 설치도 로그인도 필요 없어요.",
  },
  {
    no: "03",
    title: "AI가 인터뷰합니다",
    body: "진행자가 음성으로 질문하고, 답에 따라 꼬리질문을 이어갑니다. 응답자는 말하거나 입력하면 돼요.",
  },
  {
    no: "04",
    title: "인사이트를 받습니다",
    body: "전사·요약·감정 태그가 자동 정리되고, 응답자 전체를 가로지르는 주제까지 뽑아 드려요.",
  },
];

export default function LandingPage() {
  return (
    <main>
      <section className="section-ice section-glow pb-20 pt-16 md:pb-28 md:pt-24">
        <Container className="max-w-prose text-center">
          <p className="eyebrow justify-center">AI 음성 인터뷰 플랫폼</p>
          <h1 className="mt-5 text-display md:text-headline">
            설문으로는 안 나오던 <span className="grad">진짜 이유</span>를 듣습니다
          </h1>
          <p className="mx-auto mt-6 max-w-md text-lead text-ink-soft">
            객관식은 무엇을 골랐는지 알려주지만, 왜 그랬는지는 말해주지 않죠. mindlens는 AI 진행자가
            응답자 한 명 한 명과 대화하며 그 이유를 파고듭니다.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link href="/projects" className={buttonVariants({ size: "lg" })}>
              프로젝트 만들기
            </Link>
            <Link href="/projects" className={buttonVariants({ variant: "outline", size: "lg" })}>
              내 프로젝트 보기
            </Link>
          </div>
          <p className="mt-4 text-meta text-ink-faint">가입 없이 바로 시작할 수 있어요</p>
        </Container>
      </section>

      <section className="py-16 md:py-24">
        <Container>
          <h2 className="text-title text-center">어떻게 진행되나요</h2>
          <ol className="mx-auto mt-10 grid max-w-5xl gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s) => (
              <li key={s.no} className="rounded-xl bg-surface p-6 shadow-card ring-1 ring-line">
                <p className="font-mono text-meta text-accent">{s.no}</p>
                <h3 className="mt-2 text-lead font-medium text-ink">{s.title}</h3>
                <p className="mt-2 text-meta leading-relaxed text-ink-soft">{s.body}</p>
              </li>
            ))}
          </ol>
        </Container>
      </section>

      <section className="section-tint py-16 md:py-20">
        <Container className="max-w-prose text-center">
          <h2 className="text-title">응답자에게는 이렇게 보입니다</h2>
          <p className="mt-4 text-base leading-relaxed text-ink-soft">
            링크를 열면 수집 목적과 보관 기간을 먼저 안내하고, 동의한 경우에만 인터뷰가 시작됩니다.
            개인정보로 보이는 표현은 저장 전에 마스킹돼요.
          </p>
          <Link href="/projects" className={buttonVariants({ className: "mt-8" })}>
            프로젝트 만들기
          </Link>
        </Container>
      </section>

      <footer className="border-t border-line py-8">
        <Container>
          <p className="text-center font-mono text-2xs uppercase text-ink-faint">mindlens</p>
        </Container>
      </footer>
    </main>
  );
}
