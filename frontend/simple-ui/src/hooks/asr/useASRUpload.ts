// File upload validation and processing for ASR

import { useCallback } from "react";
import {
  MAX_AUDIO_FILE_SIZE,
  MAX_RECORDING_DURATION,
  MIN_RECORDING_DURATION,
  UPLOAD_ERRORS,
} from "../../config/constants";
import type { AsrToast } from "./shared";

export interface UseASRUploadOptions {
  toast: AsrToast;
  onError: (message: string | null) => void;
  onFileReady: (base64: string) => void;
  resetResultState: () => void;
}

export function useASRUpload({
  toast,
  onError,
  onFileReady,
  resetResultState,
}: UseASRUploadOptions) {
  const validateAudioDuration = (
    file: File
  ): Promise<{ isValid: boolean; duration: number; error?: string }> => {
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
  };

  const handleFileUpload = useCallback(
    (file: File) => {
      if (!file) {
        const err = UPLOAD_ERRORS.NO_FILE_SELECTED;
        toast({
          title: err.title,
          description: err.description,
          status: "error",
          duration: 3000,
          isClosable: true,
        });
        onError(err.description);
        return;
      }

      if (file.size > MAX_AUDIO_FILE_SIZE) {
        const err = UPLOAD_ERRORS.FILE_TOO_LARGE;
        toast({
          title: err.title,
          description: err.description,
          status: "error",
          duration: 3000,
          isClosable: true,
        });
        onError(err.description);
        return;
      }

      const isMP3 =
        file.type === "audio/mpeg" ||
        file.type === "audio/mp3" ||
        file.name.toLowerCase().endsWith(".mp3");
      const isWAV =
        file.type === "audio/wav" ||
        file.type === "audio/wave" ||
        file.type === "audio/x-wav" ||
        file.name.toLowerCase().endsWith(".wav");

      if (!isMP3 && !isWAV) {
        const err = UPLOAD_ERRORS.UNSUPPORTED_FORMAT;
        toast({
          title: err.title,
          description: err.description,
          status: "error",
          duration: 3000,
          isClosable: true,
        });
        onError(err.description);
        return;
      }

      validateAudioDuration(file)
        .then((result) => {
          if (!result.isValid) {
            let err;
            switch (result.error) {
              case "AUDIO_TOO_SHORT":
                err = UPLOAD_ERRORS.AUDIO_TOO_SHORT;
                break;
              case "AUDIO_TOO_LONG":
                err = UPLOAD_ERRORS.AUDIO_TOO_LONG;
                break;
              case "EMPTY_AUDIO_FILE":
                err = UPLOAD_ERRORS.EMPTY_AUDIO_FILE;
                break;
              case "UPLOAD_TIMEOUT":
                err = UPLOAD_ERRORS.UPLOAD_TIMEOUT;
                break;
              default:
                err = UPLOAD_ERRORS.INVALID_FILE;
                break;
            }
            toast({
              title: err.title,
              description: err.description,
              status: "error",
              duration: 5000,
              isClosable: true,
            });
            onError(err.description);
            return;
          }

          try {
            onError(null);
            resetResultState();

            const reader = new FileReader();
            reader.onload = () => {
              try {
                const fileResult = reader.result as string;
                const base64Data = fileResult?.split(",")[1];
                if (!base64Data) {
                  throw new Error("Failed to extract base64 data");
                }
                onFileReady(base64Data);
              } catch (err) {
                console.error("Error processing file result:", err);
                onError("Failed to process file. Please try again.");
              }
            };
            reader.onerror = () => {
              const err = UPLOAD_ERRORS.INVALID_FILE;
              toast({
                title: err.title,
                description: err.description,
                status: "error",
                duration: 3000,
                isClosable: true,
              });
              onError(err.description);
            };
            reader.readAsDataURL(file);
          } catch (err) {
            console.error("Error processing file upload:", err);
            const uploadErr = UPLOAD_ERRORS.UPLOAD_FAILED;
            toast({
              title: uploadErr.title,
              description: uploadErr.description,
              status: "error",
              duration: 3000,
              isClosable: true,
            });
            onError(uploadErr.description);
          }
        })
        .catch((validationError) => {
          console.error("Error validating audio duration:", validationError);
          const err = UPLOAD_ERRORS.INVALID_FILE;
          toast({
            title: err.title,
            description: err.description,
            status: "error",
            duration: 3000,
            isClosable: true,
          });
          onError(err.description);
        });
    },
    [onError, onFileReady, resetResultState, toast]
  );

  return { handleFileUpload };
}
