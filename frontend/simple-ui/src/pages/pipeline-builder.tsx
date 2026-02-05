// Custom Pipeline Builder Page - Configure and test custom pipelines

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
  Button,
  Textarea,
  VStack,
  Box,
  useToast,
  Alert,
  AlertIcon,
  AlertDescription,
  SimpleGrid,
  Stat,
  StatLabel,
  StatNumber,
  Code,
  Badge,
} from '@chakra-ui/react';
import { useRouter } from 'next/router';
import { ArrowBackIcon } from '@chakra-ui/icons';
import ContentLayout from '../components/common/ContentLayout';
import { PipelineInferenceRequest } from '../types/pipeline';
import { runPipelineInference } from '../services/pipelineService';
import { ASR_SUPPORTED_LANGUAGES, TTS_SUPPORTED_LANGUAGES } from '../config/constants';

const PipelineBuilderPage: React.FC = () => {
  const toast = useToast();
  const router = useRouter();
  
  // Pipeline configuration
  const [sourceLanguage, setSourceLanguage] = useState('hi');
  const [targetLanguage, setTargetLanguage] = useState('hi'); // Start with 'hi' (Hindi) which is TTS-supported
  const [nmtServiceId, setNmtServiceId] = useState('ai4bharat/indictrans-v2-all-gpu--tensorrt');
  const [ttsServiceId, setTtsServiceId] = useState('ai4bharat/indic-tts-coqui-indo-aryan-gpu');
  
  // Input/Output
  const [inputText, setInputText] = useState('Hello, how are you today?');
  const [pipelineType, setPipelineType] = useState<'translation' | 'translation-tts'>('translation-tts');
  
  // Results
  const [result, setResult] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [rawResponse, setRawResponse] = useState<string>('');

  const handleRunPipeline = async () => {
    setIsLoading(true);
    setResult(null);
    setRawResponse('');

    try {
      let request: PipelineInferenceRequest;

      if (pipelineType === 'translation') {
        request = {
          pipelineTasks: [
            {
              taskType: 'translation',
              config: {
                serviceId: nmtServiceId,
                language: { sourceLanguage, targetLanguage },
              },
            },
          ],
          inputData: {
            input: [{ source: inputText }],
          },
        };
      } else {
        request = {
          pipelineTasks: [
            {
              taskType: 'translation',
              config: {
                serviceId: nmtServiceId,
                language: { sourceLanguage, targetLanguage },
              },
            },
            {
              taskType: 'tts',
              config: {
                serviceId: ttsServiceId,
                language: { sourceLanguage: targetLanguage },
                gender: 'female',
              },
            },
          ],
          inputData: {
            input: [{ source: inputText }],
          },
        };
      }

      const response = await runPipelineInference(request);
      
      // Handle different response formats based on pipeline type
      let displayResult: any = {};
      
      if (pipelineType === 'translation') {
        // Translation only
        const translationOutput = response.pipelineResponse?.[0]?.output?.[0];
        displayResult = {
          sourceText: translationOutput?.source || inputText,
          targetText: translationOutput?.target || '',
          audio: '',
        };
      } else {
        // Translation → TTS
        const translationOutput = response.pipelineResponse?.[0]?.output?.[0];
        const ttsOutput = response.pipelineResponse?.[1];
        
        // Handle audio from TTS response
        let audioContent = '';
        if (ttsOutput?.output && ttsOutput.output.length > 0) {
          // Audio is in output array
          audioContent = ttsOutput.output[0]?.audioContent || '';
        } else if (ttsOutput?.audio && ttsOutput.audio.length > 0) {
          // Audio is in audio array
          audioContent = ttsOutput.audio[0]?.audioContent || '';
        }
        
        displayResult = {
          sourceText: translationOutput?.source || inputText,
          targetText: translationOutput?.target || '',
          audio: audioContent ? `data:audio/wav;base64,${audioContent}` : '',
        };
      }
      
      setResult(displayResult);
      setRawResponse(JSON.stringify(response, null, 2));
      
      toast({
        title: 'Pipeline Completed',
        description: 'Pipeline executed successfully!',
        status: 'success',
        duration: 3000,
      });
    } catch (error: any) {
      toast({
        title: 'Pipeline Failed',
        description: error.message || 'Failed to execute pipeline',
        status: 'error',
        duration: 5000,
      });
      setResult(null);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <Head>
        <title>Customize Pipeline - Custom | AI4Inclusion Console</title>
        <meta name="description" content="Build and test custom AI pipelines" />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Header with Back Button */}
          <Box w="full">
            <Button
              leftIcon={<ArrowBackIcon />}
              variant="outline"
              colorScheme="gray"
              onClick={() => router.back()}
              mb={4}
            >
              Back
            </Button>
            <Box textAlign="center">
              <Heading size="xl" color="gray.800" mb={2} userSelect="none" cursor="default" tabIndex={-1}>
                Customize Pipeline
              </Heading>
              <Text color="gray.600" fontSize="lg" userSelect="none" cursor="default">
                Configure and test custom AI pipelines
              </Text>
            </Box>
          </Box>

          <Grid
            templateColumns={{ base: '1fr', lg: '1fr 1fr' }}
            gap={8}
            w="full"
            maxW="1400px"
            mx="auto"
            alignItems="start"
          >
            {/* Configuration Panel */}
            <GridItem minW="0">
              <Box position="sticky" top="20px" w="100%">
              <VStack spacing={6} align="stretch" w="100%">
                <Alert status="warning" borderRadius="md">
                  <AlertIcon />
                  <AlertDescription fontSize="sm">
                    <strong>Note:</strong> For TTS to work, ensure the target language is supported by the TTS model.
                    Supported languages include: en, hi, ta, te, kn, ml, bn, gu, mr, pa
                  </AlertDescription>
                </Alert>

                {/* Image Type Selection */}
                <FormControl>
                  <FormLabel>Pipeline Type</FormLabel>
                  <Select value={pipelineType} onChange={(e) => setPipelineType(e.target.value as any)}>
                    <option value="translation">Translation Only</option>
                    <option value="translation-tts">Translation → TTS</option>
                  </Select>
                </FormControl>

                {/* Source Language */}
                <FormControl>
                  <FormLabel>Source Language</FormLabel>
                  <Select value={sourceLanguage} onChange={(e) => setSourceLanguage(e.target.value)}>
                    {ASR_SUPPORTED_LANGUAGES.map((lang) => (
                      <option key={lang.code} value={lang.code}>
                        {lang.label}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                {/* Target Language */}
                <FormControl>
                  <FormLabel>Target Language</FormLabel>
                  <Select value={targetLanguage} onChange={(e) => setTargetLanguage(e.target.value)}>
                    {TTS_SUPPORTED_LANGUAGES.map((lang) => (
                      <option key={lang.code} value={lang.code}>
                        {lang.label}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                {/* NMT Service ID */}
                <FormControl>
                  <FormLabel>NMT Service ID</FormLabel>
                  <Select value={nmtServiceId} onChange={(e) => setNmtServiceId(e.target.value)}>
                    <option value="ai4bharat/indictrans-v2-all-gpu--tensorrt">
                      ai4bharat/indictrans-v2-all-gpu--tensorrt
                    </option>
                  </Select>
                </FormControl>

                {/* TTS Service ID (if TTS is enabled) */}
                {pipelineType === 'translation-tts' && (
                  <FormControl>
                    <FormLabel>TTS Service ID</FormLabel>
                    <Select value={ttsServiceId} onChange={(e) => setTtsServiceId(e.target.value)}>
                      <option value="ai4bharat/indic-tts-coqui-indo-aryan-gpu">
                        ai4bharat/indic-tts-coqui-indo-aryan-gpu
                      </option>
                    </Select>
                  </FormControl>
                )}

                {/* Input Text */}
                <FormControl>
                  <FormLabel>Input Text</FormLabel>
                  <Textarea
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    placeholder="Enter text to translate..."
                    rows={6}
                    resize="vertical"
                  />
                </FormControl>

                {/* Run Button */}
                <Button
                  colorScheme="blue"
                  size="lg"
                  onClick={handleRunPipeline}
                  isLoading={isLoading}
                  loadingText="Running Pipeline..."
                >
                  Run Pipeline
                </Button>
              </VStack>
              </Box>
            </GridItem>

            {/* Results Panel */}
            <GridItem minW="0">
              <VStack spacing={6} align="stretch" w="100%">
                <Box>
                  <Heading size="md" mb={2} userSelect="none" cursor="default" tabIndex={-1}>Pipeline Results</Heading>
                  <Text fontSize="sm" color="gray.600" userSelect="none" cursor="default">
                    View translated text, audio output, and raw API response
                  </Text>
                </Box>

                {isLoading && (
                  <Alert status="info">
                    <AlertIcon />
                    <AlertDescription>Executing pipeline tasks...</AlertDescription>
                  </Alert>
                )}

                {result && (
                  <>
                    {/* Translation Output */}
                    <Box>
                      <Text mb={2} fontSize="sm" fontWeight="semibold" color="gray.700">
                        Translated Text
                      </Text>
                      <Box
                        p={4}
                        bg="blue.50"
                        borderRadius="md"
                        border="1px"
                        borderColor="blue.200"
                        minH="100px"
                      >
                        {result?.targetText || 'No translation output'}
                      </Box>
                    </Box>

                    {/* Audio Output (if TTS) */}
                    {pipelineType === 'translation-tts' && result?.audio && (
                      <Box>
                        <Text mb={2} fontSize="sm" fontWeight="semibold" color="gray.700">
                          Generated Audio
                        </Text>
                        <Box
                          p={4}
                          bg="green.50"
                          borderRadius="md"
                          border="1px"
                          borderColor="green.200"
                        >
                          <audio 
                            controls 
                            src={result.audio} 
                            style={{ width: '100%' }}
                          />
                        </Box>
                        <Text mt={2} fontSize="xs" color="gray.500">
                          Audio format: WAV | Language: {targetLanguage}
                        </Text>
                      </Box>
                    )}

                    {/* Raw Response */}
                    <Box>
                      <Text mb={2} fontSize="sm" fontWeight="semibold" color="gray.700">
                        Raw API Response
                      </Text>
                      <Box
                        p={4}
                        bg="gray.50"
                        borderRadius="md"
                        border="1px"
                        borderColor="gray.300"
                        maxH="400px"
                        overflowY="auto"
                      >
                        <Code whiteSpace="pre-wrap" fontSize="xs">
                          {rawResponse}
                        </Code>
                      </Box>
                    </Box>
                  </>
                )}

                {!result && !isLoading && (
                  <Alert status="info">
                    <AlertIcon />
                    <AlertDescription>Run the pipeline to see results here</AlertDescription>
                  </Alert>
                )}
              </VStack>
            </GridItem>
          </Grid>
        </VStack>
      </ContentLayout>
    </>
  );
};

export default PipelineBuilderPage;

