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

/**
 * Convert WebM audio blob to WAV format
 * @param webmBlob - WebM audio blob
 * @param targetSampleRate - Target sample rate (default: 16000)
 * @returns Promise that resolves to WAV blob
 */
export const convertWebmToWav = async (webmBlob: Blob, targetSampleRate: number = 16000): Promise<Blob> => {
  try {
    // Create audio context
    const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
    
    // Decode WebM audio
    const arrayBuffer = await webmBlob.arrayBuffer();
    let audioBuffer: AudioBuffer;
    
    try {
      audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
    } catch (decodeError) {
      // If decodeAudioData fails, throw error instead of silently returning WebM
      audioContext.close();
      throw new Error(`Failed to decode WebM audio: ${decodeError}`);
    }
    
    // Get audio data
    let sampleRate = audioBuffer.sampleRate;
    const numChannels = audioBuffer.numberOfChannels;
    const length = audioBuffer.length;
    
    // Convert multi-channel to mono if needed, or use first channel
    let samples = numChannels > 1 ? new Float32Array(length) : audioBuffer.getChannelData(0);
    
    if (numChannels > 1) {
      // Mix down to mono
      const channels: Float32Array[] = [];
      for (let i = 0; i < numChannels; i++) {
        channels.push(audioBuffer.getChannelData(i));
      }
      for (let i = 0; i < length; i++) {
        let sum = 0;
        for (let ch = 0; ch < numChannels; ch++) {
          sum += channels[ch][i];
        }
        samples[i] = sum / numChannels;
      }
    }
    
    // Resample to target sample rate if needed
    if (sampleRate !== targetSampleRate) {
      const resampleRatio = targetSampleRate / sampleRate;
      const newLength = Math.floor(samples.length * resampleRatio);
      const resampledSamples = new Float32Array(newLength);
      
      // Simple linear interpolation resampling
      for (let i = 0; i < newLength; i++) {
        const srcIndex = i / resampleRatio;
        const srcIndexFloor = Math.floor(srcIndex);
        const srcIndexCeil = Math.min(srcIndexFloor + 1, samples.length - 1);
        const t = srcIndex - srcIndexFloor;
        resampledSamples[i] = samples[srcIndexFloor] * (1 - t) + samples[srcIndexCeil] * t;
      }
      
      samples = resampledSamples;
      sampleRate = targetSampleRate;
    }
    
    // Convert float32 samples to int16 PCM
    const pcmData = new Int16Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    
    // Create WAV file header
    const wavHeader = new ArrayBuffer(44);
    const view = new DataView(wavHeader);
    
    // RIFF header
    const writeString = (offset: number, string: string) => {
      for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
      }
    };
    
    writeString(0, 'RIFF');
    view.setUint32(4, 36 + pcmData.length * 2, true); // File size - 8
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true); // fmt chunk size
    view.setUint16(20, 1, true); // Audio format (1 = PCM)
    view.setUint16(22, 1, true); // Number of channels (mono)
    view.setUint32(24, sampleRate, true); // Sample rate
    view.setUint32(28, sampleRate * 2, true); // Byte rate
    view.setUint16(32, 2, true); // Block align
    view.setUint16(34, 16, true); // Bits per sample
    writeString(36, 'data');
    view.setUint32(40, pcmData.length * 2, true); // Data chunk size
    
    // Combine header and PCM data
    const wavData = new Uint8Array(wavHeader.byteLength + pcmData.length * 2);
    wavData.set(new Uint8Array(wavHeader), 0);
    
    // Convert Int16Array to bytes (little-endian)
    const pcmBytes = new Uint8Array(pcmData.buffer);
    wavData.set(pcmBytes, wavHeader.byteLength);
    
    // Create WAV blob
    const wavBlob = new Blob([wavData], { type: 'audio/wav' });
    
    // Cleanup
    audioContext.close();
    
    return wavBlob;
  } catch (error) {
    console.error('Error converting WebM to WAV:', error);
    // Don't silently fallback - throw error so caller knows conversion failed
    throw error;
  }
};

/**
 * Convert WebM audio blob to MP3 format (deprecated - use convertWebmToWav instead)
 * @param webmBlob - WebM audio blob
 * @returns Promise that resolves to MP3 blob
 * @deprecated Use convertWebmToWav instead for better performance
 */
export const convertWebmToMp3 = async (webmBlob: Blob): Promise<Blob> => {
  try {
    // Create audio context
    const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
    
    // Decode WebM audio
    const arrayBuffer = await webmBlob.arrayBuffer();
    let audioBuffer: AudioBuffer;
    
    try {
      audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
    } catch (decodeError) {
      // If decodeAudioData fails (e.g., in Firefox), return original WebM blob
      // decodeAudioData may not support WebM in all browsers
      console.warn('decodeAudioData failed, returning original WebM blob:', decodeError);
      audioContext.close();
      return webmBlob;
    }
    
    // Get audio data
    const sampleRate = audioBuffer.sampleRate;
    const numChannels = audioBuffer.numberOfChannels;
    const length = audioBuffer.length;
    
    // Convert multi-channel to mono if needed, or use first channel
    const samples = numChannels > 1 ? new Float32Array(length) : audioBuffer.getChannelData(0);
    
    if (numChannels > 1) {
      // Mix down to mono
      const channels: Float32Array[] = [];
      for (let i = 0; i < numChannels; i++) {
        channels.push(audioBuffer.getChannelData(i));
      }
      for (let i = 0; i < length; i++) {
        let sum = 0;
        for (let ch = 0; ch < numChannels; ch++) {
          sum += channels[ch][i];
        }
        samples[i] = sum / numChannels;
      }
    }
    
    // Convert float32 samples to int16 PCM
    const pcmData = new Int16Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    
    // Use lamejs for MP3 encoding (loaded from CDN)
    // Dynamically load lamejs if not available
    if (!(window as any).lamejs) {
      await new Promise<void>((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/lamejs@1.2.1/lame.min.js';
        script.onload = () => resolve();
        script.onerror = () => reject(new Error('Failed to load lamejs'));
        document.head.appendChild(script);
      });
    }
    
    const lamejs = (window as any).lamejs;
    const mp3encoder = new lamejs.Mp3Encoder(1, sampleRate, 128); // Always mono
    
    // Encode PCM to MP3
    const sampleBlockSize = 1152;
    const mp3Data: Uint8Array[] = [];
    
    for (let i = 0; i < pcmData.length; i += sampleBlockSize) {
      const sampleChunk = pcmData.subarray(i, i + sampleBlockSize);
      const mp3buf = mp3encoder.encodeBuffer(sampleChunk);
      if (mp3buf && mp3buf.length > 0) {
        // Convert to Uint8Array if it's not already
        const buf = mp3buf instanceof Uint8Array ? mp3buf : new Uint8Array(mp3buf);
        mp3Data.push(buf);
      }
    }
    
    // Flush remaining data
    const mp3buf = mp3encoder.flush();
    if (mp3buf && mp3buf.length > 0) {
      // Convert to Uint8Array if it's not already
      const buf = mp3buf instanceof Uint8Array ? mp3buf : new Uint8Array(mp3buf);
      mp3Data.push(buf);
    }
    
    // Combine all MP3 chunks into a single Uint8Array
    const totalLength = mp3Data.reduce((sum, arr) => sum + arr.length, 0);
    const combinedMp3Data = new Uint8Array(totalLength);
    let offset = 0;
    for (const chunk of mp3Data) {
      combinedMp3Data.set(chunk, offset);
      offset += chunk.length;
    }
    
    // Create MP3 blob
    const mp3Blob = new Blob([combinedMp3Data], { type: 'audio/mpeg' });
    
    // Cleanup
    audioContext.close();
    
    return mp3Blob;
  } catch (error) {
    console.error('Error converting WebM to MP3:', error);
    // Fallback: return original WebM blob if conversion fails
    console.warn('Falling back to original WebM format');
    return webmBlob;
  }
};