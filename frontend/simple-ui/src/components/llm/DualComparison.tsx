// Side-by-side comparison component for LLM and NMT results

import React from 'react';
import {
  Box,
  VStack,
  HStack,
  Text,
  Stat,
  StatLabel,
  StatNumber,
  StatHelpText,
  Divider,
  Grid,
  GridItem,
  IconButton,
  useClipboard,
} from '@chakra-ui/react';
import { FaCopy } from 'react-icons/fa';

interface DualComparisonProps {
  sourceText: string;
  llmOutput: string;
  nmtOutput: string;
  requestWordCount: number;
  llmResponseWordCount: number;
  nmtResponseWordCount: number;
  llmResponseTime: number;
  nmtResponseTime: number;
}

const DualComparison: React.FC<DualComparisonProps> = ({
  sourceText,
  llmOutput,
  nmtOutput,
  requestWordCount,
  llmResponseWordCount,
  nmtResponseWordCount,
  llmResponseTime,
  nmtResponseTime,
}) => {
  const { onCopy: onCopyLLM, hasCopied: hasCopiedLLM } = useClipboard(llmOutput);
  const { onCopy: onCopyNMT, hasCopied: hasCopiedNMT } = useClipboard(nmtOutput);

  return (
    <VStack spacing={4} align="stretch">
      {/* Side-by-side Comparison */}
      <Grid templateColumns={{ base: '1fr', lg: '1fr 1fr' }} gap={4}>
        {/* LLM Output */}
        <GridItem>
          <Box>
            <HStack justify="space-between" mb={2}>
              <Text fontWeight="bold" fontSize="md" color="orange.600">
                LLM Output:
              </Text>
              <IconButton
                aria-label="Copy LLM output"
                icon={<FaCopy />}
                size="sm"
                onClick={onCopyLLM}
                variant="ghost"
              />
            </HStack>
            <Box
              p={4}
              bg="orange.50"
              borderRadius="md"
              border="1px"
              borderColor="orange.200"
              minH="200px"
              maxH="400px"
              overflowY="auto"
            >
              <Text whiteSpace="pre-wrap" wordBreak="break-word">
                {llmOutput || 'No output yet'}
              </Text>
            </Box>
          </Box>
        </GridItem>

        {/* NMT Output */}
        <GridItem>
          <Box>
            <HStack justify="space-between" mb={2}>
              <Text fontWeight="bold" fontSize="md" color="blue.600">
                NMT Output:
              </Text>
              <IconButton
                aria-label="Copy NMT output"
                icon={<FaCopy />}
                size="sm"
                onClick={onCopyNMT}
                variant="ghost"
              />
            </HStack>
            <Box
              p={4}
              bg="blue.50"
              borderRadius="md"
              border="1px"
              borderColor="blue.200"
              minH="200px"
              maxH="400px"
              overflowY="auto"
            >
              <Text whiteSpace="pre-wrap" wordBreak="break-word">
                {nmtOutput || 'No output yet'}
              </Text>
            </Box>
          </Box>
        </GridItem>
      </Grid>

      <Divider />

      {/* Statistics Row */}
      <HStack spacing={4} justify="space-around">
        <Stat>
          <StatLabel>Input Words</StatLabel>
          <StatNumber>{requestWordCount}</StatNumber>
        </Stat>
        <Stat>
          <StatLabel>LLM Words</StatLabel>
          <StatNumber>{llmResponseWordCount}</StatNumber>
        </Stat>
        <Stat>
          <StatLabel>NMT Words</StatLabel>
          <StatNumber>{nmtResponseWordCount}</StatNumber>
        </Stat>
        <Stat>
          <StatLabel>LLM Time</StatLabel>
          <StatNumber>{(llmResponseTime / 1000).toFixed(2)}s</StatNumber>
          <StatHelpText>API response time</StatHelpText>
        </Stat>
        <Stat>
          <StatLabel>NMT Time</StatLabel>
          <StatNumber>{(nmtResponseTime / 1000).toFixed(2)}s</StatNumber>
          <StatHelpText>API response time</StatHelpText>
        </Stat>
      </HStack>
    </VStack>
  );
};

export default DualComparison;

