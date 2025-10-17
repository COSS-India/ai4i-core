// Audio recorder component with microphone recording and file upload

import React, { useRef } from 'react';
import {
  Stack,
  Button,
  Text,
  Alert,
  AlertIcon,
  AlertDescription,
  CloseButton,
  useToast,
  Input,
  FormControl,
  FormLabel,
} from '@chakra-ui/react';
import { FaMicrophone, FaMicrophoneSlash, FaUpload } from 'react-icons/fa';
import { AudioRecorderProps } from '../../types/asr';
import { formatDuration, MAX_RECORDING_DURATION } from '../../config/constants';

const AudioRecorder: React.FC<AudioRecorderProps> = ({
  onAudioReady,
  isRecording,
  onRecordingChange,
  sampleRate,
  disabled = false,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const toast = useToast();

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith('audio/')) {
      toast({
        title: 'Invalid File Type',
        description: 'Please select an audio file.',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    // Validate file size (max 10MB)
    const maxSize = 10 * 1024 * 1024; // 10MB
    if (file.size > maxSize) {
      toast({
        title: 'File Too Large',
        description: 'Please select a file smaller than 10MB.',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    try {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        const base64Data = result.split(',')[1];
        onAudioReady(base64Data);
      };
      reader.readAsDataURL(file);
    } catch (error) {
      console.error('Error reading file:', error);
      toast({
        title: 'File Read Error',
        description: 'Failed to read the selected file.',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    }
  };

  const handleRecordClick = () => {
    if (isRecording) {
      onRecordingChange(false);
    } else {
      onRecordingChange(true);
    }
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <Stack spacing={4} w="full">
      {/* Recording Timer Display */}
      {isRecording && (
        <Alert status="info" borderRadius="md">
          <AlertIcon />
          <AlertDescription>
            Recording Time: {formatDuration(MAX_RECORDING_DURATION - 0)} / {formatDuration(MAX_RECORDING_DURATION)} seconds
          </AlertDescription>
        </Alert>
      )}

      {/* Recording and Upload Buttons */}
      <Stack direction="row" spacing={4}>
        {/* Record Button */}
        <Button
          leftIcon={isRecording ? <FaMicrophoneSlash /> : <FaMicrophone />}
          colorScheme={isRecording ? 'red' : 'orange'}
          variant={isRecording ? 'solid' : 'outline'}
          onClick={handleRecordClick}
          disabled={disabled}
          flex={1}
          h="50px"
        >
          {isRecording ? 'Stop Recording' : 'Start Recording'}
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
          Choose File
        </Button>
      </Stack>

      {/* Hidden File Input */}
      <FormControl display="none">
        <FormLabel>Audio File</FormLabel>
        <Input
          ref={fileInputRef}
          type="file"
          accept="audio/*"
          onChange={handleFileUpload}
        />
      </FormControl>

      {/* Instructions */}
      <Text fontSize="sm" color="gray.600" textAlign="center">
        {isRecording
          ? 'Click "Stop Recording" when finished'
          : 'Click "Start Recording" to record audio or "Choose File" to upload an audio file'}
      </Text>
    </Stack>
  );
};

export default AudioRecorder;
