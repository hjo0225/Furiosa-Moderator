import { ProjectView } from "./project-view";

export const dynamic = "force-dynamic";

export default function ProjectDetailPage({ params }: { params: { id: string } }) {
  return <ProjectView projectId={params.id} />;
}
