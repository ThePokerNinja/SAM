import { useState } from "react";
import { Track } from "livekit-client";
import { useDisconnectButton, useTrackToggle } from "@livekit/components-react";
import {
  VIZ_LABELS,
  VIZ_TREATMENTS,
  type VizTreatment,
  storeVizTreatment,
} from "../viz/types";
import { ChatPanel } from "./ChatPanel";
import { IconChat, IconLeave, IconMic } from "./PortalIcons";

interface Props {
  treatment: VizTreatment;
  onTreatmentChange: (t: VizTreatment) => void;
}

/** Mic, viz cycle, chat, and disconnect in one polished strip. */
export function PortalCommandStrip({ treatment, onTreatmentChange }: Props) {
  const [chatOpen, setChatOpen] = useState(false);
  const mic = useTrackToggle({ source: Track.Source.Microphone });
  const { buttonProps: leaveProps } = useDisconnectButton({});

  const cycleViz = () => {
    const i = VIZ_TREATMENTS.indexOf(treatment);
    const next = VIZ_TREATMENTS[(i + 1) % VIZ_TREATMENTS.length];
    storeVizTreatment(next);
    onTreatmentChange(next);
  };

  return (
    <div className="portal-command">
      <ChatPanel open={chatOpen} />

      <div className="portal-command-strip">
        <button
          type="button"
          className={`cmd-btn${mic.enabled ? " cmd-btn--active" : ""}`}
          onClick={() => mic.toggle()}
          disabled={mic.buttonProps.disabled}
          aria-label={mic.enabled ? "Mute microphone" : "Unmute microphone"}
          aria-pressed={mic.enabled}
        >
          <IconMic on={mic.enabled} />
        </button>

        <span className="cmd-div" aria-hidden="true" />

        <button
          type="button"
          className="cmd-btn cmd-btn--label"
          onClick={cycleViz}
          aria-label={`Visualization: ${VIZ_LABELS[treatment]}. Tap to change.`}
        >
          {VIZ_LABELS[treatment]}
        </button>

        <span className="cmd-div" aria-hidden="true" />

        <button
          type="button"
          className={`cmd-btn${chatOpen ? " cmd-btn--active" : ""}`}
          onClick={() => setChatOpen((o) => !o)}
          aria-label="Chat"
          aria-expanded={chatOpen}
        >
          <IconChat open={chatOpen} />
        </button>

        <span className="cmd-div" aria-hidden="true" />

        <button
          type="button"
          className="cmd-btn cmd-btn--leave"
          onClick={leaveProps.onClick}
          disabled={leaveProps.disabled}
          aria-label="Disconnect"
        >
          <IconLeave />
        </button>
      </div>
    </div>
  );
}
