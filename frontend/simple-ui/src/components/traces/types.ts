import type { Span, Trace } from "../../services/observabilityService";
import type { ProcessedSpan } from "../../lib/traces";

export interface SpanRelationships {
  spanMap: Map<string, Span>;
  spanToParent: Map<string, string>;
  childSpans: Map<string, string[]>;
}

export interface TraceDetailViewProps {
  traceDetailsLoading: boolean;
  traceError: unknown;
  traceDetails: Trace | undefined;
  processedSpans: ProcessedSpan[];
  traceStatus: { status: "success" | "error" | "warning"; message: string };
  primaryErrorMessage: string | null;
  traceStartTime: number | undefined;
  traceDuration: number | undefined;
  spanRelationships: SpanRelationships;
  expandedTags: Set<string>;
  setExpandedTags: React.Dispatch<React.SetStateAction<Set<string>>>;
}
