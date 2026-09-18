// Services Management service API client

import { z } from "zod";
import { apiService } from "./api";
import { apiEndpoints } from "./apiEndpoints";
import {
  serviceSingleSchema,
  servicesListSchema,
} from "./dto/schemas/platform";
import type {
  DeleteServiceResponse,
  PaginatedServices,
  Service,
  ServiceListParams,
} from "../types/platform";

export type {
  DeleteServiceResponse,
  PaginatedServices,
  Service,
  ServiceCreateRequest,
  ServiceDetailResponse,
  ServiceListItem,
  ServiceListParams,
  ServiceResponse,
  ServiceUpdateRequest,
} from "../types/platform";

type ServiceRecord = Service & Record<string, unknown>;

const isNonEmptySecret = (value: unknown): boolean => {
  if (value == null) return false;
  const text = String(value).trim();
  return text.length > 0;
};

const nestedInferenceKey = (endpoint: unknown): unknown => {
  if (!endpoint || typeof endpoint !== "object") return undefined;
  const ep = endpoint as Record<string, unknown>;
  return ep.inferenceApiKey ?? ep.inference_api_key;
};

const nestedHasInferenceKey = (endpoint: unknown): boolean => {
  const key = nestedInferenceKey(endpoint);
  if (!key) return false;
  if (typeof key === "string") return isNonEmptySecret(key);
  if (typeof key === "object") {
    const rec = key as Record<string, unknown>;
    return isNonEmptySecret(rec.value) || isNonEmptySecret(rec.name);
  }
  return false;
};

/**
 * Whether a vLLM auth token is configured. Prefers `hasAuthToken` (AI4IDS-3148)
 * and falls back to current/legacy payload shapes so the UI works before and
 * after the backend field lands. Never treats the raw secret as display data.
 */
export const resolveHasAuthToken = (
  service: Partial<Service> | null | undefined,
): boolean => {
  if (!service) return false;
  if (typeof service.hasAuthToken === "boolean") return service.hasAuthToken;
  if (typeof service.has_auth_token === "boolean") return service.has_auth_token;
  const rec = service as ServiceRecord;
  if (
    nestedHasInferenceKey(rec.inferenceEndPoint) ||
    nestedHasInferenceKey(rec.inference_end_point)
  ) {
    return true;
  }
  return (
    isNonEmptySecret(service.api_key) ||
    isNonEmptySecret(service.apiKey) ||
    isNonEmptySecret(rec.authToken) ||
    isNonEmptySecret(rec.auth_token)
  );
};

const redactNestedInferenceKey = (endpoint: unknown): unknown => {
  if (!endpoint || typeof endpoint !== "object") return endpoint;
  const ep = { ...(endpoint as Record<string, unknown>) };
  const redact = (key: unknown): unknown => {
    if (!key || typeof key !== "object") return key;
    const rec = { ...(key as Record<string, unknown>) };
    if ("value" in rec) rec.value = isNonEmptySecret(rec.value) ? "***" : rec.value;
    return rec;
  };
  if ("inferenceApiKey" in ep) ep.inferenceApiKey = redact(ep.inferenceApiKey);
  if ("inference_api_key" in ep) ep.inference_api_key = redact(ep.inference_api_key);
  return ep;
};

/** Drop raw token fields so list/detail/form state never hold the secret. */
export const sanitizeService = (service: Service): Service => {
  if (!service || typeof service !== "object") return service;
  const rec = { ...(service as ServiceRecord) };
  const hasAuthToken = resolveHasAuthToken(rec);
  delete rec.authToken;
  delete rec.auth_token;
  delete rec.api_key;
  delete rec.apiKey;
  if (rec.inferenceEndPoint) {
    rec.inferenceEndPoint = redactNestedInferenceKey(
      rec.inferenceEndPoint,
    ) as Service["inferenceEndPoint"];
  }
  if (rec.inference_end_point) {
    rec.inference_end_point = redactNestedInferenceKey(rec.inference_end_point);
  }
  rec.hasAuthToken = hasAuthToken;
  return rec as Service;
};

/** Attach the planned `authToken` field, plus today's `api_key` alias. */
const applyAuthTokenToPayload = (
  apiPayload: Record<string, unknown>,
  serviceData: Partial<Service>,
  { sendEmptyApiKey }: { sendEmptyApiKey: boolean },
) => {
  const token = (serviceData.authToken || "").trim();
  if (token) {
    apiPayload.authToken = token;
    apiPayload.api_key = token;
    return;
  }
  if (sendEmptyApiKey) {
    apiPayload.api_key = serviceData.api_key || serviceData.apiKey || "";
  }
};

/**
 * List all services (no pagination — returns everything, backward-compatible)
 * @returns Promise with list of services
 */
export const listServices = async (): Promise<Service[]> => {
  try {
    const response = await apiService.get(apiEndpoints.platform.services.base, {
      suppressErrorAlert: true,
      responseSchema: servicesListSchema,
    });
    return (response.data || []).map(sanitizeService);
  } catch (error: any) {
    console.error("List services error:", error);
    throw error;
  }
};

/**
 * Fetch every existing serviceId (no `limit` → backend returns all).
 * Used by the create form to flag duplicate service ids.
 */
export const fetchExistingServiceIds = async (): Promise<string[]> => {
  const services = await listServices();
  return services
    .map((s) => s.serviceId || s.service_id || "")
    .filter((id): id is string => Boolean(id));
};

/**
 * List services with server-side pagination, filtering, and search.
 * Reads the X-Total-Count response header for the accurate total count.
 */
const REGISTRY_FETCH_PAGE_SIZE = 100;
const MAX_REGISTRY_FETCH_PAGES = 500;

/**
 * Fetches every service matching list filters by walking paginated API pages.
 * Used by the registry UI so name search and table pagination stay consistent (frontend-only).
 */
export const fetchAllServicesMatchingFilters = async (
  params: Pick<
    ServiceListParams,
    "taskType" | "taskTypes" | "isPublished" | "createdBy"
  > = {},
): Promise<PaginatedServices> => {
  const items: Service[] = [];
  let total = 0;
  let offset = 0;

  for (let page = 0; page < MAX_REGISTRY_FETCH_PAGES; page++) {
    const result = await listServicesPaginated({
      ...params,
      offset,
      limit: REGISTRY_FETCH_PAGE_SIZE,
    });
    total = result.total;
    items.push(...result.items);
    if (items.length >= total || result.items.length === 0) break;
    offset += REGISTRY_FETCH_PAGE_SIZE;
  }

  return { items, total, offset: 0, limit: null };
};

export const listServicesPaginated = async (
  params: ServiceListParams = {},
): Promise<PaginatedServices> => {
  try {
    const queryParams: Record<string, any> = {};
    if (params.offset !== undefined && params.offset > 0)
      queryParams.offset = params.offset;
    if (params.limit !== undefined) queryParams.limit = params.limit;
    // drill-down selected -> it's already in the allowlist, so it IS the intersection
    const taskTypesParam = params.taskType ?? params.taskTypes;
    if (taskTypesParam) queryParams.task_types = taskTypesParam;
    if (params.isPublished !== undefined)
      queryParams.is_published = params.isPublished;
    if (params.createdBy) queryParams.created_by = params.createdBy;

    const response = await apiService.get(apiEndpoints.platform.services.base, {
      params: queryParams,
      suppressErrorAlert: true,
      responseSchema: servicesListSchema,
    });

    const headerTotal = Number.parseInt(
      response.headers["x-total-count"] ?? "",
      10,
    );
    const payload = response.data;
    const items = (Array.isArray(payload) ? payload : []).map(sanitizeService);
    // Fall back to items.length when the header is absent (API uses meta.total instead)
    const total = Number.isNaN(headerTotal) ? items.length : headerTotal;

    return {
      items,
      total: Number.isNaN(total) ? items.length : total,
      offset: params.offset ?? 0,
      limit: params.limit ?? null,
    };
  } catch (error: any) {
    console.error("List services (paginated) error:", error);
    throw error;
  }
};

/**
 * Get service details by service_id
 * @param serviceId - The service_id of the service to fetch
 * @returns Promise with service details
 */
export const getServiceById = async (serviceId: string): Promise<Service> => {
  try {
    // The apiClient interceptor will automatically add authentication headers
    const response = await apiService.get(
      apiEndpoints.platform.services.byId(serviceId),
      {
        suppressErrorAlert: true,
        responseSchema: serviceSingleSchema,
      },
    );
    return sanitizeService(response.data);
  } catch (error: any) {
    console.error("Get service error:", error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};

/**
 * Create a new service
 * @param serviceData - The service data to create
 * @returns Promise with created service
 */
export const createService = async (
  serviceData: Partial<Service>,
): Promise<Service> => {
  try {
    // Transform snake_case to camelCase for API
    // The API expects camelCase format
    const apiPayload: Record<string, unknown> = {
      serviceId: serviceData.serviceId || serviceData.service_id,
      name: serviceData.name,
      description: serviceData.serviceDescription || serviceData.description,
      hardwareDescription: serviceData.hardwareDescription,
      publishedOn: serviceData.publishedOn || Math.floor(Date.now() / 1000),
      modelId: serviceData.modelId || serviceData.model_id,
      modelVersion:
        serviceData.modelVersion || serviceData.model_version || "1.0", // Default to '1.0' if not provided
      endpoint: serviceData.endpoint || serviceData.endpoint_url,
    };
    applyAuthTokenToPayload(apiPayload, serviceData, { sendEmptyApiKey: true });

    // Add billing/pricing fields if provided
    if (serviceData.task_type) apiPayload.taskType = serviceData.task_type;
    if (serviceData.costPerUnit !== undefined)
      apiPayload.costPerUnit = serviceData.costPerUnit;
    if (serviceData.unitSize !== undefined)
      apiPayload.unitSize = serviceData.unitSize;
    if (serviceData.tierIds?.length) apiPayload.tierIds = serviceData.tierIds;

    // Add optional healthStatus if provided
    if (serviceData.healthStatus || serviceData.status) {
      apiPayload.healthStatus = serviceData.healthStatus || {
        status: serviceData.status || "active",
        lastUpdated: new Date().toISOString(),
      };
    }

    // The apiClient interceptor will automatically add:
    // - Content-Type: application/json
    // - Accept: application/json
    // - Authorization: Bearer <token>
    // - X-API-Key: <api_key> (if available)
    // - x-auth-source: AUTH_TOKEN | API_KEY | BOTH
    const response = await apiService.post(
      apiEndpoints.platform.services.base,
      apiPayload,
      { suppressErrorAlert: true, responseSchema: serviceSingleSchema },
    );
    return sanitizeService(response.data);
  } catch (error: any) {
    console.error("Create service error:", error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};

/**
 * Update a service
 * @param serviceData - The service data to update (must include serviceId)
 * @returns Promise with updated service
 */
export const updateService = async (
  serviceData: Partial<Service>,
): Promise<Service> => {
  try {
    // For publish/unpublish, only send serviceId and isPublished
    // For other updates, send all fields
    const isPublishUpdate =
      serviceData.serviceId &&
      serviceData.hasOwnProperty("isPublished") &&
      Object.keys(serviceData).length <= 2;

    let apiPayload: Record<string, unknown>;

    if (isPublishUpdate) {
      // Publish/unpublish: only send serviceId and isPublished
      apiPayload = {
        serviceId: serviceData.serviceId || serviceData.service_id,
        isPublished: serviceData.isPublished,
      };
    } else {
      // Full update: send all fields
      apiPayload = {
        serviceId: serviceData.serviceId || serviceData.service_id,
        name: serviceData.name,
        hardwareDescription: serviceData.hardwareDescription,
        publishedOn: serviceData.publishedOn,
        modelId: serviceData.modelId || serviceData.model_id,
        modelVersion: serviceData.modelVersion || serviceData.model_version,
        endpoint: serviceData.endpoint || serviceData.endpoint_url,
      };
      applyAuthTokenToPayload(apiPayload, serviceData, { sendEmptyApiKey: false });

      // Preserve empty string so admins can clear an existing description.
      if ("serviceDescription" in serviceData) {
        apiPayload.serviceDescription = serviceData.serviceDescription;
      } else if ("description" in serviceData) {
        apiPayload.serviceDescription = serviceData.description;
      }

      // Add billing/pricing fields if provided (mirrors createService)
      if (serviceData.task_type) apiPayload.taskType = serviceData.task_type;
      if (serviceData.costPerUnit !== undefined)
        apiPayload.costPerUnit = serviceData.costPerUnit;
      if (serviceData.unitSize !== undefined)
        apiPayload.unitSize = serviceData.unitSize;
      if (serviceData.tierIds?.length) apiPayload.tierIds = serviceData.tierIds;

      // Add optional healthStatus if provided
      if (serviceData.healthStatus || serviceData.status) {
        apiPayload.healthStatus = serviceData.healthStatus || {
          status: serviceData.status || "active",
          lastUpdated: new Date().toISOString(),
        };
      }

      // Add isPublished if provided
      if (serviceData.hasOwnProperty("isPublished")) {
        apiPayload.isPublished = serviceData.isPublished;
      }
    }

    const response = await apiService.patch(
      apiEndpoints.platform.services.base,
      apiPayload,
      { suppressErrorAlert: true, responseSchema: serviceSingleSchema },
    );
    return sanitizeService(response.data);
  } catch (error: any) {
    console.error("Update service error:", error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};

/**
 * Delete a service
 * @param serviceId - The service_id of the service to delete
 * @returns Promise with deletion response
 */
export const deleteService = async (
  serviceId: string,
): Promise<DeleteServiceResponse> => {
  try {
    // The apiClient interceptor will automatically add authentication headers
    const response = await apiService.delete(
      apiEndpoints.platform.services.byId(serviceId),
      {
        suppressErrorAlert: true,
        responseSchema: z.unknown(),
      },
    );
    return response.data;
  } catch (error: any) {
    console.error("Delete service error:", error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};
