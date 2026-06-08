// Trace detail panel — summary, activity log, and technical spans

import { Grid, VStack } from "@chakra-ui/react";
import TraceBehindTheScenesPanel from "./TraceBehindTheScenesPanel";
import TraceDetailStates from "./TraceDetailStates";
import TraceSummaryCard from "./TraceSummaryCard";
import TraceUserInterfacePanel from "./TraceUserInterfacePanel";
import type { TraceDetailViewProps } from "./types";

export type { TraceDetailViewProps } from "./types";

export default function TraceDetailView({
  traceDetailsLoading,
  traceError,
  traceDetails,
  processedSpans,
  traceStatus,
  primaryErrorMessage,
  traceStartTime,
  traceDuration,
  spanRelationships,
  expandedTags,
  setExpandedTags,
}: TraceDetailViewProps) {
  if (traceDetailsLoading) {
    return <TraceDetailStates variant="loading" />;
  }

  if (traceError) {
    return <TraceDetailStates variant="error" error={traceError} />;
  }

  if (!traceDetails) {
    return <TraceDetailStates variant="empty" />;
  }

  return (
    <VStack spacing={4} w="full" align="stretch">
      <TraceSummaryCard
        traceDetails={traceDetails}
        processedSpans={processedSpans}
        traceStatus={traceStatus}
        primaryErrorMessage={primaryErrorMessage}
        traceStartTime={traceStartTime}
        traceDuration={traceDuration}
      />

      <Grid templateColumns={{ base: "1fr", lg: "1fr 1fr" }} gap={6} w="full">
        <TraceUserInterfacePanel traceDetails={traceDetails} processedSpans={processedSpans} />
        <TraceBehindTheScenesPanel
          traceDetails={traceDetails}
          processedSpans={processedSpans}
          spanRelationships={spanRelationships}
          traceStatus={traceStatus}
          expandedTags={expandedTags}
          setExpandedTags={setExpandedTags}
        />
      </Grid>
    </VStack>
  );
}
