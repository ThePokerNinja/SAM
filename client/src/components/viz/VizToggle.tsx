import { useState } from "react";
import {
  type VizTreatment,
  readVizTreatment,
  storeVizTreatment,
} from "./types";

export function useVizTreatment(): [VizTreatment, (t: VizTreatment) => void] {
  const [treatment, setTreatment] = useState(readVizTreatment);
  const set = (t: VizTreatment) => {
    storeVizTreatment(t);
    setTreatment(t);
  };
  return [treatment, set];
}
