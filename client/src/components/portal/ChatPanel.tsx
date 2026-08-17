import { useEffect, useRef, useState } from "react";
import { useRoomContext } from "@livekit/components-react";
import { ConnectionState, RoomEvent } from "livekit-client";
import { IconAttach, IconSend } from "./PortalIcons";

interface Msg {
  id: string;
  role: "sam" | "you";
  text: string;
  at: number; // Date.now() for ordering
}

interface Props {
  open: boolean;
}

const ENCODER = new TextEncoder();
const CHAT_TOPIC = "sam-chat";

/**
 * Expandable chat panel — typed messages are sent to Samuel over the LiveKit
 * data channel (SAM-007). Text replies return on the same channel without TTS.
 */
export function ChatPanel({ open }: Props) {
  const room = useRoomContext();
  const [text, setText] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const seenIds = useRef(new Set<string>());
  const inputRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const connected = room.state === ConnectionState.Connected;

  useEffect(() => {
    const onData = (payload: Uint8Array, _participant: unknown, _kind: unknown, topic?: string) => {
      if (topic !== CHAT_TOPIC) return;
      try {
        const message = JSON.parse(new TextDecoder().decode(payload)) as {
          type?: string;
          request_id?: string;
          text?: string;
        };
        if (message.type !== "assistant_text" || !message.text) return;
        const id = message.request_id ? `reply-${message.request_id}` : crypto.randomUUID();
        if (seenIds.current.has(id)) return;
        seenIds.current.add(id);
        const incoming: Msg = {
          id,
          role: "sam",
          text: message.text,
          at: Date.now(),
        };
        setMessages((prev) => [...prev, incoming].sort((a, b) => a.at - b.at));
      } catch {
        // Malformed data-channel messages are ignored.
      }
    };
    room.on(RoomEvent.DataReceived, onData);
    return () => {
      room.off(RoomEvent.DataReceived, onData);
    };
  }, [room]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = () => {
    const trimmed = text.trim();
    if (!trimmed || !connected) return;

    const msg: Msg = { id: crypto.randomUUID(), role: "you", text: trimmed, at: Date.now() };
    setMessages((prev) => [...prev, msg]);
    setText("");
    inputRef.current?.focus();

    try {
      const payload = ENCODER.encode(JSON.stringify({
        type: "text_input",
        request_id: msg.id,
        text: trimmed,
      }));
      room.localParticipant.publishData(payload, { reliable: true, topic: CHAT_TOPIC });
    } catch (err) {
      console.warn("[ChatPanel] publishData failed:", err);
    }
  };

  if (!open) return null;

  return (
    <div className="chat-panel" role="region" aria-label="Chat with Samuel">
      <div className="chat-transcript">
        {messages.length === 0 && (
          <p className="chat-empty">Voice or type a message for Samuel.</p>
        )}
        {messages.map((m) => (
          <p key={m.id} className={`chat-line chat-line--${m.role}`}>{m.text}</p>
        ))}
        <div ref={bottomRef} />
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
          placeholder={connected ? "Message Samuel…" : "Connecting…"}
          value={text}
          onChange={(e) => setText(e.target.value)}
          aria-label="Message Samuel"
          disabled={!connected}
        />
        <button
          type="submit"
          className="chat-send"
          aria-label="Send"
          disabled={!text.trim() || !connected}
        >
          <IconSend />
        </button>
      </form>
    </div>
  );
}
