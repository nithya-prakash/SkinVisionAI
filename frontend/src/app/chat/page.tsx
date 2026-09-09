"use client";

import { useEffect, useState } from "react";
import { AgentStatusBadge } from "@/components/StatusBadge";
import { Disclaimer, DISCLAIMER } from "@/components/Disclaimer";
import {
  AgentStatus,
  ProductAnalysisError,
  ToolCallTraceEntry,
  getChatMessages,
  sendAgentChatMessage,
} from "@/lib/api";
import { getOrCreateAppSession, getStoredChatSessionId, setStoredChatSessionId } from "@/lib/session";
import { citationsFromTrace, summarizeToolResult } from "./toolSummary";

type ChatEntry =
  | { id: string; role: "user"; content: string }
  | {
      id: string;
      role: "assistant";
      content: string;
      toolTrace: ToolCallTraceEntry[];
      status?: AgentStatus;
    };

let idCounter = 0;
function nextId(): string {
  idCounter += 1;
  return `msg-${idCounter}`;
}

export default function ChatPage() {
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [hydrating, setHydrating] = useState(true);
  const [chatSessionId, setChatSessionId] = useState<string | undefined>(undefined);

  useEffect(() => {
    // Restore a persisted conversation after a page refresh, instead of
    // starting empty every time (Phase 8) -- the message list itself
    // stays server-side; this only reloads it.
    async function hydrate() {
      const existing = getStoredChatSessionId();
      if (!existing) {
        setHydrating(false);
        return;
      }
      try {
        const history = await getChatMessages(existing);
        setChatSessionId(existing);
        setEntries(
          history.messages.map((m) =>
            m.role === "user"
              ? { id: m.id, role: "user" as const, content: m.content }
              : { id: m.id, role: "assistant" as const, content: m.content, toolTrace: m.tool_trace },
          ),
        );
      } catch {
        // Unknown/expired chat session id -- start fresh silently.
      } finally {
        setHydrating(false);
      }
    }
    hydrate();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const message = input.trim();
    if (!message || sending) return;

    setEntries((prev) => [...prev, { id: nextId(), role: "user", content: message }]);
    setInput("");
    setSending(true);

    try {
      const sessionId = await getOrCreateAppSession();
      const response = await sendAgentChatMessage({ message, chatSessionId, sessionId });
      if (response.chat_session_id) {
        setChatSessionId(response.chat_session_id);
        setStoredChatSessionId(response.chat_session_id);
      }
      const content =
        response.status === "success"
          ? response.answer
          : response.answer ||
            "I wasn't able to produce a validated answer for that. The deterministic details, if any, are below.";
      setEntries((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "assistant",
          content,
          toolTrace: response.tool_trace,
          status: response.status,
        },
      ]);
    } catch (err) {
      const content =
        err instanceof ProductAnalysisError
          ? err.message
          : "Something went wrong reaching the assistant. Please try again.";
      setEntries((prev) => [...prev, { id: nextId(), role: "assistant", content, toolTrace: [] }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-6 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">Copilot Chat</h1>
      <p className="text-neutral-600 dark:text-neutral-300">
        Ask about ingredient compatibility, a product comparison, or a
        routine. The assistant selects a deterministic tool for any
        skincare-domain fact and never diagnoses medical conditions. Every
        step in &ldquo;How SkinVision AI reached this answer&rdquo; below was
        computed by a deterministic tool, not guessed by the model.
      </p>

      <div className="flex flex-col gap-4">
        {hydrating && <p className="text-sm text-neutral-400">Loading conversation&hellip;</p>}

        {!hydrating && entries.length === 0 && (
          <p className="text-sm text-neutral-400">
            Try: &ldquo;Can I use retinol and salicylic acid together?&rdquo;
          </p>
        )}

        {entries.map((entry) =>
          entry.role === "user" ? (
            <div key={entry.id} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-neutral-900 px-4 py-2.5 text-sm text-white dark:bg-white dark:text-black">
                {entry.content}
              </div>
            </div>
          ) : (
            <div key={entry.id} className="flex flex-col items-start gap-2">
              <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-neutral-200 bg-neutral-50 px-4 py-2.5 text-sm text-neutral-800 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-100">
                {entry.status && entry.status !== "success" && (
                  <div className="mb-1.5 flex items-center gap-1.5">
                    <AgentStatusBadge status={entry.status} />
                  </div>
                )}
                <p>{entry.content}</p>
              </div>

              {entry.toolTrace.length > 0 && (
                <details className="w-full max-w-[85%] rounded-lg border border-violet-200 bg-violet-50/40 px-3 py-2 text-xs dark:border-violet-900 dark:bg-violet-950/20">
                  <summary className="cursor-pointer select-none font-medium text-violet-700 dark:text-violet-300">
                    How SkinVision AI reached this answer
                  </summary>
                  <ol className="mt-2 flex flex-col gap-2">
                    {entry.toolTrace.map((step) => (
                      <li
                        key={step.call_index}
                        className="rounded-md border border-violet-100 bg-white px-2.5 py-2 dark:border-violet-900/60 dark:bg-neutral-900"
                      >
                        <div className="flex items-center gap-1.5">
                          <span className="text-neutral-400 dark:text-neutral-500">
                            {step.call_index + 1}.
                          </span>
                          <code className="rounded bg-neutral-100 px-1.5 py-0.5 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-200">
                            {step.tool_name}
                          </code>
                          {!step.success && (
                            <span className="text-red-500 dark:text-red-400">failed</span>
                          )}
                        </div>
                        <p className="mt-1 text-neutral-600 dark:text-neutral-400">
                          {summarizeToolResult(step)}
                        </p>
                      </li>
                    ))}
                  </ol>
                  {citationsFromTrace(entry.toolTrace).length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-neutral-500 dark:text-neutral-400">
                      {citationsFromTrace(entry.toolTrace).map((c) => (
                        <span key={c.source}>
                          Source:{" "}
                          {c.source_url ? (
                            <a
                              href={c.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="underline"
                            >
                              {c.source}
                            </a>
                          ) : (
                            c.source
                          )}
                        </span>
                      ))}
                    </div>
                  )}
                </details>
              )}
            </div>
          ),
        )}

        {sending && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-sm border border-neutral-200 bg-neutral-50 px-4 py-2.5 text-sm text-neutral-400 dark:border-neutral-800 dark:bg-neutral-900">
              Thinking&hellip;
            </div>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="sticky bottom-6 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a skincare question…"
          aria-label="Message to the AI assistant"
          disabled={sending}
          className="flex-1 rounded-full border border-neutral-300 bg-white px-4 py-2.5 text-sm shadow-sm disabled:opacity-50 dark:border-neutral-700 dark:bg-neutral-950"
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="rounded-full bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
        >
          Send
        </button>
      </form>

      <Disclaimer className="mt-auto" text={DISCLAIMER} />
    </main>
  );
}
