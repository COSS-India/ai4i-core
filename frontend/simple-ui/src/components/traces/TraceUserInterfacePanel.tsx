import {
  Box,
  Badge,
  Card,
  CardBody,
  Divider,
  GridItem,
  Heading,
  HStack,
  Icon,
  Text,
  VStack,
  useColorModeValue,
} from "@chakra-ui/react";
import { FiClock, FiEye, FiGlobe, FiInfo } from "react-icons/fi";
import type { Trace } from "../../services/observabilityService";
import type { ProcessedSpan } from "../../lib/traces";
import {
  formatDuration,
  formatRelativeTime,
  getMainOperation,
  getServiceName,
  getUserFriendlyDescription,
} from "../../lib/traces";

interface TraceUserInterfacePanelProps {
  traceDetails: Trace;
  processedSpans: ProcessedSpan[];
}

export default function TraceUserInterfacePanel({
  traceDetails,
  processedSpans,
}: TraceUserInterfacePanelProps) {
  const cardBg = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("gray.200", "gray.700");

  return (
    <GridItem minW="0">
      <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" h="full">
  <CardBody>
    <VStack spacing={4} align="stretch">
      <Box>
        <HStack spacing={2} align="center" mb={1}>
          <Icon as={FiEye} color="blue.500" boxSize={5} />
          <Heading size="sm" color="gray.700">
            User Interface
          </Heading>
        </HStack>
        <Text fontSize="xs" color="gray.500" pl={7}>
          (What the user sees)
  </Text>
</Box>

      <Divider />

      {/* Request Summary */}
      <Box>
        <HStack mb={2} align="center">
          <Icon as={FiInfo} color="blue.500" boxSize={4} />
          <Text fontSize="sm" fontWeight="medium" color="gray.600">
            Request Summary
          </Text>
        </HStack>
        <Box p={4} bg="blue.50" borderRadius="md" border="1px" borderColor="blue.200" boxShadow="sm">
          <VStack align="start" spacing={2}>
            <HStack spacing={2} align="center">
              <Icon as={FiGlobe} color="blue.600" boxSize={4} />
              <Text fontSize="sm" fontWeight="semibold" color="blue.800">
                {getServiceName(traceDetails)}: {getMainOperation(traceDetails)}
              </Text>
            </HStack>
            <HStack spacing={2} align="center" pl={6}>
              <Text fontSize="xs" color="blue.600" fontFamily="mono">
                ID: {traceDetails.traceID.slice(0, 16)}...
              </Text>
            </HStack>
          </VStack>
        </Box>
      </Box>

      {/* Activity Log */}
      <Box>
        <HStack mb={2} align="center">
          <Icon as={FiClock} color="orange.500" boxSize={4} />
          <Text fontSize="sm" fontWeight="medium" color="gray.600">
            Activity Log
          </Text>
        </HStack>
        <VStack spacing={2} align="stretch" maxH="400px" overflowY="auto">
          {processedSpans && processedSpans.length > 0 ? (
            processedSpans.map((processed: ProcessedSpan, idx: number) => {
              const relativeTime = formatRelativeTime(processed.relativeStart);
              const duration = formatDuration(processed.effectiveDuration ?? processed.span.duration);
              return (
                <Box
                  key={idx}
          p={3}
                  bg={processed.hasError ? "red.50" : "white"}
                  borderRadius="md"
                  borderLeft="4px solid"
                  borderLeftColor={
                    processed.hasError || processed.category === "error" ? "red.500" :
                    processed.category === "auth" ? "green.500" :
                    processed.category === "processing" ? "blue.500" :
                    processed.category === "routing" ? "purple.500" :
                    "gray.400"
                  }
                  boxShadow="sm"
                  _hover={{ boxShadow: "md", transform: "translateX(2px)" }}
          transition="all 0.2s"
        >
                  <HStack justify="space-between" mb={2} align="start">
                    <HStack spacing={2} align="center">
                      <Icon
                        as={processed.icon}
                        color={
                          processed.hasError || processed.category === "error" ? "red.500" :
                          processed.category === "auth" ? "green.500" :
                          processed.category === "processing" ? "blue.500" :
                          processed.category === "routing" ? "purple.500" :
                          "gray.500"
                        }
                        boxSize={4}
                      />
                      <VStack align="start" spacing={0}>
                        <HStack spacing={2} align="center" flexWrap="wrap">
                          <Text fontSize="sm" color={processed.hasError ? "red.700" : "gray.700"} fontWeight="semibold">
                            {processed.displayName}
                          </Text>
                          {processed.hasError && (
                            <>
                              <Badge colorScheme="red" fontSize="xx-small" px={1.5} py={0.5} borderRadius="full">
                                FAILED
                              </Badge>
                              {processed.errorMessage && (
                                <Text
                                  fontSize="xs"
                                  color="red.600"
                                  fontWeight="bold"
                                  bg="red.50"
                                  px={2}
                                  py={0.5}
                                  borderRadius="md"
                                  border="1px solid"
                                  borderColor="red.200"
                                >
                                  {processed.errorMessage}
                                </Text>
                              )}
                            </>
                          )}
                        </HStack>
                        <Text fontSize="xs" color="gray.500" fontFamily="mono">
                          +{relativeTime} since start
              </Text>
                      </VStack>
                    </HStack>
                    <Badge fontSize="xs" colorScheme={processed.hasError ? "red" : "orange"} px={2} py={1} borderRadius="full" textTransform="none">
                      {duration}
                </Badge>
              </HStack>
                  <Text fontSize="xs" color={processed.hasError ? "red.700" : "gray.600"} pl={6} fontWeight={processed.hasError ? "medium" : "normal"}>
                    {processed.hasError && processed.errorMessage
                      ? `❌ ${processed.errorMessage}`
                      : getUserFriendlyDescription(processed)}
              </Text>
        </Box>
              );
            })
          ) : traceDetails?.spans && traceDetails.spans.length > 0 ? (
            <Box>
              <Text fontSize="sm" color="orange.600" textAlign="center" py={2} fontWeight="medium">
                ⚠️ Spans found but not processed
    </Text>
              <Text fontSize="xs" color="gray.500" textAlign="center">
                Check browser console for details. Total spans: {traceDetails.spans.length}
    </Text>
            </Box>
) : (
            <Text fontSize="sm" color="gray.500" textAlign="center" py={4}>
              Waiting for activity...
    </Text>
    )}
  </VStack>
  </Box>
    </VStack>
      </CardBody>
    </Card>
    </GridItem>
  );
}
