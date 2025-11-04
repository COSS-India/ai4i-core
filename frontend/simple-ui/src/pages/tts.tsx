// TTS service testing page with text input, voice selection, and audio playback

  import React, { useState } from 'react';
import Head from 'next/head';
import {
  Grid,
  GridItem,
  Heading,
  Text,
  Button,
  Progress,
  VStack,
  Box,
  useToast,
  FormControl,
  FormLabel,
  Select,
} from '@chakra-ui/react';
import { useQuery } from '@tanstack/react-query';
import { FaRegFileAudio } from 'react-icons/fa';
import { useTTS } from '../hooks/useTTS';
import { listVoices } from '../services/ttsService';
import ContentLayout from '../components/common/ContentLayout';
import TextInput from '../components/tts/TextInput';
import VoiceSelector from '../components/tts/VoiceSelector';
import TTSResults from '../components/tts/TTSResults';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { SUPPORTED_LANGUAGES } from '../config/constants';

const TTSPage: React.FC = () => {
  const toast = useToast();
  const [serviceId, setServiceId] = useState<string>('');
  const {
    language,
    gender,
    audioFormat,
    samplingRate,
    inputText,
    audio,
    fetching,
    fetched,
    requestWordCount,
    requestTime,
    audioDuration,
    error,
    performInference,
    setInputText,
    setLanguage,
    setGender,
    setAudioFormat,
    setSamplingRate,
    clearResults,
  } = useTTS();

  // Fetch available voices
  const { data: voicesData, isLoading: voicesLoading } = useQuery({
    queryKey: ['tts-voices', language, gender],
    queryFn: () => listVoices({ language, gender }),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const handleGenerate = () => {
    if (!inputText.trim()) {
      toast({
        title: 'Input Required',
        description: 'Please enter text to synthesize.',
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    performInference(inputText);
  };

  // Restrict available languages to Indo-Aryan list requested
  const indoAryanLanguages = ['hi', 'mr', 'as', 'bn', 'gu', 'or', 'pa'];

  return (
    <>
      <Head>
        <title>TTS - Text-to-Speech | AI4Inclusion Console</title>
        <meta name="description" content="Test Text-to-Speech with multiple voice options and audio formats" />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Page Header */}
          <Box textAlign="center">
            <Heading size="xl" color="gray.800" mb={2}>
              Text-to-Speech
            </Heading>
            <Text color="gray.600" fontSize="lg">
              Convert text to natural-sounding speech with multiple voice options
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
                {/* Service Selection (fixed to Indo-Aryan model) */}
                <Box>
                  <FormControl>
                    <FormLabel className="dview-service-try-option-title">
                      Translation Service:
                    </FormLabel>
                    <Select
                      placeholder="Select a model"
                      value={serviceId}
                      onChange={(e) => setServiceId(e.target.value)}
                    >
                      <option value="indic-tts-coqui-indo_aryan">indic-tts-coqui-indo_aryan</option>
                    </Select>
                  </FormControl>

                  <Text className="dview-service-try-option-title" mt={4} mb={2}>
                    Language Configuration
                  </Text>

                  {!serviceId ? (
                    <Box p={3} bg="gray.50" borderRadius="md" textAlign="center">
                      <Text fontSize="sm" color="gray.600">No model selected</Text>
                    </Box>
                  ) : (
                    <Box p={3} bg="gray.50" borderRadius="md">
                      <Text fontSize="sm" color="gray.600" mb={1}>
                        <strong>Provider:</strong> AI4Bharat
                      </Text>
                      <Text fontSize="sm" color="gray.600" mb={1}>
                        <strong>Supported Languages:</strong> 8
                      </Text>
                      <Text fontSize="sm" color="gray.600" mb={1}>
                        <strong>Service ID:</strong> ai4bharat/indic-tts-coqui-indo_aryan-gpu--t4
                      </Text>
                    </Box>
                  )}
                </Box>

                {/* Voice Selector */}
                <Box>
                  <Text className="dview-service-try-option-title" mb={4}>
                    Voice Configuration
                  </Text>
                  <VoiceSelector
                    language={language}
                    gender={gender}
                    audioFormat={audioFormat}
                    samplingRate={samplingRate}
                    onLanguageChange={setLanguage}
                    onGenderChange={setGender}
                    onFormatChange={setAudioFormat}
                    onSampleRateChange={setSamplingRate}
                    availableLanguages={serviceId ? indoAryanLanguages : []}
                    availableVoices={voicesData?.voices}
                    loading={voicesLoading}
                  />
                </Box>

                {/* Text Input */}
                <Box>
                  <TextInput
                    value={inputText}
                    onChange={setInputText}
                    language={language}
                    maxLength={512}
                    placeholder="Enter text to synthesize..."
                    disabled={fetching}
                  />
                </Box>

                {/* Generate Button */}
                <Button
                  leftIcon={<FaRegFileAudio />}
                  colorScheme="orange"
                  size="lg"
                  onClick={handleGenerate}
                  isLoading={fetching}
                  loadingText="Generating..."
                  isDisabled={!inputText.trim() || fetching}
                >
                  Generate Audio
                </Button>
              </VStack>
            </GridItem>

            {/* Results Panel */}
            <GridItem>
              <VStack spacing={6} align="stretch">
                {/* Progress Indicator */}
                {fetching && (
                  <Box>
                    <Text mb={2} fontSize="sm" color="gray.600">
                      Generating speech...
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

                {/* TTS Results */}
                {fetched && audio && (
                  <TTSResults
                    audioSrc={audio}
                    wordCount={requestWordCount}
                    responseTime={Number(requestTime)}
                    audioDuration={audioDuration}
                  />
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

                {/* Instructions */}
                {!fetched && !fetching && (
                  <Box p={6} bg="gray.50" borderRadius="md" textAlign="center">
                    <Text color="gray.600" fontSize="sm">
                      Enter text and click &quot;Generate Audio&quot; to create speech synthesis.
                      You can adjust voice settings and audio format in the configuration panel.
                    </Text>
                  </Box>
                )}
              </VStack>
            </GridItem>
          </Grid>

          {/* Voices Loading Indicator */}
          {voicesLoading && (
            <Box textAlign="center">
              <LoadingSpinner label="Loading voice options..." />
            </Box>
          )}
        </VStack>
      </ContentLayout>
    </>
  );
};

export default TTSPage;