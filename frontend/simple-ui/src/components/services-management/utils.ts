import type { QueryClient } from "@tanstack/react-query";
import type { Service } from "../../services/servicesManagementService";

const SERVICE_REGISTRY_QUERY_KEYS = [
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

export function invalidateServiceRegistryQueries(queryClient: QueryClient): void {
  for (const queryKey of SERVICE_REGISTRY_QUERY_KEYS) {
    queryClient.invalidateQueries({ queryKey });
  }
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

export function getTaskColor(taskType?: string): string {
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

export function getStatusColor(status?: string): string {
  if (!status) return "gray";
  switch (status.toLowerCase()) {
    case "active":
      return "green";
    case "inactive":
      return "red";
    case "pending":
      return "yellow";
    default:
      return "gray";
  }
}

export function isServiceModelDeprecated(service: Service | null | undefined): boolean {
  if (!service) return false;
  const modelVersionStatus =
    (service.model as any)?.versionStatus ??
    (service.model as any)?.version_status ??
    (service as any).versionStatus ??
    (service as any).version_status;
  return typeof modelVersionStatus === "string" && modelVersionStatus.toLowerCase() === "deprecated";
}
