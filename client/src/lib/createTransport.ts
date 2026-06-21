import { LiveKitTransport } from "./livekitTransport";
import { MockTransport } from "./mockTransport";
import type { Transport } from "./transport";

/** Mock by default; set VITE_USE_MOCK=0 once the Phase 5 LiveKit path is wired. */
export function createTransport(): Transport {
  const useMock = (import.meta.env.VITE_USE_MOCK ?? "1") !== "0";
  return useMock ? new MockTransport() : new LiveKitTransport();
}
