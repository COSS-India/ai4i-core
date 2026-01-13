/**
 * Utility functions for handling and formatting API errors
 */

export interface ErrorInfo {
  title: string;
  message: string;
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
    
    // Handle nested detail object with error and message
    if (data.detail && typeof data.detail === 'object' && !Array.isArray(data.detail)) {
      if (data.detail.message) {
        errorMessage = String(data.detail.message);
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
  // Handle 401 authentication errors
  else if (error?.response?.status === 401 || error?.status === 401 || error?.message?.includes('401')) {
    errorTitle = 'Authentication Failed';
    if (error?.message?.includes('API key') || error?.message?.includes('api key')) {
      errorMessage = 'API key is missing or invalid. Please set a valid API key in your profile.';
    } else if (error?.message?.includes('token') || error?.message?.includes('Token')) {
      errorMessage = 'Your session has expired. Please sign in again.';
    } else {
      errorMessage = 'Authentication failed. Please check your API key and login status, then try again.';
    }
  } 
  // Handle standard error message
  else if (error?.message) {
    errorMessage = error.message;
  }

  return {
    title: errorTitle,
    message: errorMessage,
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

