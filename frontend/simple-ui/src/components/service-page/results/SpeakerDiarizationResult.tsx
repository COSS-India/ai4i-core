import React from "react";
import { Box, HStack, Text, VStack } from "@chakra-ui/react";

export interface SpeakerDiarizationResultData {
  output?: Array<{
    segments?: Array<Record<string, unknown>>;
    speakers?: string[];
    num_speakers?: number;
    total_segments?: number;
  }>;
  segments?: Array<Record<string, unknown>>;
  speakers?: string[];
  num_speakers?: number;
  total_segments?: number;
}

interface SpeakerDiarizationResultProps {
  result: SpeakerDiarizationResultData;
}

const SpeakerDiarizationResult: React.FC<SpeakerDiarizationResultProps> = ({ result }) => {
  const outputData =
    result.output && Array.isArray(result.output) && result.output.length > 0
      ? result.output[0]
      : null;
  const data =
    outputData ||
    (result.segments !== undefined || result.speakers !== undefined ? result : null);

  if (!data) {
    return (
      <Box p={4} bg="yellow.50" borderRadius="md" border="1px" borderColor="yellow.200">
        <Text fontSize="sm" color="yellow.800" fontWeight="semibold" mb={2}>
          Unexpected Response Format
        </Text>
        <Text fontSize="xs" color="yellow.700">
          The API response structure is not recognized.
        </Text>
      </Box>
    );
  }

  const segments = (data.segments || []) as Array<Record<string, unknown>>;
  const speakers = data.speakers || [];
  const numSpeakers = data.num_speakers !== undefined ? data.num_speakers : speakers.length || 0;
  const totalSegments = data.total_segments !== undefined ? data.total_segments : segments.length;

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(2);
    return mins > 0 ? `${mins}:${secs.padStart(5, "0")}` : `${secs}s`;
  };

  const getSpeakerColor = (speaker: string) => {
    const speakerIndex = speakers.indexOf(speaker);
    const colors = ["orange", "blue", "green", "purple", "pink", "teal", "cyan", "yellow"];
    return colors[speakerIndex % colors.length] || "gray";
  };

  const sortedSegments = [...segments].sort((a, b) => {
    const aStart = (a.start_time as number) ?? (a.start as number) ?? 0;
    const bStart = (b.start_time as number) ?? (b.start as number) ?? 0;
    return aStart - bStart;
  });

  return (
    <Box p={4} bg="gray.50" borderRadius="md" border="1px" borderColor="gray.200">
      <Text fontSize="sm" fontWeight="semibold" mb={3} color="gray.700">
        Diarization Results:
      </Text>
      <HStack spacing={4} mb={4}>
        <Box p={3} bg="orange.100" borderRadius="md" border="1px" borderColor="orange.300">
          <Text fontSize="xs" color="gray.600" mb={1}>
            Total Speakers
          </Text>
          <Text fontSize="lg" fontWeight="bold" color="orange.700">
            {numSpeakers}
          </Text>
        </Box>
        <Box p={3} bg="blue.100" borderRadius="md" border="1px" borderColor="blue.300">
          <Text fontSize="xs" color="gray.600" mb={1}>
            Total Segments
          </Text>
          <Text fontSize="lg" fontWeight="bold" color="blue.700">
            {totalSegments}
          </Text>
        </Box>
      </HStack>
      {segments.length === 0 && numSpeakers === 0 ? (
        <Box p={4} bg="blue.50" borderRadius="md" border="1px" borderColor="blue.200" textAlign="center">
          <Text fontSize="sm" color="blue.700" fontWeight="semibold" mb={1}>
            No Speakers Detected
          </Text>
          <Text fontSize="xs" color="blue.600">
            No speakers or segments were identified in the audio.
          </Text>
        </Box>
      ) : (
        <>
          {speakers.length > 0 && (
            <Box mb={4}>
              <Text fontSize="xs" fontWeight="semibold" color="gray.600" mb={2}>
                Identified Speakers:
              </Text>
              <HStack spacing={2} flexWrap="wrap">
                {speakers.map((speaker) => {
                  const colorScheme = getSpeakerColor(speaker);
                  return (
                    <Box
                      key={speaker}
                      px={3}
                      py={1}
                      bg={`${colorScheme}.100`}
                      borderRadius="full"
                      border="1px"
                      borderColor={`${colorScheme}.300`}
                    >
                      <Text fontSize="sm" fontWeight="semibold" color={`${colorScheme}.700`}>
                        {speaker}
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
                  const duration =
                    (segment.duration as number) ?? (endTime && startTime ? endTime - startTime : 0);
                  const speaker = (segment.speaker as string) || "Unknown";
                  const colorScheme = getSpeakerColor(speaker);
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
                            {speaker}
                          </Text>
                        </Box>
                        <Text fontSize="xs" color="gray.600">
                          Duration: {formatTime(duration as number)}
                        </Text>
                      </HStack>
                      <HStack spacing={2} fontSize="xs" color="gray.600">
                        <Text>
                          Start: {formatTime(startTime)}
                        </Text>
                        <Text>•</Text>
                        <Text>
                          End: {formatTime(endTime)}
                        </Text>
                      </HStack>
                    </Box>
                  );
                })}
              </VStack>
            </Box>
          )}
        </>
      )}
    </Box>
  );
};

export default SpeakerDiarizationResult;
