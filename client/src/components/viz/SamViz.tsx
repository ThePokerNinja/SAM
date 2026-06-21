import { BarVisualizer, useVoiceAssistant, useTrackVolume } from "@livekit/components-react";
import { AuraCanvas } from "../AuraCanvas";
import { GridCanvas } from "./GridCanvas";
import { RadialCanvas } from "./RadialCanvas";
import { WaveCanvas } from "./WaveCanvas";
import type { VizTreatment } from "./types";

interface Props {
  treatment: VizTreatment;
}

/** Renders one of the five visual treatments with live agent state + audio. */
export function SamViz({ treatment }: Props) {
  const { state, audioTrack } = useVoiceAssistant();
  const volume = useTrackVolume(audioTrack) || 0;

  switch (treatment) {
    case "wave":
      return <WaveCanvas state={state} volume={volume} />;
    case "radial":
      return <RadialCanvas state={state} volume={volume} />;
    case "grid":
      return <GridCanvas state={state} volume={volume} />;
    case "bar":
      return (
        <BarVisualizer
          state={state}
          trackRef={audioTrack}
          barCount={9}
          className="sam-bars"
        />
      );
    case "aura":
    default:
      return <AuraCanvas state={state} volume={volume} />;
  }
}
