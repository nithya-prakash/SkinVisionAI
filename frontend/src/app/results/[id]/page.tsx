import { ResultsClient } from "./ResultsClient";

export default async function ResultsPage({
  params,
}: PageProps<"/results/[id]">) {
  const { id } = await params;

  return <ResultsClient analysisId={id} />;
}
