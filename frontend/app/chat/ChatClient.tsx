"use client";

import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api, friendlyError } from "@/lib/api";
import { getAccessToken } from "@/lib/auth-api";
import { toast } from "sonner";
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
  const [transcriptCopied, setTranscriptCopied] = useState(false);
  const [endedRemote, setEndedRemote] = useState(false);
  // Set true when we successfully recovered the session from the
  // backend's `roast_sessions` table after a server cold start. We
  // show a one-time banner so the user knows their state was rebuilt
  // and not freshly fetched from memory.
  const [recoveredFromDb, setRecoveredFromDb] = useState(false);
  // True iff the latest error was a "free tier" 402 from the backend.
  // Drives the "See plans â†’" CTA â€” branching on the typed error code
  // rather than substring matching the human-readable message.
  const [hitFreeTier, setHitFreeTier] = useState(false);

  const scrollerRef = useRef<HTMLDivElement>(null);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Per-send AbortController so we can cancel in-flight requests on
  // unmount or when a new send is triggered. Without this, a user
  // who navigates away mid-request would have `setMessages`/
  // `setScores` called on the unmounted component (React warns, the
  // calls are dropped, the response is wasted bandwidth).
  const sendControllerRef = useRef<AbortController | null>(null);

  // Bootstrap: load session + opener. If the in-memory store lost it
  // (free-tier host cold start) and the user is logged in, try the
  // recovery endpoint which rebuilds the session from the
  // `roast_sessions` table.
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
        if (cancelled) return;
        // If we got a 404, the in-memory store lost this session â€”
        // typical after a free-tier host cold start. Authenticated
        // users can recover from the persisted `roast_sessions` row.
        if (e instanceof ApiError && e.code === "not_found" && getAccessToken()) {
          try {
            const recovered = await api.recoverSession(sessionId);
            if (cancelled) return;
            setMode(recovered.mode);
            setPersonality(recovered.personality);
            setScores(recovered.scores);
            setMessages(recovered.history);
            setEndedRemote(recovered.is_ended);
            setRecoveredFromDb(true);
            if (recovered.is_ended && recovered.history.length > 0) {
              const last = recovered.history[recovered.history.length - 1];
              if (last.role === "assistant") setCloser(last.content);
            }
            return;
          } catch {
            // Fall through to the regular error UI.
          }
        }
        setError(friendlyError(e));
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
    sendControllerRef.current?.abort();
  }, []);

  async function send() {
    const text = input.trim();
    // canSend is the gate the button uses; the form's onSubmit also
    // calls send() on Enter, so we re-check here.
    if (!text || busy || endedRemote || !!finalScores) {
      if (endedRemote || finalScores) {
        setError("This session has ended. Start a new one to keep roasting.");
      }
      return;
    }
    setInput("");
    setError(null);
    setHitFreeTier(false);
    setBusy(true);
    // Optimistic: show the user message immediately. The user message
    // is keyed by an in-place id so the rollback below can remove
    // THIS bubble (not the last item in the list) even if a 404 +
    // recovery path has just replaced the whole list.
    const optimisticId = `optimistic-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setMessages((m) => [...m, { role: "user", content: text, _id: optimisticId } as ChatMessage]);

    // Cancel any in-flight send (defensive â€” busy guard already
    // prevents re-entry, but a stale promise from before unmount
    // could still resolve).
    sendControllerRef.current?.abort();
    const controller = new AbortController();
    sendControllerRef.current = controller;

    try {
      const r: RoastResponse = await api.roast(sessionId, { message: text }, { signal: controller.signal });
      setMessages((m) => [...m, { role: "assistant", content: r.roast, intents: r.intents_detected }]);
      setScores(r.scores);
    } catch (e) {
      // 404 mid-session usually means the server restarted and lost
      // the in-memory store. Authenticated users can recover from
      // the persisted `roast_sessions` row, then re-send
      // automatically. The recovery path REPLACES the message list
      // (with the optimistic bubble removed) so the regular rollback
      // below is skipped.
      if (e instanceof ApiError && e.code === "not_found" && getAccessToken()) {
        try {
          const recovered = await api.recoverSession(sessionId);
          setMode(recovered.mode);
          setPersonality(recovered.personality);
          setScores(recovered.scores);
          setRecoveredFromDb(true);
          const r2: RoastResponse = await api.roast(sessionId, { message: text }, { signal: controller.signal });
          // REPLACEMENT (not append): the recovered history is the
          // pre-cold-start view; we then append the new user +
          // assistant pair so the optimistic user message (which is
          // NOT in `recovered.history`) is the one shown in context.
          setMessages((recovered.history || []).concat([
            { role: "user", content: text },
            { role: "assistant", content: r2.roast, intents: r2.intents_detected },
          ]));
          setScores(r2.scores);
          return;
        } catch {
          // Fall through to the regular error UI.
        }
      }
      // Roll back ONLY the optimistic bubble we added (by id), not
      // the last item in the list. This prevents corrupting the chat
      // if a 404-recovery path had just replaced the list and then
      // the re-send also failed.
      setMessages((m) => m.filter((msg) => (msg as ChatMessage)._id !== optimisticId));
      setInput(text);
      if (e instanceof ApiError && e.code === "session_ended") {
        setEndedRemote(true);
      }
      setHitFreeTier(e instanceof ApiError && e.code === "free_tier");
      setError(friendlyError(e));
    } finally {
      if (sendControllerRef.current === controller) {
        sendControllerRef.current = null;
      }
      setBusy(false);
    }
  }

  /** After a refresh on an ended session, the local `finalScores` is null
   * (state is fresh) but the server reports `is_ended: true`. The share UI
   * should appear in that case too â€” otherwise the user sees their full
   * conversation with no way to share or restart. */
  const showShareUI = !!closer && (!!finalScores || endedRemote);
  const sessionIsLocked = !!finalScores || endedRemote;

  async function endSession() {
    if (ending || finalScores) return;
    // If the session is already ended remotely (e.g., server-side
    // timeout or admin action), short-circuit. The user can still
    // see the closer from the recovered history.
    if (endedRemote) {
      return;
    }
    setEnding(true);
    setError(null);
    try {
      const r = await api.endSession(sessionId);
      setFinalScores(r.final_scores);
      const closerText = r.closer;
      setCloser(closerText);
      if (closerText) {
        setMessages((m) => [...m, { role: "assistant", content: closerText }]);
      }
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setEnding(false);
    }
  }

  function copyShareLink() {
    async function doShare() {
      try {
        const r = await api.shareSession(sessionId);
        const url = `${window.location.origin}${r.share_url}`;
        if (typeof navigator === "undefined" || !navigator.clipboard) {
          setError("Your browser doesn't support one-click copy. Long-press the link instead.");
          return;
        }
        await navigator.clipboard.writeText(url);
        setCopied(true);
        if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
        copyTimerRef.current = setTimeout(() => setCopied(false), 1800);
      } catch (e) {
        setError("Share failed. " + ((e as ApiError)?.detail || ""));
      }
    }
    doShare();
  }

  function copyTranscript() {
    if (messages.length === 0) return;
    if (typeof window === "undefined" || !window.isSecureContext || !navigator.clipboard) {
      setError("Your browser doesn't support one-click copy.");
      return;
    }
    const lines = messages.map((m) => {
      const who = m.role === "user" ? "You" : "RoastGPT";
      return `${who}: ${m.content}`;
    });
    navigator.clipboard.writeText(lines.join("\n")).then(
      () => {
        setTranscriptCopied(true);
        if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
        copyTimerRef.current = setTimeout(() => setTranscriptCopied(false), 1800);
      },
      () => {
        setError("Couldn't copy transcript.");
      },
    );
  }

  const canSend = !busy && !endedRemote && !finalScores && input.trim().length > 0;

  return (
    <div className="grid gap-4 md:grid-cols-[1fr,320px] md:gap-6">
      <section className="card flex min-h-[70vh] flex-col p-0">
        <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <div>
            <div className="font-display text-lg font-bold capitalize">
              {personality.replace("_", " ")} Â· {mode}
            </div>
            <div className="text-xs text-muted">
              Session <span className="font-mono">{sessionId}</span>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={copyTranscript}
              disabled={messages.length === 0}
              className="btn-ghost text-xs"
              title="Copy the full conversation as text"
            >
              {transcriptCopied ? "Copied ✓" : "Copy transcript"}
            </button>
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

        {recoveredFromDb && (
          <div
            role="status"
            className="border-b border-accent/30 bg-accent/10 px-4 py-2 text-xs text-accent"
          >
            Session recovered from history. The server restarted and lost its
            short-term state, but your full conversation is intact.
          </div>
        )}

        <div
          ref={scrollerRef}
          className="flex-1 space-y-4 overflow-y-auto px-4 py-6"
        >
          {messages.length === 0 && !error && !endedRemote && (
            <div className="text-center text-muted">Loading openerâ€¦</div>
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
                Cooking up something devastatingâ€¦
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
                {hitFreeTier && (
                  <a
                    href="/pricing"
                    className="ml-3 inline-block rounded-md bg-gradient-to-r from-purple-600 to-pink-600 px-3 py-1 text-xs font-semibold text-white"
                  >
                    See plans â†’
                  </a>
                )}
              </div>
              <button
                onClick={() => { setError(null); setHitFreeTier(false); }}
                aria-label="Dismiss error"
                className="text-accent/70 hover:text-accent"
              >
                âœ•
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
                  {copied ? "Copied âœ“" : "Copy share link"}
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
                onKeyDown={(e) => {
                  // Ctrl+Enter / Cmd+Enter sends without the user
                  // having to click. Plain Enter still submits via the
                  // form's implicit submit, so single-line keystrokes
                  // work the same.
                  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                    e.preventDefault();
                    send();
                  }
                }}
                placeholder="Say something to be roastedâ€¦ (Enter to send, Shift+Enter for newline)"
                className="input"
                maxLength={2000}
                autoFocus
                aria-label="Your message"
              />
              <button
                type="submit"
                disabled={!canSend}
                className="btn-primary"
                aria-label="Send message"
              >
                Send ðŸ”¥
              </button>
            </form>
            <div className="mt-2 flex items-center justify-between text-[10px] text-muted/70">
              <span>
                {input.length > 0 && input.length < 10
                  ? "Tip: longer messages get sharper roasts."
                  : ""}
              </span>
              <span>
                {input.length} / 2000
              </span>
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
