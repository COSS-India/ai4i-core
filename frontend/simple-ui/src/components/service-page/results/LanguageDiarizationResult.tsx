import React from "react";
import { Box, HStack, Text, VStack } from "@chakra-ui/react";

export interface LanguageDiarizationResultData {
  output?: Array<{
    segments?: Array<Record<string, unknown>>;
    languages?: string[];
    num_languages?: number;
  }>;
  segments?: Array<Record<string, unknown>>;
  languages?: string[];
  num_languages?: number;
}

interface LanguageDiarizationResultProps {
  result: LanguageDiarizationResultData;
}

const LanguageDiarizationResult: React.FC<LanguageDiarizationResultProps> = ({ result }) => {
  const data = result.output?.[0] ?? result;
  const segments = (data.segments || []) as Array<Record<string, unknown>>;
  const languages = data.languages || [];
  const uniqueLanguages =
    languages.length > 0
      ? languages
      : Array.from(new Set(segments.map((s) => s.language as string).filter(Boolean)));
  const numLanguages = data.num_languages || uniqueLanguages.length || 0;

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(2);
    return mins > 0 ? `${mins}:${secs.padStart(5, "0")}` : `${secs}s`;
  };

  const getLanguageColor = (language: string) => {
    const languageIndex = uniqueLanguages.indexOf(language);
    const colors = ["orange", "blue", "green", "purple", "pink", "teal", "cyan", "yellow"];
    return colors[languageIndex % colors.length] || "gray";
  };

  const sortedSegments = [...segments].sort((a, b) => {
    const aStart = (a.start_time as number) ?? (a.start as number) ?? 0;
    const bStart = (b.start_time as number) ?? (b.start as number) ?? 0;
    return aStart - bStart;
  });

  const hasStructuredData = segments.length > 0 || numLanguages > 0;

  return (
    <Box p={4} bg="gray.50" borderRadius="md" border="1px" borderColor="gray.200">
      <Text fontSize="sm" fontWeight="semibold" mb={3} color="gray.700">
        Language Diarization Results:
      </Text>
      {hasStructuredData ? (
        <>
          <HStack spacing={4} mb={4}>
            <Box p={3} bg="orange.100" borderRadius="md" border="1px" borderColor="orange.300">
              <Text fontSize="xs" color="gray.600" mb={1}>
                Total Languages
              </Text>
              <Text fontSize="lg" fontWeight="bold" color="orange.700">
                {numLanguages}
              </Text>
            </Box>
            <Box p={3} bg="blue.100" borderRadius="md" border="1px" borderColor="blue.300">
              <Text fontSize="xs" color="gray.600" mb={1}>
                Total Segments
              </Text>
              <Text fontSize="lg" fontWeight="bold" color="blue.700">
                {segments.length}
              </Text>
            </Box>
          </HStack>
          {uniqueLanguages.length > 0 && (
            <Box mb={4}>
              <Text fontSize="xs" fontWeight="semibold" color="gray.600" mb={2}>
                Detected Languages:
              </Text>
              <HStack spacing={2} flexWrap="wrap">
                {uniqueLanguages.map((language) => {
                  const colorScheme = getLanguageColor(language);
                  return (
                    <Box
                      key={language}
                      px={3}
                      py={1}
                      bg={`${colorScheme}.100`}
                      borderRadius="full"
                      border="1px"
                      borderColor={`${colorScheme}.300`}
                    >
                      <Text fontSize="sm" fontWeight="semibold" color={`${colorScheme}.700`}>
                        {language.toUpperCase()}
                      </Text>
                    </Box>
                  );
                })}
              </HStack>
            </Box>
          )}
          {sortedSegments.length > 0 && (
            <Box p={3} bg="white" borderRadius="md" maxH="400px" overflowY="auto" border="1px" borderColor="gray.200">
              <VStack align="stretch" spacing={2}>
                {sortedSegments.map((segment, idx) => {
                  const startTime = (segment.start_time as number) ?? (segment.start as number) ?? 0;
                  const endTime = (segment.end_time as number) ?? (segment.end as number) ?? 0;
                  const duration = (segment.duration as number) ?? endTime - startTime;
                  const language = (segment.language as string) || "Unknown";
                  const colorScheme = getLanguageColor(language);
                  return (
                    <Box
                      key={idx}
                      p={3}
                      bg={`${colorScheme}.50`}
                      borderRadius="md"
                      border="1px"
                      borderColor={`${colorScheme}.200`}
                    >
                      <HStack justify="space-between" mb={2}>
                        <Box px={2} py={1} bg={`${colorScheme}.200`} borderRadius="md">
                          <Text fontSize="xs" fontWeight="bold" color={`${colorScheme}.800`}>
                            {language.toUpperCase()}
                          </Text>
                        </Box>
                        <Text fontSize="xs" color="gray.600">
                          Duration: {formatTime(duration as number)}
                        </Text>
                      </HStack>
                      <HStack spacing={2} fontSize="xs" color="gray.600">
                        <Text>Start: {formatTime(startTime)}</Text>
                        <Text>•</Text>
                        <Text>End: {formatTime(endTime)}</Text>
                      </HStack>
                    </Box>
                  );
                })}
              </VStack>
            </Box>
          )}
        </>
      ) : (
        <Box p={3} bg="white" borderRadius="md" maxH="400px" overflowY="auto">
          <Text as="pre" fontSize="xs" whiteSpace="pre-wrap" wordBreak="break-word">
            {JSON.stringify(result, null, 2)}
          </Text>
        </Box>
      )}
    </Box>
  );
};

export default LanguageDiarizationResult;
