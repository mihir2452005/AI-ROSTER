import ChatClient from "../ChatClient";

export default function ChatPage({ params }: { params: { sessionId: string } }) {
  return <ChatClient sessionId={params.sessionId} />;
}
