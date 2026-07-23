import { BenchmarkView } from "@/components/benchmark/benchmark-view";

// 백엔드 없이도 빌드가 통과해야 한다 — 데이터는 클라이언트에서 가져오고, 이 페이지는 셸만 낸다.
// 셸(사이드바)은 app/projects/layout.tsx 가 이 라우트까지 포함해서 감싼다.
export const dynamic = "force-dynamic";

export default function BenchmarkPage() {
  return <BenchmarkView />;
}
