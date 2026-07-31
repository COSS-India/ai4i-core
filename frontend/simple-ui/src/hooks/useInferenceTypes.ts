import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchInferenceTypes,
  type InferenceTypeItem,
} from "../services/inferenceTypesService";
import {
  getEnabledTaskTypes,
  getRuntimeConfig,
} from "../config/runtimeConfig";

const INFERENCE_TYPES_QUERY_KEY = "inferenceTypes";

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

  // Deployment allowlist from runtime server config (ENABLED_TASK_TYPES /
  // ConfigMap), intersected with the catalog. Unset ⇒ whole catalog.
  const enabledTaskTypesRaw = getRuntimeConfig().enabledTaskTypes;
  const taskTypeNames: string[] = useMemo(() => {
    const envEnabled = getEnabledTaskTypes();
    const allNames = inferenceTypes.map((t) => t.name);
    return envEnabled.length > 0
      ? allNames.filter((n) => envEnabled.includes(n.trim().toLowerCase()))
      : allNames;
  }, [inferenceTypes, enabledTaskTypesRaw]);

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
