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
  useToast,
} from "@chakra-ui/react";
import React, { useRef } from "react";
import { FaMicrophone, FaMicrophoneSlash, FaUpload } from "react-icons/fa";
import { formatDuration, MAX_RECORDING_DURATION } from "../../config/constants";
import { AudioRecorderProps } from "../../types/asr";

const AudioRecorder: React.FC<AudioRecorderProps> = ({
  onAudioReady,
  isRecording,
  onRecordingChange,
  sampleRate,
  disabled = false,
  timer = 0,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const toast = useToast();

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];

    // Reset input value immediately to allow selecting the same file again
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }

    if (!file) {
      console.log("No file selected");
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
      toast({
        title: "Invalid File Type",
        description:
          "Only MP3 and WAV files are supported. Please select a valid audio file.",
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    // Validate file size (max 10MB)
    const maxSize = 10 * 1024 * 1024; // 10MB
    if (file.size > maxSize) {
      toast({
        title: "File Too Large",
        description: "Please select a file smaller than 10MB.",
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    // Validate audio duration (max 1 minute)
    const validateAudioDuration = (file: File): Promise<boolean> => {
      return new Promise((resolve) => {
        const audio = new Audio();
        const url = URL.createObjectURL(file);

        audio.addEventListener("loadedmetadata", () => {
          URL.revokeObjectURL(url);
          const duration = audio.duration;
          console.log("Audio duration:", duration, "seconds");
          resolve(duration <= MAX_RECORDING_DURATION);
        });

        audio.addEventListener("error", () => {
          URL.revokeObjectURL(url);
          console.error("Error loading audio metadata");
          // If we can't determine duration, allow it but warn user
          resolve(true);
        });

        audio.src = url;
      });
    };

    // Validate duration first, then process file
    validateAudioDuration(file)
      .then((isValidDuration) => {
        if (!isValidDuration) {
          toast({
            title: "Audio Too Long",
            description: `Audio file exceeds the 1 minute limit. Please select a file that is ${MAX_RECORDING_DURATION} seconds or less.`,
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
              toast({
                title: "File Processing Error",
                description: "Failed to process the selected file.",
                status: "error",
                duration: 3000,
                isClosable: true,
              });
            }
          };

          reader.onerror = (error) => {
            console.error("FileReader error:", error);
            toast({
              title: "File Read Error",
              description: "Failed to read the selected file.",
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
          toast({
            title: "File Read Error",
            description: "Failed to read the selected file.",
            status: "error",
            duration: 3000,
            isClosable: true,
          });
        }
      })
      .catch((error) => {
        console.error("Error validating audio duration:", error);
        toast({
          title: "File Validation Error",
          description: "Failed to validate audio file. Please try again.",
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
