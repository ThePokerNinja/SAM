import type { TierPreset } from "../tier/types";

export function TierBadge({ preset, reason }: { preset: TierPreset; reason: string }) {
  return (
    <div className={`tier-badge tier-${preset.id}`} title={`reason: ${reason || "init"}`}>
      <span className="tier-dot" />
      <span className="tier-name">{preset.name}</span>
      <span className="tier-meta">
        {preset.visual} · {preset.brainModel} · {preset.ttsSettings}
      </span>
    </div>
  );
}
