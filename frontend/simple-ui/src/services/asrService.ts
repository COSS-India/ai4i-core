// ASR service API client with typed methods

import { asrApiClient, apiEndpoints } from './api';
import { 
  ASRInferenceRequest, 
  ASRInferenceResponse, 
  ASRModel, 
  ASRHealthResponse,
  ASRModelsResponse 
} from '../types/asr';
import { io, Socket } from 'socket.io-client';
import { listServices } from './modelManagementService';

// ASR Service details from model management
export interface ASRServiceDetails {
  service_id: string;
  model_id: string;
  model_version?: string;
  name: string;
  description: string;
  endpoint: string;
  languages?: string[];
  modelVersion?: string;
}

/**
 * Perform ASR inference on audio content
 * @param audioContent - Base64 encoded audio content
 * @param config - ASR configuration
 * @returns Promise with ASR inference response
 */
export const performASRInference = async (
  audioContent: string,
  config: ASRInferenceRequest['config']
): Promise<ASRInferenceResponse> => {
  try {
    const payload: ASRInferenceRequest = {
      audio: [{ audioContent }],
      config,
      controlConfig: {
        dataTracking: false,
      },
    };

    const response = await asrApiClient.post<ASRInferenceResponse>(
      apiEndpoints.asr.inference,
      payload
    );

    return response.data;
  } catch (error) {
    console.error('ASR inference error:', error);
    throw error; // Re-throw so toast can show backend message via extractErrorInfo
  }
};

/**
 * Transcribe audio using the transcribe endpoint (alias for inference)
 * @param audioContent - Base64 encoded audio content
 * @param config - ASR configuration
 * @returns Promise with ASR inference response and timing info
 */
export const transcribeAudio = async (
  audioContent: string,
  config: ASRInferenceRequest['config']
): Promise<{ data: ASRInferenceResponse; responseTime: number }> => {
  try {
    // Dhruva Platform ASR request schema
    const payload: ASRInferenceRequest = {
      audio: [{ audioContent }],
      config: {
        ...config,
        encoding: 'base64', // Required for Dhruva Platform
        preProcessors: ['vad', 'denoise'], // Voice Activity Detection and denoising
        postProcessors: ['lm', 'punctuation'], // Language model and punctuation
      },
      controlConfig: {
        dataTracking: false,
      },
    };

    console.log('=== ASR API Request ===');
    console.log('Endpoint:', apiEndpoints.asr.inference);
    console.log('Audio length:', audioContent.length);
    console.log('Config:', JSON.stringify(payload.config, null, 2));
    console.log('Full payload (audio truncated):', {
      ...payload,
      audio: [{ audioContent: `${audioContent.substring(0, 50)}... (truncated)` }]
    });

    const response = await asrApiClient.post<ASRInferenceResponse>(
      apiEndpoints.asr.inference,
      payload
    );

    console.log('=== ASR API Response ===');
    console.log('Response status:', response.status);
    console.log('Response data:', response.data);
    console.log('Response output:', response.data.output);

    // Extract response time from headers
    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error: any) {
    console.error('ASR transcription error:', error);
    throw error; // Re-throw so toast can show backend message via extractErrorInfo
  }
};

/**
 * Get list of available ASR models
 * @returns Promise with ASR models response
 */
export const listASRModels = async (): Promise<ASRModelsResponse> => {
  try {
    const response = await asrApiClient.get<ASRModelsResponse>(
      apiEndpoints.asr.models
    );

    return response.data;
  } catch (error) {
    console.error('Failed to fetch ASR models:', error);
    throw new Error('Failed to fetch ASR models');
  }
};

/**
 * Get list of available ASR services from model management service
 * @returns Promise with ASR services list
 */
export const listASRServices = async (): Promise<ASRServiceDetails[]> => {
  try {
    // Fetch services from model management service filtered by task_type='asr'
    const services = await listServices('asr');
    const seen = new Set<string>();

    // Transform model management service response to ASRServiceDetails format
    const normalized = services.map((service: any) => {
      // Extract languages from service.languages array
      const supportedLanguages: string[] = [];
      if (service.languages && Array.isArray(service.languages)) {
        service.languages.forEach((lang: any) => {
          if (typeof lang === 'string') {
            supportedLanguages.push(lang);
          } else if (lang && typeof lang === 'object') {
            // Handle different language object formats
            const langCode = lang.code || lang.sourceLanguage || lang.language;
            if (langCode) {
              supportedLanguages.push(langCode);
            }
          }
        });
      }
      
      // Extract endpoint
      const endpoint = service.endpoint || service.endpoint_url || '';
      
      return {
        service_id: service.serviceId || service.service_id,
        model_id: service.modelId || service.model_id,
        model_version: service.modelVersion || service.model_version || '',
        name: service.name || service.serviceId || service.service_id || '',
        description: service.serviceDescription || service.description || '',
        endpoint: endpoint,
        languages: Array.from(new Set(supportedLanguages)), // Remove duplicates
        modelVersion: service.modelVersion || service.model_version,
      } as ASRServiceDetails;
    });

    // Deduplicate by service_id in case API returns duplicates
    const deduplicated = normalized.filter((service) => {
      if (seen.has(service.service_id)) {
        return false;
      }
      seen.add(service.service_id);
      return true;
    });

    return deduplicated;
  } catch (error) {
    console.error('Failed to fetch ASR services:', error);
    throw new Error('Failed to fetch ASR services');
  }
};

/**
 * Check ASR service health
 * @returns Promise with health status
 */
export const checkASRHealth = async (): Promise<ASRHealthResponse> => {
  try {
    const response = await asrApiClient.get<ASRHealthResponse>(
      apiEndpoints.asr.health
    );

    return response.data;
  } catch (error) {
    console.error('Failed to check ASR health:', error);
    throw new Error('Failed to check ASR service health');
  }
};

/**
 * Get ASR service configuration
 * @returns Promise with service configuration
 */
export const getASRConfig = async () => {
  try {
    const response = await asrApiClient.get('/api/v1/asr/config');
    return response.data;
  } catch (error) {
    console.error('Failed to fetch ASR config:', error);
    throw new Error('Failed to fetch ASR configuration');
  }
};

/**
 * Validate ASR request before sending
 * @param audioContent - Base64 encoded audio content
 * @param config - ASR configuration
 * @returns Validation result
 */
export const validateASRRequest = (
  audioContent: string,
  config: ASRInferenceRequest['config']
): { isValid: boolean; error?: string } => {
  if (!audioContent || audioContent.trim() === '') {
    return { isValid: false, error: 'Audio content is required' };
  }

  if (!config.language.sourceLanguage) {
    return { isValid: false, error: 'Source language is required' };
  }

  if (!config.serviceId) {
    return { isValid: false, error: 'Service ID is required' };
  }

  if (!config.audioFormat) {
    return { isValid: false, error: 'Audio format is required' };
  }

  if (!config.samplingRate || config.samplingRate <= 0) {
    return { isValid: false, error: 'Valid sampling rate is required' };
  }

  return { isValid: true };
};

/**
 * WebSocket streaming ASR service
 */
export class ASRStreamingService {
  private socket: Socket | null = null;
  private isConnected = false;

  constructor() {
    this.socket = null;
    this.isConnected = false;
  }

  /**
   * Connect to ASR streaming service
   */
  connect(config: {
    serviceId: string;
    language: string;
    samplingRate: number;
    apiKey?: string;
  }): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.socket?.connected) {
        resolve();
        return;
      }

      console.log('Connecting to ASR streaming service...', config);

      this.socket = io(apiEndpoints.asr.streaming, {
        transports: ['websocket'],
        query: {
          serviceId: config.serviceId,
          language: config.language,
          samplingRate: config.samplingRate.toString(),
          ...(config.apiKey && { apiKey: config.apiKey }),
        },
      });

      this.socket.on('connect', () => {
        console.log('Connected to ASR streaming service');
        this.isConnected = true;
        resolve();
      });

      this.socket.on('connect_error', (error) => {
        console.error('ASR streaming connection error:', error);
        this.isConnected = false;
        reject(error);
      });

      this.socket.on('disconnect', (reason) => {
        console.log('ASR streaming disconnected:', reason);
        this.isConnected = false;
      });
    });
  }

  /**
   * Start streaming session
   */
  startSession(config: {
    serviceId: string;
    language: string;
    samplingRate: number;
    preProcessors?: string[];
    postProcessors?: string[];
  }): void {
    if (!this.socket?.connected) {
      throw new Error('Not connected to streaming service');
    }

    console.log('Starting ASR streaming session...', config);
    this.socket.emit('start', config);
  }

  /**
   * Send audio data
   */
  sendAudioData(audioData: ArrayBuffer): void {
    if (!this.socket?.connected) {
      throw new Error('Not connected to streaming service');
    }

    this.socket.emit('data', audioData);
  }

  /**
   * Listen for responses
   */
  onResponse(callback: (response: any) => void): void {
    if (!this.socket) return;
    this.socket.on('response', callback);
  }

  /**
   * Listen for errors
   */
  onError(callback: (error: any) => void): void {
    if (!this.socket) return;
    this.socket.on('error', callback);
  }

  /**
   * Listen for ready event
   */
  onReady(callback: (data: any) => void): void {
    if (!this.socket) return;
    this.socket.on('ready', callback);
  }

  /**
   * Disconnect from streaming service
   */
  disconnect(): void {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
      this.isConnected = false;
    }
  }

  /**
   * Check if connected
   */
  get connected(): boolean {
    return this.isConnected && this.socket?.connected === true;
  }
}
