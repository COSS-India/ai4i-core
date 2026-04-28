// Services Management service API client

import { apiClient } from './api';

type ApiEnvelope<T> = {
  success?: boolean;
  data?: T;
  meta?: Record<string, any>;
};

const unwrapData = <T>(payload: T | ApiEnvelope<T>): T => {
  if (payload && typeof payload === 'object' && 'data' in (payload as any)) {
    return ((payload as ApiEnvelope<T>).data ?? null) as T;
  }
  return payload as T;
};

export interface ServiceListParams {
  offset?: number;
  limit?: number;
  taskType?: string;
  isPublished?: boolean;
  createdBy?: string;
}

export interface PaginatedServices {
  items: Service[];
  total: number;
  offset: number;
  limit: number | null;
}

export interface Service {
  serviceId?: string;
  service_id?: string; // For backward compatibility
  name?: string;
  serviceDescription?: string;
  description?: string; // For backward compatibility
  hardwareDescription?: string;
  publishedOn?: number;
  modelId?: string;
  model_id?: string; // For backward compatibility
  modelVersion?: string;
  model_version?: string; // For backward compatibility
  modelSubmissionDate?: string;
  endpoint?: string;
  endpoint_url?: string; // For backward compatibility
  api_key?: string;
  apiKey?: string; // For backward compatibility
  task_type?: string; // For backward compatibility
  task?: {
    type: string;
  };
  model?: {
    task?: {
      type: string;
    };
    [key: string]: any;
  };
  status?: string;
  healthStatus?: {
    status: string;
    lastUpdated: string;
  };
  isPublished?: boolean;
  /** ISO timestamp when service was published; used for list ordering */
  publishedAt?: string | null;
  /** ISO timestamp when service was unpublished; used for list ordering */
  unpublishedAt?: string | null;
  createdAt?: string;
  created_at?: string;
  updated_at?: string;
  /** ISO timestamp when status was last updated; used for list ordering */
  versionStatusUpdatedAt?: string;
  [key: string]: any;
}

/**
 * List all services (no pagination — returns everything, backward-compatible)
 * @returns Promise with list of services
 */
export const listServices = async (): Promise<Service[]> => {
  try {
    const response = await apiClient.get<Service[] | ApiEnvelope<Service[]>>('/api/v1/services');
    return unwrapData(response.data) || [];
  } catch (error: any) {
    console.error('List services error:', error);
    throw error;
  }
};

/**
 * List services with server-side pagination, filtering, and search.
 * Reads the X-Total-Count response header for the accurate total count.
 */
export const listServicesPaginated = async (params: ServiceListParams = {}): Promise<PaginatedServices> => {
  try {
    const queryParams: Record<string, any> = {};
    if (params.offset !== undefined && params.offset > 0) queryParams.offset = params.offset;
    if (params.limit !== undefined) queryParams.limit = params.limit;
    if (params.taskType) queryParams.task_type = params.taskType;
    if (params.isPublished !== undefined) queryParams.is_published = params.isPublished;
    if (params.createdBy) queryParams.created_by = params.createdBy;

    const response = await apiClient.get<Service[] | ApiEnvelope<Service[]>>('/api/v1/services', {
      params: queryParams,
    });

    const total = parseInt(response.headers['x-total-count'] ?? '0', 10);
    const payload = unwrapData(response.data);
    const items = Array.isArray(payload) ? payload : [];

    return {
      items,
      total: Number.isNaN(total) ? items.length : total,
      offset: params.offset ?? 0,
      limit: params.limit ?? null,
    };
  } catch (error: any) {
    console.error('List services (paginated) error:', error);
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
    const response = await apiClient.get<Service | ApiEnvelope<Service>>(
      `/api/v1/services/${serviceId}`
    );
    return unwrapData(response.data);
  } catch (error: any) {
    console.error('Get service error:', error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};

/**
 * Create a new service
 * @param serviceData - The service data to create
 * @returns Promise with created service
 */
export const createService = async (serviceData: Partial<Service>): Promise<Service> => {
  try {
    // Transform snake_case to camelCase for API
    // The API expects camelCase format
    const apiPayload: any = {
      serviceId: serviceData.serviceId || serviceData.service_id,
      name: serviceData.name,
      serviceDescription: serviceData.serviceDescription || serviceData.description,
      hardwareDescription: serviceData.hardwareDescription || 'Default hardware',
      publishedOn: serviceData.publishedOn || Math.floor(Date.now() / 1000),
      modelId: serviceData.modelId || serviceData.model_id,
      modelVersion: serviceData.modelVersion || serviceData.model_version || '1.0', // Default to '1.0' if not provided
      endpoint: serviceData.endpoint || serviceData.endpoint_url,
      api_key: serviceData.api_key || serviceData.apiKey || '',
    };
    
    // Add optional healthStatus if provided
    if (serviceData.healthStatus || serviceData.status) {
      apiPayload.healthStatus = serviceData.healthStatus || {
        status: serviceData.status || 'active',
        lastUpdated: new Date().toISOString(),
      };
    }
    
    // The apiClient interceptor will automatically add:
    // - Content-Type: application/json
    // - Accept: application/json
    // - Authorization: Bearer <token>
    // - X-API-Key: <api_key> (if available)
    // - x-auth-source: AUTH_TOKEN | API_KEY | BOTH
    const response = await apiClient.post<Service>(
      '/api/v1/services',
      apiPayload
    );
    return unwrapData(response.data as any);
  } catch (error: any) {
    console.error('Create service error:', error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};

/**
 * Update a service
 * @param serviceData - The service data to update (must include serviceId)
 * @returns Promise with updated service
 */
export const updateService = async (serviceData: Partial<Service>): Promise<Service> => {
  try {
    // For publish/unpublish, only send serviceId and isPublished
    // For other updates, send all fields
    const isPublishUpdate = serviceData.serviceId && serviceData.hasOwnProperty('isPublished') && Object.keys(serviceData).length <= 2;
    
    let apiPayload: any;
    
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
        serviceDescription: serviceData.serviceDescription || serviceData.description,
        hardwareDescription: serviceData.hardwareDescription,
        publishedOn: serviceData.publishedOn,
        modelId: serviceData.modelId || serviceData.model_id,
        modelVersion: serviceData.modelVersion || serviceData.model_version,
        endpoint: serviceData.endpoint || serviceData.endpoint_url,
        api_key: serviceData.api_key || serviceData.apiKey,
      };
      
      // Add optional healthStatus if provided
      if (serviceData.healthStatus || serviceData.status) {
        apiPayload.healthStatus = serviceData.healthStatus || {
          status: serviceData.status || 'active',
          lastUpdated: new Date().toISOString(),
        };
      }
      
      // Add isPublished if provided
      if (serviceData.hasOwnProperty('isPublished')) {
        apiPayload.isPublished = serviceData.isPublished;
      }
    }
    
    const response = await apiClient.patch<Service>(
      '/api/v1/services',
      apiPayload
    );
    return unwrapData(response.data as any);
  } catch (error: any) {
    console.error('Update service error:', error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};

/**
 * Delete a service
 * @param serviceId - The service_id of the service to delete
 * @returns Promise with deletion response
 */
export const deleteService = async (serviceId: string): Promise<any> => {
  try {
    // The apiClient interceptor will automatically add authentication headers
    const response = await apiClient.delete<any>(
      `/api/v1/services/${serviceId}`
    );
    return unwrapData(response.data as any);
  } catch (error: any) {
    console.error('Delete service error:', error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};

