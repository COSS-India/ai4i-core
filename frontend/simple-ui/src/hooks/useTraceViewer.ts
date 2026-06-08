// Trace viewer state, fetch, and span processing

import { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/router";
import { getTelemetryTraceById, type Span } from "../services/observabilityService";
import { useToastWithDeduplication } from "./useToastWithDeduplication";
import { useAuth } from "./useAuth";
import {
  extractImportantSpans,
  getTraceStatus,
  telemetryTraceToJaegerTrace,
  type ProcessedSpan,
} from "../lib/traces";

export function useTraceViewer() {
  const toast = useToastWithDeduplication();
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [traceIdSearch, setTraceIdSearch] = useState<string>("");
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [expandedTags, setExpandedTags] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      toast({
        title: "Authentication Required",
        description: "Please log in to view traces.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      router.push("/auth");
    }
  }, [isAuthenticated, authLoading, router, toast]);

  useEffect(() => {
    if (router.isReady && router.query.traceId) {
      const traceIdFromQuery = String(router.query.traceId).trim();
      if (traceIdFromQuery) {
        setTraceIdSearch(traceIdFromQuery);
        setSelectedTraceId(traceIdFromQuery);
      }
    }
  }, [router.isReady, router.query.traceId]);

  const {
    data: traceDetails,
    isLoading: traceDetailsLoading,
    error: traceError,
  } = useQuery({
    queryKey: ["trace-details", selectedTraceId],
    queryFn: async () => {
      const detail = await getTelemetryTraceById(selectedTraceId!);
      return telemetryTraceToJaegerTrace(detail);
    },
    enabled: !!selectedTraceId && isAuthenticated,
    staleTime: 5 * 60 * 1000,
  });

  const handleSearchByTraceId = () => {
    if (!traceIdSearch.trim()) {
      toast({
        title: "Trace ID Required",
        description: "Please enter a trace ID to search.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    setSelectedTraceId(traceIdSearch.trim());
  };

  const processedSpans = useMemo(() => {
    if (!traceDetails) return [];

    try {
      if (!traceDetails.spans?.length) return [];
      if (!traceDetails.processes || Object.keys(traceDetails.processes).length === 0) {
        return [];
      }

      if (!traceDetails.startTime) {
        const minStartTime = Math.min(...traceDetails.spans.map((s: Span) => s.startTime));
        if (minStartTime) {
          traceDetails.startTime = minStartTime;
        } else {
          return [];
        }
      }

      return extractImportantSpans(traceDetails);
    } catch (error) {
      console.error("Error processing spans:", error);
      return [];
    }
  }, [traceDetails]);

  const traceStatus = useMemo(() => {
    if (!traceDetails) return { status: "success" as const, message: "Completed" };
    return getTraceStatus(traceDetails);
  }, [traceDetails]);

  const spanRelationships = useMemo(() => {
    if (!traceDetails?.spans) {
      return {
        spanMap: new Map<string, Span>(),
        spanToParent: new Map<string, string>(),
        childSpans: new Map<string, string[]>(),
      };
    }

    const spanMap = new Map<string, Span>();
    const spanToParent = new Map<string, string>();
    const childSpans = new Map<string, string[]>();

    traceDetails.spans.forEach((span: Span) => {
      spanMap.set(span.spanID, span);

      if (span.references?.length) {
        const parentRef = span.references.find((ref) => ref.refType === "CHILD_OF");
        if (parentRef) {
          spanToParent.set(span.spanID, parentRef.spanID);
          if (!childSpans.has(parentRef.spanID)) {
            childSpans.set(parentRef.spanID, []);
          }
          childSpans.get(parentRef.spanID)!.push(span.spanID);
        }
      }
    });

    return { spanMap, spanToParent, childSpans };
  }, [traceDetails]);

  const primaryErrorMessage = useMemo(() => {
    if (!processedSpans.length) return null;

    const isTrivialError = (msg: string | undefined): boolean => {
      if (!msg) return true;
      const msgLower = msg.toLowerCase().trim();
      return (
        msgLower === "true" ||
        msgLower === "false" ||
        msgLower.length <= 3 ||
        msgLower === "error" ||
        /^status:\s*\d+$/.test(msgLower) ||
        /^\d+$/.test(msgLower)
      );
    };

    const errorSpans = processedSpans
      .filter((p: ProcessedSpan) => p.hasError && p.errorMessage && !isTrivialError(p.errorMessage))
      .map((p: ProcessedSpan) => ({
        span: p,
        errorMessage: p.errorMessage!,
        priority: 0,
      }));

    if (errorSpans.length > 0) {
      errorSpans.forEach((item) => {
        if (item.span.category === "error" || item.span.displayName.includes("Rejection")) {
          item.priority += 10;
        }
        if (item.span.isTopLevel) item.priority += 5;
        if (item.errorMessage.length > 20) item.priority += 3;
        if (item.errorMessage.length > 10) item.priority += 1;
      });
      errorSpans.sort((a, b) => b.priority - a.priority);
      return errorSpans[0]?.errorMessage || null;
    }

    const anyError = processedSpans.find(
      (p: ProcessedSpan) =>
        p.hasError &&
        p.errorMessage &&
        (p.category === "error" || p.displayName.includes("Rejection"))
    );
    if (anyError?.errorMessage) return anyError.errorMessage;

    const firstError = processedSpans.find((p: ProcessedSpan) => p.hasError && p.errorMessage);
    return firstError?.errorMessage || null;
  }, [processedSpans]);

  const traceStartTime = useMemo(() => {
    if (!traceDetails?.spans?.length) return traceDetails?.startTime;
    if (traceDetails.startTime && traceDetails.startTime > 0) return traceDetails.startTime;

    const startTimes = traceDetails.spans.map((s: Span) => s.startTime).filter((t: number) => t > 0);
    if (startTimes.length > 0) return Math.min(...startTimes);
    return traceDetails.startTime;
  }, [traceDetails]);

  const traceDuration = useMemo(() => {
    if (!traceDetails?.spans?.length) return traceDetails?.duration;
    if (traceDetails.duration && traceDetails.duration > 0) return traceDetails.duration;

    const startTimes = traceDetails.spans.map((s: Span) => s.startTime).filter((t: number) => t > 0);
    const endTimes = traceDetails.spans
      .map((s: Span) => s.startTime + s.duration)
      .filter((t: number) => t > 0);

    if (!startTimes.length || !endTimes.length) return traceDetails.duration;

    const calculatedDuration = Math.max(...endTimes) - Math.min(...startTimes);
    return calculatedDuration > 0 ? calculatedDuration : traceDetails.duration;
  }, [traceDetails]);

  return {
    authLoading,
    isAuthenticated,
    router,
    traceIdSearch,
    setTraceIdSearch,
    expandedTags,
    setExpandedTags,
    traceDetails,
    traceDetailsLoading,
    traceError,
    handleSearchByTraceId,
    processedSpans,
    traceStatus,
    spanRelationships,
    primaryErrorMessage,
    traceStartTime,
    traceDuration,
  };
}
