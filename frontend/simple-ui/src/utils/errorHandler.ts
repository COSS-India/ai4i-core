/**
 * Utility functions for handling and formatting API errors
 */

import { ASR_ERRORS, TTS_ERRORS, NMT_ERRORS, PIPELINE_ERRORS, COMMON_ERRORS, OCR_ERRORS, TRANSLITERATION_ERRORS, LANGUAGE_DETECTION_ERRORS, SPEAKER_DIARIZATION_ERRORS, AUDIO_LANGUAGE_DETECTION_ERRORS, NER_ERRORS } from '../config/constants';

export interface ErrorInfo {
  title: string;
  message: string;
  showOnlyMessage?: boolean; // If true, show only message in toast (hide title)
}

/**
 * Extracts error information from API error responses
 * Handles various error response formats:
 * - { detail: { error: "PERMISSION_DENIED", message: "..." } }
 * - { detail: "Error message" }
 * - { message: "Error message" }
 * - Standard error objects
 */
export type ErrorHandlerService = 'asr' | 'tts' | 'nmt' | 'pipeline' | 'ocr' | 'transliteration' | 'language-detection' | 'speaker-diarization' | 'audio-language-detection' | 'ner';

export function extractErrorInfo(error: any, service?: ErrorHandlerService): ErrorInfo {
  let errorMessage = 'An unexpected error occurred. Please try again.';
  let errorTitle = 'Error';

  // Check for API error response structure
  if (error?.response?.data) {
    const data = error.response.data;
    
    // Prefer backend message as default when we have one (for unknown error codes)
    const backendMessage = data.detail?.message || data.message;
    if (backendMessage && typeof backendMessage === 'string') {
      errorMessage = backendMessage;
    }
    
    // Handle Pydantic validation errors (detail is an array)
    if (data.detail && Array.isArray(data.detail) && data.detail.length > 0) {
      // Extract error messages from validation errors
      const errorMessages = data.detail
        .filter((err: any) => err.msg)
        .map((err: any) => {
          // Clean up the message - remove "Value error, " prefix if present
          let msg = String(err.msg);
          if (msg.startsWith('Value error, ')) {
            msg = msg.substring('Value error, '.length);
          }
          // Include field location if available
          if (err.loc && Array.isArray(err.loc) && err.loc.length > 0) {
            const fieldPath = err.loc.slice(1).join('.'); // Skip 'body' from loc
            return `${fieldPath ? `${fieldPath}: ` : ''}${msg}`;
          }
          return msg;
        });
      
      if (errorMessages.length > 0) {
        errorMessage = errorMessages.join('; ');
        errorTitle = 'Validation Error';
        return {
          title: errorTitle,
          message: errorMessage,
          showOnlyMessage: true,
        };
      }
    }
    
    // Handle nested detail object with error and message
    if (data.detail && typeof data.detail === 'object' && !Array.isArray(data.detail)) {
      if (data.detail.message) {
        let rawMessage = String(data.detail.message);
        
        // Try to extract nested message from string representations like "{'kind': 'DBError', 'message': 'Error listing service details'}"
        // This handles cases where the message is a stringified dict/object
        try {
          // Check if the message looks like a dict/object string representation
          if (rawMessage.trim().startsWith('{') || rawMessage.trim().startsWith('[')) {
            let extracted = false;
            
            // First, try JSON parsing (replace single quotes with double quotes)
            try {
              const jsonLike = rawMessage.replace(/'/g, '"');
              const parsed = JSON.parse(jsonLike);
              if (parsed && typeof parsed === 'object') {
                // If it has a 'message' property, use that
                if (parsed.message) {
                  errorMessage = String(parsed.message);
                  extracted = true;
                } else if (parsed.error) {
                  errorMessage = String(parsed.error);
                  extracted = true;
                }
              }
            } catch (jsonError) {
              // JSON parsing failed, try regex
            }
            
            // If JSON parsing didn't work, try regex to extract message from Python dict-like string
            if (!extracted) {
              // Pattern matches: 'message': 'value' or "message": "value"
              // Updated pattern to handle more cases including escaped quotes
              const messageMatch = rawMessage.match(/['"]message['"]\s*:\s*['"]([^'"]+)['"]/);
              if (messageMatch && messageMatch[1]) {
                errorMessage = messageMatch[1];
                extracted = true;
              }
            }
            
            // If extraction failed, use the raw message
            if (!extracted) {
              errorMessage = rawMessage;
            }
          } else {
            // Not a dict-like string, use as-is
            errorMessage = rawMessage;
          }
        } catch (e) {
          // Fallback to original message if parsing fails
          errorMessage = rawMessage;
        }
        
        // When we have a structured error with message, show only the message in toast
        // (hide the title/code)
      }
      
      if (data.detail.error) {
        const errorCode = String(data.detail.error).toUpperCase();
        
        // Check for common errors first (apply to all services)
        if (COMMON_ERRORS[errorCode as keyof typeof COMMON_ERRORS]) {
          const commonError = COMMON_ERRORS[errorCode as keyof typeof COMMON_ERRORS];
          errorTitle = commonError.title;
          errorMessage = data.detail.message || commonError.description;
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        // Check for TTS-specific error codes when service is TTS
        if (service === 'tts' && TTS_ERRORS[errorCode as keyof typeof TTS_ERRORS]) {
          const ttsError = TTS_ERRORS[errorCode as keyof typeof TTS_ERRORS];
          errorTitle = ttsError.title;
          errorMessage = data.detail.message || ttsError.description;
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        // Check for NMT-specific error codes when service is NMT
        if (service === 'nmt' && NMT_ERRORS[errorCode as keyof typeof NMT_ERRORS]) {
          const nmtError = NMT_ERRORS[errorCode as keyof typeof NMT_ERRORS];
          errorTitle = nmtError.title;
          // Handle LANGUAGE_PAIR_NOT_SUPPORTED with source/target replacement
          if (errorCode === 'LANGUAGE_PAIR_NOT_SUPPORTED') {
            const source = data.detail.sourceLanguage || data.detail.source || 'source';
            const target = data.detail.targetLanguage || data.detail.target || 'target';
            errorMessage = data.detail.message || nmtError.description.replace('{source}', source).replace('{target}', target);
          } else {
            errorMessage = data.detail.message || nmtError.description;
          }
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        // Check for Pipeline-specific error codes when service is pipeline
        if (service === 'pipeline' && PIPELINE_ERRORS[errorCode as keyof typeof PIPELINE_ERRORS]) {
          const pipelineError = PIPELINE_ERRORS[errorCode as keyof typeof PIPELINE_ERRORS];
          errorTitle = pipelineError.title;
          // Handle S2S_LANGUAGE_PAIR_NOT_SUPPORTED with source/target replacement
          if (errorCode === 'S2S_LANGUAGE_PAIR_NOT_SUPPORTED') {
            const source = data.detail.sourceLanguage || data.detail.source || 'source';
            const target = data.detail.targetLanguage || data.detail.target || 'target';
            errorMessage = data.detail.message || pipelineError.description.replace('{source}', source).replace('{target}', target);
          } else {
            errorMessage = data.detail.message || pipelineError.description;
          }
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        // Check for OCR-specific error codes when service is OCR
        if (service === 'ocr' && OCR_ERRORS[errorCode as keyof typeof OCR_ERRORS]) {
          const ocrError = OCR_ERRORS[errorCode as keyof typeof OCR_ERRORS];
          errorTitle = ocrError.title;
          errorMessage = data.detail.message || ocrError.description;
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        // Check for Transliteration-specific error codes when service is Transliteration
        if (service === 'transliteration' && TRANSLITERATION_ERRORS[errorCode as keyof typeof TRANSLITERATION_ERRORS]) {
          const transliterationError = TRANSLITERATION_ERRORS[errorCode as keyof typeof TRANSLITERATION_ERRORS];
          errorTitle = transliterationError.title;
          errorMessage = data.detail.message || transliterationError.description;
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        // Check for Language Detection-specific error codes when service is Language Detection
        if (service === 'language-detection' && LANGUAGE_DETECTION_ERRORS[errorCode as keyof typeof LANGUAGE_DETECTION_ERRORS]) {
          const languageDetectionError = LANGUAGE_DETECTION_ERRORS[errorCode as keyof typeof LANGUAGE_DETECTION_ERRORS];
          errorTitle = languageDetectionError.title;
          errorMessage = data.detail.message || languageDetectionError.description;
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        // Check for Speaker Diarization-specific error codes when service is Speaker Diarization
        if (service === 'speaker-diarization' && SPEAKER_DIARIZATION_ERRORS[errorCode as keyof typeof SPEAKER_DIARIZATION_ERRORS]) {
          const speakerDiarizationError = SPEAKER_DIARIZATION_ERRORS[errorCode as keyof typeof SPEAKER_DIARIZATION_ERRORS];
          errorTitle = speakerDiarizationError.title;
          errorMessage = data.detail.message || speakerDiarizationError.description;
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        // Check for Audio Language Detection-specific error codes when service is Audio Language Detection
        if (service === 'audio-language-detection' && AUDIO_LANGUAGE_DETECTION_ERRORS[errorCode as keyof typeof AUDIO_LANGUAGE_DETECTION_ERRORS]) {
          const audioLanguageDetectionError = AUDIO_LANGUAGE_DETECTION_ERRORS[errorCode as keyof typeof AUDIO_LANGUAGE_DETECTION_ERRORS];
          errorTitle = audioLanguageDetectionError.title;
          errorMessage = data.detail.message || audioLanguageDetectionError.description;
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        // Check for NER-specific error codes when service is NER
        if (service === 'ner' && NER_ERRORS[errorCode as keyof typeof NER_ERRORS]) {
          const nerError = NER_ERRORS[errorCode as keyof typeof NER_ERRORS];
          errorTitle = nerError.title;
          errorMessage = data.detail.message || nerError.description;
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        // Check for ASR-specific error codes (or when no service / asr)
        if (ASR_ERRORS[errorCode as keyof typeof ASR_ERRORS]) {
          const asrError = ASR_ERRORS[errorCode as keyof typeof ASR_ERRORS];
          errorTitle = asrError.title;
          errorMessage = data.detail.message || asrError.description;
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        // Unknown error code: use backend message (already set above) and format title from code
        if (data.detail.message) {
          errorTitle = formatErrorCode(errorCode);
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        // Format permission denied errors with clear title
        if (errorCode === 'PERMISSION_DENIED' || errorCode.includes('PERMISSION_DENIED')) {
          errorTitle = 'PERMISSION DENIED';
          // If message is not provided, use a default
          if (!data.detail.message) {
            errorMessage = 'You do not have the required permissions to perform this action.';
          }
        } else {
          // For other error codes, format them nicely
          errorTitle = formatErrorCode(errorCode);
        }
      } else if (data.detail.code) {
        const errorCode = String(data.detail.code).toUpperCase();
        
        // Check for common errors first (apply to all services)
        if (COMMON_ERRORS[errorCode as keyof typeof COMMON_ERRORS]) {
          const commonError = COMMON_ERRORS[errorCode as keyof typeof COMMON_ERRORS];
          errorTitle = commonError.title;
          errorMessage = data.detail.message || commonError.description;
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        if (service === 'tts' && TTS_ERRORS[errorCode as keyof typeof TTS_ERRORS]) {
          const ttsError = TTS_ERRORS[errorCode as keyof typeof TTS_ERRORS];
          errorTitle = ttsError.title;
          errorMessage = data.detail.message || ttsError.description;
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        if (service === 'nmt' && NMT_ERRORS[errorCode as keyof typeof NMT_ERRORS]) {
          const nmtError = NMT_ERRORS[errorCode as keyof typeof NMT_ERRORS];
          errorTitle = nmtError.title;
          if (errorCode === 'LANGUAGE_PAIR_NOT_SUPPORTED') {
            const source = data.detail.sourceLanguage || data.detail.source || 'source';
            const target = data.detail.targetLanguage || data.detail.target || 'target';
            errorMessage = data.detail.message || nmtError.description.replace('{source}', source).replace('{target}', target);
          } else {
            errorMessage = data.detail.message || nmtError.description;
          }
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        if (service === 'pipeline' && PIPELINE_ERRORS[errorCode as keyof typeof PIPELINE_ERRORS]) {
          const pipelineError = PIPELINE_ERRORS[errorCode as keyof typeof PIPELINE_ERRORS];
          errorTitle = pipelineError.title;
          if (errorCode === 'S2S_LANGUAGE_PAIR_NOT_SUPPORTED') {
            const source = data.detail.sourceLanguage || data.detail.source || 'source';
            const target = data.detail.targetLanguage || data.detail.target || 'target';
            errorMessage = data.detail.message || pipelineError.description.replace('{source}', source).replace('{target}', target);
          } else {
            errorMessage = data.detail.message || pipelineError.description;
          }
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        if (service === 'ocr' && OCR_ERRORS[errorCode as keyof typeof OCR_ERRORS]) {
          const ocrError = OCR_ERRORS[errorCode as keyof typeof OCR_ERRORS];
          errorTitle = ocrError.title;
          errorMessage = data.detail.message || ocrError.description;
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        if (service === 'transliteration' && TRANSLITERATION_ERRORS[errorCode as keyof typeof TRANSLITERATION_ERRORS]) {
          const transliterationError = TRANSLITERATION_ERRORS[errorCode as keyof typeof TRANSLITERATION_ERRORS];
          errorTitle = transliterationError.title;
          errorMessage = data.detail.message || transliterationError.description;
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        if (service === 'language-detection' && LANGUAGE_DETECTION_ERRORS[errorCode as keyof typeof LANGUAGE_DETECTION_ERRORS]) {
          const languageDetectionError = LANGUAGE_DETECTION_ERRORS[errorCode as keyof typeof LANGUAGE_DETECTION_ERRORS];
          errorTitle = languageDetectionError.title;
          errorMessage = data.detail.message || languageDetectionError.description;
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        if (service === 'speaker-diarization' && SPEAKER_DIARIZATION_ERRORS[errorCode as keyof typeof SPEAKER_DIARIZATION_ERRORS]) {
          const speakerDiarizationError = SPEAKER_DIARIZATION_ERRORS[errorCode as keyof typeof SPEAKER_DIARIZATION_ERRORS];
          errorTitle = speakerDiarizationError.title;
          errorMessage = data.detail.message || speakerDiarizationError.description;
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        if (service === 'audio-language-detection' && AUDIO_LANGUAGE_DETECTION_ERRORS[errorCode as keyof typeof AUDIO_LANGUAGE_DETECTION_ERRORS]) {
          const audioLanguageDetectionError = AUDIO_LANGUAGE_DETECTION_ERRORS[errorCode as keyof typeof AUDIO_LANGUAGE_DETECTION_ERRORS];
          errorTitle = audioLanguageDetectionError.title;
          errorMessage = data.detail.message || audioLanguageDetectionError.description;
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        if (service === 'ner' && NER_ERRORS[errorCode as keyof typeof NER_ERRORS]) {
          const nerError = NER_ERRORS[errorCode as keyof typeof NER_ERRORS];
          errorTitle = nerError.title;
          errorMessage = data.detail.message || nerError.description;
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        if (ASR_ERRORS[errorCode as keyof typeof ASR_ERRORS]) {
          const asrError = ASR_ERRORS[errorCode as keyof typeof ASR_ERRORS];
          errorTitle = asrError.title;
          errorMessage = data.detail.message || asrError.description;
          if (errorCode === 'RATE_LIMIT_EXCEEDED' && data.detail.retryAfter) {
            errorMessage = `Too many requests. Please wait ${data.detail.retryAfter} seconds before trying again.`;
          }
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        if (data.detail.message) {
          errorTitle = formatErrorCode(errorCode);
          return {
            title: errorTitle,
            message: errorMessage,
            showOnlyMessage: true,
          };
        }
        
        if (errorCode === 'PERMISSION_DENIED' || errorCode.includes('PERMISSION_DENIED')) {
          errorTitle = 'PERMISSION DENIED';
        } else {
          errorTitle = formatErrorCode(errorCode);
        }
      }
      
      // Append hint when present (e.g. multi-tenant "set MULTI_TENANT_SERVICE_URL=...")
      if (data.detail.hint && typeof data.detail.hint === 'string') {
        errorMessage = errorMessage + (errorMessage.endsWith('.') ? ' ' : '. ') + data.detail.hint;
      }

      // If we have both code/error and message, show only the message in toast
      if ((data.detail.error || data.detail.code) && data.detail.message) {
        return {
          title: errorTitle,
          message: errorMessage,
          showOnlyMessage: true,
        };
      }
    } 
    // Handle detail as string
    else if (data.detail && typeof data.detail === 'string') {
      errorMessage = data.detail;
    } 
    // Handle message at root level
    else if (data.message) {
      errorMessage = String(data.message);
    }
  }
  // Check for ASR-specific error messages in detail string or message
  const detailStr = typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : '';
  const detailObj = error?.response?.data?.detail;
  const detailMessage = typeof detailObj === 'object' && detailObj !== null && detailObj.message ? String(detailObj.message) : '';
  if (
    error?.response?.data?.detail?.message?.toLowerCase().includes('api key') ||
    error?.response?.data?.detail?.error === 'API_KEY_MISSING' ||
    (error?.response?.data?.detail?.error === 'INVALID_API_KEY' && detailMessage) ||
    error?.message?.toLowerCase().includes('api key') ||
    detailStr.toLowerCase().includes('api key')
  ) {
    if (detailMessage && detailMessage.toLowerCase().includes('api key')) {
      errorMessage = detailMessage; // e.g. "Invalid API key: This key does not have access to ASR."
    } else if (detailStr && detailStr.toLowerCase().includes('api key')) {
      errorMessage = detailStr; // e.g. "Invalid API key"
    } else if (error?.message?.toLowerCase().includes('api key')) {
      errorMessage = error.message; // Preserve message from asrService etc. when thrown as Error(detail.message)
    } else if (!errorMessage || errorMessage === 'An unexpected error occurred. Please try again.') {
      errorMessage = 'API key is required to access this service.';
    }
    return { title: errorTitle, message: errorMessage, showOnlyMessage: true };
  }
  // Handle 500/503 service unavailable (e.g. backend or multi-tenant service down)
  const status = error?.response?.status;
  if ((status === 500 || status === 503) && typeof errorMessage === 'string' && errorMessage.toLowerCase().includes('unavailable')) {
    errorTitle = 'Service Unavailable';
  }
  // Handle 401 authentication errors
  if (status === 401 || error?.status === 401 || error?.message?.includes('401')) {
    errorTitle = 'Authentication Failed';
    if (error?.message?.includes('API key') || error?.message?.includes('api key')) {
      errorMessage = 'API key is required to access this service.';
    } else {
      errorMessage = err.description;
    }
    return {
      title: errorTitle,
      message: errorMessage,
      showOnlyMessage: true,
    };
  }
  
  if (status === 403) {
    const errorCode = String(error?.response?.data?.detail?.error || error?.response?.data?.detail?.code || '').toUpperCase();
    if (errorCode === 'TENANT_SUSPENDED' || errorCode.includes('SUSPENDED')) {
      const err = 'TENANT_SUSPENDED' in serviceErrors ? (serviceErrors as typeof ASR_ERRORS).TENANT_SUSPENDED : ASR_ERRORS.TENANT_SUSPENDED;
      return {
        title: err.title,
        message: err.description,
        showOnlyMessage: true,
      };
    }
    // Check if it's unauthorized access (not permission denied)
    if (errorCode === 'UNAUTHORIZED' || lowerMessage.includes('unauthorized') || lowerMessage.includes('permission')) {
      const err = COMMON_ERRORS.UNAUTHORIZED;
      return {
        title: err.title,
        message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : err.description,
        showOnlyMessage: true,
      };
    }
  }
  // Handle network errors (connection refused, not found, etc.)
  if (error?.code === 'ECONNREFUSED' || error?.code === 'ENOTFOUND' || error?.code === 'ETIMEDOUT' || 
      error?.code === 'ECONNABORTED' || error?.message?.includes('Network Error') || 
      error?.message?.includes('network') || error?.message?.includes('Failed to fetch')) {
    const err = COMMON_ERRORS.NETWORK_ERROR;
    return {
      title: err.title,
      message: err.description,
      showOnlyMessage: true,
    };
  }
  
  // Use error.message only when we didn't get a message from response.data (e.g. avoid overwriting "Invalid API key" with "Request failed with status code 403")
  else if (error?.message && errorMessage === 'An unexpected error occurred. Please try again.') {
    errorMessage = error.message;
  }

  return {
    title: errorTitle,
    message: errorMessage,
    showOnlyMessage: false,
  };
}

/**
 * Formats error codes to readable titles
 * Converts "PERMISSION_DENIED" to "PERMISSION DENIED"
 * Converts "INVALID_API_KEY" to "Invalid API Key"
 */
function formatErrorCode(code: string): string {
  // Handle permission denied specifically
  if (code === 'PERMISSION_DENIED' || code.includes('PERMISSION_DENIED')) {
    return 'PERMISSION DENIED';
  }
  
  // Convert snake_case to Title Case
  return code
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

/**
 * Checks if an error is a permission denied error
 */
export function isPermissionDeniedError(error: any): boolean {
  const errorCode = error?.response?.data?.detail?.error || error?.response?.data?.detail?.code || '';
  return String(errorCode).includes('PERMISSION_DENIED');
}

