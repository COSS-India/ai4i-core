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
  const messageStr = error?.response?.data?.detail?.message || error?.response?.data?.message || error?.message || '';
  const lowerMessage = String(messageStr).toLowerCase();
  const lowerDetail = detailStr.toLowerCase();
  
  // Check for common errors in message (apply to all services)
  if (lowerMessage.includes('network') && (lowerMessage.includes('error') || lowerMessage.includes('lost') || lowerMessage.includes('connection'))) {
    const commonError = COMMON_ERRORS.NETWORK_ERROR;
    return {
      title: commonError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : commonError.description,
      showOnlyMessage: true,
    };
  }
  
  if (lowerMessage.includes('session') && (lowerMessage.includes('expired') || lowerMessage.includes('invalid'))) {
    const commonError = COMMON_ERRORS.SESSION_EXPIRED;
    return {
      title: commonError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : commonError.description,
      showOnlyMessage: true,
    };
  }
  
  if (lowerMessage.includes('maintenance') || lowerMessage.includes('under maintenance')) {
    const commonError = COMMON_ERRORS.SERVICE_MAINTENANCE;
    return {
      title: commonError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : commonError.description,
      showOnlyMessage: true,
    };
  }
  
  if (lowerMessage.includes('invalid') && (lowerMessage.includes('response') || lowerMessage.includes('format'))) {
    const commonError = COMMON_ERRORS.INVALID_RESPONSE;
    return {
      title: commonError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : commonError.description,
      showOnlyMessage: true,
    };
  }
  
  if (lowerMessage.includes('tenant') && (lowerMessage.includes('invalid') || lowerMessage.includes('not found'))) {
    const commonError = COMMON_ERRORS.INVALID_TENANT;
    return {
      title: commonError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : commonError.description,
      showOnlyMessage: true,
    };
  }
  
  if (lowerMessage.includes('not found') || lowerMessage.includes('resource not found')) {
    const commonError = COMMON_ERRORS.NOT_FOUND;
    return {
      title: commonError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : commonError.description,
      showOnlyMessage: true,
    };
  }
  
  // Check for language not supported
  if (lowerMessage.includes('language') && (lowerMessage.includes('not supported') || lowerMessage.includes('unsupported') || lowerMessage.includes('mismatch'))) {
    const asrError = ASR_ERRORS.LANGUAGE_NOT_SUPPORTED;
    return {
      title: asrError.title,
      message: asrError.description,
      showOnlyMessage: true,
    };
  }
  
  // Check for poor audio quality
  if (lowerMessage.includes('audio quality') || lowerMessage.includes('poor quality') || lowerMessage.includes('low quality') || 
      lowerMessage.includes('unclear') || lowerMessage.includes('noise') || lowerMessage.includes('too poor')) {
    const asrError = ASR_ERRORS.POOR_AUDIO_QUALITY;
    return {
      title: asrError.title,
      message: asrError.description,
      showOnlyMessage: true,
    };
  }
  
  // Check for model unavailable
  if (lowerMessage.includes('model') && (lowerMessage.includes('unavailable') || lowerMessage.includes('not available') || 
      lowerMessage.includes('not found') || lowerMessage.includes('does not exist'))) {
    const asrError = ASR_ERRORS.MODEL_UNAVAILABLE;
    return {
      title: asrError.title,
      message: asrError.description,
      showOnlyMessage: true,
    };
  }
  
  // TTS-specific: voice not available
  if (service === 'tts' && (lowerMessage.includes('voice') && (lowerMessage.includes('not available') || lowerMessage.includes('unavailable') || lowerMessage.includes('not found')))) {
    const ttsError = TTS_ERRORS.VOICE_NOT_AVAILABLE;
    return {
      title: ttsError.title,
      message: ttsError.description,
      showOnlyMessage: true,
    };
  }
  
  // TTS-specific: language mismatch
  if (service === 'tts' && (lowerMessage.includes('language') && (lowerMessage.includes('mismatch') || lowerMessage.includes('doesn\'t match') || lowerMessage.includes('does not match')))) {
    const ttsError = TTS_ERRORS.LANGUAGE_MISMATCH;
    return {
      title: ttsError.title,
      message: ttsError.description,
      showOnlyMessage: true,
    };
  }
  
  // NMT-specific: language pair not supported
  if (service === 'nmt' && (lowerMessage.includes('language pair') || lowerMessage.includes('translation') && (lowerMessage.includes('not supported') || lowerMessage.includes('unsupported')))) {
    const nmtError = NMT_ERRORS.LANGUAGE_PAIR_NOT_SUPPORTED;
    // Try to extract source/target from message or use defaults
    const sourceMatch = lowerMessage.match(/from\s+([a-z]+)/i) || lowerMessage.match(/source[:\s]+([a-z]+)/i);
    const targetMatch = lowerMessage.match(/to\s+([a-z]+)/i) || lowerMessage.match(/target[:\s]+([a-z]+)/i);
    const source = sourceMatch?.[1] || error?.response?.data?.detail?.sourceLanguage || error?.response?.data?.detail?.source || 'source';
    const target = targetMatch?.[1] || error?.response?.data?.detail?.targetLanguage || error?.response?.data?.detail?.target || 'target';
    const message = nmtError.description.replace('{source}', source).replace('{target}', target);
    return {
      title: nmtError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : message,
      showOnlyMessage: true,
    };
  }
  
  // NMT-specific: translation failed
  if (service === 'nmt' && (lowerMessage.includes('translation') && (lowerMessage.includes('failed') || lowerMessage.includes('error')))) {
    const nmtError = NMT_ERRORS.TRANSLATION_FAILED;
    return {
      title: nmtError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : nmtError.description,
      showOnlyMessage: true,
    };
  }
  
  // Pipeline-specific: ASR processing failed
  if (service === 'pipeline' && (lowerMessage.includes('asr') || lowerMessage.includes('speech recognition')) && (lowerMessage.includes('failed') || lowerMessage.includes('error'))) {
    const pipelineError = PIPELINE_ERRORS.ASR_FAILED;
    return {
      title: pipelineError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : pipelineError.description,
      showOnlyMessage: true,
    };
  }
  
  // Pipeline-specific: Translation failed
  if (service === 'pipeline' && (lowerMessage.includes('translation') && (lowerMessage.includes('failed') || lowerMessage.includes('error')))) {
    const pipelineError = PIPELINE_ERRORS.TRANSLATION_FAILED;
    return {
      title: pipelineError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : pipelineError.description,
      showOnlyMessage: true,
    };
  }
  
  // Pipeline-specific: TTS generation failed
  if (service === 'pipeline' && (lowerMessage.includes('tts') || lowerMessage.includes('speech generation') || lowerMessage.includes('audio generation')) && (lowerMessage.includes('failed') || lowerMessage.includes('error'))) {
    const pipelineError = PIPELINE_ERRORS.TTS_FAILED;
    return {
      title: pipelineError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : pipelineError.description,
      showOnlyMessage: true,
    };
  }
  
  // Pipeline-specific: Pipeline timeout
  if (service === 'pipeline' && (lowerMessage.includes('timeout') || lowerMessage.includes('timed out'))) {
    const pipelineError = PIPELINE_ERRORS.PIPELINE_TIMEOUT;
    return {
      title: pipelineError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : pipelineError.description,
      showOnlyMessage: true,
    };
  }
  
  // Pipeline-specific: Language pair not supported (S2S)
  if (service === 'pipeline' && (lowerMessage.includes('language pair') || lowerMessage.includes('speech-to-speech') || lowerMessage.includes('translation')) && (lowerMessage.includes('not supported') || lowerMessage.includes('unsupported'))) {
    const pipelineError = PIPELINE_ERRORS.S2S_LANGUAGE_PAIR_NOT_SUPPORTED;
    const sourceMatch = lowerMessage.match(/from\s+([a-z]+)/i) || lowerMessage.match(/source[:\s]+([a-z]+)/i);
    const targetMatch = lowerMessage.match(/to\s+([a-z]+)/i) || lowerMessage.match(/target[:\s]+([a-z]+)/i);
    const source = sourceMatch?.[1] || error?.response?.data?.detail?.sourceLanguage || error?.response?.data?.detail?.source || 'source';
    const target = targetMatch?.[1] || error?.response?.data?.detail?.targetLanguage || error?.response?.data?.detail?.target || 'target';
    const message = pipelineError.description.replace('{source}', source).replace('{target}', target);
    return {
      title: pipelineError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : message,
      showOnlyMessage: true,
    };
  }
  
  // OCR-specific: language mismatch
  if (service === 'ocr' && (lowerMessage.includes('language') && (lowerMessage.includes('mismatch') || lowerMessage.includes('doesn\'t match') || lowerMessage.includes('does not match')))) {
    const ocrError = OCR_ERRORS.LANGUAGE_MISMATCH;
    return {
      title: ocrError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : ocrError.description,
      showOnlyMessage: true,
    };
  }
  
  // OCR-specific: no text detected
  if (service === 'ocr' && (lowerMessage.includes('no text') || lowerMessage.includes('text not detected') || lowerMessage.includes('no text found'))) {
    const ocrError = OCR_ERRORS.NO_TEXT_DETECTED;
    return {
      title: ocrError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : ocrError.description,
      showOnlyMessage: true,
    };
  }
  
  // OCR-specific: text too blurry
  if (service === 'ocr' && (lowerMessage.includes('blurry') || lowerMessage.includes('blur') || lowerMessage.includes('unclear') || lowerMessage.includes('low quality'))) {
    const ocrError = OCR_ERRORS.TEXT_TOO_BLURRY;
    return {
      title: ocrError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : ocrError.description,
      showOnlyMessage: true,
    };
  }
  
  // OCR-specific: image resolution low
  if (service === 'ocr' && (lowerMessage.includes('resolution') && (lowerMessage.includes('low') || lowerMessage.includes('too low')))) {
    const ocrError = OCR_ERRORS.IMAGE_RESOLUTION_LOW;
    return {
      title: ocrError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : ocrError.description,
      showOnlyMessage: true,
    };
  }
  
  // Transliteration-specific: language pair not supported
  if (service === 'transliteration' && (lowerMessage.includes('language pair') || lowerMessage.includes('transliteration')) && (lowerMessage.includes('not supported') || lowerMessage.includes('unsupported'))) {
    const transliterationError = TRANSLITERATION_ERRORS.LANGUAGE_PAIR_NOT_SUPPORTED;
    return {
      title: transliterationError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : transliterationError.description,
      showOnlyMessage: true,
    };
  }
  
  // Transliteration-specific: script mismatch
  if (service === 'transliteration' && (lowerMessage.includes('script') && (lowerMessage.includes('mismatch') || lowerMessage.includes('doesn\'t match') || lowerMessage.includes('does not match')))) {
    const transliterationError = TRANSLITERATION_ERRORS.SCRIPT_MISMATCH;
    return {
      title: transliterationError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : transliterationError.description,
      showOnlyMessage: true,
    };
  }
  
  // Transliteration-specific: processing failed
  if (service === 'transliteration' && (lowerMessage.includes('transliteration') && (lowerMessage.includes('failed') || lowerMessage.includes('error')))) {
    const transliterationError = TRANSLITERATION_ERRORS.PROCESSING_FAILED;
    return {
      title: transliterationError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : transliterationError.description,
      showOnlyMessage: true,
    };
  }
  
  // Language Detection-specific: detection failed
  if (service === 'language-detection' && (lowerMessage.includes('detect') || lowerMessage.includes('detection')) && (lowerMessage.includes('failed') || lowerMessage.includes('cannot') || lowerMessage.includes('unable'))) {
    const languageDetectionError = LANGUAGE_DETECTION_ERRORS.DETECTION_FAILED;
    return {
      title: languageDetectionError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : languageDetectionError.description,
      showOnlyMessage: true,
    };
  }
  
  // Speaker Diarization-specific: no speakers detected
  if (service === 'speaker-diarization' && (lowerMessage.includes('no speaker') || lowerMessage.includes('no speakers') || lowerMessage.includes('speaker not detected'))) {
    const speakerDiarizationError = SPEAKER_DIARIZATION_ERRORS.NO_SPEAKERS_DETECTED;
    return {
      title: speakerDiarizationError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : speakerDiarizationError.description,
      showOnlyMessage: true,
    };
  }
  
  // Speaker Diarization-specific: audio quality poor
  if (service === 'speaker-diarization' && (lowerMessage.includes('audio quality') || lowerMessage.includes('poor quality') || lowerMessage.includes('low quality') || lowerMessage.includes('quality too low'))) {
    const speakerDiarizationError = SPEAKER_DIARIZATION_ERRORS.AUDIO_QUALITY_POOR;
    return {
      title: speakerDiarizationError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : speakerDiarizationError.description,
      showOnlyMessage: true,
    };
  }
  
  // Audio Language Detection-specific: no speech detected
  if (service === 'audio-language-detection' && (lowerMessage.includes('no speech') || lowerMessage.includes('speech not detected'))) {
    const audioLanguageDetectionError = AUDIO_LANGUAGE_DETECTION_ERRORS.NO_SPEECH_DETECTED;
    return {
      title: audioLanguageDetectionError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : audioLanguageDetectionError.description,
      showOnlyMessage: true,
    };
  }
  
  // Audio Language Detection-specific: detection failed
  if (service === 'audio-language-detection' && (lowerMessage.includes('detect') || lowerMessage.includes('detection')) && (lowerMessage.includes('failed') || lowerMessage.includes('cannot') || lowerMessage.includes('unable'))) {
    const audioLanguageDetectionError = AUDIO_LANGUAGE_DETECTION_ERRORS.DETECTION_FAILED;
    return {
      title: audioLanguageDetectionError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : audioLanguageDetectionError.description,
      showOnlyMessage: true,
    };
  }
  
  // Audio Language Detection-specific: confidence too low
  if (service === 'audio-language-detection' && (lowerMessage.includes('confidence') && (lowerMessage.includes('too low') || lowerMessage.includes('low')))) {
    const audioLanguageDetectionError = AUDIO_LANGUAGE_DETECTION_ERRORS.CONFIDENCE_TOO_LOW;
    return {
      title: audioLanguageDetectionError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : audioLanguageDetectionError.description,
      showOnlyMessage: true,
    };
  }
  
  // Audio Language Detection-specific: audio quality poor
  if (service === 'audio-language-detection' && (lowerMessage.includes('audio quality') || lowerMessage.includes('poor quality') || lowerMessage.includes('low quality') || lowerMessage.includes('quality too low'))) {
    const audioLanguageDetectionError = AUDIO_LANGUAGE_DETECTION_ERRORS.AUDIO_QUALITY_POOR;
    return {
      title: audioLanguageDetectionError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : audioLanguageDetectionError.description,
      showOnlyMessage: true,
    };
  }
  
  // NER-specific: language mismatch
  if (service === 'ner' && (lowerMessage.includes('language') && (lowerMessage.includes('mismatch') || lowerMessage.includes('doesn\'t match') || lowerMessage.includes('does not match')))) {
    const nerError = NER_ERRORS.LANGUAGE_MISMATCH;
    return {
      title: nerError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : nerError.description,
      showOnlyMessage: true,
    };
  }
  
  // NER-specific: no entities found
  if (service === 'ner' && (lowerMessage.includes('no entit') || lowerMessage.includes('no entities') || lowerMessage.includes('entity not found'))) {
    const nerError = NER_ERRORS.NO_ENTITIES_FOUND;
    return {
      title: nerError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : nerError.description,
      showOnlyMessage: true,
    };
  }
  
  // NER-specific: processing failed
  if (service === 'ner' && (lowerMessage.includes('entity recognition') || lowerMessage.includes('ner')) && (lowerMessage.includes('failed') || lowerMessage.includes('error'))) {
    const nerError = NER_ERRORS.PROCESSING_FAILED;
    return {
      title: nerError.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : nerError.description,
      showOnlyMessage: true,
    };
  }
  
  // Handle API key missing or invalid (from backend or when no key set)
  if (
    lowerMessage.includes('api key') ||
    error?.response?.data?.detail?.error === 'API_KEY_MISSING' ||
    lowerDetail.includes('api key')
  ) {
    if (lowerDetail.includes('invalid') && lowerDetail.includes('api key')) {
      errorMessage = detailStr; // e.g. "Invalid API key"
    } else if (!errorMessage || errorMessage === 'An unexpected error occurred. Please try again.') {
      errorMessage = 'API key is required to access this service.';
    }
    return { title: errorTitle, message: errorMessage, showOnlyMessage: true };
  }
  // Handle HTTP status codes (use TTS, NMT, Pipeline, OCR, Transliteration, Language Detection, Speaker Diarization, Audio Language Detection, NER, or ASR messages based on service)
  const status = error?.response?.status || error?.status;
  const serviceErrors = service === 'tts' ? TTS_ERRORS 
    : service === 'nmt' ? NMT_ERRORS 
    : service === 'pipeline' ? PIPELINE_ERRORS 
    : service === 'ocr' ? OCR_ERRORS 
    : service === 'transliteration' ? TRANSLITERATION_ERRORS 
    : service === 'language-detection' ? LANGUAGE_DETECTION_ERRORS 
    : service === 'speaker-diarization' ? SPEAKER_DIARIZATION_ERRORS 
    : service === 'audio-language-detection' ? AUDIO_LANGUAGE_DETECTION_ERRORS 
    : service === 'ner' ? NER_ERRORS 
    : ASR_ERRORS;
  
  // Handle common HTTP status codes first (apply to all services)
  if (status === 500) {
    const err = COMMON_ERRORS.INTERNAL_SERVER_ERROR;
    return {
      title: err.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : err.description,
      showOnlyMessage: true,
    };
  }
  
  if (status === 502 || status === 504) {
    const err = COMMON_ERRORS.GATEWAY_TIMEOUT;
    return {
      title: err.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : err.description,
      showOnlyMessage: true,
    };
  }
  
  if (status === 404) {
    const err = COMMON_ERRORS.NOT_FOUND;
    return {
      title: err.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : err.description,
      showOnlyMessage: true,
    };
  }
  
  if (status === 503) {
    const err = serviceErrors.SERVICE_UNAVAILABLE;
    return {
      title: err.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : err.description,
      showOnlyMessage: true,
    };
  }
  
  if (status === 429) {
    const retryAfter = error?.response?.headers?.['retry-after'] || error?.response?.headers?.['Retry-After'];
    const err = serviceErrors.RATE_LIMIT_EXCEEDED;
    const message: string = retryAfter
      ? `Too many requests. Please wait ${retryAfter} seconds before trying again.`
      : err.description;
    return {
      title: err.title,
      message,
      showOnlyMessage: true,
    };
  }
  
  if (status === 408 || error?.code === 'ECONNABORTED' || error?.message?.toLowerCase().includes('timeout')) {
    const err = service === 'tts' ? TTS_ERRORS.PROCESSING_FAILED 
      : service === 'nmt' ? NMT_ERRORS.TRANSLATION_FAILED 
      : service === 'pipeline' ? PIPELINE_ERRORS.PIPELINE_TIMEOUT 
      : ASR_ERRORS.PROCESSING_TIMEOUT;
    return {
      title: err.title,
      message: err.description,
      showOnlyMessage: true,
    };
  }
  
  if (status === 402) {
    const err = serviceErrors.QUOTA_EXCEEDED;
    return {
      title: err.title,
      message: err.description,
      showOnlyMessage: true,
    };
  }
  
  if (status === 400 && !errorMessage.includes('API key')) {
    const err = 'INVALID_REQUEST' in serviceErrors ? (serviceErrors as typeof ASR_ERRORS).INVALID_REQUEST : ASR_ERRORS.INVALID_REQUEST;
    return {
      title: err.title,
      message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : err.description,
      showOnlyMessage: true,
    };
  }
  
  if (status === 401 || error?.status === 401 || error?.message?.includes('401')) {
    // Check if it's a session expiration vs authentication failure
    if (error?.message?.includes('session') || error?.message?.includes('expired') || error?.message?.includes('token') || error?.message?.includes('Token')) {
      const err = COMMON_ERRORS.SESSION_EXPIRED;
      return {
        title: err.title,
        message: errorMessage !== 'An unexpected error occurred. Please try again.' ? errorMessage : err.description,
        showOnlyMessage: true,
      };
    }
    // Otherwise treat as authentication failure
    const err = 'AUTH_FAILED' in serviceErrors ? (serviceErrors as typeof ASR_ERRORS).AUTH_FAILED : ASR_ERRORS.AUTH_FAILED;
    errorTitle = err.title;
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

