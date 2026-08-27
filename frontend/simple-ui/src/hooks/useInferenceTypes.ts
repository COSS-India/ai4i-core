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

// "pipeline" is a real catalog/metering task type (the Speech-to-Speech
// Pipeline feature), but the pay-per-use service (tiers, usage-summary,
// usage-tenants, usage-tenant) doesn't recognize it and 422s if it's sent.
const PAY_PER_USE_EXCLUDED_TASK_TYPES = new Set(["pipeline"]);

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

  // Deployment allowlist from runtime server config (ENABLED_TASK_TYPES /
  // ConfigMap), intersected with the catalog. Unset/empty ⇒ whole catalog.
  // While the catalog is still loading, surface the env allowlist so metering
  // / Service Management do not briefly query an unfiltered set.
  const enabledTaskTypesRaw = getRuntimeConfig().enabledTaskTypes;
  const taskTypeNames: string[] = useMemo(() => {
    const envEnabled = getEnabledTaskTypes();
    const allNames = inferenceTypes.map((t) => t.name);
    if (envEnabled.length === 0) return allNames;
    if (allNames.length === 0) return envEnabled;
    return allNames.filter((n) => envEnabled.includes(n.trim().toLowerCase()));
  }, [inferenceTypes, enabledTaskTypesRaw]);

  // Units only for enabled task types (from /inference-types catalog).
  const unitByTaskType: Record<string, string> = useMemo(() => {
    const enabled = new Set(taskTypeNames.map((n) => n.trim().toLowerCase()));
    return Object.fromEntries(
      inferenceTypes
        .filter((t) => enabled.has(t.name.trim().toLowerCase()))
        .map((t) => [t.name, t.unit]),
    );
  }, [inferenceTypes, taskTypeNames]);

  // Enabled ServiceIds — the single source for gating the UI catalog
  // (home cards, sidebar nav, logs filter, tier/model selectors).
  const enabledServiceIds = useMemo(
    () => new Set(taskTypeNames.map(toServiceId)),
    [taskTypeNames],
  );

  // `taskTypeNames` minus "pipeline" — the set to send/offer wherever the
  // pay-per-use service is involved (tiers, usage-summary, usage-tenants,
  // usage-tenant, and the task-type filters that feed them).
  const payPerUseTaskTypeNames = useMemo(
    () =>
      taskTypeNames.filter(
        (n) => !PAY_PER_USE_EXCLUDED_TASK_TYPES.has(n.trim().toLowerCase()),
      ),
    [taskTypeNames],
  );

  return {
    inferenceTypes,
    taskTypeNames,
    payPerUseTaskTypeNames,
    unitByTaskType,
    enabledServiceIds,
    isLoading: query.isLoading,
  };
}
