import { useVoiceAssistant, useTrackVolume } from "@livekit/components-react";
import { AuraCanvas } from "./AuraCanvas";

/**
 * Live "Aura" - binds Samuel's LiveKit state + audio amplitude to the pure
 * AuraCanvas renderer. Full brand control, no WebGL, cheap on high tiers.
 */
export function AuraVisualizer() {
  const { state, audioTrack } = useVoiceAssistant();
  const volume = useTrackVolume(audioTrack); // 0..1, smoothed by LiveKit
  return <AuraCanvas state={state} volume={volume || 0} />;
}
