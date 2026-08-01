import { useEffect, useMemo, useRef, useState } from "react";

import type { Room } from "livekit-client";

import { ConnectionState } from "livekit-client";

import { TierController } from "../tier/TierController";

import type { TierPreset, TierSignals } from "../tier/types";

import { peerConnectionFromRoom, publishTierUpdate } from "../lib/tierSync";



export function useTierController(room: Room | null) {

  const controller = useMemo(() => new TierController({ startTier: 2 }), []);

  const [preset, setPreset] = useState<TierPreset>(controller.getPreset());

  const [signals, setSignals] = useState<TierSignals>(controller.getSignals());

  const [lastReason, setLastReason] = useState<string>("");

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const roomRef = useRef<Room | null>(null);



  useEffect(() => {

    roomRef.current = room;

  }, [room]);



  useEffect(() => {

    const off = controller.onChange((next, _prev, reason) => {

      setPreset(next);

      setLastReason(reason);

      publishTierUpdate(roomRef.current, next, reason);

    });

    controller.start(peerConnectionFromRoom(room ?? null) ?? undefined);

    pollRef.current = setInterval(() => setSignals(controller.getSignals()), 500);

    return () => {

      off();

      controller.stop();

      if (pollRef.current) clearInterval(pollRef.current);

    };

  }, [controller, room]);



  // Report initial tier when the LiveKit room connects (SAM-034).

  useEffect(() => {

    if (!room) return;

    const syncInitial = () => {

      if (room.state !== ConnectionState.Connected) return;

      publishTierUpdate(room, controller.getPreset(), "init");

    };

    room.on("connectionStateChanged", syncInitial);

    syncInitial();

    return () => {

      room.off("connectionStateChanged", syncInitial);

    };

  }, [room, controller]);



  return { controller, preset, signals, lastReason };

}

