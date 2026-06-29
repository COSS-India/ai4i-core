import type { QueryClient } from "@tanstack/react-query";
import type { NextRouter } from "next/router";
import type { ModelDetails } from "../types/platform";
import type { Service } from "../services/servicesManagementService";
import { getModelById } from "../services/modelManagementService";
import { SERVICE_PUBLISH } from "../constants";

const INFERENCE_SERVICE_QUERY_KEYS = [
  ["asr-services"],
  ["tts-services"],
  ["ocr-services"],
  ["nmt-services"],
  ["nerServices"],
  ["llm-services"],
  ["transliteration-services"],
  ["speaker-diarization-services"],
  ["language-detection-services"],
  ["language-diarization-services"],
  ["audioLanguageDetectionServices"],
] as const;

export function invalidateInferenceServiceQueries(queryClient: QueryClient): void {
  for (const queryKey of INFERENCE_SERVICE_QUERY_KEYS) {
    queryClient.invalidateQueries({ queryKey });
  }
}

export function isServiceModelDeprecated(service: Service | null | undefined): boolean {
  if (!service) return false;
  const modelVersionStatus =
    (service.model as { versionStatus?: string; version_status?: string } | undefined)?.versionStatus ??
    (service.model as { version_status?: string } | undefined)?.version_status ??
    (service as { versionStatus?: string; version_status?: string }).versionStatus ??
    (service as { version_status?: string }).version_status;
  return isModelVersionDeprecated(modelVersionStatus);
}

export function isModelVersionDeprecated(versionStatus?: string | null): boolean {
  return typeof versionStatus === "string" && versionStatus.toLowerCase() === "deprecated";
}

export function formatModelSubmissionDate(value?: string | number | null): string {
  if (value == null || value === "") return "";

  let timestampMs: number;
  if (typeof value === "number") {
    timestampMs = value > 1e12 ? value : value * 1000;
  } else if (/^\d+$/.test(value)) {
    const parsed = Number(value);
    timestampMs = parsed > 1e12 ? parsed : parsed * 1000;
  } else {
    timestampMs = new Date(value).getTime();
  }

  if (Number.isNaN(timestampMs)) return "";
  return new Date(timestampMs).toISOString().slice(0, 10);
}

export function getServiceTaskColor(taskType?: string): string {
  if (!taskType) return "gray";
  switch (taskType.toLowerCase()) {
    case "asr":
      return "orange";
    case "nmt":
      return "green";
    case "tts":
      return "blue";
    case "llm":
      return "purple";
    default:
      return "gray";
  }
}

export function resolvePublishedFilter(filterStatus: string): boolean | undefined {
  if (filterStatus === SERVICE_PUBLISH.FILTER.PUBLISHED) return true;
  if (filterStatus === SERVICE_PUBLISH.FILTER.UNPUBLISHED) return false;
  return undefined;
}

export function buildModelsForDropdown(
  models: ModelDetails[],
  preselectedModelFromQuery: ModelDetails | null
): ModelDetails[] {
  const preselectedNotDeprecated =
    preselectedModelFromQuery &&
    preselectedModelFromQuery.versionStatus?.toLowerCase() !== "deprecated";
  if (
    preselectedNotDeprecated &&
    !models.some(
      (m) =>
        (m.modelId || m.model_id) ===
        (preselectedModelFromQuery.modelId || preselectedModelFromQuery.model_id)
    )
  ) {
    return [preselectedModelFromQuery, ...models];
  }
  return models;
}

export function filterAndSortRegistryServices(
  services: Service[],
  searchQuery: string,
  sortBy: "time" | "name",
  nameSortDirection: "asc" | "desc"
): Service[] {
  const q = searchQuery.trim().toLowerCase();
  const filtered = q
    ? services.filter((s) => (s.name ?? "").toLowerCase().includes(q))
    : services;
  if (sortBy === "time") return filtered;
  return [...filtered].sort((a, b) => {
    const nameCmp = (a.name ?? "").localeCompare(b.name ?? "", undefined, { sensitivity: "base" });
    if (nameCmp !== 0) return nameSortDirection === "asc" ? nameCmp : -nameCmp;
    return 0;
  });
}

export const EMPTY_CREATE_SERVICE_FORM: Partial<Service> = {
  name: "",
  serviceDescription: "",
  publishedOn: Math.floor(Date.now() / 1000),
  modelId: "",
  modelName: "",
  endpoint: "",
  task_type: "",
  modelSubmissionDate: "",
  modelVersion: "1.0",
};

export function shallowReplaceServicesRoutePreservingTab(router: NextRouter): void {
  const { tab: currentTab } = router.query;
  const nextQuery: Record<string, string> = {};
  if (typeof currentTab === "string") nextQuery.tab = currentTab;
  router.replace({ pathname: "/services-management", query: nextQuery }, undefined, { shallow: true });
}

function modelIdInActiveList(models: ModelDetails[], modelId: string): boolean {
  return models.some((m) => (m.modelId || m.model_id) === modelId);
}

export async function preselectModelFromUrlQuery(
  modelId: string,
  models: ModelDetails[],
  currentFormModelId: string | undefined,
  handlers: {
    setActiveTab: (tab: number) => void;
    setPreselectedModelFromQuery: (model: ModelDetails | null) => void;
    handleModelNameChange: (modelId: string) => void;
    clearModelIdFromUrl: () => void;
  },
  options: { switchToCreateTab: boolean },
): Promise<void> {
  if (options.switchToCreateTab) handlers.setActiveTab(1);

  const inActiveList = modelIdInActiveList(models, modelId);
  if (inActiveList && currentFormModelId !== modelId) {
    handlers.handleModelNameChange(modelId);
    handlers.clearModelIdFromUrl();
    return;
  }

  if (!inActiveList) {
    try {
      const modelDetails = await getModelById(modelId);
      if (modelDetails && !isModelVersionDeprecated(modelDetails.versionStatus)) {
        handlers.setPreselectedModelFromQuery(modelDetails);
        if (currentFormModelId !== modelId) {
          handlers.handleModelNameChange(modelId);
        }
      }
    } catch (e) {
      console.error("Failed to load preselected model:", e);
    }
    handlers.clearModelIdFromUrl();
  }
}
