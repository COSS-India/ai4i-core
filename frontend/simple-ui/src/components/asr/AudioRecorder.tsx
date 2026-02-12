// Audio recorder component with microphone recording and file upload

import {
  Alert,
  AlertDescription,
  AlertIcon,
  Button,
  FormControl,
  FormLabel,
  Input,
  Stack,
  Text,
} from "@chakra-ui/react";
import React, { useRef } from "react";
import { FaMicrophone, FaMicrophoneSlash, FaUpload } from "react-icons/fa";
import { formatDuration, MAX_RECORDING_DURATION, MIN_RECORDING_DURATION, MAX_AUDIO_FILE_SIZE, UPLOAD_ERRORS } from "../../config/constants";
import { AudioRecorderProps } from "../../types/asr";
import { useToastWithDeduplication } from "../../hooks/useToastWithDeduplication";

const AudioRecorder: React.FC<AudioRecorderProps> = ({
  onAudioReady,
  isRecording,
  onRecordingChange,
  sampleRate,
  disabled = false,
  timer = 0,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const toast = useToastWithDeduplication();

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];

    // Reset input value immediately to allow selecting the same file again
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }

    if (!file) {
      console.log("No file selected");
      const err = UPLOAD_ERRORS.NO_FILE_SELECTED;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    console.log(
      "File selected:",
      file.name,
      "Size:",
      file.size,
      "Type:",
      file.type
    );

    // Validate file size
    if (file.size > MAX_AUDIO_FILE_SIZE) {
      const err = UPLOAD_ERRORS.FILE_TOO_LARGE;
      toast({
        title: err.title,
        description: err.description,
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    // Validate file type - only MP3 and WAV files are supported
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
      return;
    }

    // Validate audio duration (min 1 second, max 60 seconds)
    const validateAudioDuration = (file: File): Promise<{ isValid: boolean; duration: number; error?: string }> => {
      return new Promise((resolve) => {
        const audio = new Audio();
        const url = URL.createObjectURL(file);

        const timeout = setTimeout(() => {
          URL.revokeObjectURL(url);
          resolve({ isValid: false, duration: 0, error: 'UPLOAD_TIMEOUT' });
        }, 10000); // 10 second timeout

        audio.addEventListener("loadedmetadata", () => {
          clearTimeout(timeout);
          URL.revokeObjectURL(url);
          const duration = audio.duration;
          console.log("Audio duration:", duration, "seconds");
          
          if (duration < MIN_RECORDING_DURATION) {
            resolve({ isValid: false, duration, error: 'AUDIO_TOO_SHORT' });
          } else if (duration > MAX_RECORDING_DURATION) {
            resolve({ isValid: false, duration, error: 'AUDIO_TOO_LONG' });
          } else if (isNaN(duration) || duration === 0) {
            resolve({ isValid: false, duration, error: 'EMPTY_AUDIO_FILE' });
          } else {
            resolve({ isValid: true, duration });
          }
        });

        audio.addEventListener("error", () => {
          clearTimeout(timeout);
          URL.revokeObjectURL(url);
          console.error("Error loading audio metadata");
          resolve({ isValid: false, duration: 0, error: 'INVALID_FILE' });
        });

        audio.src = url;
      });
    };

    // Validate duration first, then process file
    validateAudioDuration(file)
      .then((result) => {
        if (!result.isValid) {
          let err;
          switch (result.error) {
            case 'AUDIO_TOO_SHORT':
              err = UPLOAD_ERRORS.AUDIO_TOO_SHORT;
              break;
            case 'AUDIO_TOO_LONG':
              err = UPLOAD_ERRORS.AUDIO_TOO_LONG;
              break;
            case 'EMPTY_AUDIO_FILE':
              err = UPLOAD_ERRORS.EMPTY_AUDIO_FILE;
              break;
            case 'UPLOAD_TIMEOUT':
              err = UPLOAD_ERRORS.UPLOAD_TIMEOUT;
              break;
            case 'INVALID_FILE':
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
          return;
        }

        // If duration is valid, proceed with file processing
        try {
          console.log("Reading file:", file.name);
          const reader = new FileReader();

          reader.onload = () => {
            try {
              const result = reader.result as string;
              if (!result) {
                throw new Error("FileReader result is empty");
              }
              const base64Data = result.split(",")[1];
              if (!base64Data) {
                throw new Error("Failed to extract base64 data");
              }
              console.log(
                "File read successfully, base64 length:",
                base64Data.length
              );
              onAudioReady(base64Data);
            } catch (err) {
              console.error("Error processing file result:", err);
              const uploadErr = UPLOAD_ERRORS.UPLOAD_FAILED;
              toast({
                title: uploadErr.title,
                description: uploadErr.description,
                status: "error",
                duration: 3000,
                isClosable: true,
              });
            }
          };

          reader.onerror = (error) => {
            console.error("FileReader error:", error);
            const err = UPLOAD_ERRORS.INVALID_FILE;
            toast({
              title: err.title,
              description: err.description,
              status: "error",
              duration: 3000,
              isClosable: true,
            });
          };

          reader.onabort = () => {
            console.log("File read aborted");
          };

          reader.readAsDataURL(file);
        } catch (error) {
          console.error("Error reading file:", error);
          const err = UPLOAD_ERRORS.INVALID_FILE;
          toast({
            title: err.title,
            description: err.description,
            status: "error",
            duration: 3000,
            isClosable: true,
          });
        }
      })
      .catch((error) => {
        console.error("Error validating audio duration:", error);
        const err = UPLOAD_ERRORS.INVALID_FILE;
        toast({
          title: err.title,
          description: err.description,
          status: "error",
          duration: 3000,
          isClosable: true,
        });
      });
  };

  const handleRecordClick = () => {
    if (isRecording) {
      onRecordingChange(false);
    } else {
      onRecordingChange(true);
    }
  };

  const handleUploadClick = () => {
    // Reset input value before opening file dialog to ensure onChange fires
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    fileInputRef.current?.click();
  };

  return (
    <Stack spacing={4} w="full">
      {/* Recording Timer Display */}
      {isRecording && (
        <Alert status="info" borderRadius="md">
          <AlertIcon />
          <AlertDescription>
            Recording Time: {formatDuration(timer)} /{" "}
            {formatDuration(MAX_RECORDING_DURATION)} seconds
          </AlertDescription>
        </Alert>
      )}

      {/* Recording and Upload Buttons */}
      <Stack direction="row" spacing={4}>
        {/* Record Button */}
        <Button
          leftIcon={isRecording ? <FaMicrophoneSlash /> : <FaMicrophone />}
          colorScheme={isRecording ? "red" : "orange"}
          variant={isRecording ? "solid" : "outline"}
          onClick={handleRecordClick}
          disabled={disabled}
          flex={1}
          h="50px"
        >
          {isRecording ? "Stop" : "Record"}
        </Button>

        {/* Upload Button */}
        <Button
          leftIcon={<FaUpload />}
          colorScheme="blue"
          variant="outline"
          onClick={handleUploadClick}
          disabled={disabled || isRecording}
          flex={1}
          h="50px"
        >
          Upload
        </Button>
      </Stack>

      {/* Hidden File Input */}
      <FormControl display="none">
        <FormLabel>Audio File</FormLabel>
        <Input
          ref={fileInputRef}
          type="file"
          accept="audio/mpeg,audio/mp3,.mp3,audio/wav,audio/wave,audio/x-wav,.wav"
          onChange={handleFileUpload}
        />
      </FormControl>

      {/* Instructions */}
      <Text fontSize="sm" color="gray.600" textAlign="center">
        {isRecording
          ? 'Click "Stop Recording" when finished'
          : `Click "Start Recording" to record audio or "Choose File" to upload an audio file (max ${MAX_RECORDING_DURATION} seconds). Only MP3 and WAV files are supported.`}
      </Text>
    </Stack>
  );
};

export default AudioRecorder;
