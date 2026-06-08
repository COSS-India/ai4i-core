// Audio record/upload controls for the speech-to-speech pipeline page

import React from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  Button,
  FormLabel,
  Text,
  VStack,
} from "@chakra-ui/react";
import { FaMicrophone, FaMicrophoneSlash, FaUpload } from "react-icons/fa";
import AudioInputPreview from "../common/AudioInputPreview";
import { formatDuration, MAX_RECORDING_DURATION } from "../../config/constants";

export interface PipelineAudioSectionProps {
  isRecording: boolean;
  timer: number;
  pendingAudio: string | null;
  uploadedFileName: string | null;
  canRunPipeline: boolean;
  isLoading: boolean;
  onRecordClick: () => void;
  onFileUpload: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onClear: () => void;
}

const PipelineAudioSection: React.FC<PipelineAudioSectionProps> = ({
  isRecording,
  timer,
  pendingAudio,
  uploadedFileName,
  canRunPipeline,
  isLoading,
  onRecordClick,
  onFileUpload,
  onClear,
}) => (
  <Box>
    <FormLabel className="dview-service-try-option-title" mb={4}>
      Audio Input{" "}
      <Text as="span" color="red.500">
        *
      </Text>
    </FormLabel>

    {isRecording && (
      <Alert status="info" borderRadius="md">
        <AlertIcon />
        <AlertDescription>
          Recording Time: {formatDuration(timer)} / {formatDuration(MAX_RECORDING_DURATION)} seconds
        </AlertDescription>
      </Alert>
    )}

    {!isRecording && pendingAudio && (
      <>
        <Alert status="success" borderRadius="md" mt={4}>
          <AlertIcon />
          <AlertDescription>
            {uploadedFileName
              ? `File "${uploadedFileName}" is ready.`
              : "Recording complete. Audio is ready."}{" "}
            Click Run Pipeline to generate results.
          </AlertDescription>
        </Alert>
        <AudioInputPreview
          audioBase64OrDataUrl={pendingAudio}
          label="Review your audio"
          onClear={onClear}
        />
      </>
    )}

    <VStack spacing={4} mt={4} align="stretch">
      <Box p={3} borderRadius="md" borderWidth="1px" borderColor="gray.200" bg="gray.50">
        <Text fontSize="sm" color="gray.600" mb={2}>
          Click Record to capture speech using your microphone (max{" "}
          {formatDuration(MAX_RECORDING_DURATION)} seconds).
        </Text>
        <Button
          leftIcon={isRecording ? <FaMicrophoneSlash /> : <FaMicrophone />}
          colorScheme={isRecording ? "red" : "orange"}
          variant={isRecording ? "solid" : "outline"}
          onClick={onRecordClick}
          disabled={!canRunPipeline || isLoading}
          w="full"
          h="50px"
        >
          {isRecording ? "Stop" : "Record"}
        </Button>
      </Box>

      <Box p={3} borderRadius="md" borderWidth="1px" borderColor="gray.200" bg="gray.50">
        <Text fontSize="sm" color="gray.600" mb={2}>
          Click Upload to choose an audio file (MP3 or WAV) from your device to run through the
          pipeline.
        </Text>
        <Button
          as="label"
          leftIcon={<FaUpload />}
          colorScheme="blue"
          variant="outline"
          cursor="pointer"
          disabled={!canRunPipeline || isLoading || isRecording}
          w="full"
          h="50px"
        >
          Upload
          <input
            type="file"
            accept="audio/*"
            onChange={onFileUpload}
            style={{ display: "none" }}
          />
        </Button>
        {uploadedFileName && (
          <Text fontSize="sm" color="gray.700" mt={2} noOfLines={1} title={uploadedFileName}>
            Uploaded: {uploadedFileName}
          </Text>
        )}
      </Box>
    </VStack>
  </Box>
);

export default PipelineAudioSection;
