import type { ReactNode } from "react";

import { ContentHeader } from "@/components/shell/content-header";
import { Sidebar } from "@/components/shell/sidebar";

// 의뢰자 앱 셸 — /projects 이하 전체(목록·상세·새 프로젝트)에만 적용된다.
// 응답자 라우트(/i/*)와 랜딩(/)은 이 레이아웃 밖이라 영향받지 않는다(design.md §0 이원화).
// active 유추는 Sidebar 내부에서 pathname 으로 처리하므로 이 레이아웃은 서버 컴포넌트로 남는다.
// ContentHeader(뒤로·브레드크럼)도 동일 이유로 콘텐츠 컬럼 안에서 pathname 을 직접 읽는다.
export default function ProjectsLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-canvas md:flex">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <ContentHeader />
        {children}
      </div>
    </div>
  );
}
