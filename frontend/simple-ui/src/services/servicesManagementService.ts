// Services Management service API client

import { z } from "zod";
import { apiService } from "./api";
import { apiEndpoints } from "./apiEndpoints";
import {
  serviceRecordSchema,
  serviceSingleSchema,
  servicesListSchema,
} from "./dto/schemas/platform";
import type {
  DeleteServiceResponse,
  PaginatedServices,
  Service,
  ServiceCreateRequest,
  ServiceListParams,
  ServiceUpdateRequest,
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
    return response.data || [];
  } catch (error: any) {
    console.error("List services error:", error);
    throw error;
  }
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
    "taskType" | "isPublished" | "createdBy"
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
    if (params.taskType) queryParams.task_type = params.taskType;
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
    const items = Array.isArray(payload) ? payload : [];
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
    return response.data;
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
      serviceDescription:
        serviceData.serviceDescription || serviceData.description,
      hardwareDescription:
        serviceData.hardwareDescription || "Default hardware",
      publishedOn: serviceData.publishedOn || Math.floor(Date.now() / 1000),
      modelId: serviceData.modelId || serviceData.model_id,
      modelVersion:
        serviceData.modelVersion || serviceData.model_version || "1.0", // Default to '1.0' if not provided
      endpoint: serviceData.endpoint || serviceData.endpoint_url,
      api_key: serviceData.api_key || serviceData.apiKey || "",
    };

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
    return response.data;
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
        serviceDescription:
          serviceData.serviceDescription || serviceData.description,
        hardwareDescription: serviceData.hardwareDescription,
        publishedOn: serviceData.publishedOn,
        modelId: serviceData.modelId || serviceData.model_id,
        modelVersion: serviceData.modelVersion || serviceData.model_version,
        endpoint: serviceData.endpoint || serviceData.endpoint_url,
        api_key: serviceData.api_key || serviceData.apiKey,
      };

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
    return response.data;
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
