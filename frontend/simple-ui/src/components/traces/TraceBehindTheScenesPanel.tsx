import {
  Box,
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
import { FiLayers } from "react-icons/fi";
import type { Trace } from "../../services/observabilityService";
import type { ProcessedSpan } from "../../lib/traces";
import BehindTheScenesStepCard from "./BehindTheScenesStepCard";
import type { SpanRelationships } from "./types";

interface TraceBehindTheScenesPanelProps {
  traceDetails: Trace;
  processedSpans: ProcessedSpan[];
  spanRelationships: SpanRelationships;
  traceStatus: { status: "success" | "error" | "warning"; message: string };
  expandedTags: Set<string>;
  setExpandedTags: React.Dispatch<React.SetStateAction<Set<string>>>;
}

export default function TraceBehindTheScenesPanel({
  traceDetails,
  processedSpans,
  spanRelationships,
  traceStatus,
  expandedTags,
  setExpandedTags,
}: TraceBehindTheScenesPanelProps) {
  const cardBg = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("gray.200", "gray.700");

  return (
    <GridItem minW="0">
      <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" h="full">
        <CardBody>
          <VStack spacing={4} align="stretch">
            <Box>
              <HStack spacing={2} align="center" mb={1}>
                <Icon as={FiLayers} color="purple.500" boxSize={5} />
                <Heading size="sm" color="gray.700">
                  Behind the Scenes
                </Heading>
              </HStack>
              <Text fontSize="xs" color="gray.500" pl={7}>
                (What the orchestrator does)
              </Text>
            </Box>

            <Divider />

            <VStack spacing={3} align="stretch">
              {processedSpans.length > 0 ? (
                processedSpans.map((processed, idx) => (
                  <BehindTheScenesStepCard
                    key={processed.span.spanID || idx}
                    processed={processed}
                    idx={idx}
                    processedSpans={processedSpans}
                    spanRelationships={spanRelationships}
                    traceStatus={traceStatus}
                    expandedTags={expandedTags}
                    setExpandedTags={setExpandedTags}
                  />
                ))
              ) : traceDetails.spans && traceDetails.spans.length > 0 ? (
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
                  No processing steps available
                </Text>
              )}
            </VStack>
          </VStack>
        </CardBody>
      </Card>
    </GridItem>
  );
}
