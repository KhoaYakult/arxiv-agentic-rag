import { PaperView } from "@/components/paper-view";

export default async function PaperPage({ params }: { params: Promise<{ paperId: string }> }) {
  const { paperId } = await params;
  const id = decodeURIComponent(paperId);
  return <PaperView key={id} paperId={id} />;
}
