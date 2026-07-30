import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchInferenceTypes,
  type InferenceTypeItem,
} from "../services/inferenceTypesService";

const INFERENCE_TYPES_QUERY_KEY = "inferenceTypes";

// Frontend-owned allowlist of task types this deployment exposes in the UI.
// Comma-separated yaml names, e.g. "llm,nmt,asr". This is a UI-only filter —
// the backend is NOT restricted and still serves every task type; this just
// decides what the frontend shows and calls. Unset/empty ⇒ show the full catalog.
const ENV_ENABLED: string[] = (process.env.NEXT_PUBLIC_ENABLED_TASK_TYPES ?? "")
  .split(",")
  .map((s) => s.trim().toLowerCase())
  .filter(Boolean);

// Task-type `name` (yaml form) → frontend `ServiceId`. Identity for all but audio
// language detection, where the yaml name and the ServiceId differ.
const NAME_TO_SERVICE_ID: Record<string, string> = {
  "audio-lang-detection": "audio-language-detection",
};

const toServiceId = (name: string): string => {
  const n = name.trim().toLowerCase();
  return NAME_TO_SERVICE_ID[n] ?? n;
};

// Module-level empty fallback so the loading/error state keeps a stable ref.
const NO_TYPES: InferenceTypeItem[] = [];

export function useInferenceTypes() {
  const query = useQuery({
    queryKey: [INFERENCE_TYPES_QUERY_KEY],
    queryFn: fetchInferenceTypes,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  // Stable fallback ref: `?? []` would mint a new array every render while the
  // query is loading/errored, cascading new refs through the memos below and
  // re-firing any effect that depends on them (e.g. the services-registry fetch).
  const inferenceTypes: InferenceTypeItem[] = query.data ?? NO_TYPES;

  // Units come from the API catalog (unfiltered on the backend).
  const unitByTaskType: Record<string, string> = Object.fromEntries(
    inferenceTypes.map((t) => [t.name, t.unit]),
  );

  // Enabled = the frontend allowlist (NEXT_PUBLIC_ENABLED_TASK_TYPES) intersected
  // with the real catalog; unset ⇒ the whole catalog. UI-only gating.
  const taskTypeNames: string[] = useMemo(() => {
    const allNames = inferenceTypes.map((t) => t.name);
    return ENV_ENABLED.length > 0
      ? allNames.filter((n) => ENV_ENABLED.includes(n.trim().toLowerCase()))
      : allNames;
  }, [inferenceTypes]);

  // Enabled ServiceIds — the single source for gating the UI catalog
  // (home cards, sidebar nav, logs filter, tier/model selectors).
  const enabledServiceIds = useMemo(
    () => new Set(taskTypeNames.map(toServiceId)),
    [taskTypeNames],
  );

  return {
    inferenceTypes,
    taskTypeNames,
    unitByTaskType,
    enabledServiceIds,
    isLoading: query.isLoading,
  };
}
