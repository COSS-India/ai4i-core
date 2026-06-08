import type { LanguageOption, ServiceOption } from "../../types/servicePage";

/** Common shape returned by model-management service list APIs */
export interface ServiceListItem {
  service_id: string;
  name?: string;
  description?: string;
  serviceDescription?: string;
  model_version?: string;
  modelVersion?: string;
}

export function mapToServiceOptions(services: ServiceListItem[]): ServiceOption[] {
  return services.map((s) => ({
    id: s.service_id,
    label: s.name || s.service_id,
    description: s.description || s.serviceDescription,
    version: s.model_version || s.modelVersion,
  }));
}

/**
 * Validates if a URL is safe to use as an image source.
 * Only allows http:, https:, blob:, and data:image/* protocols.
 */
export function isSafeImageUrl(url: string): boolean {
  if (!url || url.trim() === "") {
    return false;
  }

  try {
    if (url.startsWith("blob:")) {
      return true;
    }

    const parsedUrl = new URL(url);

    if (parsedUrl.protocol === "http:" || parsedUrl.protocol === "https:") {
      return true;
    }

    if (parsedUrl.protocol === "data:") {
      return /^data:image\//.test(url);
    }

    return false;
  } catch {
    return false;
  }
}

export const INDIC_LANGUAGE_OPTIONS: LanguageOption[] = [
  { code: "en", label: "English" },
  { code: "hi", label: "Hindi" },
  { code: "ta", label: "Tamil" },
  { code: "te", label: "Telugu" },
  { code: "kn", label: "Kannada" },
  { code: "ml", label: "Malayalam" },
  { code: "mr", label: "Marathi" },
  { code: "gu", label: "Gujarati" },
  { code: "bn", label: "Bengali" },
  { code: "pa", label: "Punjabi" },
  { code: "or", label: "Odia" },
  { code: "as", label: "Assamese" },
];
