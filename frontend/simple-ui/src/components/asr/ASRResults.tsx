// ASR results display component with stats and transcript

import React from 'react';
import {
  VStack,
  SimpleGrid,
  Stat,
  StatLabel,
  StatNumber,
  StatHelpText,
  Textarea,
  Button,
  HStack,
  Box,
  Text,
} from '@chakra-ui/react';
import { FaCopy, FaDownload } from 'react-icons/fa';
import { ASRResultsProps } from '../../types/asr';
import { showToast } from '../../utils/toast';

const ASRResults: React.FC<ASRResultsProps> = ({
  transcript,
  wordCount,
  requestWordCount = 0,
  responseWordCount,
  responseTime,
  confidence,
  onCopy,
  onDownload,
}) => {
  // For backward compatibility, use wordCount if responseWordCount is not provided
  const finalResponseWordCount = responseWordCount ?? wordCount ?? 0;

  const handleCopy = () => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(transcript).then(() => {
        showToast({ type: "success", message: "Transcript copied to clipboard." });
        onCopy?.();
      }).catch(() => {
        fallbackCopy();
      });
    } else {
      fallbackCopy();
    }
  };

  const fallbackCopy = () => {
    const textArea = document.createElement('textarea');
    textArea.value = transcript;
    document.body.appendChild(textArea);
    textArea.select();
    try {
      document.execCommand('copy');
      showToast({
        type: "success",
        message: "Transcript copied to clipboard.",
      });
      onCopy?.();
    } catch (err) {
      showToast({
        type: "error",
        message: "Failed to copy transcript to clipboard.",
      });
    }
    document.body.removeChild(textArea);
  };

  const handleDownload = () => {
    try {
      const blob = new Blob([transcript], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `transcript_${Date.now()}.txt`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      showToast({
        type: "success",
        message: "Transcript downloaded successfully.",
      });
      onDownload?.();
    } catch (error) {
      console.error('Download error:', error);
      showToast({ type: "error", message: "Failed to download transcript." });
    }
  };

  if (!transcript) {
    return (
      <Box p={8} textAlign="center" color="gray.500">
        <Text>No transcript available</Text>
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
        {/* Response Word Count Stat */}
        <Stat textAlign="center">
          <StatLabel>Response Word Count</StatLabel>
          <StatNumber color="orange.600">{finalResponseWordCount}</StatNumber>
        </Stat>

        {/* Response Time Stat */}
        <Stat textAlign="center">
          <StatLabel>Response Time</StatLabel>
          <StatNumber color="orange.600">
            {(responseTime / 1000).toFixed(2)}s
          </StatNumber>
        </Stat>

        {/* Confidence Stat (if available) */}
        {confidence !== undefined && (
          <Stat textAlign="center" gridColumn={{ base: '1', md: '1 / -1' }}>
            <StatLabel>Confidence</StatLabel>
            <StatNumber color="orange.600">
              {(confidence * 100).toFixed(1)}%
            </StatNumber>
            <StatHelpText>Accuracy</StatHelpText>
          </Stat>
        )}
      </SimpleGrid>

      {/* Transcript Display */}
      <VStack spacing={3} w="full">
        <HStack justify="space-between" w="full">
          <Text fontSize="lg" fontWeight="semibold" color="gray.700">
            Transcript
          </Text>
          <HStack spacing={2}>
            <Button
              leftIcon={<FaCopy />}
              size="sm"
              variant="outline"
              onClick={handleCopy}
            >
              Copy
            </Button>
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

        <Textarea
          value={transcript}
          readOnly
          h="200px"
          resize="none"
          placeholder="Transcript will appear here..."
          fontSize="sm"
          _focus={{
            boxShadow: 'none',
            borderColor: 'orange.300',
          }}
        />
      </VStack>
    </VStack>
  );
};

export default ASRResults;
