import { ProjectsView } from "./projects-view";

// 백엔드 없이도 빌드가 통과해야 한다 — 데이터는 전부 클라이언트에서 가져오고, 이 페이지는 셸만 낸다.
export const dynamic = "force-dynamic";

export default function ProjectsPage() {
  return <ProjectsView />;
}
