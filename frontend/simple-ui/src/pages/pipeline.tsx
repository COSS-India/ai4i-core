// Pipeline service page for Speech-to-Speech translation

import React, { useState } from 'react';
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
  Button,
  Textarea,
  Stat,
  StatLabel,
  StatNumber,
  StatHelpText,
  SimpleGrid,
  useToast,
  Alert,
  AlertIcon,
  AlertDescription,
} from '@chakra-ui/react';
import { useQuery } from '@tanstack/react-query';
import { FaMicrophone, FaMicrophoneSlash } from 'react-icons/fa';
import ContentLayout from '../components/common/ContentLayout';
import LoadingSpinner from '../components/common/LoadingSpinner';
import { SUPPORTED_LANGUAGES, LANG_CODE_TO_LABEL } from '../config/constants';
import { usePipeline } from '../hooks/usePipeline';
import { listASRModels } from '../services/asrService';
import { listNMTModels } from '../services/nmtService';
import { listVoices } from '../services/ttsService';

const PipelinePage: React.FC = () => {
  const toast = useToast();
  const [sourceLanguage, setSourceLanguage] = useState('en');
  const [targetLanguage, setTargetLanguage] = useState('hi');
  const [asrServiceId, setAsrServiceId] = useState('dhruva-asr');
  const [nmtServiceId, setNmtServiceId] = useState('dhruva-nmt');
  const [ttsServiceId, setTtsServiceId] = useState('dhruva-tts');

  const {
    isLoading,
    result,
    isRecording,
    startRecording,
    stopRecording,
    processRecordedAudio,
    processUploadedAudio,
  } = usePipeline();

  // Fetch available models
  const { data: asrModels } = useQuery({
    queryKey: ['asr-models'],
    queryFn: listASRModels,
    staleTime: 5 * 60 * 1000,
  });

  const { data: nmtModels } = useQuery({
    queryKey: ['nmt-models'],
    queryFn: listNMTModels,
    staleTime: 5 * 60 * 1000,
  });

  const { data: ttsVoices } = useQuery({
    queryKey: ['tts-voices'],
    queryFn: () => listVoices(),
    staleTime: 5 * 60 * 1000,
  });

  const handleRecordClick = async () => {
    if (isRecording) {
      stopRecording();
      // Process the recorded audio
      setTimeout(async () => {
        try {
          await processRecordedAudio(
            sourceLanguage,
            targetLanguage,
            asrServiceId,
            nmtServiceId,
            ttsServiceId
          );
        } catch (error) {
          console.error('Pipeline processing error:', error);
        }
      }, 100);
    } else {
      startRecording();
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      await processUploadedAudio(
        file,
        sourceLanguage,
        targetLanguage,
        asrServiceId,
        nmtServiceId,
        ttsServiceId
      );
    } catch (error) {
      console.error('Pipeline upload error:', error);
    }

    // Reset file input
    event.target.value = '';
  };

  // Get word count helper
  const getWordCount = (text: string): number => {
    return text.trim().split(/\s+/).filter(Boolean).length;
  };

  return (
    <>
      <Head>
        <title>Pipeline - Speech-to-Speech | Simple UI</title>
        <meta
          name="description"
          content="Speech-to-Speech translation pipeline combining ASR, NMT, and TTS"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Page Header */}
          <Box textAlign="center">
            <Heading size="xl" color="gray.800" mb={2}>
              Pipeline (Speech-to-Speech)
            </Heading>
            <Text color="gray.600" fontSize="lg">
              Chain ASR → Translation → TTS for complete speech-to-speech translation
            </Text>
          </Box>

          {/* Info Alert */}
          <Alert status="info" borderRadius="md" maxW="800px">
            <AlertIcon />
            <AlertDescription>
              The pipeline chains Automatic Speech Recognition (ASR), Neural Machine Translation
              (NMT), and Text-to-Speech (TTS) services to convert speech from one language to
              another.
            </AlertDescription>
          </Alert>

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
                {/* Source Language */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">
                    Source Language
                  </FormLabel>
                  <Select
                    value={sourceLanguage}
                    onChange={(e) => setSourceLanguage(e.target.value)}
                  >
                    {SUPPORTED_LANGUAGES.map((lang) => (
                      <option key={lang.code} value={lang.code}>
                        {lang.label}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                {/* Target Language */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">
                    Target Language
                  </FormLabel>
                  <Select
                    value={targetLanguage}
                    onChange={(e) => setTargetLanguage(e.target.value)}
                  >
                    {SUPPORTED_LANGUAGES.map((lang) => (
                      <option key={lang.code} value={lang.code}>
                        {lang.label}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                {/* ASR Service */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">ASR Service</FormLabel>
                  <Select
                    value={asrServiceId}
                    onChange={(e) => setAsrServiceId(e.target.value)}
                  >
                    <option value="dhruva-asr">dhruva-asr (Default)</option>
                    {asrModels?.models?.map((model) => (
                      <option key={model.model_id} value={model.model_id}>
                        {model.model_id}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                {/* NMT Service */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">NMT Service</FormLabel>
                  <Select
                    value={nmtServiceId}
                    onChange={(e) => setNmtServiceId(e.target.value)}
                  >
                    <option value="dhruva-nmt">dhruva-nmt (Default)</option>
                    {nmtModels?.map((model) => (
                      <option key={model.model_id} value={model.model_id}>
                        {model.model_id}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                {/* TTS Service */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">TTS Service</FormLabel>
                  <Select
                    value={ttsServiceId}
                    onChange={(e) => setTtsServiceId(e.target.value)}
                  >
                    <option value="dhruva-tts">dhruva-tts (Default)</option>
                    {ttsVoices?.voices?.slice(0, 10).map((voice) => (
                      <option key={voice.voice_id} value={voice.voice_id}>
                        {voice.voice_id}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                {/* Recording Button */}
                <Button
                  leftIcon={isRecording ? <FaMicrophoneSlash /> : <FaMicrophone />}
                  colorScheme={isRecording ? 'red' : 'orange'}
                  variant={isRecording ? 'solid' : 'outline'}
                  onClick={handleRecordClick}
                  disabled={isLoading}
                  w="full"
                  h="50px"
                >
                  {isRecording ? 'Stop Recording' : 'Start Recording'}
                </Button>

                {/* File Upload */}
                <Button as="label" cursor="pointer" disabled={isLoading || isRecording}>
                  Choose Audio File
                  <input
                    type="file"
                    accept="audio/*"
                    onChange={handleFileUpload}
                    style={{ display: 'none' }}
                  />
                </Button>

                {/* Progress Indicator */}
                {isLoading && (
                  <Box>
                    <Text mb={2} fontSize="sm" color="gray.600">
                      Processing pipeline...
                    </Text>
                    <Progress size="xs" isIndeterminate colorScheme="orange" />
                  </Box>
                )}
              </VStack>
            </GridItem>

            {/* Results Panel */}
            <GridItem>
              <VStack spacing={6} align="stretch">
                {/* Results Stats */}
                {result && (
                  <SimpleGrid
                    p={4}
                    bg="orange.50"
                    borderRadius="md"
                    border="1px"
                    borderColor="orange.200"
                    columns={2}
                    spacingX="20px"
                    spacingY="10px"
                  >
                    <Stat>
                      <StatLabel>Source Text</StatLabel>
                      <StatNumber>{getWordCount(result.sourceText)}</StatNumber>
                      <StatHelpText>words</StatHelpText>
                    </Stat>
                    <Stat>
                      <StatLabel>Translated Text</StatLabel>
                      <StatNumber>{getWordCount(result.targetText)}</StatNumber>
                      <StatHelpText>words</StatHelpText>
                    </Stat>
                  </SimpleGrid>
                )}

                {/* Source Text */}
                <Box>
                  <FormLabel mb={2} fontSize="sm" fontWeight="semibold" color="gray.700">
                    Transcribed Text (Source)
                  </FormLabel>
                  <Textarea
                    readOnly
                    value={result?.sourceText || ''}
                    placeholder="Transcribed text will appear here..."
                    rows={4}
                  />
                </Box>

                {/* Target Text */}
                <Box>
                  <FormLabel mb={2} fontSize="sm" fontWeight="semibold" color="gray.700">
                    Translated Text (Target)
                  </FormLabel>
                  <Textarea
                    readOnly
                    value={result?.targetText || ''}
                    placeholder="Translated text will appear here..."
                    rows={4}
                  />
                </Box>

                {/* Audio Player */}
                {result?.audio && (
                  <Box>
                    <FormLabel mb={2} fontSize="sm" fontWeight="semibold" color="gray.700">
                      Synthesized Audio (Target)
                    </FormLabel>
                    <audio
                      controls
                      src={result.audio}
                      style={{ width: '100%' }}
                    />
                  </Box>
                )}
              </VStack>
            </GridItem>
          </Grid>
        </VStack>
      </ContentLayout>
    </>
  );
};

export default PipelinePage;
