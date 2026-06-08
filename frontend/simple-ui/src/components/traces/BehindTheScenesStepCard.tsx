import {
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  Collapse,
  HStack,
  Icon,
  Text,
  VStack,
  useColorModeValue,
} from "@chakra-ui/react";
import { CheckCircleIcon } from "@chakra-ui/icons";
import {
  FiCheckCircle,
  FiEye,
  FiEyeOff,
  FiInfo,
  FiLayers,
  FiSettings,
} from "react-icons/fi";
import type { ProcessedSpan } from "../../lib/traces";
import {
  formatDuration,
  formatTagValue,
  getUserFriendlyDescription,
  parseErrorDetails,
} from "../../lib/traces";
import { mergeSpanTags } from "./spanTagMerge";
import type { SpanRelationships } from "./types";

interface BehindTheScenesStepCardProps {
  processed: ProcessedSpan;
  idx: number;
  processedSpans: ProcessedSpan[];
  spanRelationships: SpanRelationships;
  traceStatus: { status: "success" | "error" | "warning"; message: string };
  expandedTags: Set<string>;
  setExpandedTags: React.Dispatch<React.SetStateAction<Set<string>>>;
}

export default function BehindTheScenesStepCard({
  processed,
  idx,
  processedSpans,
  spanRelationships,
  traceStatus,
  expandedTags,
  setExpandedTags,
}: BehindTheScenesStepCardProps) {
  const borderColor = useColorModeValue("gray.200", "gray.700");
  const duration = formatDuration(processed.effectiveDuration ?? processed.span.duration);
  const {
    relevantTags,
    indentPx,
    hasSignificantOverhead,
    childSpans,
    childSpansDuration,
    parentDuration,
    overheadTime,
  } = mergeSpanTags(processed, spanRelationships, processedSpans);

  return (
<Card
  bg={processed.hasError ? "red.50" : "white"}
  border="1px"
  borderColor={processed.hasError ? "red.300" : borderColor}
  borderLeft={processed.hasError ? "4px solid" : "1px"}
  borderLeftColor={processed.hasError ? "red.500" : undefined}
  boxShadow="sm"
  borderRadius="lg"
  overflow="hidden"
  ml={indentPx > 0 ? `${indentPx}px` : 0}
  _hover={{
    bg: processed.hasError ? "red.50" : "blue.50",
    borderColor: processed.hasError ? "red.300" : "blue.300",
    boxShadow: "md",
    transform: "translateY(-2px)",
    transition: "all 0.2s"
  }}
  transition="all 0.2s"
  cursor="pointer"
>
  <CardBody>
    <VStack spacing={3} align="stretch">
      {/* Header with icon and title */}
      <HStack spacing={3} align="start">
        <Box
          p={2.5}
          borderRadius="lg"
          bg={
            processed.hasError || processed.category === "error" ? "red.50" :
            processed.category === "auth" ? "green.50" :
            processed.category === "processing" ? "blue.50" :
            processed.category === "routing" ? "purple.50" :
            "gray.50"
          }
          border="1px"
          borderColor={
            processed.hasError || processed.category === "error" ? "red.200" :
            processed.category === "auth" ? "green.200" :
            processed.category === "processing" ? "blue.200" :
            processed.category === "routing" ? "purple.200" :
            "gray.200"
          }
          flexShrink={0}
        >
          <Icon
            as={processed.icon}
            color={
              processed.hasError || processed.category === "error" ? "red.600" :
              processed.category === "auth" ? "green.600" :
              processed.category === "processing" ? "blue.600" :
              processed.category === "routing" ? "purple.600" :
              "gray.600"
            }
            boxSize={5}
          />
                            </Box>
        <VStack align="start" spacing={1} flex={1}>
          <HStack spacing={2} align="center" w="full" flexWrap="wrap">
            <Text fontSize="sm" fontWeight="bold" color={processed.hasError ? "red.700" : "gray.700"} flex={1}>
              {processed.displayName}
</Text>
            {processed.hasError ? (
              <HStack spacing={2} align="center" flexWrap="wrap">
                <Badge colorScheme="red" fontSize="xx-small" px={2} py={0.5} borderRadius="full">
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
                    maxW="400px"
                  >
                    {processed.errorMessage}
                  </Text>
                )}
              </HStack>
            ) : traceStatus.status === "success" && (
              <Icon as={CheckCircleIcon} color="green.500" boxSize={4} />
            )}
          </HStack>
          <Badge
            fontSize="xs"
            colorScheme={
              processed.hasError || processed.category === "error" ? "red" :
              processed.category === "auth" ? "green" :
              processed.category === "processing" ? "blue" :
              processed.category === "routing" ? "purple" :
              "gray"
            }
            px={2}
            py={0.5}
            borderRadius="full"
            textTransform="none"
          >
            {duration}
          </Badge>
        </VStack>
      </HStack>

      {/* User-friendly description */}
      {(() => {
        const errorDetails = processed.hasError ? parseErrorDetails(processed) : null;

        if (errorDetails) {
          // Display structured error details
          return (
            <Box>
              {/* Error Summary */}
              <Box
                p={3}
                bg="red.50"
                borderRadius="md"
                borderLeft="4px solid"
                borderLeftColor="red.500"
                boxShadow="sm"
                mb={3}
                overflow="hidden"
                w="full"
              >
                <HStack spacing={2} mb={2} align="center">
                  <Icon as={FiInfo} color="red.600" boxSize={4} />
                  <Text fontSize="sm" color="red.700" fontWeight="bold">
                    {errorDetails.errorType}
                  </Text>
                </HStack>
                <Text
                  fontSize="xs"
                  color="red.800"
                  lineHeight="1.6"
                  pl={6}
                  fontWeight="medium"
                >
                  {errorDetails.summary}
                </Text>
              </Box>

              {/* Error Details Table */}
              {errorDetails.fields.length > 0 && (
                <Box
                  p={3}
                  bg="red.100"
                  borderRadius="md"
                  border="1px solid"
                  borderColor="red.300"
                  boxShadow="sm"
                  overflow="hidden"
                  w="full"
                >
                  <HStack spacing={2} mb={3} align="center">
                    <Icon as={FiSettings} color="red.700" boxSize={3} />
                    <Text fontSize="xs" color="red.800" fontWeight="semibold">
                      Error Details:
                    </Text>
                  </HStack>
                  <VStack spacing={2} align="stretch">
                    {errorDetails.fields.map((field, idx) => (
                      <Box
                        key={idx}
                        p={2}
                        bg="white"
                        borderRadius="sm"
                        border="1px solid"
                        borderColor="red.200"
                        overflow="hidden"
                        w="full"
                      >
                        <HStack spacing={3} align="start">
                          <Text
                            fontSize="xs"
                            fontWeight="bold"
                            color="red.700"
                            minW="120px"
                            maxW="120px"
                          >
                            {field.key}:
                          </Text>
                          <Text
                            fontSize="xs"
                            color="red.900"
                            fontFamily="mono"
                            wordBreak="break-word"
                            flex={1}
                            whiteSpace="pre-wrap"
                          >
                            {field.value}
                          </Text>
                        </HStack>
                      </Box>
                    ))}
                  </VStack>
                </Box>
              )}
            </Box>
          );
        } else {
          // Display normal description for non-error spans
          return (
            <Box
              p={3}
              bg="blue.50"
              borderRadius="md"
              borderLeft="3px solid"
              borderLeftColor="blue.400"
              boxShadow="sm"
            >
              <HStack spacing={2} mb={1} align="center">
                <Icon as={FiInfo} color="blue.600" boxSize={3} />
                <Text fontSize="xs" color="blue.700" fontWeight="medium">
                  What this step does:
                </Text>
              </HStack>
              <Text
                fontSize="xs"
                color="gray.700"
                lineHeight="1.6"
                pl={5}
              >
                {getUserFriendlyDescription(processed)}
              </Text>
            </Box>
          );
        }
      })()}

      {/* Duration overhead explanation - show when parent has significant overhead vs children */}
      {hasSignificantOverhead && (
        <Box
          p={2}
          bg="yellow.50"
          borderRadius="md"
          borderLeft="3px solid"
          borderLeftColor="yellow.400"
          boxShadow="sm"
        >
          <HStack spacing={2} align="start">
            <Icon as={FiInfo} color="yellow.700" boxSize={3} mt={0.5} flexShrink={0} />
            <VStack align="start" spacing={0.5} flex={1}>
              <Text fontSize="xs" color="yellow.800" fontWeight="medium">
                Duration Breakdown:
              </Text>
              <Text fontSize="xs" color="yellow.700" lineHeight="1.4">
                This step duration ({formatDuration(parentDuration)}) includes {childSpans.length} visible child step{childSpans.length !== 1 ? 's' : ''} ({formatDuration(childSpansDuration)}) plus {formatDuration(overheadTime)} of overhead (framework processing, middleware, network latency, and filtered spans not shown here).
              </Text>
            </VStack>
          </HStack>
        </Box>
      )}

      {/* Technical details - collapsible */}
      {relevantTags.length > 0 && (
        <Box>
          <Button
            variant="outline"
            colorScheme="gray"
            width="full"
            h="22px"
            minH="22px"
            maxH="22px"
            fontSize="10px"
            px={2}
            py={0}
            lineHeight="1.2"
            sx={{
              '& .chakra-button__icon': {
                marginInlineEnd: '6px',
              }
            }}
            leftIcon={<Icon as={expandedTags.has(processed.span.spanID) ? FiEyeOff : FiEye} boxSize={2.5} />}
            onClick={() => {
              const spanId = processed.span.spanID;
              const newExpanded = new Set(expandedTags);
              if (newExpanded.has(spanId)) {
                newExpanded.delete(spanId);
              } else {
                newExpanded.add(spanId);
              }
              setExpandedTags(newExpanded);
            }}
          >
            {expandedTags.has(processed.span.spanID)
              ? "Hide Technical Details"
              : `Show Technical Details (${relevantTags.length} tags)`}
          </Button>
          <Collapse in={expandedTags.has(processed.span.spanID)} animateOpacity>
            <Box
              mt={3}
              p={3}
              bg="gray.50"
              borderRadius="md"
              border="1px"
              borderColor="gray.200"
              boxShadow="sm"
            >
              <HStack spacing={2} mb={2} align="center">
                <Icon as={FiSettings} color="gray.600" boxSize={3} />
                <Text fontSize="xs" color="gray.700" fontWeight="semibold">
                  Technical Information:
  </Text>
              </HStack>

              <VStack spacing={2} align="stretch">
                {relevantTags.map((tag: { key: string; value: any }, tagIdx: number) => (
                  <Box
                    key={tagIdx}
                    p={2}
                    bg="white"
                    borderRadius="sm"
                    border="1px"
                    borderColor="gray.200"
                  >
                    <HStack spacing={2} align="start">
                      <Text
                        fontSize="xs"
                        color="gray.600"
                        fontWeight="medium"
                        minW="140px"
                        textTransform="uppercase"
                        letterSpacing="0.5px"
                      >
                        {tag.key}:
            </Text>
                      <Text
                        color="gray.800"
                        fontFamily="mono"
                        fontSize="xs"
                        wordBreak="break-word"
                        whiteSpace="pre-wrap"
                        flex={1}
                        maxH={tag.key.toLowerCase() === 'db.statement' ? "400px" : "none"}
                        overflowY={tag.key.toLowerCase() === 'db.statement' ? "auto" : "visible"}
                      >
                        {formatTagValue(tag.key, tag.value)}
                </Text>
            </HStack>
                  </Box>
                ))}
              </VStack>

              {/* Internal child span (e.g., triton.inference) as a separate, indented "mini span card" */}
              {/* Keep it visually isolated from the parent tag list */}
              {processed.category === "phase.triton_inference" && (
                <Box mt={6} pt={4} borderTop="1px solid" borderTopColor="gray.200">
                  <HStack spacing={2} mb={2} align="center">
                    <Icon as={FiLayers} color="gray.600" boxSize={3} />
                    <Text fontSize="xs" color="gray.700" fontWeight="semibold">
                      Internal child spans:
                    </Text>
                  </HStack>

                  {(spanRelationships.childSpans.get(processed.span.spanID) || [])
                    .map((childId: string) => spanRelationships.spanMap.get(childId))
                    .filter((s: any) => s && String(s.operationName).toLowerCase() === "triton.inference")
                    .map((s: any, i: number) => (
                      <Card
                        key={i}
                        bg="white"
                        border="1px"
                        borderColor="gray.200"
                        boxShadow="sm"
                        ml={6} // visual indent under parent span
                      >
                        <CardBody py={2}>
                          <HStack justify="space-between" align="center">
                            <HStack spacing={2} align="center">
                              <Text fontSize="sm" fontFamily="mono" color="gray.800" fontWeight="semibold">
                                {s.operationName}
                              </Text>
                            </HStack>
                            <Badge fontSize="xs" colorScheme="blue">
                              {formatDuration(s.duration)}
                            </Badge>
                          </HStack>

                          <Button
                            mt={2}
                            variant="outline"
                            colorScheme="gray"
                            width="full"
                            h="22px"
                            minH="22px"
                            maxH="22px"
                            fontSize="10px"
                            px={2}
                            py={0}
                            lineHeight="1.2"
                            leftIcon={<Icon as={expandedTags.has(s.spanID) ? FiEyeOff : FiEye} boxSize={2.5} />}
                            onClick={() => {
                              const spanId = s.spanID;
                              const newExpanded = new Set(expandedTags);
                              if (newExpanded.has(spanId)) newExpanded.delete(spanId);
                              else newExpanded.add(spanId);
                              setExpandedTags(newExpanded);
                            }}
                          >
                            {expandedTags.has(s.spanID)
                              ? "Hide Technical Details"
                              : `Show Technical Details (${(s.tags || []).length} tags)`}
                          </Button>

                          <Collapse in={expandedTags.has(s.spanID)} animateOpacity>
                            <Box mt={3} p={3} bg="gray.50" borderRadius="md" border="1px" borderColor="gray.200">
                              <VStack spacing={2} align="stretch">
                                {(s.tags || []).map((tag: { key: string; value: any }, tagIdx: number) => (
                                  <Box
                                    key={tagIdx}
                                    p={2}
                                    bg="white"
                                    borderRadius="sm"
                                    border="1px"
                                    borderColor="gray.200"
                                  >
                                    <HStack spacing={2} align="start">
                                      <Text
                                        fontSize="xs"
                                        color="gray.600"
                                        fontWeight="medium"
                                        minW="140px"
                                        textTransform="uppercase"
                                        letterSpacing="0.5px"
                                      >
                                        {tag.key}:
                                      </Text>
                                      <Text
                                        color="gray.800"
                                        fontFamily="mono"
                                        fontSize="xs"
                                        wordBreak="break-word"
                                        whiteSpace="pre-wrap"
                                        flex={1}
                                      >
                                        {formatTagValue(tag.key, tag.value)}
                                      </Text>
                                    </HStack>
                                  </Box>
                                ))}
                              </VStack>
                            </Box>
                          </Collapse>
                        </CardBody>
                      </Card>
                    ))}
                </Box>
              )}
            </Box>
          </Collapse>
        </Box>
      )}
    </VStack>
  </CardBody>
</Card>
  );
}
