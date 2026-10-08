/// <reference types="jest" />

import { FiCpu, FiShield } from "react-icons/fi";
import {
  categorizeSpan,
  extractImportantSpans,
  formatDuration,
  formatRelativeTime,
  formatTagValue,
  formatTimestamp,
  getTraceStatus,
  parseErrorDetails,
  type ProcessedSpan,
} from "../../src/components/traces/traceSpanPresentation";
import type { Span, Trace, TraceTag } from "../../src/types/observability";

function span(overrides: Partial<Span> = {}): Span {
  return {
    traceID: "trace-1",
    spanID: "span-1",
    operationName: "nmt.preprocess",
    startTime: 1_000_000,
    duration: 5_000,
    tags: [],
    logs: [],
    processID: "p1",
    ...overrides,
  };
}

function trace(overrides: Partial<Trace> = {}): Trace {
  return {
    traceID: "trace-1",
    spans: [],
    processes: {
      p1: { serviceName: "nmt-service", tags: [] },
    },
    startTime: 1_000_000,
    duration: 100_000,
    ...overrides,
  };
}

function processed(overrides: Partial<ProcessedSpan> = {}): ProcessedSpan {
  return {
    span: span(),
    serviceName: "nmt-service",
    category: "processing",
    displayName: "nmt.preprocess",
    description: "",
    icon: FiCpu,
    isImportant: true,
    isTopLevel: false,
    hasError: false,
    relativeStart: 0,
    relativeEnd: 1,
    ...overrides,
  };
}

describe("traceSpanPresentation", () => {
  beforeEach(() => {
    jest.spyOn(console, "log").mockImplementation(() => undefined);
    jest.spyOn(console, "warn").mockImplementation(() => undefined);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("categorizeSpan", () => {
    it("marks nmt.preprocess as an important preprocess phase", () => {
      const result = categorizeSpan(span({ operationName: "nmt.preprocess" }), "nmt-service", 1_000_000);

      expect(result.category).toBe("phase.preprocess");
      expect(result.displayName).toBe("nmt.preprocess");
      expect(result.isImportant).toBe(true);
      expect(result.isTopLevel).toBe(false);
      expect(result.hasError).toBe(false);
      expect(result.icon).toBe(FiCpu);
      expect(result.description).toBe(
        "Text: normalize source strings (newlines→spaces, trim, empty segment→space). No base64, media download, chunking, or VAD.",
      );
    });

    it("marks request.reject as an error, important, top-level step", () => {
      const result = categorizeSpan(
        span({ operationName: "request.reject", duration: 100 }),
        "nmt-service",
        1_000_000,
      );

      expect(result.category).toBe("error");
      expect(result.displayName).toBe("Request Rejection");
      expect(result.description).toBe("Request was rejected");
      expect(result.isImportant).toBe(true);
      expect(result.isTopLevel).toBe(true);
      expect(result.hasError).toBe(true);
      expect(result.icon).toBe(FiShield);
      expect(result.errorMessage).toBe("Request was rejected during processing");
    });

    it("marks an auth-service database span as important", () => {
      const result = categorizeSpan(
        span({ operationName: "db.query", spanID: "db-1" }),
        "auth-service",
        1_000_000,
      );

      expect(result.category).toBe("database");
      expect(result.displayName).toBe("Database Query");
      expect(result.isImportant).toBe(true);
    });
  });

  describe("extractImportantSpans", () => {
    it("returns no spans when the trace has an empty span list", () => {
      expect(extractImportantSpans(trace({ spans: [] }))).toEqual([]);
      expect(console.warn).toHaveBeenCalledWith("extractImportantSpans: No spans in trace");
    });

    it("keeps important steps, drops hidden ones, and preserves start order", () => {
      const inference = span({
        spanID: "inference",
        operationName: "nmt.inference",
        startTime: 1_000_000,
        duration: 80_000,
      });
      const preprocess = span({
        spanID: "preprocess",
        operationName: "nmt.preprocess",
        startTime: 1_100_000,
        duration: 10_000,
        references: [{ refType: "CHILD_OF", traceID: "trace-1", spanID: "inference" }],
      });
      const batch = span({
        spanID: "batch",
        operationName: "nmt.process_batch",
        startTime: 1_200_000,
        duration: 20_000,
        references: [{ refType: "CHILD_OF", traceID: "trace-1", spanID: "inference" }],
      });
      const triton = span({
        spanID: "triton",
        operationName: "triton.inference",
        startTime: 1_300_000,
        duration: 30_000,
        references: [{ refType: "CHILD_OF", traceID: "trace-1", spanID: "inference" }],
      });

      const result = extractImportantSpans(
        trace({ spans: [inference, preprocess, batch, triton] }),
      );

      expect(result.map((step) => step.span.spanID)).toEqual(["inference", "preprocess"]);
    });

    it("keeps an error span even when another span has the same operation", () => {
      const first = span({
        spanID: "prep-ok",
        operationName: "nmt.preprocess",
        startTime: 1_000_000,
        duration: 10_000,
      });
      const failed = span({
        spanID: "prep-err",
        operationName: "nmt.preprocess",
        startTime: 1_200_000,
        duration: 4_000,
        tags: [{ key: "error", value: true }],
      });

      const result = extractImportantSpans(trace({ spans: [first, failed] }));

      expect(result.map((step) => step.span.spanID)).toEqual(["prep-ok", "prep-err"]);
      expect(result[1]?.hasError).toBe(true);
    });
  });

  describe("parseErrorDetails", () => {
    it("parses a unique-constraint database error", () => {
      const details = parseErrorDetails(
        processed({
          hasError: true,
          errorMessage: [
            'UniqueViolation: duplicate key value violates unique constraint "users_email_key"',
            "DETAIL: Key (email)=(ada@example.com) already exists.",
            'Operation: INSERT on table "users"',
          ].join("\n"),
        }),
      );

      expect(details).toEqual({
        errorType: "Database Constraint Violation",
        summary:
          "Multiple users trying to login simultaneously generated the same session/refresh tokens.",
        fields: [
          { key: "Constraint Violated", value: "users_email_key" },
          { key: "Duplicate Column", value: "email" },
          { key: "Duplicate Value", value: "ada@example.com" },
          { key: "SQL Operation", value: 'INSERT on table "users"' },
        ],
      });
    });

    it("returns null when the span has no error message", () => {
      expect(parseErrorDetails(processed({ hasError: false, errorMessage: "ignored" }))).toBeNull();
      expect(parseErrorDetails(processed({ hasError: true, errorMessage: "" }))).toBeNull();
      expect(parseErrorDetails(processed({ hasError: true }))).toBeNull();
    });

    it("uses the generic processing error for an unrecognized message", () => {
      expect(
        parseErrorDetails(
          processed({ hasError: true, errorMessage: "something went wrong" }),
        ),
      ).toEqual({
        errorType: "Processing Error",
        summary: "An error occurred during request processing.",
        fields: [{ key: "Error Message", value: "something went wrong" }],
      });
    });
  });

  describe("getTraceStatus", () => {
    function tagged(spanID: string, operationName: string, tags: TraceTag[], processID = "p1"): Span {
      return span({
        spanID,
        operationName,
        processID,
        tags,
        references:
          spanID === "root"
            ? undefined
            : [{ refType: "CHILD_OF", traceID: "trace-1", spanID: "root" }],
      });
    }

    it("prefers the root HTTP status over a gateway status", () => {
      const result = getTraceStatus(
        trace({
          processes: {
            p1: { serviceName: "nmt-service", tags: [] },
            p2: { serviceName: "api-gateway", tags: [] },
          },
          spans: [
            tagged("root", "nmt.inference", [{ key: "http.status_code", value: 503 }]),
            tagged("gateway", "POST /inference", [{ key: "http.status_code", value: 200 }], "p2"),
          ],
        }),
      );

      expect(result).toEqual({ status: "error", message: "Server error (503)" });
    });

    it("uses the gateway status when the root span has none", () => {
      const result = getTraceStatus(
        trace({
          processes: {
            p1: { serviceName: "nmt-service", tags: [] },
            p2: { serviceName: "api-gateway", tags: [] },
          },
          spans: [
            tagged("root", "nmt.inference", []),
            tagged("gateway", "POST /inference", [{ key: "http.status_code", value: 404 }], "p2"),
            tagged("handler", "asr.inference", [{ key: "http.status_code", value: 200 }]),
          ],
        }),
      );

      expect(result).toEqual({ status: "error", message: "Client error (404)" });
    });

    it("uses the inference handler status when root and gateway have none", () => {
      const result = getTraceStatus(
        trace({
          spans: [
            tagged("root", "cache.lookup", []),
            tagged("handler", "asr.inference", [{ key: "http.status_code", value: 500 }]),
          ],
        }),
      );

      expect(result).toEqual({ status: "error", message: "Server error (500)" });
    });

    it("reports failure from an error tag when no HTTP status exists", () => {
      const result = getTraceStatus(
        trace({
          spans: [tagged("root", "cache.lookup", [{ key: "error", value: true }])],
        }),
      );

      expect(result).toEqual({ status: "error", message: "Failed" });
    });

    it("falls back to success when status cannot be determined", () => {
      const result = getTraceStatus(
        trace({
          spans: [tagged("root", "cache.lookup", [])],
        }),
      );

      expect(result).toEqual({ status: "success", message: "Success" });
    });
  });

  describe("formatting", () => {
    it("formats sub-millisecond, millisecond, and second durations", () => {
      expect(formatDuration(500)).toBe("500μs");
      expect(formatDuration(2500)).toBe("2.50ms");
      expect(formatDuration(2_500_000)).toBe("2.50s");
    });

    it("formats timestamps and relative time", () => {
      const microseconds = 1_700_000_000_000_000;
      expect(formatTimestamp(microseconds)).toBe(new Date(microseconds / 1000).toLocaleString());
      expect(formatTimestamp(undefined)).toBe("N/A");
      expect(formatRelativeTime(12)).toBe("12ms");
      expect(formatRelativeTime(2500)).toBe("2.50s");
    });

    it("formats tag values by key", () => {
      expect(formatTagValue("audio_length_ms", 40)).toBe("40 ms");
      expect(formatTagValue("processing_time_seconds", 3)).toBe("3 s");
      expect(formatTagValue("size_bytes", 2048)).toBe("2.00 KB");
      expect(formatTagValue("error.message", "raw message")).toBe("raw message");
      expect(formatTagValue("db.statement", "SELECT id FROM users WHERE id = 1")).toBe(
        "SELECT id \nFROM users \nWHERE id = 1",
      );
      expect(formatTagValue("model", "indictrans")).toBe("indictrans");
    });
  });
});
