import { RespondentView } from "./respondent-view";

export const dynamic = "force-dynamic";

export default function RespondentPage({ params }: { params: { projectId: string } }) {
  return <RespondentView projectId={params.projectId} />;
}
