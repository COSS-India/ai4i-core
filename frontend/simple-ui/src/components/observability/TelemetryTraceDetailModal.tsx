import {
  Alert,
  AlertDescription,
  AlertIcon,
  Badge,
  Box,
  Code,
  SimpleGrid,
  Text,
  VStack,
} from "@chakra-ui/react";
import React, { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import StandardModal from "../common/StandardModal";
import DataTable, { type DataTableColumn } from "../common/table";
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

function spanDurationMs(span: TelemetrySpan): number {
  const raw = span.attributes?.total_time_ms;
  return raw != null ? Number(raw) : -1;
}

const TelemetryTraceDetailModal: React.FC<TelemetryTraceDetailModalProps> = ({
  traceId,
  isOpen,
  onClose,
}) => {
  const { data, isLoading, error } = useQuery({
    queryKey: ["telemetry-trace-detail", traceId],
    queryFn: () => getTelemetryTraceById(traceId!),
    enabled: isOpen && !!traceId,
    staleTime: 60 * 1000,
  });

  const columns = useMemo<DataTableColumn<TelemetrySpan>[]>(
    () => [
      {
        id: "span",
        header: "Span",
        sortable: true,
        sortAccessor: (span) => span.name ?? "",
        cell: (span) => (
          <>
            <Text fontWeight="medium" fontSize="sm">
              {span.name}
            </Text>
            {span.context?.span_id ? (
              <Text fontSize="xs" color="gray.500" fontFamily="mono">
                {span.context.span_id}
              </Text>
            ) : null}
          </>
        ),
      },
      {
        id: "timestamp",
        header: "Timestamp",
        sortable: true,
        sortAccessor: (span) =>
          span.timestamp ? new Date(span.timestamp).getTime() : 0,
        cell: (span) => (
          <Text fontSize="sm" color="gray.600">
            {span.timestamp ? formatTimestamp(span.timestamp) : "—"}
          </Text>
        ),
      },
      {
        id: "duration",
        header: "Duration (ms)",
        sortable: true,
        isNumeric: true,
        sortAccessor: (span) => spanDurationMs(span),
        cell: (span) => {
          const ms = span.attributes?.total_time_ms;
          return (
            <Text fontSize="sm">
              {ms != null
                ? Number(ms).toLocaleString(undefined, {
                    maximumFractionDigits: 2,
                  })
                : "—"}
            </Text>
          );
        },
      },
      {
        id: "status",
        header: "Status",
        sortable: true,
        sortAccessor: (span) => String(span.attributes?.status ?? ""),
        cell: (span) =>
          span.attributes?.status != null ? (
            <Badge colorScheme={spanStatusColor(span)} fontSize="xs">
              {String(span.attributes.status)}
            </Badge>
          ) : (
            <Text color="gray.400" fontSize="sm">
              —
            </Text>
          ),
      },
    ],
    [],
  );

  return (
    <StandardModal
      isOpen={isOpen}
      onClose={onClose}
      title="Trace details"
      size="4xl"
      bodyProps={{ maxH: "75vh", overflowY: "auto" }}
    >
      {error ? (
        <Alert status="error" borderRadius="md">
          <AlertIcon />
          <AlertDescription>
            {(error as Error).message || "Failed to load trace"}
          </AlertDescription>
        </Alert>
      ) : data || isLoading ? (
        <VStack align="stretch" spacing={5}>
          {!isLoading && data ? (
            <>
              <Box>
                <Text fontSize="xs" color="gray.500" fontWeight="medium" mb={1}>
                  Trace ID
                </Text>
                <Code
                  fontSize="sm"
                  p={2}
                  borderRadius="md"
                  display="block"
                  whiteSpace="pre-wrap"
                >
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
            </>
          ) : null}

          <DataTable
            columns={columns}
            rows={data?.spans ?? []}
            rowKey={(span) => span.context?.span_id ?? span.name}
            defaultSortKey="timestamp"
            defaultSortDirection="asc"
            isLoading={isLoading}
            isEmpty={!isLoading && (data?.spans.length ?? 0) === 0}
            emptyMessage="No spans in this trace."
            asyncStateHeight="160px"
            borderRadius="md"
            theadBg="gray.50"
            cellPy={2}
            containerMt={0}
          />

          {!isLoading && data ? (
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
          ) : null}
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
