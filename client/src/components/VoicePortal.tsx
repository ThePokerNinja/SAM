import {
  RoomAudioRenderer,
  useVoiceAssistant,
} from "@livekit/components-react";
import { SamViz } from "./viz/SamViz";
import { useVizTreatment } from "./viz/VizToggle";
import { PortalCommandStrip } from "./portal/PortalCommandStrip";

const STATE_LABEL: Record<string, string> = {
  connecting: "Connecting\u2026",
  initializing: "Waking Samuel\u2026",
  listening: "Listening",
  thinking: "Thinking\u2026",
  speaking: "Speaking",
  disconnected: "Offline",
};

/** The connected experience. Must render inside a RoomContext provider. */
export function VoicePortal() {
  const { state, agentTranscriptions } = useVoiceAssistant();
  const [treatment, setTreatment] = useVizTreatment();
  const caption = agentTranscriptions?.[agentTranscriptions.length - 1]?.text ?? "";

  return (
    <div className={`portal-stage state-${state}`}>
      <RoomAudioRenderer />

      <img src="/brand/rainmaker-mark.png" className="portal-mark" alt="" draggable={false} />

      <div className="viz-wrap">
        <SamViz treatment={treatment} />
      </div>

      <div className="portal-brand">
        <img
          src="/brand/signature-gold.png"
          className="portal-wordmark"
          alt="Michael Stewman"
          draggable={false}
        />
      </div>

      <div className="portal-status" aria-live="polite">
        {STATE_LABEL[state] ?? state}
      </div>

      {caption && <p className="portal-caption">{caption}</p>}

      <PortalCommandStrip treatment={treatment} onTreatmentChange={setTreatment} />
    </div>
  );
}
