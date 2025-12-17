// Speaker Diarization service API client

import { apiClient, apiEndpoints } from './api';

export interface SpeakerDiarizationInferenceRequest {
  audio: Array<{
    audioContent: string;
  }>;
  config: {
    serviceId: string;
    [key: string]: any;
  };
}

export interface SpeakerDiarizationInferenceResponse {
  output: Array<{
    segments?: Array<{
      start: number;
      end: number;
      speaker: string;
      text?: string;
    }>;
    [key: string]: any;
  }>;
}

/**
 * Perform speaker diarization inference
 */
export const performSpeakerDiarizationInference = async (
  audioContent: string,
  serviceId: string
): Promise<{ data: SpeakerDiarizationInferenceResponse; responseTime: number }> => {
  try {
    const payload: SpeakerDiarizationInferenceRequest = {
      audio: [{ audioContent }],
      config: {
        serviceId,
      },
    };

    const response = await apiClient.post<SpeakerDiarizationInferenceResponse>(
      apiEndpoints['speaker-diarization'].inference,
      payload
    );

    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('Speaker diarization inference error:', error);
    throw new Error('Failed to perform speaker diarization inference');
  }
};

