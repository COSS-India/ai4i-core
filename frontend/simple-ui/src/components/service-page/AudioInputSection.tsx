import React from "react";
import { Alert, AlertDescription, AlertIcon } from "@chakra-ui/react";
import AudioRecorder from "../asr/AudioRecorder";
import AudioInputPreview from "../common/AudioInputPreview";

export interface AudioInputSectionProps {
  audioData: string | null;
  isRecording: boolean;
  onAudioReady: (audioBase64: string) => void;
  onRecordingChange: (isRecording: boolean) => void;
  timer?: number;
  disabled?: boolean;
  onClear: () => void;
  clearToken?: number;
  sampleRate?: number;
  readyMessage?: string;
  showSuccessAlert?: boolean;
}

const AudioInputSection: React.FC<AudioInputSectionProps> = ({
  audioData,
  isRecording,
  onAudioReady,
  onRecordingChange,
  timer = 0,
  disabled = false,
  onClear,
  clearToken,
  sampleRate = 16000,
  readyMessage = "Audio ready. Click submit to process.",
  showSuccessAlert = true,
}) => (
  <>
    <AudioRecorder
      onAudioReady={onAudioReady}
      isRecording={isRecording}
      onRecordingChange={onRecordingChange}
      sampleRate={sampleRate}
      disabled={disabled}
      timer={timer}
      onClear={onClear}
      clearToken={clearToken}
    />
    {!isRecording && audioData && (
      <>
        {showSuccessAlert && (
          <Alert status="success" borderRadius="md" mt={4}>
            <AlertIcon />
            <AlertDescription>{readyMessage}</AlertDescription>
          </Alert>
        )}
        <AudioInputPreview
          audioBase64OrDataUrl={audioData}
          label="Review your audio"
          onClear={onClear}
        />
      </>
    )}
  </>
);

export default AudioInputSection;
