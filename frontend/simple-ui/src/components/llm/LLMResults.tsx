// LLM results display component

import React from 'react';
import {
  Box,
  VStack,
  Text,
  HStack,
  Button,
  IconButton,
  useClipboard,
  Stat,
  StatLabel,
  StatNumber,
  StatHelpText,
  Divider,
} from '@chakra-ui/react';
import { FaCopy, FaExchangeAlt } from 'react-icons/fa';
import { LLMResultsProps } from '../../types/llm';

const LLMResults: React.FC<LLMResultsProps> = ({
  sourceText,
  outputText,
  requestWordCount,
  responseWordCount,
  responseTime,
  onCopySource,
  onCopyOutput,
  onSwapTexts,
}) => {
  const { onCopy: onCopyOutputText, hasCopied: hasCopiedOutput } = useClipboard(outputText);

  const handleCopyOutput = () => {
    onCopyOutputText();
    if (onCopyOutput) onCopyOutput();
  };

  return (
    <VStack spacing={4} align="stretch">
      {/* Output Text */}
      <Box>
        <HStack justify="space-between" mb={2}>
          <Text fontWeight="bold" fontSize="md">Output:</Text>
          <HStack>
            <IconButton
              aria-label="Copy output"
              icon={<FaCopy />}
              size="sm"
              onClick={handleCopyOutput}
              variant="ghost"
            />
            {onSwapTexts && (
              <IconButton
                aria-label="Swap texts"
                icon={<FaExchangeAlt />}
                size="sm"
                onClick={onSwapTexts}
                variant="ghost"
              />
            )}
          </HStack>
        </HStack>
        <Box
          p={4}
          bg="gray.50"
          borderRadius="md"
          border="1px"
          borderColor="gray.200"
          minH="200px"
          maxH="400px"
          overflowY="auto"
        >
          <Text whiteSpace="pre-wrap" wordBreak="break-word">
            {outputText || 'No output yet'}
          </Text>
        </Box>
      </Box>

      <Divider />

      {/* Statistics */}
      <HStack spacing={4} justify="space-around">
        <Stat>
          <StatLabel>Request word count</StatLabel>
          <StatNumber>{requestWordCount}</StatNumber>
        </Stat>
        <Stat>
          <StatLabel>Response word count</StatLabel>
          <StatNumber>{responseWordCount}</StatNumber>
        </Stat>
        <Stat>
          <StatLabel>Response time</StatLabel>
          <StatNumber>{(responseTime / 1000).toFixed(2)}s</StatNumber>
        </Stat>
      </HStack>

    </VStack>
  );
};

export default LLMResults;

