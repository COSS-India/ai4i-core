// Services Management service API client

import { apiClient } from './api';

export interface Service {
  uuid?: string;
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
  created_at?: string;
  updated_at?: string;
  [key: string]: any;
}

/**
 * List all services
 * @returns Promise with list of services
 */
export const listServices = async (): Promise<Service[]> => {
  try {
    // The apiClient interceptor will automatically add:
    // - Content-Type: application/json
    // - Accept: application/json
    // - Authorization: Bearer <token>
    // - X-API-Key: <api_key> (if available)
    // - x-auth-source: AUTH_TOKEN | API_KEY | BOTH
    const response = await apiClient.get<Service[]>('/api/v1/model-management/services');
    return response.data;
  } catch (error: any) {
    console.error('List services error:', error);
    // Don't transform the error - let extractErrorInfo handle it
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
    const response = await apiClient.post<Service>(
      `/api/v1/model-management/services/${serviceId}`,
      { service_id: serviceId }
    );
    return response.data;
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
      '/api/v1/model-management/services',
      apiPayload
    );
    return response.data;
  } catch (error: any) {
    console.error('Create service error:', error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};

/**
 * Update a service
 * @param serviceData - The service data to update (must include uuid)
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
        uuid: serviceData.uuid,
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
      '/api/v1/model-management/services',
      apiPayload
    );
    return response.data;
  } catch (error: any) {
    console.error('Update service error:', error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};

/**
 * Delete a service
 * @param uuid - The UUID of the service to delete
 * @returns Promise with deletion response
 */
export const deleteService = async (uuid: string): Promise<any> => {
  try {
    // The apiClient interceptor will automatically add authentication headers
    const response = await apiClient.delete<any>(
      `/api/v1/model-management/services/${uuid}`
    );
    return response.data;
  } catch (error: any) {
    console.error('Delete service error:', error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};


