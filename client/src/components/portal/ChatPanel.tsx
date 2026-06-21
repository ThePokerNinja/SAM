import { useEffect, useRef, useState } from "react";
import { useVoiceAssistant } from "@livekit/components-react";
import { IconAttach, IconSend } from "./PortalIcons";

interface LocalMsg {
  id: string;
  role: "you";
  text: string;
}

interface Props {
  open: boolean;
}

/**
 * Expandable chat panel � text UI only for now (worker text turns later).
 * Attach is a visual placeholder (paperclip, not wired).
 */
export function ChatPanel({ open }: Props) {
  const { agentTranscriptions } = useVoiceAssistant();
  const [text, setText] = useState("");
  const [local, setLocal] = useState<LocalMsg[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const agentLines = agentTranscriptions?.map((t) => t.text).filter(Boolean) ?? [];

  const send = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setLocal((prev) => [...prev, { id: crypto.randomUUID(), role: "you", text: trimmed }]);
    setText("");
    inputRef.current?.focus();
  };

  if (!open) return null;

  return (
    <div className="chat-panel" role="region" aria-label="Chat with Samuel">
      <div className="chat-transcript">
        {agentLines.length === 0 && local.length === 0 && (
          <p className="chat-empty">Voice or type a message for Samuel.</p>
        )}
        {agentLines.map((line, i) => (
          <p key={`sam-${i}`} className="chat-line chat-line--sam">{line}</p>
        ))}
        {local.map((m) => (
          <p key={m.id} className="chat-line chat-line--you">{m.text}</p>
        ))}
      </div>
      <form
        className="chat-compose"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <button
          type="button"
          className="chat-attach"
          aria-label="Attach file (coming soon)"
          title="File attachments coming soon"
          disabled
        >
          <IconAttach />
        </button>
        <input
          ref={inputRef}
          type="text"
          className="chat-input"
          placeholder="Message Samuel�"
          value={text}
          onChange={(e) => setText(e.target.value)}
          aria-label="Message Samuel"
        />
        <button type="submit" className="chat-send" aria-label="Send" disabled={!text.trim()}>
          <IconSend />
        </button>
      </form>
    </div>
  );
}
