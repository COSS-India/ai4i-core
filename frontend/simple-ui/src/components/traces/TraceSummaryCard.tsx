import {
  Box,
  Badge,
  Card,
  CardBody,
  Heading,
  HStack,
  Icon,
  Text,
  VStack,
  useColorModeValue,
} from "@chakra-ui/react";
import { CheckCircleIcon } from "@chakra-ui/icons";
import type { Trace } from "../../services/observabilityService";
import type { ProcessedSpan } from "../../lib/traces";
import {
  formatDuration,
  formatTimestamp,
  getClientIP,
  getMainOperation,
  getServiceName,
} from "../../lib/traces";

interface TraceSummaryCardProps {
  traceDetails: Trace;
  processedSpans: ProcessedSpan[];
  traceStatus: { status: "success" | "error" | "warning"; message: string };
  primaryErrorMessage: string | null;
  traceStartTime: number | undefined;
  traceDuration: number | undefined;
}

export default function TraceSummaryCard({
  traceDetails,
  processedSpans,
  traceStatus,
  primaryErrorMessage,
  traceStartTime,
  traceDuration,
}: TraceSummaryCardProps) {
  const borderColor = useColorModeValue("gray.200", "gray.700");
  const bgGradient = useColorModeValue(
    "linear(to-br, blue.50, purple.50)",
    "linear(to-br, gray.900, gray.800)"
  );
  const clientIp = getClientIP(traceDetails);

  return (
    <Card bgGradient={bgGradient} border="1px" borderColor={borderColor} boxShadow="md" w="full">
      <CardBody>
        <VStack spacing={4} align="stretch">
          <Box>
            <Heading size="md" mb={2} color="gray.800">
              {getServiceName(traceDetails)}: {getMainOperation(traceDetails)}
            </Heading>
            <Text fontFamily="mono" fontSize="xs" color="gray.600">
              Trace ID: {traceDetails.traceID}
            </Text>
          </Box>

          <HStack spacing={6} flexWrap="wrap" align="flex-start">
            <SummaryField label="Started" value={formatTimestamp(traceStartTime)} />
            <SummaryField label="Duration" value={formatDuration(traceDuration)} />
            <SummaryField label="Steps" value={String(processedSpans.length)} />
            {clientIp && <SummaryField label="Client IP" value={clientIp} mono />}
            <Box minH="50px" display="flex" flexDirection="column" flex={1} minW="200px">
              <Text fontSize="xs" color="gray.600" mb={1}>
                Status
              </Text>
              <HStack spacing={2} align="center" flexWrap="wrap">
                <Badge
                  colorScheme={
                    traceStatus.status === "success"
                      ? "green"
                      : traceStatus.status === "error"
                        ? "red"
                        : "yellow"
                  }
                  fontSize="sm"
                  px={2}
                  py={1}
                  display="inline-flex"
                  alignItems="center"
                  height="fit-content"
                  lineHeight="1.5"
                >
                  {traceStatus.status === "success" && (
                    <Icon as={CheckCircleIcon} mr={1} boxSize={3} />
                  )}
                  {traceStatus.message}
                </Badge>
                {traceStatus.status === "error" && primaryErrorMessage && (
                  <Text
                    fontSize="xs"
                    color="red.600"
                    fontWeight="bold"
                    bg="red.50"
                    px={2}
                    py={1}
                    borderRadius="md"
                    border="1px solid"
                    borderColor="red.200"
                    maxW="500px"
                  >
                    {primaryErrorMessage}
                  </Text>
                )}
              </HStack>
            </Box>
          </HStack>
        </VStack>
      </CardBody>
    </Card>
  );
}

function SummaryField({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <Box minH="50px">
      <Text fontSize="xs" color="gray.600" mb={1}>
        {label}
      </Text>
      <Text
        fontSize="sm"
        fontWeight="medium"
        color="gray.700"
        fontFamily={mono ? "mono" : undefined}
      >
        {value}
      </Text>
    </Box>
  );
}
