// Audio input with record, upload, drag-and-drop file selection, and preview

import React, { useCallback, useMemo } from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  FormLabel,
  Text,
  VStack,
} from "@chakra-ui/react";
import AudioRecorder from "../../asr/AudioRecorder";
import AudioInputPreview from "../../common/AudioInputPreview";
import { useAudioRecorder } from "../../../hooks/useAudioRecorder";
import type { ServiceAudioInputProps } from "../../../types/servicePage";

const AudioInput: React.FC<ServiceAudioInputProps> = ({
  value,
  onChange,
  children,
  label = "Audio Input",
  required = true,
  helperSlot,
  disabled = false,
  sampleRate = 16000,
  showRecording = true,
  showUpload = true,
  readyMessage = "Audio ready. Click submit to process.",
  showSuccessAlert = true,
  clearToken,
  onClear,
  isRecording: externalIsRecording,
  onRecordingChange: externalOnRecordingChange,
  timer: externalTimer,
}) => {
  const usesExternalRecording = externalOnRecordingChange !== undefined;

  const {
    isRecording: internalIsRecording,
    timer: internalTimer,
    startRecording,
    stopRecording,
  } = useAudioRecorder({
    sampleRate,
    onRecordingComplete: (audioBase64) => onChange(audioBase64),
  });

  const isRecording = usesExternalRecording
    ? (externalIsRecording ?? false)
    : internalIsRecording;
  const timer = usesExternalRecording ? (externalTimer ?? 0) : internalTimer;

  const handleRecordingChange = useCallback(
    (recording: boolean) => {
      if (usesExternalRecording) {
        externalOnRecordingChange!(recording);
        return;
      }
      if (recording) startRecording();
      else stopRecording();
    },
    [usesExternalRecording, externalOnRecordingChange, startRecording, stopRecording]
  );

  const handleAudioReady = useCallback(
    (audioBase64: string) => onChange(audioBase64),
    [onChange]
  );

  const handleClear = useCallback(() => {
    onChange(null);
    onClear?.();
  }, [onChange, onClear]);

  const previewLabel = useMemo(
    () => (showRecording && showUpload ? "Review your audio" : "Selected audio"),
    [showRecording, showUpload]
  );

  if (children) {
    return (
      <VStack spacing={4} align="stretch" w="full">
        <Box>
          <FormLabel
            className="dview-service-try-option-title"
            mb={2}
            fontSize="sm"
            fontWeight="semibold"
          >
            {label}{" "}
            {required && (
              <Text as="span" color="red.500">
                *
              </Text>
            )}
          </FormLabel>
          {children}
        </Box>
        {helperSlot}
      </VStack>
    );
  }

  return (
    <VStack spacing={4} align="stretch" w="full">
      <Box>
        <FormLabel
          className="dview-service-try-option-title"
          mb={2}
          fontSize="sm"
          fontWeight="semibold"
        >
          {label}{" "}
          {required && (
            <Text as="span" color="red.500">
              *
            </Text>
          )}
        </FormLabel>
        <AudioRecorder
          onAudioReady={handleAudioReady}
          isRecording={isRecording}
          onRecordingChange={handleRecordingChange}
          sampleRate={sampleRate}
          disabled={disabled}
          timer={timer}
          onClear={handleClear}
          clearToken={clearToken}
          showRecording={showRecording}
          showUpload={showUpload}
        />
        {!isRecording && value && (
          <>
            {showSuccessAlert && (
              <Alert status="success" borderRadius="md" mt={4}>
                <AlertIcon />
                <AlertDescription>{readyMessage}</AlertDescription>
              </Alert>
            )}
            <AudioInputPreview
              audioBase64OrDataUrl={value}
              label={previewLabel}
              onClear={handleClear}
            />
          </>
        )}
      </Box>
      {helperSlot}
    </VStack>
  );
};

export default AudioInput;
