// Human-friendly OCR result display with plain text, confidence, and line details

import React from "react";
import {
  Accordion,
  AccordionButton,
  AccordionIcon,
  AccordionItem,
  AccordionPanel,
  Badge,
  Box,
  Code,
  HStack,
  SimpleGrid,
  Text,
  Textarea,
  VStack,
} from "@chakra-ui/react";
import type { ParsedOcrResult } from "../utils/parseOcrResult";
import { confidenceColor, formatConfidence } from "../utils/parseOcrResult";

export interface OcrResultProps {
  parsed: ParsedOcrResult;
}

const OcrResult: React.FC<OcrResultProps> = ({ parsed }) => {
  const { plainText, lines, wordCount, lineCount, averageConfidence, isStructured, rawSource } =
    parsed;

  if (!plainText) {
    return (
      <Box p={4} bg="yellow.50" borderRadius="md" border="1px" borderColor="yellow.200">
        <Text fontSize="sm" color="yellow.800" fontWeight="semibold">
          No text detected in the image.
        </Text>
      </Box>
    );
  }

  return (
    <VStack spacing={4} align="stretch" w="full">
      <Box
        p={4}
        bg="gray.50"
        borderRadius="md"
        borderWidth="1px"
        borderColor="gray.200"
        w="full"
      >
        <Text fontSize="sm" fontWeight="semibold" color="gray.700" mb={2}>
          Extracted Text
        </Text>
        <Textarea
          value={plainText}
          readOnly
          resize="none"
          minH="120px"
          fontSize="sm"
          lineHeight="tall"
          bg="white"
          _focus={{ boxShadow: "none", borderColor: "orange.300" }}
        />
      </Box>

      {isStructured && (
        <SimpleGrid columns={{ base: 2, sm: 3 }} spacing={3}>
          <Box p={3} bg="orange.50" borderRadius="md" border="1px" borderColor="orange.200">
            <Text fontSize="xs" color="gray.600" mb={1}>
              Lines
            </Text>
            <Text fontSize="lg" fontWeight="bold" color="orange.700">
              {lineCount}
            </Text>
          </Box>
          <Box p={3} bg="blue.50" borderRadius="md" border="1px" borderColor="blue.200">
            <Text fontSize="xs" color="gray.600" mb={1}>
              Words
            </Text>
            <Text fontSize="lg" fontWeight="bold" color="blue.700">
              {wordCount}
            </Text>
          </Box>
          {averageConfidence !== undefined && (
            <Box p={3} bg="green.50" borderRadius="md" border="1px" borderColor="green.200">
              <Text fontSize="xs" color="gray.600" mb={1}>
                Avg. confidence
              </Text>
              <Text fontSize="lg" fontWeight="bold" color="green.700">
                {formatConfidence(averageConfidence)}
              </Text>
            </Box>
          )}
        </SimpleGrid>
      )}

      {isStructured && lines.length > 0 && (
        <Accordion allowToggle defaultIndex={lines.length <= 6 ? [0] : undefined}>
          <AccordionItem border="1px" borderColor="gray.200" borderRadius="md" overflow="hidden">
            <AccordionButton bg="gray.50" _expanded={{ bg: "orange.50" }}>
              <Box flex="1" textAlign="left" fontSize="sm" fontWeight="semibold">
                Line-by-line details
              </Box>
              <AccordionIcon />
            </AccordionButton>
            <AccordionPanel pb={4} px={0}>
              <VStack spacing={0} align="stretch" divider={<Box borderBottom="1px" borderColor="gray.100" />}>
                {lines.map((line, index) => (
                  <HStack
                    key={`${index}-${line.text.slice(0, 24)}`}
                    px={4}
                    py={3}
                    align="start"
                    spacing={3}
                  >
                    <Text fontSize="xs" color="gray.500" fontWeight="semibold" minW="48px" pt={0.5}>
                      Line {index + 1}
                    </Text>
                    <Text flex={1} fontSize="sm" color="gray.800" whiteSpace="pre-wrap">
                      {line.text}
                    </Text>
                    {line.confidence !== undefined && (
                      <Badge
                        colorScheme={confidenceColor(line.confidence)}
                        fontSize="xs"
                        flexShrink={0}
                      >
                        {formatConfidence(line.confidence)}
                      </Badge>
                    )}
                  </HStack>
                ))}
              </VStack>
            </AccordionPanel>
          </AccordionItem>
        </Accordion>
      )}

      {rawSource && isStructured && (
        <Accordion allowToggle>
          <AccordionItem border="1px" borderColor="gray.200" borderRadius="md" overflow="hidden">
            <AccordionButton bg="gray.50" _expanded={{ bg: "gray.100" }}>
              <Box flex="1" textAlign="left" fontSize="sm" fontWeight="semibold" color="gray.600">
                Raw API response
              </Box>
              <AccordionIcon />
            </AccordionButton>
            <AccordionPanel pb={4}>
              <Box
                maxH="200px"
                overflowY="auto"
                p={3}
                bg="gray.900"
                borderRadius="md"
              >
                <Code
                  display="block"
                  whiteSpace="pre-wrap"
                  wordBreak="break-all"
                  fontSize="xs"
                  color="green.200"
                  bg="transparent"
                >
                  {rawSource}
                </Code>
              </Box>
            </AccordionPanel>
          </AccordionItem>
        </Accordion>
      )}
    </VStack>
  );
};

export default OcrResult;
