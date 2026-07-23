import type { ReactNode } from "react";

import { Sidebar } from "@/components/shell/sidebar";

// 의뢰자 앱 셸 — /projects 이하 전체(목록·상세·새 프로젝트·벤치마크)에만 적용된다.
// 응답자 라우트(/i/*)와 랜딩(/)은 이 레이아웃 밖이라 영향받지 않는다(design.md §0 이원화).
// active 유추는 Sidebar 내부에서 pathname 으로 처리하므로 이 레이아웃은 서버 컴포넌트로 남는다.
export default function ProjectsLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-canvas md:flex">
      <Sidebar />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
