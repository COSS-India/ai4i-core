// Utility helper functions for Simple UI

/**
 * Get word count from text
 * @param text - Input text
 * @returns Number of words
 */
export const getWordCount = (text: string): number => {
  if (!text || typeof text !== 'string') return 0;
  return text.trim().split(/\s+/).filter(word => word.length > 0).length;
};

/**
 * Format duration in seconds to MM:SS or HH:MM:SS format
 * @param seconds - Duration in seconds
 * @returns Formatted duration string
 */
export const formatDuration = (seconds: number): string => {
  if (!seconds || seconds < 0 || isNaN(seconds)) return '00:00';
  
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  
  if (hours > 0) {
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
  
  return `${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};

/**
 * Format file size in bytes to human readable format
 * @param bytes - File size in bytes
 * @returns Formatted file size string
 */
export const formatFileSize = (bytes: number): string => {
  if (!bytes || bytes < 0) return '0 B';
  
  const kb = bytes / 1024;
  const mb = kb / 1024;
  const gb = mb / 1024;
  
  if (gb >= 1) {
    return `${gb.toFixed(2)} GB`;
  } else if (mb >= 1) {
    return `${mb.toFixed(2)} MB`;
  } else if (kb >= 1) {
    return `${kb.toFixed(2)} KB`;
  }
  
  return `${bytes} B`;
};

/**
 * Convert base64 string to Blob
 * @param base64 - Base64 encoded string
 * @param mimeType - MIME type of the blob
 * @returns Blob object
 */
export const base64ToBlob = (base64: string, mimeType: string = 'audio/wav'): Blob => {
  try {
    const byteCharacters = atob(base64);
    const byteNumbers = new Array(byteCharacters.length);
    
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i);
    }
    
    const byteArray = new Uint8Array(byteNumbers);
    return new Blob([byteArray], { type: mimeType });
  } catch (error) {
    console.error('Error converting base64 to blob:', error);
    return new Blob();
  }
};

/**
 * Download file from blob
 * @param blob - Blob object to download
 * @param filename - Name of the file
 */
export const downloadFile = (blob: Blob, filename: string): void => {
  try {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    
    // Trigger download
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    // Cleanup
    URL.revokeObjectURL(url);
  } catch (error) {
    console.error('Error downloading file:', error);
  }
};

/**
 * Truncate text to specified length with ellipsis
 * @param text - Input text
 * @param maxLength - Maximum length
 * @returns Truncated text
 */
export const truncateText = (text: string, maxLength: number): string => {
  if (!text || text.length <= maxLength) return text;
  return text.substring(0, maxLength) + '...';
};

/**
 * Format timestamp to readable date/time string
 * @param timestamp - Unix timestamp in milliseconds
 * @returns Formatted date/time string
 */
export const formatTimestamp = (timestamp: number): string => {
  try {
    return new Date(timestamp).toLocaleString();
  } catch (error) {
    console.error('Error formatting timestamp:', error);
    return 'Invalid Date';
  }
};

/**
 * Validate email format
 * @param email - Email string to validate
 * @returns True if valid email format
 */
export const isValidEmail = (email: string): boolean => {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
};

/**
 * Generate random string of specified length
 * @param length - Length of the string
 * @returns Random string
 */
export const generateRandomString = (length: number = 8): string => {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
};

/**
 * Debounce function to limit function calls
 * @param func - Function to debounce
 * @param wait - Wait time in milliseconds
 * @returns Debounced function
 */
export const debounce = <T extends (...args: any[]) => any>(
  func: T,
  wait: number
): ((...args: Parameters<T>) => void) => {
  let timeout: NodeJS.Timeout;
  return (...args: Parameters<T>) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
};

/**
 * Throttle function to limit function calls
 * @param func - Function to throttle
 * @param limit - Time limit in milliseconds
 * @returns Throttled function
 */
export const throttle = <T extends (...args: any[]) => any>(
  func: T,
  limit: number
): ((...args: Parameters<T>) => void) => {
  let inThrottle: boolean;
  return (...args: Parameters<T>) => {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limit);
    }
  };
};