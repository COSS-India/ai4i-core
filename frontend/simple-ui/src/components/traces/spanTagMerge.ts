import type { ProcessedSpan } from "../../lib/traces";
import type { SpanRelationships } from "./types";

export interface MergedSpanTagsResult {
  relevantTags: { key: string; value: unknown }[];
  indentPx: number;
  hasSignificantOverhead: boolean;
  childSpans: ProcessedSpan[];
  childSpansDuration: number;
  parentDuration: number;
  overheadTime: number;
}

const REDUNDANT_HTTP_TAGS = new Set([
  "http.host", "http.method", "http.route", "http.server_name",
  "http.target", "http.url", "http.user_agent", "correlation.header",
]);

export function mergeSpanTags(
  processed: ProcessedSpan,
  spanRelationships: SpanRelationships,
  processedSpans: ProcessedSpan[]
): MergedSpanTagsResult {
  let allTags = [...(processed.span.tags || [])];
  const childTagKeys = new Set(allTags.map(t => t.key.toLowerCase()));


  const isServiceDomainTag = (tagKey: string): boolean =>
    tagKey.startsWith('nmt.') ||
    tagKey.startsWith('ocr.') ||
    tagKey.startsWith('transliteration.') ||
    tagKey.startsWith('audio-lang-detection.') ||
    tagKey.startsWith('speaker-diarization.') ||
    tagKey.startsWith('language-diarization.') ||
    tagKey.startsWith('language-detection.') ||
    tagKey.startsWith('ner.') ||
    tagKey.startsWith('pipeline.') ||
    tagKey.startsWith('tts.') ||
    tagKey.startsWith('asr.');

  /** Merge only parent tags that belong to that phase (Telemetry Step Standardization). */
  const shouldIncludeParentTagForStandardPhase = (
    tagKey: string,
    spanCategory: string
  ): boolean => {
    const infra =
      tagKey === 'correlation.id' ||
      tagKey === 'organization' ||
      tagKey.startsWith('user.') ||
      tagKey.startsWith('session.') ||
      tagKey.startsWith('api_key') ||
      tagKey.includes('tenant') ||
      tagKey === 'client.ip' ||
      tagKey === 'http.client_ip';

    if (spanCategory === 'phase.persist') {
      if (infra) return true;
      if (tagKey.endsWith('.service_id')) return true;
      // Persist span should carry DB attrs from the exporter; do not pull input/output/model from ancestors.
      if (isServiceDomainTag(tagKey)) return false;
      return false;
    }

    if (spanCategory === 'phase.preprocess') {
      if (infra) return true;
      if (tagKey.endsWith('.service_id')) return true;
      if (tagKey.includes('source_language') || tagKey.includes('target_language')) return true;
      if (
        tagKey.includes('.input.') ||
        tagKey.includes('input_count') ||
        tagKey.includes('input_size') ||
        tagKey.includes('request.size') ||
        tagKey.startsWith('http.request') ||
        tagKey.includes('input_type')
      )
        return true;
      if (tagKey.includes('audio_format') || tagKey.includes('sampling_rate')) return true;
      if (tagKey.includes('image_count') || tagKey.includes('image_bytes')) return true;
      if (isServiceDomainTag(tagKey)) {
        if (tagKey.includes('.output.') || tagKey.includes('output_count')) return false;
        if (tagKey.includes('.db_') || tagKey.includes('request_id')) return false;
        if (tagKey.endsWith('.model_name') || tagKey.includes('triton_endpoint')) return false;
        if (
          tagKey.endsWith('.processing_time_seconds') ||
          tagKey.endsWith('.status')
        )
          return false;
        return true;
      }
      if (tagKey.startsWith('triton.')) return false;
      return false;
    }

    if (spanCategory === 'phase.resolve_model') {
      if (infra) return true;
      // Span exporter should set *.resolve_model.* / model endpoint attrs; do not pull
      // inference context (languages, input_type, service_id) from ancestors.
      if (isServiceDomainTag(tagKey)) return false;
      return false;
    }

    if (spanCategory === 'phase.triton_inference') {
      if (infra) return true;
      // Phase span should carry *.triton_inference.* from the exporter; do not merge
      // generic inference attrs from ancestors (languages, service_id, etc.).
      if (isServiceDomainTag(tagKey)) return false;
      if (tagKey.startsWith('triton.')) return false;
      return false;
    }

    if (spanCategory === 'phase.postprocess') {
      if (infra) return true;
      // Postprocess span owns *.postprocess.* and *.output.* from the exporter only.
      if (isServiceDomainTag(tagKey)) return false;
      if (tagKey.startsWith('triton.')) return false;
      return false;
    }

    return false;
  };

  // Helper function to determine if a parent tag should be included
  const shouldIncludeParentTag = (tagKey: string, spanCategory: string): boolean => {
    // Always exclude redundant HTTP metadata from parent spans
    if (REDUNDANT_HTTP_TAGS.has(tagKey)) return false;

    if (spanCategory.startsWith('phase.')) {
      return shouldIncludeParentTagForStandardPhase(tagKey, spanCategory);
    }

    // For processing spans, include input/output data from parents
    if (spanCategory === 'processing') {
      return tagKey.includes('.input.') ||
             tagKey.includes('input_count') ||
             tagKey.includes('input_size') ||
             tagKey.includes('request.size') ||
             tagKey.startsWith('http.request') ||
             tagKey.startsWith('nmt.') ||
             tagKey.startsWith('ocr.') ||
             tagKey.startsWith('transliteration.') ||
             tagKey.startsWith('audio-lang-detection.') ||
             tagKey.startsWith('speaker-diarization.') ||
             tagKey.startsWith('language-diarization.') ||
             tagKey.startsWith('language-detection.') ||
             tagKey.startsWith('ner.') ||
             tagKey.startsWith('pipeline.') ||
             tagKey.startsWith('tts.') ||
             tagKey.startsWith('asr.') ||
             tagKey.startsWith('triton.') ||
             tagKey === 'correlation.id' ||
             tagKey === 'organization' ||
             tagKey.startsWith('user.') ||
             tagKey === 'client.ip' ||
             tagKey === 'http.client_ip';
    }

    // For auth spans, include auth-related and organization tags
    if (spanCategory === 'auth') {
      return tagKey.startsWith('auth.') ||
             tagKey === 'organization' ||
             tagKey.startsWith('user.') ||
             tagKey === 'correlation.id' ||
             tagKey === 'client.ip' ||
             tagKey === 'http.client_ip';
    }

    // For other spans, only include essential tags
    return tagKey === 'correlation.id' ||
           tagKey === 'organization' ||
           tagKey.startsWith('user.') ||
           tagKey.includes('.input.') ||
           tagKey.includes('input_count') ||
           tagKey === 'client.ip' ||
           tagKey === 'http.client_ip';
  };

  // Traverse up the parent chain to collect tags from all ancestors
  let currentParentId = spanRelationships.spanToParent.get(processed.span.spanID);
  const visitedParents = new Set<string>(); // Prevent infinite loops

  while (currentParentId && !visitedParents.has(currentParentId)) {
    visitedParents.add(currentParentId);
    const parentSpan = spanRelationships.spanMap.get(currentParentId);

    if (parentSpan && parentSpan.tags) {
      // Add parent tags that don't exist in child and are relevant
      parentSpan.tags.forEach((parentTag: { key: string; value: any }) => {
        const tagKey = parentTag.key.toLowerCase();
        if (!childTagKeys.has(tagKey) &&
            shouldIncludeParentTag(tagKey, processed.category)) {
          allTags.push(parentTag);
          childTagKeys.add(tagKey); // Track added tags to avoid duplicates
        }
      });
    }

    // Move to next parent level
    currentParentId = spanRelationships.spanToParent.get(currentParentId);
  }

  // Traverse down to child spans to collect triton.* and internal.* tags
  // This is important because triton tags might be on child spans (e.g., triton.inference under ocr.triton_batch)
  const collectTagsFromChildren = (spanId: string, visited: Set<string>) => {
    if (visited.has(spanId)) return; // Prevent infinite loops
    visited.add(spanId);

    const childSpanIds = spanRelationships.childSpans.get(spanId) || [];
    childSpanIds.forEach((childSpanId: string) => {
      const childSpan = spanRelationships.spanMap.get(childSpanId);
      if (childSpan && childSpan.tags) {
        childSpan.tags.forEach((childTag: { key: string; value: any }) => {
          const tagKey = childTag.key.toLowerCase();
          // Always include triton.* and internal.* tags from children
          if ((tagKey.startsWith("triton.") || tagKey.startsWith("internal.")) &&
              !childTagKeys.has(tagKey)) {
            allTags.push(childTag);
            childTagKeys.add(tagKey);
          }
        });
      }
      // Recursively collect from grandchildren
      collectTagsFromChildren(childSpanId, visited);
    });
  };

  // Collect triton and internal tags from all child spans.
  // Exception: for the standard Triton phase span (e.g., nmt.triton_inference),
  // keep child tags separated so the UI can show triton.inference as an indented child
  // with its own technical details.
  if (processed.category !== "phase.triton_inference") {
    const visitedChildren = new Set<string>();
    collectTagsFromChildren(processed.span.spanID, visitedChildren);
  }

  const relevantTags = allTags.filter((t: { key: string; value: any }) => {
    const key = t.key.toLowerCase();

    // PRIORITY: Always include triton.* tags FIRST (important for AI Model Inference spans)
    // This ensures they're never filtered out by other rules
    if (key.startsWith("triton.")) {
      return true;
    }

    // PRIORITY: Always include internal.* tags (span metadata)
    if (key.startsWith("internal.")) {
      return true;
    }

    // Filter out truly irrelevant tags
    if (key.includes("telemetry.") ||
        key.includes("http.flavor") ||
        key.includes("http.scheme") ||
        key.includes("net.") ||
        key.includes("correlation.generated") ||
        key === "span.kind") {
      return false;
    }

    // For non-top-level spans, filter out redundant HTTP metadata
    // Keep essential HTTP tags: status_code, request/response size_bytes
    // Remove verbose HTTP metadata: host, method, route, server_name, target, url, user_agent
    // But only if this is not a top-level processing span (which should show full HTTP context)
    if (!processed.isTopLevel && key.startsWith("http.") &&
        key !== "http.status_code" &&
        key !== "http.request.size_bytes" &&
        key !== "http.response.size_bytes") {
      return false;
    }

    // Keep otel.status_code, otel.status_description (for errors), and otel.scope.name, filter out other otel.*
    if (key.includes("otel.") &&
        key !== "otel.status_code" &&
        key !== "otel.status_description" &&
        key !== "otel.scope.name") {
      return false;
    }

    // Always include error-related tags for error spans
    if (processed.hasError && (
      key.includes("error") ||
      key.includes("exception") ||
      key === "db.statement" ||
      key === "db.system" ||
      key === "db.name"
    )) {
      return true;
    }

    return true;
  });

  // Sort tags to prioritize important ones first
  relevantTags.sort((a: { key: string; value: any }, b: { key: string; value: any }) => {
    const aKey = a.key.toLowerCase();
    const bKey = b.key.toLowerCase();

    // Priority order: error tags (for errors) > input tags > service-specific tags > http status > organization > correlation.id > user.id > otel scope > others
    const getPriority = (key: string): number => {
      // Highest priority for errors: error-related tags
      if (processed.hasError) {
        if (key === "otel.status_description") return -2;
        if (key.includes("error") || key.includes("exception")) return -1;
        if (key === "db.statement" || key === "db.system") return 0;
      }
      if (
        processed.category === "phase.persist" &&
        (key.includes(".db.") ||
          key.includes("request_id") ||
          key.includes("pii_redact"))
      ) {
        return 0.25;
      }
      if (
        processed.category === "phase.resolve_model" &&
        (key.includes("resolve_model") ||
          key.includes("model_name") ||
          key.includes("triton_endpoint") ||
          key.includes("infer_endpoint") ||
          key.includes("triton_client"))
      ) {
        return 0.25;
      }
      if (
        processed.category === "phase.triton_inference" &&
        (key.includes("triton_inference") ||
          key.startsWith("triton."))
      ) {
        return 0.25;
      }
      if (
        processed.category === "phase.postprocess" &&
        (key.includes("postprocess") ||
          key.includes(".output.") ||
          key.includes("output_count") ||
          key.includes("formatted_count"))
      ) {
        return 0.25;
      }
      // Highest priority: input-related tags (most important for understanding the request)
      if (key.includes(".input.") || key.includes("input_count") || key.includes("input_size") ||
          key.includes("request.size") || key.startsWith("http.request")) return 1;
      // High priority: client IP (important for request tracking)
      if (key === "client.ip" || key === "http.client_ip") return 1.5;
      // High priority: service-specific tags (including triton tags for AI Model Inference)
      if (key.startsWith("nmt.") || key.startsWith("ocr.") || key.startsWith("transliteration.") || key.startsWith("audio-lang-detection.") || key.startsWith("speaker-diarization.") || key.startsWith("language-diarization.") || key.startsWith("language-detection.") || key.startsWith("ner.") || key.startsWith("pipeline.") || key.startsWith("tts.") || key.startsWith("asr.") || key.startsWith("triton.")) return 2;
      if (key === "http.status_code" || key === "otel.status_code") return 3;
      if (key === "organization") return 4;
      if (key === "correlation.id") return 5;
      if (key.startsWith("user.")) return 6;
      if (key.startsWith("http.")) return 7;
      if (key === "otel.scope.name") return 8;
      return 9;
    };

    return getPriority(aKey) - getPriority(bKey);
  });

  // Calculate depth for indentation - only count displayed parent spans
  // This ensures indentation reflects the visible hierarchy
  const calculateDisplayedDepth = (spanId: string): number => {
    let depth = 0;
    let currentId: string | undefined = spanId;
    const visited = new Set<string>();
    const displayedSpanIds = new Set(processedSpans?.map((p: ProcessedSpan) => p.span.spanID) || []);

    while (currentId) {
      if (visited.has(currentId)) break; // Prevent infinite loops
      visited.add(currentId);

      const parentId: string | undefined = spanRelationships.spanToParent.get(currentId);
      if (parentId) {
        // Only increment depth if the parent is actually displayed
        if (displayedSpanIds.has(parentId)) {
          depth++;
        }
        // Continue traversing up the chain
        currentId = parentId;
      } else {
        break;
      }
    }

    return depth;
  };

  const depth = calculateDisplayedDepth(processed.span.spanID);
  const indentPx = depth * 24; // 24px per level of nesting

  // Calculate sum of visible child spans to explain duration discrepancy
  const childSpans = processedSpans?.filter((p: ProcessedSpan) => {
    const parentId = spanRelationships.spanToParent.get(p.span.spanID);
    return parentId === processed.span.spanID;
  }) || [];

  const childSpansDuration = childSpans.reduce((sum: number, child: ProcessedSpan) => {
    return sum + (child.span.duration || 0);
  }, 0);

  const parentDuration = processed.span.duration || 0;
  const overheadTime = parentDuration - childSpansDuration;
  const hasSignificantOverhead = overheadTime > 1000 && childSpans.length > 0; // > 1ms overhead with visible children
  return {
    relevantTags,
    indentPx,
    hasSignificantOverhead,
    childSpans,
    childSpansDuration,
    parentDuration,
    overheadTime,
  };
}
