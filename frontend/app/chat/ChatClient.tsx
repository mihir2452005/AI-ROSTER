"use client";

import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api, friendlyError } from "@/lib/api";
import type {
  ChatMessage,
  Personality,
  RoastMode,
  RoastResponse,
  SessionScores,
} from "@/lib/types";
import ScorePanel from "@/components/ScorePanel";

interface Props {
  sessionId: string;
}

export default function ChatClient({ sessionId }: Props) {
  const router = useRouter();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [scores, setScores] = useState<SessionScores | null>(null);
  const [mode, setMode] = useState<RoastMode>("savage");
  const [personality, setPersonality] = useState<Personality>("savage_one");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ending, setEnding] = useState(false);
  const [finalScores, setFinalScores] = useState<SessionScores | null>(null);
  const [closer, setCloser] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [endedRemote, setEndedRemote] = useState(false);

  const scrollerRef = useRef<HTMLDivElement>(null);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Bootstrap: load session + opener
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const session = await api.getSession(sessionId);
        if (cancelled) return;
        setMode(session.mode);
        setPersonality(session.personality);
        setScores(session.scores);
        setMessages(session.history);
        setEndedRemote(session.is_ended);
        // If the session is already ended (e.g. user refreshed after
        // ending, or deep-linked an ended session), recover the closer
        // from the last assistant message in history so the share UI
        // works without re-calling /end.
        if (session.is_ended && session.history.length > 0) {
          const last = session.history[session.history.length - 1];
          if (last.role === "assistant") {
            setCloser(last.content);
          }
        }
      } catch (e) {
        if (!cancelled) {
          setError(friendlyError(e));
        }
      }
    })();
    return () => { cancelled = true; };
  }, [sessionId]);

  // Auto-scroll
  useEffect(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy]);

  // Cleanup the copy-feedback timer on unmount
  useEffect(() => () => {
    if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
  }, []);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    if (endedRemote || finalScores) {
      setError("This session has ended. Start a new one to keep roasting.");
      return;
    }
    setInput("");
    setError(null);
    setBusy(true);
    // Optimistic: show the user message immediately.
    setMessages((m) => [...m, { role: "user", content: text }]);
    try {
      const r: RoastResponse = await api.roast(sessionId, { message: text });
      setMessages((m) => [...m, { role: "assistant", content: r.roast, intents: r.intents_detected }]);
      setScores(r.scores);
    } catch (e) {
      // Remove the optimistic user message and restore the input so the
      // user can retry without retyping.
      setMessages((m) => m.slice(0, -1));
      setInput(text);
      if (e instanceof ApiError && e.code === "session_ended") {
        setEndedRemote(true);
      }
      if (e instanceof ApiError && e.code === "free_tier") {
        setError("You’ve used your 5 free messages. Subscribe to keep roasting.");
      } else {
        setError(friendlyError(e));
      }
    } finally {
      setBusy(false);
    }
  }

  /** After a refresh on an ended session, the local `finalScores` is null
   * (state is fresh) but the server reports `is_ended: true`. The share UI
   * should appear in that case too — otherwise the user sees their full
   * conversation with no way to share or restart. */
  const showShareUI = !!closer && (!!finalScores || endedRemote);
  const sessionIsLocked = !!finalScores || endedRemote;

  async function endSession() {
    if (ending || finalScores) return;
    setEnding(true);
    setError(null);
    try {
      const r = await api.endSession(sessionId);
      setFinalScores(r.final_scores);
      setCloser(r.closer);
      if (r.closer) {
        setMessages((m) => [...m, { role: "assistant", content: r.closer as string }]);
      }
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setEnding(false);
    }
  }

  function copyShareLink() {
    const url = `${window.location.origin}/share/${sessionId}`;
    navigator.clipboard.writeText(url).then(
      () => {
        setCopied(true);
        if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
        copyTimerRef.current = setTimeout(() => setCopied(false), 1800);
      },
      () => {
        setError("Couldn't copy. Long-press the link instead.");
      }
    );
  }

  const canSend = !busy && !endedRemote && !finalScores && input.trim().length > 0;

  return (
    <div className="grid gap-4 md:grid-cols-[1fr,320px] md:gap-6">
      <section className="card flex min-h-[70vh] flex-col p-0">
        <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <div>
            <div className="font-display text-lg font-bold capitalize">
              {personality.replace("_", " ")} · {mode}
            </div>
            <div className="text-xs text-muted">
              Session <span className="font-mono">{sessionId}</span>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => router.push("/")}
              className="btn-ghost text-xs"
            >
              New session
            </button>
            <button
              onClick={endSession}
              disabled={ending || !!finalScores}
              className="btn-primary text-xs"
            >
              {finalScores ? "Session ended" : ending ? "Ending…" : "End & get score"}
            </button>
          </div>
        </div>

        <div
          ref={scrollerRef}
          className="flex-1 space-y-4 overflow-y-auto px-4 py-6"
        >
          {messages.length === 0 && !error && !endedRemote && (
            <div className="text-center text-muted">Loading opener…</div>
          )}

          {endedRemote && messages.length === 0 && (
            <div className="rounded-lg border border-border/60 bg-bg/40 p-4 text-center text-sm text-muted">
              This session has ended. <button onClick={() => router.push("/")} className="text-accent-3 hover:underline">Start a new one</button>.
            </div>
          )}

          {messages.map((m, i) => (
            <MessageBubble key={i} message={m} index={i} />
          ))}

          {busy && (
            <div className="flex justify-start">
              <div className="roast-bubble animate-pulse text-muted">
                Cooking up something devastating…
              </div>
            </div>
          )}

          {error && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              role="alert"
              className="flex items-start justify-between gap-3 rounded-lg border border-accent/40 bg-accent/10 p-3 text-sm text-accent"
            >
              <div className="flex-1">
                <span>{error}</span>
                {(error.includes("Subscribe") || error.includes("free messages")) && (
                  <a
                    href="/pricing"
                    className="ml-3 inline-block rounded-md bg-gradient-to-r from-purple-600 to-pink-600 px-3 py-1 text-xs font-semibold text-white"
                  >
                    See plans →
                  </a>
                )}
              </div>
              <button
                onClick={() => setError(null)}
                aria-label="Dismiss error"
                className="text-accent/70 hover:text-accent"
              >
                ✕
              </button>
            </motion.div>
          )}

          {showShareUI && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="card border-accent/40 bg-gradient-to-br from-accent/10 to-accent-2/10"
            >
              <div className="font-display text-2xl font-bold gradient-text">
                Session complete.
              </div>
              <p className="mt-2 text-sm text-muted">
                Share this roast with friends. Bragging rights optional.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  onClick={copyShareLink}
                  className="btn-ghost text-xs"
                >
                  {copied ? "Copied ✓" : "Copy share link"}
                </button>
                <a
                  href={`/share/${sessionId}`}
                  className="btn-primary text-xs"
                >
                  Open share page
                </a>
                <button
                  onClick={() => router.push("/")}
                  className="btn-ghost text-xs"
                >
                  Start another
                </button>
              </div>
            </motion.div>
          )}
        </div>

        {!sessionIsLocked && (
          <div className="border-t border-border/60 p-3">
            <form
              onSubmit={(e) => { e.preventDefault(); send(); }}
              className="flex gap-2"
            >
              <input
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  if (error) setError(null);
                }}
                placeholder="Say something to be roasted…"
                className="input"
                disabled={busy}
                maxLength={2000}
                autoFocus
              />
              <button
                type="submit"
                disabled={!canSend}
                className="btn-primary"
                aria-label="Send message"
              >
                Send 🔥
              </button>
            </form>
            <div className="mt-2 text-right text-[10px] text-muted/70">
              {input.length} / 2000
            </div>
          </div>
        )}
      </section>

      <aside>
        {scores && <ScorePanel scores={scores} />}
        {(finalScores || endedRemote) && scores && (
          <div className="card mt-4">
            <div className="text-sm font-semibold">Final damage</div>
            <div className="mt-2 text-3xl font-display font-bold gradient-text">
              {scores.emotional_damage}%
            </div>
            <div className="text-xs text-muted">emotional damage</div>
          </div>
        )}
      </aside>
    </div>
  );
}

function MessageBubble({ message, index }: { message: ChatMessage; index: number }) {
  if (message.role === "user") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="flex justify-end"
      >
        <div className="user-bubble max-w-[80%] text-sm">{message.content}</div>
      </motion.div>
    );
  }
  return (
    <motion.div
      initial={{ opacity: 0, y: 14, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="flex justify-start"
    >
      <div className="max-w-[85%]">
        <div className="roast-bubble animate-slide-up text-[15px] leading-relaxed">
          {message.content}
        </div>
        {message.intents && message.intents.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5 pl-2">
            {message.intents.map((i) => (
              <span key={i} className="pill text-[10px] uppercase tracking-wider opacity-70">
                {i}
              </span>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}
