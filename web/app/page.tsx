import Link from "next/link";

import { buttonVariants } from "@/components/shared/button";

// 랜딩 = 최소 스플래시(마케팅 랜딩 아님). design.md §5 "랜딩 = 스플래시".
// 뷰포트 중앙에 로고+워드마크 + 한 줄 태그라인 + 단일 CTA만 둔다. 이 라우트는
// /projects 레이아웃(사이드바) 밖이라 셸 없이 렌더된다(web/app/projects/layout.tsx 주석 참고).
export default function LandingPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-10 bg-paper px-6 py-16 text-center">
      <div className="flex flex-col items-center gap-3">
        <img
          src="/mindlens-logo.svg"
          alt="mindlens"
          width={64}
          height={64}
          className="h-14 w-14 md:h-16 md:w-16"
        />
        <span className="text-2xl font-semibold tracking-tight text-obsidian">mindlens</span>
      </div>

      <div className="flex flex-col items-center gap-6">
        <h1 className="max-w-md text-title text-obsidian md:text-display">
          설문으로는 안 나오던 <span className="text-red">진짜 이유</span>를 듣습니다
        </h1>

        <Link href="/projects" className={buttonVariants({ size: "lg" })}>
          시작하기
        </Link>

        <p className="text-meta text-grey">가입 없이 바로 · 링크만 공유</p>
      </div>
    </main>
  );
}
