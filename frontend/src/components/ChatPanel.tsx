import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "@/data/api";
import { formatPrice, formatShares } from "@/data/format";
import type { ChatAction } from "@/data/types";
import { Panel } from "./Panel";

const SUGGESTIONS = ["How concentrated is my portfolio?", "Buy 5 NVDA", "Add PYPL to my watchlist"];

/** Describe what an action did, or which action failed and why. */
export function describeAction(action: ChatAction) {
  if (action.type === "watchlist") {
    if (action.status === "error") {
      return `Could not ${action.action} ${action.ticker}: ${action.error}`;
    }
    const verb = action.action === "add" ? "Added" : "Removed";
    return `${verb} ${action.ticker} ${action.action === "add" ? "to" : "from"} your watchlist`;
  }
  const order = `${formatShares(action.quantity)} ${action.ticker}`;
  if (action.status === "error") return `Could not ${action.side} ${order}: ${action.error}`;
  const verb = action.side === "buy" ? "Bought" : "Sold";
  return `${verb} ${order} at $${formatPrice(action.price)}`;
}

interface Message {
  id: number;
  role: "user" | "assistant";
  text: string;
  actions?: ChatAction[];
  failed?: boolean;
}

function ActionLine({ action }: { action: ChatAction }) {
  const failed = action.status === "error";
  return (
    <li className={`border-l-2 pl-2 text-sm ${failed ? "border-loss text-loss" : "border-ai"}`}>
      {describeAction(action)}
    </li>
  );
}

function ChatMessage({ message }: { message: Message }) {
  if (message.role === "user") {
    return <p className="ml-8 self-end rounded-md bg-raised px-2.5 py-1.5">{message.text}</p>;
  }
  return (
    <div className="flex flex-col gap-1.5">
      <p className={`whitespace-pre-wrap ${message.failed ? "text-loss" : ""}`}>{message.text}</p>
      {message.actions && message.actions.length > 0 && (
        <ul className="flex flex-col gap-1">
          {message.actions.map((action, index) => (
            <ActionLine key={index} action={action} />
          ))}
        </ul>
      )}
    </div>
  );
}

function Suggestions({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="my-auto flex flex-col items-start gap-2">
      <p className="text-muted">Ask about your portfolio, or tell FinAlly what to trade.</p>
      {SUGGESTIONS.map((text) => (
        <button
          key={text}
          type="button"
          onClick={() => onPick(text)}
          className="rounded-md border border-line px-2.5 py-1 text-left text-sm hover:border-ai"
        >
          {text}
        </button>
      ))}
    </div>
  );
}

/** Docked assistant: sends messages and shows the actions each reply executed. */
export function ChatPanel({ onActions }: { onActions: () => void }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [waiting, setWaiting] = useState(false);
  const log = useRef<HTMLDivElement>(null);

  useEffect(() => {
    log.current!.scrollTop = log.current!.scrollHeight;
  }, [messages, waiting]);

  const append = (message: Omit<Message, "id">) =>
    setMessages((current) => [...current, { ...message, id: current.length }]);

  async function send(text: string) {
    setDraft("");
    setWaiting(true);
    append({ role: "user", text });
    try {
      const reply = await api.chat(text);
      append({ role: "assistant", text: reply.message, actions: reply.actions });
      if (reply.actions.some((action) => action.status === "ok")) onActions();
    } catch {
      append({
        role: "assistant",
        text: "The server did not answer. Check the connection and send your message again.",
        failed: true,
      });
    }
    setWaiting(false);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    send(draft.trim());
  }

  return (
    <Panel title="FinAlly assistant" className="max-lg:h-[28rem] lg:row-span-2 lg:row-start-1 lg:col-start-3">
      <div
        ref={log}
        aria-live="polite"
        className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-3 py-2"
      >
        {messages.length === 0 && !waiting && <Suggestions onPick={send} />}
        {messages.map((message) => (
          <ChatMessage key={message.id} message={message} />
        ))}
        {waiting && <p className="thinking text-ai">FinAlly is thinking</p>}
      </div>
      <form onSubmit={submit} className="flex shrink-0 gap-2 border-t border-line p-2">
        <input
          aria-label="Message FinAlly"
          placeholder="Message FinAlly"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          required
          className="field min-w-0 flex-1"
        />
        <button type="submit" disabled={waiting} className="btn-submit">
          Send
        </button>
      </form>
    </Panel>
  );
}
