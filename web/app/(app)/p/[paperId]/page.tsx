import { PaperView } from "@/components/paper-view";

export default async function PaperPage({ params }: { params: Promise<{ paperId: string }> }) {
  const { paperId } = await params;
  return <PaperView paperId={decodeURIComponent(paperId)} />;
}
