// ASR service testing page with recording, file upload, and results display

import React from 'react';
import Head from 'next/head';
import {
  Grid,
  GridItem,
  Heading,
  Text,
  Select,
  FormControl,
  FormLabel,
  Progress,
  VStack,
  Box,
  useToast,
} from '@chakra-ui/react';
import { useQuery } from '@tanstack/react-query';
import { useASR } from '../hooks/useASR';
import { listASRModels } from '../services/asrService';
import ContentLayout from '../components/common/ContentLayout';
import AudioRecorder from '../components/asr/AudioRecorder';
import AudioPlayer from '../components/asr/AudioPlayer';
import ASRResults from '../components/asr/ASRResults';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { SUPPORTED_LANGUAGES, ASR_SAMPLE_RATES } from '../config/constants';

const ASRPage: React.FC = () => {
  const toast = useToast();
  const {
    language,
    sampleRate,
    inferenceMode,
    recording,
    fetching,
    fetched,
    audioText,
    responseWordCount,
    requestTime,
    timer,
    error,
    startRecording,
    stopRecording,
    handleFileUpload,
    setLanguage,
    setSampleRate,
    setInferenceMode,
    clearResults,
  } = useASR();

  // Fetch available ASR models
  const { data: modelsData, isLoading: modelsLoading } = useQuery({
    queryKey: ['asr-models'],
    queryFn: listASRModels,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const handleRecordingChange = (isRecording: boolean) => {
    if (isRecording) {
      startRecording();
    } else {
      stopRecording();
    }
  };

  const handleAudioReady = (audioBase64: string) => {
    // This will be handled by the useASR hook
    console.log('Audio ready for processing');
  };

  return (
    <>
      <Head>
        <title>ASR - Speech Recognition | Simple UI</title>
        <meta name="description" content="Test Automatic Speech Recognition with microphone recording and file upload" />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Page Header */}
          <Box textAlign="center">
            <Heading size="xl" color="gray.800" mb={2}>
              Automatic Speech Recognition
            </Heading>
            <Text color="gray.600" fontSize="lg">
              Convert speech to text with support for 22+ Indian languages
            </Text>
          </Box>

          <Grid
            templateColumns={{ base: '1fr', lg: '1fr 1fr' }}
            gap={8}
            w="full"
            maxW="1200px"
            mx="auto"
          >
            {/* Configuration Panel */}
            <GridItem>
              <VStack spacing={6} align="stretch">
                {/* Inference Mode Selection */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">
                    Inference Mode
                  </FormLabel>
                  <Select
                    value={inferenceMode}
                    onChange={(e) => setInferenceMode(e.target.value as 'rest' | 'streaming')}
                  >
                    <option value="rest">REST API</option>
                    <option value="streaming">WebSocket Streaming</option>
                  </Select>
                </FormControl>

                {/* Language Selection */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">
                    Language
                  </FormLabel>
                  <Select
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                  >
                    {SUPPORTED_LANGUAGES.map((lang) => (
                      <option key={lang.code} value={lang.code}>
                        {lang.label}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                {/* Sample Rate Selection */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">
                    Sample Rate
                  </FormLabel>
                  <Select
                    value={sampleRate}
                    onChange={(e) => setSampleRate(Number(e.target.value))}
                  >
                    {ASR_SAMPLE_RATES.map((rate) => (
                      <option key={rate} value={rate}>
                        {rate} Hz
                      </option>
                    ))}
                  </Select>
                </FormControl>

                {/* Audio Recorder */}
                <Box>
                  <FormLabel className="dview-service-try-option-title" mb={4}>
                    Audio Input
                  </FormLabel>
                  <AudioRecorder
                    onAudioReady={handleAudioReady}
                    isRecording={recording}
                    onRecordingChange={handleRecordingChange}
                    sampleRate={sampleRate}
                    disabled={fetching}
                    timer={timer}
                  />
                </Box>

                {/* File Upload */}
                <Box>
                  <FormLabel className="dview-service-try-option-title" mb={4}>
                    File Upload
                  </FormLabel>
                  <input
                    type="file"
                    accept="audio/*"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleFileUpload(file);
                    }}
                    style={{ width: '100%' }}
                  />
                </Box>
              </VStack>
            </GridItem>

            {/* Results Panel */}
            <GridItem>
              <VStack spacing={6} align="stretch">
                {/* Progress Indicator */}
                {fetching && (
                  <Box>
                    <Text mb={2} fontSize="sm" color="gray.600">
                      Processing audio...
                    </Text>
                    <Progress size="xs" isIndeterminate colorScheme="orange" />
                  </Box>
                )}

                {/* Error Display */}
                {error && (
                  <Box p={4} bg="red.50" borderRadius="md" border="1px" borderColor="red.200">
                    <Text color="red.600" fontSize="sm">
                      {error}
                    </Text>
                  </Box>
                )}

                {/* Recording Timer */}
                {recording && (
                  <Box p={4} bg="orange.50" borderRadius="md" textAlign="center">
                    <Text color="orange.600" fontWeight="semibold">
                      Recording: {Math.floor(timer / 60)}:{(timer % 60).toString().padStart(2, '0')}
                    </Text>
                  </Box>
                )}

                {/* ASR Results */}
                {fetched && audioText && (
                  <ASRResults
                    transcript={audioText}
                    wordCount={responseWordCount}
                    responseTime={Number(requestTime)}
                  />
                )}

                {/* Audio Player (if available) */}
                {audioText && (
                  <Box>
                    <Text mb={2} fontSize="sm" fontWeight="semibold" color="gray.700">
                      Audio Playback
                    </Text>
                    <AudioPlayer
                      audioSrc=""
                      showVisualization={true}
                    />
                  </Box>
                )}

                {/* Clear Results Button */}
                {fetched && (
                  <Box textAlign="center">
                    <button
                      onClick={clearResults}
                      style={{
                        padding: '8px 16px',
                        backgroundColor: '#f7fafc',
                        border: '1px solid #e2e8f0',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontSize: '14px',
                        color: '#4a5568',
                      }}
                    >
                      Clear Results
                    </button>
                  </Box>
                )}
              </VStack>
            </GridItem>
          </Grid>

          {/* Models Loading Indicator */}
          {modelsLoading && (
            <Box textAlign="center">
              <LoadingSpinner label="Loading ASR models..." />
            </Box>
          )}
        </VStack>
      </ContentLayout>
    </>
  );
};

export default ASRPage;