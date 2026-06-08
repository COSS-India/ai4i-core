// Shared helpers for pipeline audio input hooks

import {
  MAX_AUDIO_FILE_SIZE,
  MAX_RECORDING_DURATION,
  MIN_RECORDING_DURATION,
} from "../../config/constants";

export function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    const timeout = setTimeout(() => {
      reader.abort();
      reject(new Error("UPLOAD_TIMEOUT"));
    }, 30000);

    reader.onloadend = () => {
      clearTimeout(timeout);
      const result = reader.result as string;
      const base64Data = result.split(",")[1];
      if (!base64Data) {
        reject(new Error("INVALID_FILE"));
      } else {
        resolve(base64Data);
      }
    };
    reader.onerror = () => {
      clearTimeout(timeout);
      reject(new Error("INVALID_FILE"));
    };
    reader.readAsDataURL(blob);
  });
}

export function inferAudioFormatFromFile(file: File): string {
  const name = file.name.toLowerCase();
  if (name.endsWith(".mp3") || file.type === "audio/mpeg" || file.type === "audio/mp3") {
    return "mp3";
  }
  return "wav";
}

export function validateAudioDuration(
  file: File
): Promise<{ isValid: boolean; duration: number; error?: string }> {
  return new Promise((resolve) => {
    const audio = new Audio();
    const url = URL.createObjectURL(file);

    const timeout = setTimeout(() => {
      URL.revokeObjectURL(url);
      resolve({ isValid: false, duration: 0, error: "UPLOAD_TIMEOUT" });
    }, 10000);

    audio.addEventListener("loadedmetadata", () => {
      clearTimeout(timeout);
      URL.revokeObjectURL(url);
      const duration = audio.duration;

      if (duration < MIN_RECORDING_DURATION) {
        resolve({ isValid: false, duration, error: "AUDIO_TOO_SHORT" });
      } else if (duration > MAX_RECORDING_DURATION) {
        resolve({ isValid: false, duration, error: "AUDIO_TOO_LONG" });
      } else if (isNaN(duration) || duration === 0) {
        resolve({ isValid: false, duration, error: "EMPTY_AUDIO_FILE" });
      } else {
        resolve({ isValid: true, duration });
      }
    });

    audio.addEventListener("error", () => {
      clearTimeout(timeout);
      URL.revokeObjectURL(url);
      resolve({ isValid: false, duration: 0, error: "INVALID_FILE" });
    });

    audio.src = url;
  });
}

export function isSupportedAudioFile(file: File): boolean {
  if (file.size > MAX_AUDIO_FILE_SIZE) return false;
  const isMP3 =
    file.type === "audio/mpeg" ||
    file.type === "audio/mp3" ||
    file.name.toLowerCase().endsWith(".mp3");
  const isWAV =
    file.type === "audio/wav" ||
    file.type === "audio/wave" ||
    file.type === "audio/x-wav" ||
    file.name.toLowerCase().endsWith(".wav");
  return isMP3 || isWAV;
}
