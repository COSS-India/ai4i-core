// Shared types and helpers for ASR hooks

import type { MutableRefObject } from "react";
import type { useToastWithDeduplication } from "../useToastWithDeduplication";

export type AsrToast = ReturnType<typeof useToastWithDeduplication>;

export interface AsrConfigRefs {
  languageRef: MutableRefObject<string>;
  sampleRateRef: MutableRefObject<number>;
  serviceIdRef: MutableRefObject<string>;
  currentRequestLanguageRef: MutableRefObject<string | null>;
}
