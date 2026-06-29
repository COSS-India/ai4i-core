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
