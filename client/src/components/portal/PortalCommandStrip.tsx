import { useState, type MouseEventHandler } from "react";
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

/**
 * Mic, chat, and a single morphing logo button.
 *
 * Collapsed (default): the Rainmaker mark. Tapping it reveals the visualization
 * toggle and morphs the mark into a red start-over icon. Tapping start-over
 * disconnects (demo restarts) and the toggle collapses again.
 */
export function PortalCommandStrip({ treatment, onTreatmentChange }: Props) {
  const [chatOpen, setChatOpen] = useState(false);
  const [vizOpen, setVizOpen] = useState(false);
  const mic = useTrackToggle({ source: Track.Source.Microphone });
  const { buttonProps: leaveProps } = useDisconnectButton({});

  const cycleViz = () => {
    const i = VIZ_TREATMENTS.indexOf(treatment);
    const next = VIZ_TREATMENTS[(i + 1) % VIZ_TREATMENTS.length];
    storeVizTreatment(next);
    onTreatmentChange(next);
  };

  const startOver: MouseEventHandler<HTMLButtonElement> = (e) => {
    setVizOpen(false);
    leaveProps.onClick?.(e);
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

        {vizOpen && (
          <>
            <button
              type="button"
              className="cmd-btn cmd-btn--label"
              onClick={cycleViz}
              aria-label={`Visualization: ${VIZ_LABELS[treatment]}. Tap to change.`}
            >
              {VIZ_LABELS[treatment]}
            </button>

            <span className="cmd-div" aria-hidden="true" />
          </>
        )}

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

        {vizOpen ? (
          <button
            type="button"
            className="cmd-btn cmd-btn--leave"
            onClick={startOver}
            disabled={leaveProps.disabled}
            aria-label="Start over"
          >
            <IconLeave />
          </button>
        ) : (
          <button
            type="button"
            className="cmd-btn cmd-btn--mark"
            onClick={() => setVizOpen(true)}
            aria-label="Visualization options"
            aria-expanded={vizOpen}
          >
            <span className="cmd-mark" aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
}
