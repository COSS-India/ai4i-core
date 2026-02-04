/**
 * Utility functions for handling and formatting API errors
 */

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
export function extractErrorInfo(error: any): ErrorInfo {
  let errorMessage = 'An unexpected error occurred. Please try again.';
  let errorTitle = 'Error';

  // Check for API error response structure
  if (error?.response?.data) {
    const data = error.response.data;
    
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
        const errorCode = String(data.detail.error);
        
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
        const errorCode = String(data.detail.code);
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
  // Handle API key missing or invalid (from backend or when no key set)
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
  // Handle 401 authentication errors
  if (error?.response?.status === 401 || error?.status === 401 || error?.message?.includes('401')) {
    errorTitle = 'Authentication Failed';
    if (error?.message?.includes('API key') || error?.message?.includes('api key')) {
      errorMessage = 'API key is required to access this service.';
    } else if (error?.message?.includes('token') || error?.message?.includes('Token')) {
      errorMessage = 'Your session has expired. Please sign in again.';
    } else {
      errorMessage = 'Authentication failed. Please check your API key and login status, then try again.';
    }
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

