import {
  Alert,
  AlertDescription,
  AlertIcon,
  Badge,
  Box,
  Center,
  Code,
  SimpleGrid,
  Spinner,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import { useQuery } from "@tanstack/react-query";
import StandardModal from "../common/StandardModal";
import { useAdminTableSurface } from "../common/TableControls";
import { getTelemetryTraceById } from "../../services/observabilityService";
import { INSTITUTION } from "../../config/constants";
import type { TelemetrySpan } from "../../types/observability";

export type TelemetryTraceDetailModalProps = {
  traceId: string | null;
  isOpen: boolean;
  onClose: () => void;
};

function formatTimestamp(value: string): string {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function spanStatusColor(span: TelemetrySpan): string {
  const status = String(span.attributes?.status ?? "").toLowerCase();
  if (status === "success" || status === "ok") return "green";
  if (status === "fail" || status === "error" || status === "failure") return "red";
  return "gray";
}

function formatAttributes(attrs: Record<string, unknown>): string {
  try {
    return JSON.stringify(attrs, null, 2);
  } catch {
    return String(attrs);
  }
}

const TelemetryTraceDetailModal: React.FC<TelemetryTraceDetailModalProps> = ({
  traceId,
  isOpen,
  onClose,
}) => {
  const { tableBg, tableHeaderBg, borderColor } = useAdminTableSurface();

  const { data, isLoading, error } = useQuery({
    queryKey: ["telemetry-trace-detail", traceId],
    queryFn: () => getTelemetryTraceById(traceId!),
    enabled: isOpen && !!traceId,
    staleTime: 60 * 1000,
  });

  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title="Trace details"
      size="4xl"
      bodyProps={{ maxH: "75vh", overflowY: "auto" }}
    >
      {isLoading ? (
        <Center py={10}>
          <VStack spacing={3}>
            <Spinner size="lg" color="blue.500" />
            <Text color="gray.600" fontSize="sm">
              Loading trace…
            </Text>
          </VStack>
        </Center>
      ) : error ? (
        <Alert status="error" borderRadius="md">
          <AlertIcon />
          <AlertDescription>{(error as Error).message || "Failed to load trace"}</AlertDescription>
        </Alert>
      ) : data ? (
        <VStack align="stretch" spacing={5}>
          <Box>
            <Text fontSize="xs" color="gray.500" fontWeight="medium" mb={1}>
              Trace ID
            </Text>
            <Code fontSize="sm" p={2} borderRadius="md" display="block" whiteSpace="pre-wrap">
              {data.trace_id}
            </Code>
          </Box>

          <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} spacing={4}>
            <MetaField label="Service" value={data.service || "—"} />
            <MetaField label={INSTITUTION} value={data.tenant_id || "—"} />
            <MetaField label="Environment" value={data.environment || "—"} />
            <MetaField label="Version" value={data.service_version || "—"} />
            <MetaField label="Hostname" value={data.hostname || "—"} />
            <MetaField label="Spans" value={String(data.spans.length)} />
          </SimpleGrid>

          <Box borderWidth="1px" borderColor={borderColor} borderRadius="md" overflow="hidden">
            <Table variant="simple" size="sm" bg={tableBg}>
              <Thead bg={tableHeaderBg}>
                <Tr>
                  <Th>Span</Th>
                  <Th>Timestamp</Th>
                  <Th isNumeric>Duration (ms)</Th>
                  <Th>Status</Th>
                </Tr>
              </Thead>
              <Tbody>
                {data.spans.map((span, index) => (
                  <Tr key={span.context?.span_id ?? `${span.name}-${index}`}>
                    <Td>
                      <Text fontWeight="medium" fontSize="sm">
                        {span.name}
                      </Text>
                      {span.context?.span_id ? (
                        <Text fontSize="xs" color="gray.500" fontFamily="mono">
                          {span.context.span_id}
                        </Text>
                      ) : null}
                    </Td>
                    <Td fontSize="sm" color="gray.600">
                      {span.timestamp ? formatTimestamp(span.timestamp) : "—"}
                    </Td>
                    <Td isNumeric fontSize="sm">
                      {span.attributes?.total_time_ms != null
                        ? Number(span.attributes.total_time_ms).toLocaleString(undefined, {
                            maximumFractionDigits: 2,
                          })
                        : "—"}
                    </Td>
                    <Td>
                      {span.attributes?.status != null ? (
                        <Badge colorScheme={spanStatusColor(span)} fontSize="xs">
                          {String(span.attributes.status)}
                        </Badge>
                      ) : (
                        <Text color="gray.400" fontSize="sm">
                          —
                        </Text>
                      )}
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </Box>

          <VStack align="stretch" spacing={3}>
            <Text fontSize="sm" fontWeight="semibold" color="gray.700">
              Span attributes
            </Text>
            {data.spans.map((span, index) => (
              <Box key={`attrs-${span.context?.span_id ?? index}`}>
                <Text fontSize="xs" fontWeight="medium" color="gray.600" mb={1}>
                  {span.name}
                </Text>
                <Code
                  display="block"
                  whiteSpace="pre-wrap"
                  fontSize="xs"
                  p={3}
                  borderRadius="md"
                  bg="gray.50"
                  maxH="200px"
                  overflowY="auto"
                >
                  {formatAttributes(span.attributes ?? {})}
                </Code>
              </Box>
            ))}
          </VStack>
        </VStack>
      ) : null}
    </StandardModal>
  );
};

function MetaField({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Text fontSize="xs" color="gray.500" fontWeight="medium" mb={0.5}>
        {label}
      </Text>
      <Text fontSize="sm" color="gray.800">
        {value}
      </Text>
    </Box>
  );
}

export default TelemetryTraceDetailModal;
