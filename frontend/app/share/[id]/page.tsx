import ShareClient from "./ShareClient";

export default function SharePage({ params }: { params: { id: string } }) {
  return <ShareClient sessionId={params.id} />;
}
