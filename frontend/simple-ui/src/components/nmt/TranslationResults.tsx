// NMT results display component with stats

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
  Box,
  Text,
} from '@chakra-ui/react';
import { FaCopy } from 'react-icons/fa';
import { TranslationResultsProps } from '../../types/nmt';
import { showToast } from '../../utils/toast';

const TranslationResults: React.FC<TranslationResultsProps> = ({
  sourceText,
  translatedText,
  requestWordCount,
  responseWordCount,
  responseTime,
  confidence,
  onCopySource,
  onCopyTranslation,
}) => {
  const handleCopySource = () => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(sourceText).then(() => {
        showToast({ type: "success", message: "Source text copied to clipboard." });
        onCopySource?.();
      }).catch(() => {
        fallbackCopy(sourceText);
      });
    } else {
      fallbackCopy(sourceText);
    }
  };

  const handleCopyTranslation = () => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(translatedText).then(() => {
        showToast({ type: "success", message: "Translation copied to clipboard." });
        onCopyTranslation?.();
      }).catch(() => {
        fallbackCopy(translatedText);
      });
    } else {
      fallbackCopy(translatedText);
    }
  };

  const fallbackCopy = (text: string) => {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    document.body.appendChild(textArea);
    textArea.select();
    try {
      document.execCommand('copy');
      showToast({ type: "success", message: "Text copied to clipboard." });
    } catch (err) {
      showToast({ type: "error", message: "Failed to copy text to clipboard." });
    }
    document.body.removeChild(textArea);
  };

  if (!sourceText || !translatedText) {
    return (
      <Box p={8} textAlign="center" color="gray.500">
        <Text>No translation available</Text>
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
        {/* Request Word Count Stat */}
        <Stat textAlign="center">
          <StatLabel>Request word count</StatLabel>
          <StatNumber color="orange.600">{requestWordCount}</StatNumber>
        </Stat>

        {/* Response Word Count Stat */}
        <Stat textAlign="center">
          <StatLabel>Response word count</StatLabel>
          <StatNumber color="orange.600">{responseWordCount}</StatNumber>
        </Stat>

        {/* Response Time Stat */}
        <Stat textAlign="center">
          <StatLabel>Response time</StatLabel>
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

      {/* Action Buttons */}
      <HStack spacing={4} w="full" justify="center">
        <Button
          leftIcon={<FaCopy />}
          size="sm"
          variant="outline"
          onClick={handleCopySource}
        >
          Copy Source
        </Button>
        <Button
          leftIcon={<FaCopy />}
          size="sm"
          variant="outline"
          onClick={handleCopyTranslation}
        >
          Copy Translation
        </Button>
      </HStack>
    </VStack>
  );
};

export default TranslationResults;
