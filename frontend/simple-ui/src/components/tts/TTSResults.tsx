// TTS results display component with stats and audio player

import React from 'react';
import {
  VStack,
  SimpleGrid,
  Stat,
  StatLabel,
  StatNumber,
  StatHelpText,
  Button,
  HStack,
  useToast,
  Box,
  Text,
} from '@chakra-ui/react';
import { FaPlay, FaPause, FaDownload } from 'react-icons/fa';
import { TTSResultsProps } from '../../types/tts';

const TTSResults: React.FC<TTSResultsProps> = ({
  audioSrc,
  wordCount,
  responseTime,
  audioDuration,
  onPlay,
  onPause,
  onDownload,
}) => {
  const toast = useToast();

  const handleDownload = () => {
    if (!audioSrc) return;

    try {
      const link = document.createElement('a');
      link.href = audioSrc;
      link.download = `tts_audio_${Date.now()}.wav`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      toast({
        title: 'Download Started',
        description: 'Audio file downloaded successfully.',
        status: 'success',
        duration: 2000,
        isClosable: true,
      });
      onDownload?.();
    } catch (error) {
      console.error('Download error:', error);
      toast({
        title: 'Download Failed',
        description: 'Failed to download audio file.',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    }
  };

  if (!audioSrc) {
    return (
      <Box p={8} textAlign="center" color="gray.500">
        <Text>No audio generated</Text>
      </Box>
    );
  }

  return (
    <VStack spacing={5} w="full">
      {/* Stats Grid */}
      <SimpleGrid
        columns={{ base: 1, md: 2 }}
        spacing={{ base: 4, md: 8 }}
        w="full"
        p="1rem"
        bg="orange.100"
        borderRadius="15px"
      >
        {/* Request word count */}
        <Stat textAlign="center">
          <StatLabel>Request word count</StatLabel>
          <StatNumber color="orange.600">{wordCount}</StatNumber>
        </Stat>

        {/* Response Time Stat */}
        <Stat textAlign="center">
          <StatLabel>Response Time</StatLabel>
          <StatNumber color="orange.600">
            {(responseTime / 1000).toFixed(2)}s
          </StatNumber>
          <StatHelpText>seconds</StatHelpText>
        </Stat>

        {/* Audio Duration Stat */}
        <Stat textAlign="center" gridColumn={{ base: '1', md: '1 / -1' }}>
          <StatLabel>TTS Audio Duration</StatLabel>
          <StatNumber color="orange.600">
            {audioDuration.toFixed(2)}s
          </StatNumber>
          <StatHelpText>seconds</StatHelpText>
        </Stat>
      </SimpleGrid>

      {/* Audio Player */}
      <VStack spacing={4} w="full">
        <HStack justify="space-between" w="full">
          <Text fontSize="lg" fontWeight="semibold" color="gray.700">
            Generated Audio
          </Text>
          <HStack spacing={2}>
            <Button
              leftIcon={<FaDownload />}
              size="sm"
              variant="outline"
              onClick={handleDownload}
            >
              Download
            </Button>
          </HStack>
        </HStack>

        {/* HTML5 Audio Player */}
        <Box w="full" maxW="600px">
          <audio
            controls
            style={{ width: '100%' }}
            src={audioSrc}
            preload="metadata"
          >
            Your browser does not support the audio element.
          </audio>
        </Box>
      </VStack>
    </VStack>
  );
};

export default TTSResults;
