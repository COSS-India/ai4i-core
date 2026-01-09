// Jaeger API service for fetching trace data

import axios from 'axios';

// Use Next.js API routes to proxy requests (avoids CORS issues)
const JAEGER_API_URL = process.env.NEXT_PUBLIC_JAEGER_URL || '/api/tracing';

const api = axios.create({
  baseURL: JAEGER_API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface JaegerService {
  name: string;
  operations?: Array<{
    name: string;
    spanKind: string;
  }>;
}

export interface JaegerTrace {
  traceID: string;
  spans: any[];
  processes: Record<string, any>;
  warnings?: string[];
}

export interface TraceSearchParams {
  service?: string;
  operation?: string;
  tags?: Record<string, string>;
  startTime?: number;
  endTime?: number;
  limit?: number;
  minDuration?: string;
  maxDuration?: string;
  lookback?: string;
}

export const jaegerService = {
  /**
   * Get all services
   */
  async getServices(): Promise<string[]> {
    try {
      const response = await api.get<{ data: string[] }>('/services');
      return response.data.data || [];
    } catch (error) {
      console.error('Error fetching services:', error);
      throw error;
    }
  },

  /**
   * Get operations for a service
   */
  async getOperations(service: string): Promise<Array<{ name: string; spanKind: string }>> {
    try {
      const response = await api.get<{ data: Array<{ name: string; spanKind: string }> }>(
        `/services/${encodeURIComponent(service)}/operations`
      );
      return response.data.data || [];
    } catch (error) {
      console.error('Error fetching operations:', error);
      throw error;
    }
  },

  /**
   * Search traces
   */
  async searchTraces(params: TraceSearchParams): Promise<JaegerTrace[]> {
    try {
      const queryParams = new URLSearchParams();
      
      if (params.service) queryParams.append('service', params.service);
      if (params.operation) queryParams.append('operation', params.operation);
      if (params.limit) queryParams.append('limit', params.limit.toString());
      if (params.lookback) queryParams.append('lookback', params.lookback);
      if (params.minDuration) queryParams.append('minDuration', params.minDuration);
      if (params.maxDuration) queryParams.append('maxDuration', params.maxDuration);
      if (params.startTime) queryParams.append('start', params.startTime.toString());
      if (params.endTime) queryParams.append('end', params.endTime.toString());
      if (params.tags) {
        queryParams.append('tags', JSON.stringify(params.tags));
      }

      const response = await api.get<{ data: JaegerTrace[] }>(`/traces?${queryParams.toString()}`);
      return response.data.data || [];
    } catch (error) {
      console.error('Error searching traces:', error);
      throw error;
    }
  },

  /**
   * Get single trace by ID
   */
  async getTrace(traceId: string): Promise<JaegerTrace | null> {
    try {
      const response = await api.get<{ data: JaegerTrace[] }>(`/trace/${traceId}`);
      return response.data.data?.[0] || null;
    } catch (error) {
      console.error('Error fetching trace:', error);
      throw error;
    }
  },
};

