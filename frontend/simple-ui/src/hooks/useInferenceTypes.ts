import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchInferenceTypes,
  type InferenceTypeItem,
} from "../services/inferenceTypesService";

const INFERENCE_TYPES_QUERY_KEY = "inferenceTypes";

// Backend task-type `name` (yaml form) → frontend `ServiceId`. Identity for all
// but audio language detection, where the yaml name and the ServiceId differ.
const NAME_TO_SERVICE_ID: Record<string, string> = {
  "audio-lang-detection": "audio-language-detection",
};

const toServiceId = (name: string): string => {
  const n = name.trim().toLowerCase();
  return NAME_TO_SERVICE_ID[n] ?? n;
};

export function useInferenceTypes() {
  const query = useQuery({
    queryKey: [INFERENCE_TYPES_QUERY_KEY],
    queryFn: fetchInferenceTypes,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const inferenceTypes: InferenceTypeItem[] = query.data ?? [];

  // The enabled task types are exactly what the backend reports
  // (ENABLED_TASK_TYPES, filtered server-side). No static fallback — falling
  // back to a hardcoded list would surface disabled types on an API hiccup.
  const taskTypeNames: string[] = inferenceTypes.map((t) => t.name);

  // { "asr": "Audio minutes", "llm": "M Tokens", ... } derived from API
  const unitByTaskType: Record<string, string> = Object.fromEntries(
    inferenceTypes.map((t) => [t.name, t.unit]),
  );

  // Enabled ServiceIds — the single source for gating the UI catalog
  // (home cards, sidebar nav, route guards).
  const enabledServiceIds = useMemo(
    () => new Set(taskTypeNames.map(toServiceId)),
    [inferenceTypes],
  );

  return {
    inferenceTypes,
    taskTypeNames,
    unitByTaskType,
    enabledServiceIds,
    isLoading: query.isLoading,
  };
}
