// Traces Dashboard - User-friendly trace visualization

import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Heading,
  HStack,
  Input,
  Text,
  VStack,
  Badge,
  Spinner,
  Flex,
  useColorModeValue,
  Card,
  CardBody,
  Grid,
  GridItem,
  Alert,
  AlertIcon,
  AlertDescription,
  Divider,
  Icon,
  Collapse,
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { SearchIcon, CheckCircleIcon } from "@chakra-ui/icons";
import { FiCheckCircle, FiClock, FiShield, FiCpu, FiDatabase, FiGlobe, FiSettings, FiEye, FiEyeOff, FiInfo, FiImage, FiLayers } from "react-icons/fi";
import ContentLayout from "../components/common/ContentLayout";
import { useAuth } from "../hooks/useAuth";
import { useRouter } from "next/router";
import {
  getTraceById,
  Trace,
  Span,
} from "../services/observabilityService";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";

// Utility functions to extract and categorize spans
interface ProcessedSpan {
  span: Span;
  serviceName: string;
  category: string;
  displayName: string;
  description: string;
  icon: any;
  isImportant: boolean;
  isTopLevel: boolean;
  hasError: boolean;
  errorMessage?: string;
  relativeStart: number; // milliseconds from trace start
  relativeEnd: number;
  effectiveDuration?: number; // exclusive duration: span.duration minus direct children (used for root/wrapper spans)
}

const categorizeSpan = (span: Span, serviceName: string, traceStartTime: number): ProcessedSpan => {
  const opName = span.operationName.toLowerCase();
  const tags = span.tags || [];
  
  // Extract relevant tags
  const getTag = (key: string) => {
    const tag = tags.find(t => t.key.toLowerCase() === key.toLowerCase());
    return tag ? String(tag.value) : null;
  };

  /** e.g. nmt.inference, tts.inference, language-detection.inference — not triton.inference */
  const isStandardSvcInferenceOp =
    /^[a-z0-9-]+\.inference$/.test(opName) && !opName.startsWith("triton.");

  // Determine category and importance
  let category = "other";
  let displayName = span.operationName;
  let description = "";
  let icon = FiSettings;
  let isImportant = false;
  let isTopLevel = false; // Flag for top-level operations
  let hasError = false;
  let errorMessage: string | undefined = undefined;

  // --- Standard 7-phase lifecycle spans (Telemetry Step Standardization) ---
  // Make these appear as distinct steps in the Trace UI instead of collapsing them
  // under generic "processing/routing/database" buckets.
  //
  // {svc}.inference (Phase 1 parent + Phase 7 on close) is categorized under "processing" below — not listed here.
  //
  // Examples:
  // - nmt.preprocess / ocr.preprocess / tts.preprocess
  // - nmt.resolve_model (optional)
  // - nmt.triton_inference (phase wrapper) containing internal triton.inference (leaf)
  // - nmt.postprocess
  // - nmt.persist | nmt.persist_request | nmt.persist_results (split DB phases)
  const isPersistPhaseSpan =
    opName.endsWith(".persist") ||
    opName.endsWith(".persist_request") ||
    opName.endsWith(".persist_results");
  const isStandardPhaseSpan =
    opName.endsWith(".preprocess") ||
    opName.endsWith(".resolve_model") ||
    opName.endsWith(".triton_inference") ||
    opName.endsWith(".postprocess") ||
    isPersistPhaseSpan;

  if (isStandardPhaseSpan) {
    isImportant = true;
    isTopLevel = false;

    if (opName.endsWith(".preprocess")) {
      category = "phase.preprocess";
      // Use the proposed span name verbatim (e.g., nmt.preprocess)
      displayName = span.operationName;
      // Service-specific: match Telemetry Step Standardization (text vs image vs audio prep)
      if (opName.startsWith("nmt.")) {
        description =
          "Text: normalize source strings (newlines→spaces, trim, empty segment→space). No base64, media download, chunking, or VAD.";
      } else if (opName.startsWith("ocr.")) {
        description =
          "Images: resolve inputs (e.g. download or decode base64), prepare tensors for inference.";
      } else if (opName.startsWith("tts.")) {
        description =
          "Text: TTS-specific normalization, then chunk long lines (~400 chars) for per-chunk synthesis (no audio input or VAD).";
      } else if (opName.startsWith("asr.")) {
        description =
          "Audio: fetch bytes (base64/URI), decode to mono 16 kHz, optional VAD chunking before ASR (no image/OCR).";
      } else if (opName.startsWith("ner.")) {
        description =
          "Text: normalize each input line (newlines→space, trim) for batched NER; same pattern as NMT text prep, no audio/image.";
      } else if (opName.startsWith("transliteration.")) {
        description =
          "Text: normalize and prepare token sequences for the model.";
      } else if (opName.startsWith("language-detection.")) {
        description =
          "Text: prepare segments for language detection.";
      } else if (opName.startsWith("speaker-diarization.")) {
        description =
          "Audio: load/prepare audio for diarization (who spoke when).";
      } else if (opName.startsWith("language-diarization.")) {
        description =
          "Audio: load/prepare audio for language diarization.";
      } else if (opName.startsWith("audio-lang-detection.")) {
        description =
          "Audio: load/prepare audio for spoken language detection.";
      } else if (opName.startsWith("pipeline.")) {
        description =
          "Pipeline: validate and normalize task inputs before orchestration.";
      } else {
        description = "Prepares inputs for inference (service-specific).";
      }
      icon = FiCpu;
    } else if (opName.endsWith(".resolve_model")) {
      category = "phase.resolve_model";
      // Use the proposed span name verbatim (e.g., nmt.resolve_model)
      displayName = span.operationName;
      if (opName.startsWith("nmt.")) {
        description =
          "Looks up registry/Triton model name and infer URL for this service_id, builds the Triton client, applies invoke-name aliases (e.g. indictrans→nmt).";
      } else if (opName.startsWith("ocr.")) {
        description =
          "Resolves the OCR Triton model name used for inference.";
      } else if (opName.startsWith("tts.")) {
        description =
          "Confirms TTS model name and endpoint (usually precached from model management when the service starts; same phase as dynamic lookup elsewhere).";
      } else if (opName.startsWith("asr.")) {
        description =
          "Confirms ASR model name and endpoint (typically precached from model management at service startup).";
      } else if (opName.startsWith("transliteration.")) {
        description =
          "Resolves the transliteration Triton model and endpoint.";
      } else if (opName.startsWith("ner.")) {
        description =
          "Confirms NER Triton model name and endpoint (configured on the NER service instance).";
      } else if (opName.startsWith("language-detection.")) {
        description =
          "Resolves the Triton model and endpoint for this text task.";
      } else if (opName.startsWith("speaker-diarization.") || opName.startsWith("language-diarization.") || opName.startsWith("audio-lang-detection.")) {
        description =
          "Resolves the Triton model and endpoint for this audio task.";
      } else if (opName.startsWith("pipeline.")) {
        description =
          "Resolves models or endpoints needed for pipeline orchestration.";
      } else {
        description =
          "Looks up Triton model name and endpoint (skip or shorten if the model is hardcoded).";
      }
      icon = FiGlobe;
    } else if (opName.endsWith(".triton_inference")) {
      category = "phase.triton_inference";
      // Use the proposed span name verbatim (e.g., nmt.triton_inference)
      displayName = span.operationName;
      if (opName.startsWith("nmt.")) {
        description =
          "Prepare NMT tensors per batch, call triton.inference (HTTP infer), read raw OUTPUT_TEXT; repeats for large segment counts.";
      } else if (opName.startsWith("tts.")) {
        description =
          "Prepare TTS tensors per chunk, call triton.inference, read raw audio output.";
      } else if (opName.startsWith("ocr.")) {
        description =
          "Prepare image batch tensors, call triton.inference, read raw OCR outputs.";
      } else if (opName.startsWith("asr.")) {
        description =
          "Batch AUDIO_SIGNAL tensors, call triton.inference, decode TRANSCRIPTS JSON/text per chunk (may loop batches per audio).";
      } else if (opName.startsWith("ner.")) {
        description =
          "Batch INPUT_TEXT + LANG_ID, single triton.inference, read OUTPUT_TEXT (JSON entity payload).";
      } else if (opName.startsWith("language-detection.") || opName.startsWith("transliteration.")) {
        description =
          "Prepare text tensors, call triton.inference, read raw model outputs.";
      } else if (opName.startsWith("speaker-diarization.") || opName.startsWith("language-diarization.") || opName.startsWith("audio-lang-detection.")) {
        description =
          "Prepare audio tensors, call triton.inference, read raw outputs.";
      } else if (opName.startsWith("pipeline.")) {
        description =
          "Delegated Triton work inside a pipeline task (if any).";
      } else {
        description =
          "Prepare Triton inputs, call triton.inference, extract raw outputs (may loop per batch).";
      }
      icon = FiCpu;
    } else if (opName.endsWith(".postprocess")) {
      category = "phase.postprocess";
      // Use the proposed span name verbatim (e.g., nmt.postprocess)
      displayName = span.operationName;
      if (opName.startsWith("nmt.")) {
        description =
          "Text: decode each Triton OUTPUT_TEXT cell (bytes→UTF-8 or scalar), pair with preprocessed source segments, build TranslationOutput list for the API (no audio resample/encode).";
      } else if (opName.startsWith("tts.")) {
        description =
          "Audio: concatenate chunks, resample, adjust duration, convert format, base64-encode, build audio response objects.";
      } else if (opName.startsWith("ocr.")) {
        description =
          "Parse OCR model output (e.g. JSON/text), normalize, build OCR response objects.";
      } else if (opName.startsWith("asr.")) {
        description =
          "Optional text post-processors, then build plain / SRT / WebVTT transcript strings and TranscriptOutput list.";
      } else if (opName.startsWith("ner.")) {
        description =
          "Parse OUTPUT_TEXT JSON, align BIO-style predictions to words, build NerPrediction / NerTokenPrediction list.";
      } else if (opName.startsWith("language-detection.") || opName.startsWith("transliteration.")) {
        description =
          "Parse model outputs into entities, labels, or transliteration response objects.";
      } else if (opName.startsWith("speaker-diarization.") || opName.startsWith("language-diarization.") || opName.startsWith("audio-lang-detection.")) {
        description =
          "Turn raw diarization / lang-detection outputs into API-friendly segments or labels.";
      } else if (opName.startsWith("pipeline.")) {
        description =
          "Shape pipeline task results for the orchestration response.";
      } else {
        description =
          "Parse results, resample or convert where applicable, encode if needed, build response objects.";
      }
      icon = FiSettings;
    } else if (isPersistPhaseSpan) {
      category = "phase.persist";
      displayName = span.operationName;
      if (opName.startsWith("tts.")) {
        description =
          "DB: create tts_requests row, insert tts_results (duration, format, sample rate, size; audio preview path), set request completed.";
      } else if (opName.startsWith("nmt.")) {
        description =
          "DB: create nmt_requests, bulk nmt_results (with optional PII redact), update request status.";
      } else if (opName.startsWith("asr.")) {
        description =
          "DB: create asr_requests, one asr_results row per audio input (transcript + timestamps), set request completed.";
      } else if (opName.startsWith("ner.")) {
        description =
          "DB: create ner_requests, one ner_results row per prediction (entities JSON + source text), set request completed.";
      } else if (opName.startsWith("language-detection.")) {
        description =
          "DB: create language_detection_requests, one language_detection_results row per input segment (lang + script + confidence), set request completed.";
      } else if (opName.startsWith("transliteration.")) {
        description =
          "DB: create transliteration_requests, one transliteration_results row per input (string or suggestion list), set request completed.";
      } else if (opName.startsWith("language-diarization.")) {
        description =
          "DB: create language_diarization_requests, one language_diarization_results row per audio (segments JSON), set request completed (may be partial-failure).";
      } else if (opName.startsWith("speaker-diarization.")) {
        description =
          "DB: create speaker_diarization_requests, one speaker_diarization_results row per audio (segments JSON + speaker list), set request completed (may be partial-failure).";
      } else if (opName.startsWith("audio-lang-detection.")) {
        description =
          "DB: create audio_lang_detection_requests, one audio_lang_detection_results row per audio (lang + confidence + scores JSON), set request completed (may be partial-failure).";
      } else {
        description =
          "Stores request/results and updates status in the database (single persist span).";
      }
      icon = FiDatabase;
    }
  }
  // Hide internal Triton leaf span from the main step list (still available in technical details)
  else if (opName === "triton.inference") {
    category = "triton";
    isImportant = false;
    icon = FiCpu;
    displayName = span.operationName;
  }

  // Check for errors in span
  const checkForErrors = () => {
    // Debug: Log all tags for error spans (helpful for troubleshooting)
    const hasErrorTag = tags.some(t => 
      (t.key === "error" && t.value === true) ||
      (t.key === "otel.status_code" && String(t.value) === "ERROR") ||
      t.key.toLowerCase().includes("status_description")
    );
    
    if (hasErrorTag) {
      console.log(`[DEBUG ERROR SPAN] "${span.operationName}" from ${serviceName}:`, {
        allTags: tags.map(t => ({ key: t.key, value: typeof t.value === 'string' && t.value.length > 100 ? t.value.substring(0, 100) + '...' : t.value })),
        statusDescription: tags.find(t => t.key.toLowerCase().includes("status_description"))
      });
    }
    
    // Priority 0: Check for OpenTelemetry status description (MOST DETAILED - includes stack traces, SQL errors, etc)
    const otelStatusDescription = tags.find(t => 
      t.key.toLowerCase() === "otel.status_description" ||
      t.key.toLowerCase().includes("status_description") ||
      t.key.toLowerCase().includes("status.description")
    );
    
    // Priority 1: Check for reject.reason (most specific for rejections)
    const rejectReasonTag = tags.find(t => 
      t.key === "reject.reason" || 
      t.key === "REJECT.REASON" || 
      t.key.toLowerCase() === "reject.reason"
    );
    
    // Priority 2: Check for specific error message fields (most descriptive)
    const errorMessageTag = tags.find(t => 
      t.key === "error.message" || 
      t.key === "ERROR.MESSAGE" || 
      t.key.toLowerCase() === "error.message"
    );
    const errorReasonTag = tags.find(t => 
      t.key === "error.reason" || 
      t.key === "ERROR.REASON" || 
      t.key.toLowerCase() === "error.reason"
    );
    
    // Priority 3: Check for database error descriptions
    const dbStatementTag = tags.find(t => t.key === "db.statement");
    
    // Priority 4: Check for generic error indicator tags.
    //
    // IMPORTANT: do NOT treat arbitrary keys containing "error" as actual errors.
    // Example: `language-detection.postprocess.parsed_error_count=0` is a *metric*,
    // not a failure signal, but naive substring matching would incorrectly flag it.
    const errorTag = tags.find(t => {
      const k = (t.key || "").toLowerCase();
      if (k === "error") return true;
      if (k.startsWith("error.")) return true;
      if (k.startsWith("exception.")) return true;
      if (k.startsWith("otel.error")) return true;
      return false;
    });
    const statusCode = tags.find(t => t.key === "otel.status_code" || t.key === "http.status_code");
    const rejectTag = tags.find(t => t.key.toLowerCase().includes("reject") && t.key.toLowerCase() !== "reject.reason");
    const httpStatus = tags.find(t => t.key === "http.status_code");
    
    // Priority 0: Use OpenTelemetry status description if available (HIGHEST PRIORITY - most detailed)
    if (otelStatusDescription && String(otelStatusDescription.value) !== "OK") {
      hasError = true;
      const fullDescription = String(otelStatusDescription.value);
      
      // Extract the key parts of the error message
      // Format is usually: "<class 'ExceptionType'>: error message\nDETAIL: additional details"
      let cleanedMessage = fullDescription;
      
      // Remove the Python class prefix if present
      cleanedMessage = cleanedMessage.replace(/^<class ['"]([^'"]+)['"]>:\s*/, '$1: ');
      
      // For database errors, extract the main error and detail
      if (cleanedMessage.includes('DETAIL:')) {
        const parts = cleanedMessage.split('DETAIL:');
        const mainError = parts[0].trim();
        const detail = parts[1]?.trim() || '';
        
        // Shorten long details (like JWT tokens) for display
        if (detail.length > 200) {
          const detailPreview = detail.substring(0, 200) + '...';
          errorMessage = `${mainError}\n\nDetails: ${detailPreview}`;
        } else {
          errorMessage = `${mainError}\n\nDetails: ${detail}`;
        }
      } else {
        errorMessage = cleanedMessage;
      }
      
      // Add SQL statement context if this is a database error
      if (dbStatementTag && (cleanedMessage.includes('duplicate key') || cleanedMessage.includes('constraint'))) {
        const sqlStatement = String(dbStatementTag.value);
        // Extract just the operation type and table for brevity
        const sqlMatch = sqlStatement.match(/^(INSERT|UPDATE|DELETE|SELECT)\s+(?:INTO\s+)?(\w+)/i);
        if (sqlMatch) {
          errorMessage = `${errorMessage}\n\nOperation: ${sqlMatch[1]} on table "${sqlMatch[2]}"`;
        }
      }
    }
    // Priority 1: Use reject.reason if available (most specific for rejections)
    else if (rejectReasonTag) {
      hasError = true;
      errorMessage = String(rejectReasonTag.value);
    }
    // Priority 2: Use specific error message if available
    else if (errorMessageTag) {
      hasError = true;
      errorMessage = String(errorMessageTag.value);
      // Add reason if available
      if (errorReasonTag) {
        errorMessage += ` (${errorReasonTag.value})`;
      }
    }
    // Priority 3: Check for error tags (but skip boolean false/true values)
    else if (errorTag) {
      const errorValue = errorTag.value;
      // Skip if value is explicitly false - this means NO error (e.g., has_errors: false)
      if (errorValue === false || errorValue === "false" || String(errorValue).toLowerCase() === "false") {
        // Value is false - not an error, do nothing
      }
      // Skip if it's just a boolean true - not helpful as message
      else if (errorValue !== true && errorValue !== "true" && String(errorValue).toLowerCase() !== "true") {
        hasError = true;
        errorMessage = String(errorValue);
      } else {
        // If error is just "true", check if there's an otel.status_description we missed
        const statusDesc = tags.find(t => 
          t.key.toLowerCase().includes("status") && 
          t.key.toLowerCase().includes("description")
        );
        if (statusDesc && String(statusDesc.value) !== "OK") {
          hasError = true;
          errorMessage = String(statusDesc.value);
        } else {
          // Fall back to checking status codes
          hasError = true;
          errorMessage = "An error occurred during processing";
        }
      }
    } 
    // Priority 4: Check for non-OK status codes
    else if (statusCode && String(statusCode.value) !== "OK" && String(statusCode.value) !== "200") {
      hasError = true;
      errorMessage = `Status: ${statusCode.value}`;
    }
    // Priority 5: Check for HTTP error status codes (4xx, 5xx)
    else if (httpStatus) {
      const status = parseInt(String(httpStatus.value));
      if (status >= 400) {
        hasError = true;
        if (status >= 500) {
          errorMessage = `Server error (${status})`;
        } else {
          errorMessage = `Client error (${status})`;
        }
      }
    }
    // Priority 6: Check for reject tags
    else if (rejectTag) {
      hasError = true;
      errorMessage = String(rejectTag.value);
    }
    // Priority 7: Check operation name for reject
    else if (opName.includes("reject")) {
      hasError = true;
      errorMessage = "Request was rejected during processing";
    }
    // Priority 8: Check logs for errors
    else if (span.logs && span.logs.length > 0) {
      const errorLog = span.logs.find((log: any) => {
        if (log.fields) {
          return log.fields.some((f: any) => 
            f.key === "error" ||
            f.key === "exception" ||
            (f.key === "level" && String(f.value).toLowerCase() === "error") ||
            (f.key === "otel.status_code" && String(f.value) === "ERROR")
          );
        }
        return false;
      });
      if (errorLog) {
        hasError = true;
        const errorField = errorLog.fields.find((f: any) =>
          f.key === "error" || f.key === "exception" || f.key === "message"
        );
        errorMessage = errorField ? String(errorField.value) : "Error occurred during processing";
      }
    }
  };
  
  checkForErrors();

  // IMPORTANT: If this span is one of the standardized phase spans, keep its categorization.
  // Do not override it with the generic rules below.
  if (!isStandardPhaseSpan && opName !== "triton.inference") {
    // Authentication & Authorization - show request.authorize or auth.validate
    if (opName === "request.authorize" || (opName.includes("authorize") && !opName.includes("decision") && !opName.includes("check"))) {
      category = "auth";
      isImportant = true;
      isTopLevel = true;
      icon = FiShield;
      const authMethod = getTag("auth.method") || getTag("auth_source") || "API Key";
      const org = getTag("organization");
      const authResult = getTag("auth.decision.result");
      const authValid = getTag("auth.valid");
      
      // Check if authorization failed
      if (authResult && (authResult.toLowerCase().includes("reject") || authResult.toLowerCase().includes("deny") || authResult.toLowerCase().includes("fail"))) {
        hasError = true;
        errorMessage = `Authorization failed: ${authResult}`;
      } else if (authValid && String(authValid).toLowerCase() === "false") {
        hasError = true;
        errorMessage = "Authorization validation failed";
      }
      displayName = "Request Authorization";
      description = `Validates authentication credentials using ${authMethod}${org ? ` for ${org}` : ""}`;
    }
  // Also show auth.validate if it's a top-level operation
  else if (opName.includes("auth.validate") && !opName.includes("decision") && !opName.includes("check")) {
    category = "auth";
    isImportant = true;
    isTopLevel = false; // Might be nested, but still important
    icon = FiShield;
    const authMethod = getTag("auth.method") || getTag("auth_source") || "API Key";
    const org = getTag("organization");
    const authValid = getTag("auth.valid");
    const authResponseStatus = getTag("auth.response_status");
    
    // Check if validation failed
    if (authValid && String(authValid).toLowerCase() === "false") {
      hasError = true;
      errorMessage = "Authentication validation failed";
    } else if (authResponseStatus && parseInt(authResponseStatus) >= 400) {
      hasError = true;
      errorMessage = `Authentication service returned error (${authResponseStatus})`;
    }
    
    displayName = "Authentication Validation";
    description = `Validates authentication credentials using ${authMethod}${org ? ` for ${org}` : ""}`;
  }
  // end: generic categorization overrides (only for non-standard spans)
  // Skip nested auth decision spans - they're redundant
  else if (opName.includes("auth.decision") || (opName.includes("auth") && opName.includes("check"))) {
    category = "auth";
    isImportant = false; // Don't show nested auth decisions
    icon = FiShield;
    displayName = span.operationName;
    description = "Internal authentication check";
  }
  // Main service operations — {svc}.inference (Telemetry Phase 1 parent; Phase 7 finalizes on close)
  else if (isStandardSvcInferenceOp ||
           opName.includes("/api/v1/ocr/inference") || opName.includes("/api/v1/nmt/inference") ||
           opName.includes("/api/v1/transliteration/inference") ||
           opName.includes("/api/v1/tts/inference") || opName.includes("/api/v1/asr/inference") ||
           (opName.includes("post") && opName.includes("inference") && !serviceName.includes("gateway"))) {
    category = "processing";
    isImportant = true;
    isTopLevel = true;
    icon = FiCpu;
    const serviceId = getTag("ocr.service_id") || getTag("nmt.service_id") ||
           getTag("transliteration.service_id") ||
           getTag("tts.service_id") || getTag("asr.service_id") ||
           getTag("speaker-diarization.service_id") ||
           getTag("language-diarization.service_id") ||
           getTag("language-detection.service_id") ||
           getTag("ner.service_id") ||
           getTag("pipeline.task_types") ||
           getTag("service_id");
    const imageCount = getTag("ocr.image_count");
    const outputCount = getTag("ocr.output_count") || getTag("nmt.output_count") ||
           getTag("transliteration.output_count") ||
           getTag("tts.output_count") || getTag("asr.output_count") ||
           getTag("audio-lang-detection.output_count") ||
           getTag("speaker-diarization.output_count") ||
           getTag("language-diarization.output_count") ||
           getTag("language-detection.output_count") ||
           getTag("ner.output_count") ||
           getTag("pipeline.output_count");
    const sourceLang = getTag("ocr.source_language") || getTag("nmt.source_language") ||
           getTag("transliteration.source_language") ||
           getTag("ner.source_language");
    const targetLang = getTag("nmt.target_language") ||
           getTag("transliteration.target_language");
    displayName = span.operationName;
    // Telemetry Step Standardization: same span is Phase 1 (entry) and Phase 7 (final attrs on close).
    let phaseDesc =
      "Phase 1 — service inference entry (parent span). Phases 2–6 are child spans (preprocess → resolve_model → triton_inference → postprocess → persist). Phase 7 — when this span ends, final metrics are set here ({svc}.processing_time_seconds, {svc}.status).";
    if (isStandardSvcInferenceOp) {
      if (opName.startsWith("nmt.")) {
        phaseDesc =
          "Phase 1 & 7 (NMT): parent span for the translation request; children run the standard phases; on close, records processing time and status.";
      } else if (opName.startsWith("tts.")) {
        phaseDesc =
          "Phase 1 & 7 (TTS): parent span for synthesis; children run preprocess → … → persist; on close, finalizes duration and status.";
      } else if (opName.startsWith("asr.")) {
        phaseDesc =
          "Phase 1 & 7 (ASR): parent span for transcription; children run the standard phases; on close, finalizes timing and status.";
      } else if (opName.startsWith("ocr.")) {
        phaseDesc =
          "Phase 1 & 7 (OCR): parent span for the OCR request; children run the standard phases; on close, finalizes timing and status.";
      } else if (opName.startsWith("pipeline.")) {
        phaseDesc =
          "Phase 1 & 7 (Pipeline): parent span for pipeline orchestration; sub-task spans follow the same lifecycle pattern where applicable.";
      }
    }
    const contextBits: string[] = [];
    if (serviceId) contextBits.push(`service_id ${serviceId}`);
    if (imageCount) contextBits.push(`${imageCount} image(s)`);
    if (sourceLang && targetLang) contextBits.push(`${sourceLang} → ${targetLang}`);
    else if (sourceLang) contextBits.push(`source ${sourceLang}`);
    if (outputCount) contextBits.push(`${outputCount} output(s)`);
    description =
      phaseDesc + (contextBits.length > 0 ? ` Tags: ${contextBits.join(", ")}.` : "");
  }
  // Skip API gateway POST spans - they're just wrappers
  else if (serviceName.includes("gateway") && (opName.includes("post") || opName.includes("http"))) {
    category = "network";
    isImportant = false; // Don't show gateway wrapper spans
    icon = FiGlobe;
    displayName = span.operationName;
    description = "API Gateway routing";
  }
  // Image processing - make this important (it's a key step)
  else if (opName.includes("resolve_image") || (opName.includes("image") && !opName.includes("resolve_images"))) {
    category = "processing";
    isImportant = true;
    icon = FiImage;
    const imageSize = getTag("ocr.image_size_bytes");
    const downloadStatus = getTag("ocr.download_status");
    const imageSource = getTag("ocr.image_source");
    displayName = "Image Processing";
    let descParts = ["Processes image"];
    if (imageSource) descParts.push(`from ${imageSource}`);
    if (imageSize) descParts.push(`(${(parseInt(imageSize) / 1024).toFixed(1)} KB)`);
    if (downloadStatus) descParts.push(`- ${downloadStatus}`);
    description = descParts.join(" ");
  }
  // process_batch is an important AI processing step; resolve_images (plural) and build_response are redundant
  else if (opName.includes("process_batch")) {
    category = "processing";
    isImportant = true; // Show batch processing step - it's a key AI inference step
    icon = FiCpu;
    // Build a friendly display name from the operation name (e.g. "audio-lang-detection.process_batch" → "Batch Processing")
    const servicePart = span.operationName.split(".")[0];
    displayName = "Batch Processing";
    const outputCount = getTag("audio-lang-detection.output_count") || getTag("output_count");
    const processingTime = getTag("audio-lang-detection.processing_time_seconds") || getTag("processing_time_seconds");
    let descParts = [`Processes ${servicePart} batch`];
    if (outputCount) descParts.push(`(${outputCount} output${parseInt(outputCount) !== 1 ? "s" : ""})`);
    if (processingTime) descParts.push(`in ${parseFloat(processingTime).toFixed(2)}s`);
    description = descParts.join(" ");
  }
  // Skip resolve_images (plural) and build_response - they're redundant
  else if (opName.includes("resolve_images") || opName.includes("build_response")) {
    category = "processing";
    isImportant = false; // Don't show these nested processing steps
    icon = FiCpu;
    displayName = span.operationName;
    description = "Internal processing step";
  }
  // Model/Service resolution
  else if (opName.includes("resolve") || opName.includes("model") || opName.includes("routing")) {
    category = "routing";
    isImportant = true;
    icon = FiGlobe;
    displayName = "Model Resolution";
    description = "Determines which model/service to use for processing";
  }
  // Database operations - IMPORTANT for auth-service or if there are errors
  else if (opName.includes("db") || opName.includes("database") || opName.includes("query") || 
           opName.includes("SELECT") || opName.includes("INSERT") || opName.includes("UPDATE") || 
           opName.includes("connect") || opName.includes("commit")) {
    category = "database";
    // ALWAYS mark as important for auth-service AND check for error tags
    const hasDbError = tags.some(t => 
      t.key === "error" && t.value === true ||
      t.key === "otel.status_code" && String(t.value) === "ERROR" ||
      t.key === "otel.status_description" && String(t.value) !== "OK"
    );
    isImportant = serviceName.includes("auth") || hasDbError;
    icon = FiDatabase;
    
    // Debug logging for database spans
    if (serviceName.includes("auth")) {
      console.log(`[DEBUG] Auth-service database span: "${span.operationName}"`, {
        serviceName,
        isImportant,
        hasDbError,
        errorTags: tags.filter(t => t.key.includes("error") || t.key.includes("status"))
      });
    }
    
    // Better display names for different database operations
    if (opName.includes("connect")) {
      displayName = "Database Connection";
      description = "Establishes connection to database";
    } else if (opName.includes("SELECT")) {
      displayName = "Database SELECT";
      description = "Queries data from database";
    } else if (opName.includes("INSERT")) {
      displayName = "Database INSERT";
      description = "Inserts new data into database";
    } else if (opName.includes("UPDATE")) {
      displayName = "Database UPDATE";
      description = "Updates existing data in database";
    } else if (opName.includes("DELETE")) {
      displayName = "Database DELETE";
      description = "Deletes data from database";
    } else if (opName.includes("commit")) {
      displayName = "Database Commit";
      description = "Commits transaction to database";
    } else {
      displayName = "Database Query";
      description = "Retrieves or stores data";
    }
  }
  // HTTP requests - only show main API endpoint, not internal HTTP spans
  else if ((opName.includes("http") && opName.includes("receive")) || 
           (opName.includes("http") && opName.includes("send"))) {
    category = "network";
    isImportant = false; // Don't show low-level HTTP spans
    icon = FiGlobe;
    displayName = span.operationName;
    description = "HTTP request handling";
  }
  // Skip other HTTP spans
  else if (opName.includes("http") || (opName === "post" && !opName.includes("inference"))) {
    category = "network";
    isImportant = false;
    icon = FiGlobe;
    displayName = span.operationName;
    description = "Internal HTTP operation";
  }
  // Middleware
  else if (opName.includes("middleware") || opName.includes("logging") || opName.includes("correlation")) {
    category = "middleware";
    isImportant = false;
    icon = FiSettings;
    displayName = span.operationName.replace("middleware.", "").replace(/_/g, " ");
    description = "Request processing middleware";
  }
  // Triton inference - check this BEFORE batch processing
  else if (opName.includes("triton")) {
    category = "processing";
    isImportant = true;
    icon = FiCpu;
    const modelName = getTag("triton.model_name");
    const batchSize = getTag("triton.batch_size");
    const status = getTag("triton.status");
    const outputCount = getTag("triton.output_count");
    const parseErrors = getTag("triton.parse_errors");
    const outputStatus = getTag("triton.output_status");
    displayName = "AI Model Inference";
    let descParts = ["Runs AI model"];
    if (modelName) descParts.push(`(${modelName})`);
    if (batchSize) descParts.push(`on batch of ${batchSize}`);
    if (outputCount) descParts.push(`→ ${outputCount} result${parseInt(outputCount) !== 1 ? "s" : ""}`);
    if (status) descParts.push(`- ${status}`);
    description = descParts.join(" ");
    
    // Override error detection for triton spans: check triton.status explicitly
    // Priority 1: If triton.status is "success", clear any error flags (definitive success)
    if (status && String(status).trim().toLowerCase() === "success") {
      hasError = false;
      errorMessage = undefined;
    }
    // Priority 2: If triton.status is "failed", mark as error (definitive failure)
    else if (status && String(status).trim().toLowerCase() === "failed") {
      hasError = true;
      if (!errorMessage) {
        errorMessage = "Triton inference failed";
      }
    }
    // Priority 3: If parse_errors exists and is > 0, mark as error
    else if (parseErrors && parseInt(parseErrors) > 0) {
      hasError = true;
      if (!errorMessage) {
        errorMessage = `Triton parsing errors: ${parseErrors}`;
      }
    }
    // Priority 4: If output_status is "error" or "failed", mark as error
    else if (outputStatus && (String(outputStatus).toLowerCase() === "error" || String(outputStatus).toLowerCase() === "failed")) {
      hasError = true;
      if (!errorMessage) {
        errorMessage = `Triton output status: ${outputStatus}`;
      }
    }
    // Priority 5: If triton.status is empty/missing but indicators suggest success:
    // - parse_errors is 0 or missing
    // - output_status is "parsed" or "success"
    // - No explicit error tags from checkForErrors
    // Then clear error flags (assume success)
    else if ((!status || String(status).trim() === "") && 
             (!parseErrors || parseInt(parseErrors) === 0) && 
             outputStatus && 
             (String(outputStatus).toLowerCase() === "parsed" || String(outputStatus).toLowerCase() === "success")) {
      // Only clear error if there's no explicit error tag from OpenTelemetry
      const hasExplicitError = tags.some(t => 
        (t.key === "error" && t.value === true) ||
        (t.key === "otel.status_code" && String(t.value) === "ERROR")
      );
      if (!hasExplicitError) {
        hasError = false;
        errorMessage = undefined;
      }
    }
  }
  // Batch processing - but exclude triton_batch (already handled above)
  else if (opName.includes("batch") && !opName.includes("triton")) {
    category = "processing";
    isImportant = true;
    icon = FiCpu;
    const totalImages = getTag("ocr.total_images");
    const outputCount = getTag("ocr.output_count");
    const resultsCount = getTag("ocr.results_count");
    const successCount = getTag("ocr.success_count");
    displayName = "Batch Processing";
    let descParts = ["Processes multiple items in a batch"];
    if (totalImages) descParts.push(`(${totalImages} image${parseInt(totalImages) !== 1 ? "s" : ""})`);
    if (resultsCount) descParts.push(`→ ${resultsCount} result${parseInt(resultsCount) !== 1 ? "s" : ""}`);
    if (successCount) descParts.push(`(${successCount} successful)`);
    description = descParts.join(" ");
  }
  // Response building
  else if (opName.includes("response") || opName.includes("build")) {
    category = "response";
    isImportant = true;
    icon = FiCheckCircle;
    const responseSize = getTag("http.response.size_bytes");
    const outputCount = getTag("ocr.output_count") || getTag("ocr.successful_outputs");
    displayName = "Response Construction";
    let descParts = ["Formats the final response"];
    if (outputCount) descParts.push(`(${outputCount} output${parseInt(outputCount) !== 1 ? "s" : ""})`);
    if (responseSize) descParts.push(`- ${(parseInt(responseSize) / 1024).toFixed(1)} KB`);
    description = descParts.join(" ");
  }
  // Default: mark as important if it has any meaningful duration (>1ms) and is not middleware/HTTP
  else if (span.duration > 1000 && !opName.includes("middleware") && !opName.includes("correlation") && 
           !opName.includes("http receive") && !opName.includes("http send") &&
           !opName.includes("asgi.event")) {
    category = "processing";
    isImportant = true;
    icon = FiCpu;
    // Try to create a better display name
    if (opName.includes("post") || opName.includes("get")) {
      displayName = span.operationName;
      description = `Handles ${span.operationName}`;
    } else {
      displayName = span.operationName.replace(/\./g, " ").replace(/_/g, " ");
      description = `Processes ${displayName}`;
    }
  }

  } // <-- closes: if (!isStandardPhaseSpan && opName !== "triton.inference")

  // Check for request.reject operations - mark as important and error
  if (opName.includes("reject") || opName.includes("request.reject")) {
    category = "error";
    hasError = true;
    isImportant = true; // Always show reject operations
    isTopLevel = true; // Make them prominent
    icon = FiShield; // Use shield icon for security-related rejections
    displayName = "Request Rejection";
    description = "Request was rejected";
    
    // Try to get more specific error message from tags
    const rejectReason = getTag("reject.reason") || getTag("error.message") || getTag("error");
    if (rejectReason) {
      errorMessage = String(rejectReason);
    } else {
      errorMessage = "Request was rejected during processing";
    }
  }
  
  // SPECIAL OVERRIDE: For auth-service, mark all auth-related operations as important
  // This ensures we see the full authentication flow including database operations
  if (serviceName.includes("auth")) {
    if (opName.includes("login") || opName.includes("auth") || opName.includes("user") || 
        opName.includes("session") || opName.includes("token") || category === "database") {
      isImportant = true;
      if (opName.includes("login") || opName.includes("POST") && opName.includes("auth")) {
        isTopLevel = true; // Main auth endpoints are top-level
      }
    }
  }
  
  // SPECIAL OVERRIDE: Any span with errors should be marked as important
  if (hasError) {
    isImportant = true;
  }

  return {
    span,
    serviceName,
    category,
    displayName,
    description,
    icon,
    isImportant,
    isTopLevel,
    hasError,
    errorMessage,
    relativeStart: (span.startTime - traceStartTime) / 1000, // Convert microseconds to milliseconds, relative to trace start
    relativeEnd: (span.startTime + span.duration - traceStartTime) / 1000,
  };
};

const extractImportantSpans = (trace: Trace): ProcessedSpan[] => {
  if (!trace.spans || trace.spans.length === 0) {
    console.warn("extractImportantSpans: No spans in trace");
    return [];
  }
  
  if (!trace.processes || Object.keys(trace.processes).length === 0) {
    console.warn("extractImportantSpans: No processes in trace");
    return [];
  }
  
  // Use startTime if available, otherwise calculate from spans
  let traceStartTime = trace.startTime;
  if (!traceStartTime || traceStartTime === 0) {
    traceStartTime = Math.min(...trace.spans.map(s => s.startTime));
    console.log("Calculated traceStartTime from spans:", traceStartTime);
  }
  
  if (!traceStartTime || traceStartTime === 0) {
    console.warn("extractImportantSpans: Cannot determine trace start time");
    return [];
  }

  // Build span tree to understand parent-child relationships
  const spanMap = new Map<string, Span>();
  const childSpans = new Map<string, string[]>(); // parentSpanID -> [childSpanIDs]
  const spanToParent = new Map<string, string>(); // childSpanID -> parentSpanID

  trace.spans.forEach(span => {
    spanMap.set(span.spanID, span);
    
    // Check for parent references
    if (span.references && span.references.length > 0) {
      const parentRef = span.references.find(ref => ref.refType === "CHILD_OF");
      if (parentRef) {
        spanToParent.set(span.spanID, parentRef.spanID);
        if (!childSpans.has(parentRef.spanID)) {
          childSpans.set(parentRef.spanID, []);
        }
        childSpans.get(parentRef.spanID)!.push(span.spanID);
      }
    }
  });

  // Process all spans
  const processed: ProcessedSpan[] = trace.spans.map(span => {
    const process = trace.processes[span.processID];
    const serviceName = process?.serviceName || "unknown";
    const categorized = categorizeSpan(span, serviceName, traceStartTime);
    return categorized;
  });

  // Detect VAD fallback pattern: VAD failed but ASR preprocessing succeeded with single chunk
  // This indicates graceful degradation - VAD failed but processing continued with fallback
  const detectVadFallback = () => {
    // Find failed VAD triton inference spans
    const failedVadSpans = processed.filter(p => {
      const opName = p.span.operationName.toLowerCase();
      const tags = p.span.tags || [];
      const modelName = tags.find(t => t.key.toLowerCase() === "triton.model_name");
      return opName.includes("triton") && 
             p.hasError && 
             modelName && 
             String(modelName.value).toLowerCase() === "vad";
    });

    if (failedVadSpans.length === 0) return;

    // For each failed VAD span, check if its parent is a successful preprocessing span
    failedVadSpans.forEach(vadSpan => {
      const vadSpanId = vadSpan.span.spanID;
      const parentId = spanToParent.get(vadSpanId);

      if (parentId) {
        const parentSpan = processed.find(p => p.span.spanID === parentId);

        if (parentSpan) {
          const parentOpName = parentSpan.span.operationName.toLowerCase();
          const parentTags = parentSpan.span.tags || [];
          const chunksCount = parentTags.find(t => t.key.toLowerCase() === "asr.chunks_count");
          const isAsrPreprocess = (parentOpName.includes("preprocess") || parentOpName.includes("asr.preprocess")) &&
                                  parentSpan.serviceName.toLowerCase().includes("asr");

          // If parent is ASR preprocessing that succeeded with single chunk, VAD error was handled
          if (isAsrPreprocess && !parentSpan.hasError && chunksCount && parseInt(String(chunksCount.value)) === 1) {
            // Mark VAD span as not important - it's a handled error, don't show it prominently
            vadSpan.isImportant = false;
            // Add note to parent preprocessing span about fallback
            if (!parentSpan.description.includes("fallback")) {
              parentSpan.description = `${parentSpan.description} (VAD fallback activated - processing continued with single chunk)`;
            }
          }
        }
      }
    });
  };

  detectVadFallback();

  // Debug: Log how many spans are marked as important
  const importantCount = processed.filter(p => p.isImportant).length;
  console.log(`Processed ${processed.length} spans, ${importantCount} marked as important`);

  // Detect the primary service from the trace
  // Primary service is the one with the most top-level important spans, or the longest duration
  const topLevelSpans = processed.filter(p => p.isTopLevel && p.isImportant);
  const serviceDuration = new Map<string, number>();
  const serviceTopLevelCount = new Map<string, number>();
  
  processed.forEach(p => {
    const current = serviceDuration.get(p.serviceName) || 0;
    serviceDuration.set(p.serviceName, current + p.span.duration);
    
    if (p.isTopLevel && p.isImportant) {
      const count = serviceTopLevelCount.get(p.serviceName) || 0;
      serviceTopLevelCount.set(p.serviceName, count + 1);
    }
  });
  
  // Find primary service: prefer service with most top-level spans, then longest duration
  let primaryService = "unknown";
  let maxTopLevelCount = 0;
  for (const [service, count] of Array.from(serviceTopLevelCount.entries())) {
    if (count > maxTopLevelCount) {
      maxTopLevelCount = count;
      primaryService = service;
    }
  }
  
  // If no clear winner by top-level count, use duration
  if (maxTopLevelCount === 0 || (maxTopLevelCount === 1 && serviceTopLevelCount.size > 1)) {
    let maxDuration = 0;
    for (const [service, duration] of Array.from(serviceDuration.entries())) {
      if (duration > maxDuration) {
        maxDuration = duration;
        primaryService = service;
      }
    }
  }
  
  const isAuthServiceTrace = primaryService.includes("auth-service");
  console.log(`[DEBUG] Primary service detected: ${primaryService}, isAuthServiceTrace: ${isAuthServiceTrace}`);

  // Filter out child spans when we have a parent span of the same category
  const filtered: ProcessedSpan[] = [];
  const seenOperations = new Map<string, ProcessedSpan>(); // operationKey -> best span
  
  // Then, collect other important spans that aren't children of top-level spans
  for (const processedSpan of processed) {
    if (!processedSpan.isImportant) continue;
    
    // SPECIAL FILTERING: For non-auth-service traces, filter out child auth-service spans
    // Only show top-level auth spans from auth-service when it's not the primary service
    if (!isAuthServiceTrace && processedSpan.serviceName.includes("auth-service")) {
      // Check if this is a child span (has a parent)
      const parentId = spanToParent.get(processedSpan.span.spanID);
      if (parentId) {
        // This is a child span from auth-service - filter it out
        // Only keep top-level auth spans (like POST /api/v1/auth/validate)
        if (!processedSpan.isTopLevel || processedSpan.category === "database") {
          console.log(`[DEBUG] Filtering out child auth-service span (non-auth trace): ${processedSpan.displayName}`);
          continue;
        }
      }
    }
    
    // Check if this span is a child of a top-level span with same category
    const parentId = spanToParent.get(processedSpan.span.spanID);
    if (parentId) {
      const parentSpan = processed.find(p => p.span.spanID === parentId);
      if (parentSpan && parentSpan.isTopLevel && parentSpan.category === processedSpan.category) {
        // Skip this child span, parent is more important
        continue;
      }
    }
    
    // SPECIAL: Error spans should NEVER be deduplicated - always show them
    // They contain critical debugging information
    if (processedSpan.hasError) {
      filtered.push(processedSpan);
      console.log(`[DEBUG] Including error span (never deduplicated): ${processedSpan.displayName}`);
      continue; // Skip deduplication logic
    }
    
    // SPECIAL: Database operations should NEVER be deduplicated - show all of them
    // BUT: Only show all database operations for auth-service traces
    // For other traces, database operations from auth-service are already filtered above
    if (processedSpan.category === "database") {
      // Only show all database operations if this is an auth-service trace
      // OR if the database operation is not from auth-service
      if (isAuthServiceTrace || !processedSpan.serviceName.includes("auth-service")) {
        filtered.push(processedSpan);
        console.log(`[DEBUG] Including database operation (never deduplicated): ${processedSpan.displayName}`);
        continue; // Skip deduplication logic
      } else {
        // For non-auth traces, filter out auth-service database operations
        console.log(`[DEBUG] Filtering out auth-service database operation (non-auth trace): ${processedSpan.displayName}`);
        continue;
      }
    }
    
    // Create a unique key for this operation (service + category + displayName)
    const operationKey = `${processedSpan.serviceName}:${processedSpan.category}:${processedSpan.displayName}`;
    const existing = seenOperations.get(operationKey);
    
    if (!existing) {
      // First time seeing this operation
      seenOperations.set(operationKey, processedSpan);
      filtered.push(processedSpan);
    } else {
      // We've seen this operation before - keep the better one
      // Prefer: ERROR SPANS > top-level > longer duration
      const shouldReplace = 
        (processedSpan.hasError && !existing.hasError) || // ALWAYS prefer error spans!
        (!existing.hasError && processedSpan.isTopLevel && !existing.isTopLevel) ||
        (!existing.hasError && !existing.isTopLevel && processedSpan.span.duration > existing.span.duration) ||
        (processedSpan.isTopLevel === existing.isTopLevel && 
         processedSpan.span.duration > existing.span.duration * 1.5); // Significantly longer
      
      if (shouldReplace) {
        // Replace the existing one
        const index = filtered.indexOf(existing);
        if (index >= 0) {
          filtered[index] = processedSpan;
        }
        seenOperations.set(operationKey, processedSpan);
      }
    }
  }

  // Sort by start time
  const sorted = filtered.sort((a, b) => a.relativeStart - b.relativeStart);

  // ─── Displayed-tree exclusive duration ────────────────────────────────────
  // Each displayed span should show ONLY the time it spends on its OWN work,
  // not time covered by any displayed descendant. This ensures all step
  // durations add up correctly to the total trace duration.
  //
  // Algorithm: build a "displayed tree" where the parent of each displayed
  // span is its nearest displayed ancestor (walking up the Jaeger parent chain).
  // Then: effectiveDuration = span.duration − Σ(displayed direct children durations)
  const computeEffectiveDurations = (spanList: ProcessedSpan[]): void => {
    const displayedIds = new Set(spanList.map(p => p.span.spanID));
    const processedById = new Map<string, ProcessedSpan>(
      spanList.map(p => [p.span.spanID, p])
    );

    // For each displayed span, walk up the Jaeger parent chain to find the
    // nearest displayed ancestor (which may be a grandparent if the direct
    // parent is not in the displayed list).
    const displayedParentOf = new Map<string, string>(); // childId → parentId
    spanList.forEach(p => {
      let cur: string | undefined = spanToParent.get(p.span.spanID);
      while (cur) {
        if (displayedIds.has(cur)) {
          displayedParentOf.set(p.span.spanID, cur);
          break;
        }
        cur = spanToParent.get(cur);
      }
    });

    // Invert: parentId → [childId, ...]
    const displayedChildrenOf = new Map<string, string[]>();
    displayedParentOf.forEach((parentId, childId) => {
      if (!displayedChildrenOf.has(parentId)) displayedChildrenOf.set(parentId, []);
      displayedChildrenOf.get(parentId)!.push(childId);
    });

    // Set effectiveDuration for each span that has displayed children
    spanList.forEach(p => {
      const children = displayedChildrenOf.get(p.span.spanID) || [];
      if (children.length > 0) {
        const childrenSum = children.reduce((sum, childId) => {
          const child = processedById.get(childId);
          return sum + (child ? child.span.duration : 0);
        }, 0);
        const exclusive = p.span.duration - childrenSum;
        p.effectiveDuration = exclusive >= 0 ? exclusive : 0;
      } else {
        p.effectiveDuration = undefined; // no displayed children → show full span duration
      }
    });
  };

  // Phase 7 (Telemetry Step Standardization): {svc}.processing_time_seconds and {svc}.status are set when
  // {svc}.inference ends — no separate span; see categorizeSpan description for that parent span.

  // If we have too few spans, include some important non-top-level ones
  if (sorted.length < 3) {
    const additional = processed
      .filter(p => p.isImportant && !sorted.some(s => s.span.spanID === p.span.spanID))
      .filter(p => {
        // Don't add if parent is already in the list
        const parentId = spanToParent.get(p.span.spanID);
        if (parentId) {
          return !sorted.some(s => s.span.spanID === parentId);
        }
        return true;
      })
      .sort((a, b) => a.relativeStart - b.relativeStart)
      .slice(0, 5 - sorted.length);
    
    const combined = [...sorted, ...additional].sort((a, b) => a.relativeStart - b.relativeStart);
    computeEffectiveDurations(combined);
    return combined;
  }

  // If still no spans, include any spans that have significant duration (>10ms) or are root spans
  if (sorted.length === 0) {
    console.log("No spans matched criteria, using fallback. Total processed spans:", processed.length);
    console.log("Important spans count:", processed.filter(p => p.isImportant).length);
    
    // First try: spans with significant duration (>1ms to be more inclusive)
    let fallbackSpans = processed
      .filter(p => {
        const hasSignificantDuration = p.span.duration > 1000; // > 1ms (more inclusive)
        return hasSignificantDuration;
      })
      .filter(p => {
        // Skip middleware and low-level HTTP
        const opName = p.span.operationName.toLowerCase();
        return !opName.includes("middleware") &&
               !opName.includes("correlation") &&
               !opName.includes("http receive") &&
               !opName.includes("http send");
      })
      .sort((a, b) => b.span.duration - a.span.duration) // Sort by duration descending
      .slice(0, 10);
    
    console.log("Fallback spans with duration >1ms:", fallbackSpans.length);
    
    // If still empty, include root spans (no parent) or any spans with duration >100μs
    if (fallbackSpans.length === 0) {
      fallbackSpans = processed
        .filter(p => {
          const hasParent = spanToParent.has(p.span.spanID);
          const hasAnyDuration = p.span.duration > 100; // > 100μs
          return !hasParent || hasAnyDuration;
        })
        .filter(p => {
          const opName = p.span.operationName.toLowerCase();
          return !opName.includes("middleware") &&
                 !opName.includes("correlation") &&
                 !opName.includes("http receive") &&
                 !opName.includes("http send");
        })
        .sort((a, b) => {
          // Prefer root spans, then by duration
          const aIsRoot = !spanToParent.has(a.span.spanID);
          const bIsRoot = !spanToParent.has(b.span.spanID);
          if (aIsRoot !== bIsRoot) return aIsRoot ? -1 : 1;
          return b.span.duration - a.span.duration;
        })
        .slice(0, 10);
      
      console.log("Fallback spans (root or any duration):", fallbackSpans.length);
    }
    
    // Re-categorize fallback spans to make them important and improve descriptions
    const finalSpans = fallbackSpans.map(p => {
      const opName = p.span.operationName.toLowerCase();
      let displayName = p.displayName || p.span.operationName;
      let description = p.description;
      
      // Improve display names for common operations
      if (opName.includes("post") && opName.includes("inference")) {
        displayName = p.serviceName.includes("ocr") ? "OCR Processing" : 
                     p.serviceName.includes("nmt") ? "Translation Processing" : 
                     "Request Processing";
        description = "Processes the request";
      } else if (opName.includes("authorize") || opName.includes("auth")) {
        displayName = "Request Authorization";
        description = "Validates authentication credentials";
      } else if (opName.includes("triton")) {
        displayName = "AI Model Inference";
        description = "Runs AI model";
      }
      
      return {
        ...p,
        isImportant: true,
        hasError: p.hasError || false,
        errorMessage: p.errorMessage,
        displayName,
        description: description || `Processes ${p.span.operationName}`,
        icon: p.icon || FiSettings,
      };
    }).sort((a, b) => a.relativeStart - b.relativeStart);
    
    console.log("Final fallback spans:", finalSpans.length, finalSpans.map(s => s.displayName));
    computeEffectiveDurations(finalSpans);
    return finalSpans;
  }

  computeEffectiveDurations(sorted);
  return sorted;
};

const formatDuration = (microseconds: number | undefined) => {
  if (!microseconds || isNaN(microseconds)) return "N/A";
  if (microseconds < 1000) return `${microseconds}μs`;
  if (microseconds < 1000000) return `${(microseconds / 1000).toFixed(2)}ms`;
  return `${(microseconds / 1000000).toFixed(2)}s`;
};

const formatTimestamp = (microseconds: number | undefined) => {
  if (!microseconds || isNaN(microseconds)) return "N/A";
  try {
    const milliseconds = microseconds / 1000;
    const date = new Date(milliseconds);
    if (isNaN(date.getTime())) return "Invalid Date";
    return date.toLocaleString();
  } catch {
    return "Invalid Date";
  }
};

const formatRelativeTime = (milliseconds: number) => {
  if (milliseconds < 1000) return `${milliseconds.toFixed(0)}ms`;
  return `${(milliseconds / 1000).toFixed(2)}s`;
};

// Format tag values with units based on key name
const formatTagValue = (key: string, value: any): string => {
  const keyLower = key.toLowerCase();
  const numValue = typeof value === 'number' ? value : parseFloat(String(value));
  
  // Special handling for database statements - make them more readable
  if (keyLower === 'db.statement') {
    const sqlStatement = String(value);
    
    // Truncate very long SQL statements
    if (sqlStatement.length > 500) {
      // Show first 500 chars with proper SQL formatting
      const truncated = sqlStatement.substring(0, 500);
      const formattedSql = truncated
        .replace(/\s+/g, ' ') // Collapse multiple spaces
        .replace(/(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|JOIN|LEFT JOIN|RIGHT JOIN|INNER JOIN|ORDER BY|GROUP BY|VALUES|SET|AND|OR)/gi, '\n$1')
        .trim();
      return `${formattedSql}\n\n... (truncated, ${sqlStatement.length} total chars)`;
    }
    
    // Format SQL for readability
    return sqlStatement
      .replace(/\s+/g, ' ') // Collapse multiple spaces
      .replace(/(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|JOIN|LEFT JOIN|RIGHT JOIN|INNER JOIN|ORDER BY|GROUP BY|VALUES|SET|AND|OR)/gi, '\n$1')
      .trim();
  }
  
  // Special handling for status descriptions - format for readability
  if (keyLower === 'otel.status_description') {
    let description = String(value);
    
    // Clean up the Python class prefix
    description = description.replace(/^<class ['"]([^'"]+)['"]>:\s*/, '$1:\n');
    
    // Format DETAIL sections on new lines
    description = description.replace(/\s+DETAIL:\s+/g, '\n\nDETAIL:\n  ');
    
    // Format constraint violations nicely
    description = description.replace(/duplicate key value violates unique constraint/gi, 
      'Duplicate key value violates unique constraint');
    
    return description.trim();
  }
  
  // Special handling for error messages - preserve formatting
  if (keyLower.includes('error') && (keyLower.includes('message') || keyLower.includes('description'))) {
    return String(value);
  }
  
  // Check for milliseconds - look for _ms, .ms, or keys ending with ms
  if (keyLower.includes('_ms') || keyLower.includes('.ms') || 
      keyLower.endsWith('ms') || keyLower.includes('audio_length_ms') ||
      keyLower.includes('length_ms') || keyLower.includes('duration_ms')) {
    if (!isNaN(numValue)) {
      return `${numValue} ms`;
    }
  }
  
  // Check for seconds - look for _seconds, .seconds, or keys ending with seconds
  if (keyLower.includes('_seconds') || keyLower.includes('.seconds') || 
      keyLower.endsWith('seconds') || keyLower.includes('audio_length_seconds') ||
      keyLower.includes('length_seconds') || keyLower.includes('duration_seconds') ||
      keyLower.includes('total_duration') || keyLower.includes('processing_time_seconds')) {
    if (!isNaN(numValue)) {
      return `${numValue} s`;
    }
  }
  
  // Check for bytes - look for _bytes, .bytes, or keys ending with bytes
  if (keyLower.includes('_bytes') || keyLower.includes('.bytes') || 
      keyLower.endsWith('bytes') || keyLower.includes('size_bytes')) {
    if (!isNaN(numValue)) {
      // Format bytes with appropriate unit (B, KB, MB, GB)
      if (numValue < 1024) {
        return `${numValue} B`;
      } else if (numValue < 1024 * 1024) {
        return `${(numValue / 1024).toFixed(2)} KB`;
      } else if (numValue < 1024 * 1024 * 1024) {
        return `${(numValue / (1024 * 1024)).toFixed(2)} MB`;
      } else {
        return `${(numValue / (1024 * 1024 * 1024)).toFixed(2)} GB`;
      }
    }
  }
  
  // Default: return value as string
  return String(value);
};

// Parse error message into structured key-value pairs
interface ErrorDetails {
  errorType: string;
  summary: string;
  fields: { key: string; value: string }[];
}

const parseErrorDetails = (processed: ProcessedSpan): ErrorDetails | null => {
  if (!processed.hasError || !processed.errorMessage) {
    return null;
  }

  const errorMessage = processed.errorMessage;
  const errorMsgLower = errorMessage.toLowerCase();
  const fields: { key: string; value: string }[] = [];
  let errorType = "";
  let summary = "";

  // Parse database constraint violation errors
  if (errorMsgLower.includes("uniqueviolation") || errorMsgLower.includes("duplicate key")) {
    errorType = "Database Constraint Violation";
    summary = "Multiple users trying to login simultaneously generated the same session/refresh tokens.";

    // Extract exception class
    const exceptionMatch = errorMessage.match(/([A-Za-z]+Error|[A-Za-z]+Exception):/);
    if (exceptionMatch) {
      fields.push({ key: "Exception Type", value: exceptionMatch[1] });
    }

    // Extract constraint name
    const constraintMatch = errorMessage.match(/unique constraint ["']([^"']+)["']/i);
    if (constraintMatch) {
      fields.push({ key: "Constraint Violated", value: constraintMatch[1] });
    }

    // Extract the duplicate key information from DETAIL
    const detailMatch = errorMessage.match(/Details?:\s*(.+?)(?:\n|$)/i);
    if (detailMatch) {
      let detail = detailMatch[1].trim();
      // Extract just the key part if it's formatted like "Key (column_name)=(value) already exists"
      const keyMatch = detail.match(/Key \(([^)]+)\)=\(([^)]+)\)/);
      if (keyMatch) {
        fields.push({ key: "Duplicate Column", value: keyMatch[1] });
        // Truncate long values (like tokens)
        const value = keyMatch[2];
        if (value.length > 50) {
          fields.push({ key: "Duplicate Value", value: value.substring(0, 50) + "..." });
        } else {
          fields.push({ key: "Duplicate Value", value: value });
        }
      } else {
        fields.push({ key: "Detail", value: detail });
      }
    }

    // Extract SQL operation
    const operationMatch = errorMessage.match(/Operation:\s*(\w+)\s+on\s+table\s+["']?(\w+)["']?/i);
    if (operationMatch) {
      fields.push({ key: "SQL Operation", value: `${operationMatch[1]} on table "${operationMatch[2]}"` });
    }

    // Extract SQL statement if available
    const tags = processed.span.tags || [];
    const dbStatement = tags.find(t => t.key === "db.statement");
    if (dbStatement) {
      const stmt = String(dbStatement.value);
      const stmtMatch = stmt.match(/^(INSERT|UPDATE|DELETE|SELECT)\s+(?:INTO\s+)?(\w+)/i);
      if (stmtMatch && !operationMatch) {
        fields.push({ key: "SQL Operation", value: `${stmtMatch[1]} INTO ${stmtMatch[2]}` });
      }
    }

  }
  // Parse greenlet/async errors
  else if (errorMsgLower.includes("greenlet_spawn") || errorMsgLower.includes("await_only")) {
    errorType = "Async Operation Error";
    summary = "Database accessed incorrectly after transaction rollback - this is a code bug.";

    // Extract exception class
    const exceptionMatch = errorMessage.match(/([A-Za-z]+Error|[A-Za-z]+Exception):/);
    if (exceptionMatch) {
      fields.push({ key: "Exception Type", value: exceptionMatch[1] });
    }

    fields.push({ key: "Root Cause", value: "Attempted to use database session after rollback" });
    fields.push({ key: "Fix Required", value: "Move db.refresh() inside try block or use a new session" });

    // Try to extract the specific error message
    const msgMatch = errorMessage.match(/(?:Error|Exception):\s*(.+?)(?:\n|$)/);
    if (msgMatch) {
      fields.push({ key: "Error Message", value: msgMatch[1].trim() });
    }
  }
  // Parse operational/connection errors
  else if (errorMsgLower.includes("operationalerror") || errorMsgLower.includes("connection")) {
    errorType = "Database Connection Error";
    summary = "Failed to connect to or communicate with the database.";

    // Extract exception class
    const exceptionMatch = errorMessage.match(/([A-Za-z]+Error|[A-Za-z]+Exception):/);
    if (exceptionMatch) {
      fields.push({ key: "Exception Type", value: exceptionMatch[1] });
    }

    // Check for specific connection issues
    if (errorMsgLower.includes("timeout")) {
      fields.push({ key: "Cause", value: "Connection timeout" });
    } else if (errorMsgLower.includes("refused")) {
      fields.push({ key: "Cause", value: "Connection refused" });
    } else {
      fields.push({ key: "Cause", value: "Database operational issue" });
    }

    // Extract error message
    const msgMatch = errorMessage.match(/(?:Error|Exception):\s*(.+?)(?:\n|$)/);
    if (msgMatch) {
      fields.push({ key: "Error Message", value: msgMatch[1].trim() });
    }
  }
  // Parse authentication errors
  else if (processed.category === "auth" || processed.displayName.includes("Authorization")) {
    errorType = "Authentication Failure";
    summary = "The provided credentials were invalid, expired, or insufficient.";

    fields.push({ key: "Error", value: errorMessage });

    // Check for specific auth error types
    if (errorMsgLower.includes("expired")) {
      fields.push({ key: "Reason", value: "Token or session has expired" });
    } else if (errorMsgLower.includes("invalid")) {
      fields.push({ key: "Reason", value: "Invalid credentials or token" });
    } else if (errorMsgLower.includes("permission")) {
      fields.push({ key: "Reason", value: "Insufficient permissions" });
    }
  }
  // Generic error
  else {
    errorType = "Processing Error";
    summary = "An error occurred during request processing.";

    // Try to extract exception type
    const exceptionMatch = errorMessage.match(/([A-Za-z]+Error|[A-Za-z]+Exception):/);
    if (exceptionMatch) {
      fields.push({ key: "Exception Type", value: exceptionMatch[1] });
      errorType = exceptionMatch[1];
    }

    // Extract error message
    const msgMatch = errorMessage.match(/(?:Error|Exception):\s*(.+?)(?:\n|$)/);
    if (msgMatch) {
      fields.push({ key: "Error Message", value: msgMatch[1].trim() });
    } else {
      fields.push({ key: "Error Message", value: errorMessage });
    }
  }

  return {
    errorType,
    summary,
    fields
  };
};

// Generate user-friendly description for spans
const getUserFriendlyDescription = (processed: ProcessedSpan): string => {
  const tags = processed.span.tags || [];
  const getTag = (key: string) => {
    const tag = tags.find(t => t.key.toLowerCase() === key.toLowerCase());
    return tag ? String(tag.value) : null;
  };
  const opLc = (processed.span.operationName || "").toLowerCase();
  const isStandardSvcInferenceName =
    /^[a-z0-9-]+\.inference$/.test(opLc) && !opLc.startsWith("triton.");
  const isHttpInferenceRoute =
    opLc.includes("/api/v1/nmt/inference") ||
    opLc.includes("/api/v1/ocr/inference") ||
    opLc.includes("/api/v1/transliteration/inference") ||
    opLc.includes("/api/v1/tts/inference") ||
    opLc.includes("/api/v1/asr/inference") ||
    opLc.includes("/api/v1/ner/inference") ||
    (opLc.includes("post") && opLc.includes("inference") && opLc.includes("/api/v1/"));

  // If there's an error, return simple error indicator
  // (detailed error will be shown in separate section)
  if (processed.hasError) {
    return "This step encountered an error during processing.";
  }

  switch (processed.category) {
    case "auth":
      if (processed.displayName.includes("Authorization")) {
        const org = getTag("organization");
        const method = getTag("auth.method") || "API Key";
        return `This step verifies that the request is coming from an authorized user or application. It checks the ${method} credentials${org ? ` for the organization "${org}"` : ""} to ensure the request has permission to access the service.`;
      } else if (processed.displayName.includes("Validation")) {
        const org = getTag("organization");
        return `This step validates the authentication credentials to confirm they are valid and not expired. It ensures the user has the necessary permissions${org ? ` for "${org}"` : ""} to perform this operation.`;
      }
      return "This step verifies the identity and permissions of the user making the request.";

    case "processing":
      if (processed.displayName.includes("OCR Processing")) {
        const imageCount = getTag("ocr.image_count");
        const outputCount = getTag("ocr.output_count");
        const serviceId = getTag("ocr.service_id");
        let desc = "This step processes the image(s) to extract text using Optical Character Recognition (OCR). ";
        if (imageCount) desc += `It analyzes ${imageCount} image${parseInt(imageCount) !== 1 ? "s" : ""}. `;
        if (serviceId) desc += `The processing is done using the ${serviceId} service. `;
        if (outputCount) desc += `Successfully extracted text from ${outputCount} image${parseInt(outputCount) !== 1 ? "s" : ""}.`;
        return desc.trim();
      } else if (processed.displayName.includes("Translation Processing")) {
        const sourceLang = getTag("nmt.source_language");
        const targetLang = getTag("nmt.target_language");
        let desc = "This step translates the text from one language to another using Neural Machine Translation. ";
        if (sourceLang && targetLang) desc += `It converts text from ${sourceLang} to ${targetLang}.`;
        return desc.trim();
      } else if (processed.displayName.includes("AI Model Inference")) {
        const modelName = getTag("triton.model_name");
        const batchSize = getTag("triton.batch_size");
        let desc = "This is the core AI processing step where the machine learning model analyzes the input data. ";
        if (modelName) desc += `It uses the ${modelName} model. `;
        if (batchSize) desc += `Processing ${batchSize} item${parseInt(batchSize) !== 1 ? "s" : ""} in a batch. `;
        desc += "This typically takes the longest time as it involves complex AI computations.";
        return desc.trim();
      } else if (processed.displayName.includes("Image Processing")) {
        const imageSize = getTag("ocr.image_size_bytes");
        const imageSource = getTag("ocr.image_source");
        let desc = "This step prepares the image for processing. ";
        if (imageSource === "uri") desc += "It downloads the image from the provided URL. ";
        if (imageSize) desc += `The image size is ${(parseInt(imageSize) / 1024).toFixed(1)} KB. `;
        desc += "The image is then validated and prepared for text extraction.";
        return desc.trim();
      } else if (processed.displayName.includes("Request Processing")) {
        return "This step receives and initializes the request. It validates the request format and prepares it for processing through the system.";
      } else if (isStandardSvcInferenceName || isHttpInferenceRoute) {
        const task =
          opLc.includes("nmt") || opLc.startsWith("nmt.")
            ? "NMT translation"
            : opLc.includes("tts") || opLc.startsWith("tts.")
              ? "TTS synthesis"
              : opLc.includes("asr") || opLc.startsWith("asr.")
                ? "ASR transcription"
                : opLc.includes("ocr") || opLc.startsWith("ocr.")
                  ? "OCR"
                  : opLc.includes("ner") || opLc.startsWith("ner.")
                    ? "NER"
                    : opLc.includes("pipeline") || opLc.startsWith("pipeline.")
                      ? "pipeline"
                      : "inference";
        return (
          `One ${task} request. This span wraps the whole call (telemetry phases 1 & 7: start here; duration and status when it ends). ` +
          `Child spans—preprocess → resolve_model → triton_inference → postprocess → persist—run in order under this parent.`
        );
      }
      return "This step processes the request data and performs the necessary computations to generate the response.";

    case "routing":
      return "This step determines which AI model or service should be used to handle the request. It considers factors like accuracy requirements, cost, and availability to select the best option.";

    case "response":
      const outputCount = getTag("ocr.output_count") || getTag("ocr.successful_outputs");
      let desc = "This step formats the results into the final response that will be sent back to the user. ";
      if (outputCount) desc += `It packages ${outputCount} result${parseInt(outputCount) !== 1 ? "s" : ""} into the response.`;
      return desc.trim();

    default:
      return processed.description || "This step performs processing as part of the request workflow.";
  }
};

const getTraceStatus = (trace: Trace): { status: "success" | "error" | "warning"; message: string } => {
  if (!trace.spans) return { status: "success", message: "Completed" };
  
  // Build parent-child relationships to find root spans
  const spanToParent = new Map<string, string>();
  trace.spans.forEach(span => {
    if (span.references && span.references.length > 0) {
      const parentRef = span.references.find(ref => ref.refType === "CHILD_OF");
      if (parentRef) {
        spanToParent.set(span.spanID, parentRef.spanID);
      }
    }
  });

  // Find root spans (spans with no parent) - these are typically the main HTTP request handlers
  const rootSpans = trace.spans.filter(span => !spanToParent.has(span.spanID));

  // Helper function to find HTTP status code in span tags (check all possible variations)
  const findHttpStatus = (tags: Array<{ key: string; value: any }>): number | null => {
    if (!tags || tags.length === 0) return null;
    
    // Check all possible variations of HTTP status code tag
    const httpStatusTag = tags.find(t => {
      const key = String(t.key).toLowerCase();
      return key === "http.status_code" || 
             key === "http_status_code" ||
             key === "http.statuscode" ||
             key === "status_code" ||
             key === "statuscode" ||
             (key.includes("http") && key.includes("status"));
    });
    
    if (httpStatusTag) {
      const statusCode = parseInt(String(httpStatusTag.value));
      if (!isNaN(statusCode) && statusCode > 0) {
        return statusCode;
      }
    }
    return null;
  };

  // Priority 1: Check root spans for HTTP status code FIRST (these match what's logged)
  // Root spans represent the actual HTTP request/response that gets logged
  for (const span of rootSpans) {
    const tags = span.tags || [];
    const statusCode = findHttpStatus(tags);
    
    if (statusCode !== null) {
      // HTTP status code found on root span - this matches the log status
      if (statusCode >= 200 && statusCode < 300) {
        return { status: "success", message: "Success" };
      } else if (statusCode >= 400 && statusCode < 500) {
        return { status: "error", message: `Client error (${statusCode})` };
      } else if (statusCode >= 500) {
        return { status: "error", message: `Server error (${statusCode})` };
      }
    }
  }

  // Priority 2: Check API Gateway spans (if present) - these represent the actual HTTP response
  // API Gateway spans are the authoritative source for HTTP status codes
  const apiGatewaySpans = trace.spans.filter(span => {
    const process = trace.processes?.[span.processID];
    const serviceName = process?.serviceName || "";
    return serviceName.toLowerCase().includes("api-gateway") || 
           serviceName.toLowerCase().includes("gateway");
  });

  for (const span of apiGatewaySpans) {
    const tags = span.tags || [];
    const statusCode = findHttpStatus(tags);
    
    if (statusCode !== null) {
      // HTTP status code from API Gateway - this is authoritative
      if (statusCode >= 200 && statusCode < 300) {
        return { status: "success", message: "Success" };
      } else if (statusCode >= 400 && statusCode < 500) {
        return { status: "error", message: `Client error (${statusCode})` };
      } else if (statusCode >= 500) {
        return { status: "error", message: `Server error (${statusCode})` };
      }
    }
  }

  // Priority 3: Check service-level request handler spans (like "asr.inference", "ocr.inference")
  // These are the main endpoint handlers that set HTTP status codes
  const requestHandlerSpans = trace.spans.filter(span => {
    const opName = span.operationName.toLowerCase();
    return (opName.includes("inference") || opName.includes("login") || opName.includes("auth")) &&
           !opName.includes("triton") && 
           !opName.includes("database") &&
           !opName.includes("middleware");
  });

  for (const span of requestHandlerSpans) {
    const tags = span.tags || [];
    const statusCode = findHttpStatus(tags);
    
    if (statusCode !== null) {
      // HTTP status code found on request handler - use it
      if (statusCode >= 200 && statusCode < 300) {
        return { status: "success", message: "Success" };
      } else if (statusCode >= 400 && statusCode < 500) {
        return { status: "error", message: `Client error (${statusCode})` };
      } else if (statusCode >= 500) {
        return { status: "error", message: `Server error (${statusCode})` };
      }
    }
  }

  // Priority 3.5: Check ALL spans for HTTP status code (fallback for edge cases)
  // This ensures we don't miss HTTP status codes even if they're on unexpected spans
  for (const span of trace.spans) {
    // Skip if we already checked this span in previous priorities
    const isRoot = rootSpans.includes(span);
    const isApiGateway = apiGatewaySpans.includes(span);
    const isRequestHandler = requestHandlerSpans.includes(span);
    
    if (!isRoot && !isApiGateway && !isRequestHandler) {
      const tags = span.tags || [];
      const statusCode = findHttpStatus(tags);
      
      if (statusCode !== null) {
        // HTTP status code found - use it
        if (statusCode >= 200 && statusCode < 300) {
          return { status: "success", message: "Success" };
        } else if (statusCode >= 400 && statusCode < 500) {
          return { status: "error", message: `Client error (${statusCode})` };
        } else if (statusCode >= 500) {
          return { status: "error", message: `Server error (${statusCode})` };
        }
      }
    }
  }

  // Priority 4: Check root spans for errors (if no HTTP status found)
  const rootSpanHasError = rootSpans.some(span => {
    const tags = span.tags || [];
    return tags.some(t => 
      (t.key === "error" && t.value === true) || 
      (t.key === "otel.status_code" && String(t.value) === "ERROR")
    );
  });

  if (rootSpanHasError) {
    return { status: "error", message: "Failed" };
  }

  // Priority 5: Check request handler spans for errors (if no HTTP status found)
  const requestHandlerHasError = requestHandlerSpans.some(span => {
    const tags = span.tags || [];
    return tags.some(t => 
      (t.key === "error" && t.value === true) || 
      (t.key === "otel.status_code" && String(t.value) === "ERROR")
    );
  });

  if (requestHandlerHasError) {
    return { status: "error", message: "Failed" };
  }

  // Default: If we can't determine, assume success
  return { status: "success", message: "Success" };
};

const TracesPage: React.FC = () => {
  const toast = useToastWithDeduplication();
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading, user } = useAuth();
  const [traceIdSearch, setTraceIdSearch] = useState<string>("");
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [expandedTags, setExpandedTags] = useState<Set<string>>(new Set());

  const cardBg = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("gray.200", "gray.700");
  const bgGradient = useColorModeValue("linear(to-br, blue.50, purple.50)", "linear(to-br, gray.900, gray.800)");

  // Redirect to login if not authenticated
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

  // Handle traceId from query parameter (e.g., from logs page)
  useEffect(() => {
    if (router.isReady && router.query.traceId) {
      const traceIdFromQuery = String(router.query.traceId).trim();
      if (traceIdFromQuery) {
        setTraceIdSearch(traceIdFromQuery);
        setSelectedTraceId(traceIdFromQuery);
      }
    }
  }, [router.isReady, router.query.traceId]);

  // Fetch selected trace details (only if authenticated and ADMIN)
  const { data: traceDetails, isLoading: traceDetailsLoading, error: traceError } = useQuery({
    queryKey: ["trace-details", selectedTraceId],
    queryFn: () => getTraceById(selectedTraceId!),
    enabled: !!selectedTraceId && isAuthenticated,
    staleTime: 5 * 60 * 1000,
  });

  const handleSearchByTraceId = async () => {
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

    try {
      setSelectedTraceId(traceIdSearch.trim());
    } catch (error: any) {
      toast({
        title: "Trace Not Found",
        description: error?.message || "Could not find trace with the provided ID.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  };

  // Process trace data
  const processedSpans = useMemo(() => {
    if (!traceDetails) {
      console.log("No trace details available");
      return [];
    }
    
    try {
      console.log("Processing trace:", {
        traceID: traceDetails.traceID,
        spansCount: traceDetails.spans?.length || 0,
        processesCount: traceDetails.processes ? Object.keys(traceDetails.processes).length : 0,
        startTime: traceDetails.startTime,
        duration: traceDetails.duration,
        hasSpans: !!traceDetails.spans,
        hasProcesses: !!traceDetails.processes,
      });
      
      if (!traceDetails.spans || traceDetails.spans.length === 0) {
        console.warn("Trace has no spans!");
        return [];
      }
      
      if (!traceDetails.processes || Object.keys(traceDetails.processes).length === 0) {
        console.warn("Trace has no processes!");
        return [];
      }
      
      if (!traceDetails.startTime) {
        console.warn("Trace has no startTime!");
        // Try to calculate from spans
        const minStartTime = Math.min(...traceDetails.spans.map((s: Span) => s.startTime));
        if (minStartTime) {
          console.log("Using min span startTime as trace startTime:", minStartTime);
          traceDetails.startTime = minStartTime;
        } else {
          return [];
        }
      }
      
      const spans = extractImportantSpans(traceDetails);
      console.log("Extracted", spans.length, "important spans");
      
      // Debug logging
      if (spans.length === 0 && traceDetails.spans && traceDetails.spans.length > 0) {
        console.warn("No spans extracted from trace. Total spans:", traceDetails.spans.length);
        console.log("Sample span operations:", traceDetails.spans.slice(0, 10).map((s: Span) => ({
          op: s.operationName,
          duration: s.duration,
          startTime: s.startTime,
          processID: s.processID,
          service: traceDetails.processes?.[s.processID]?.serviceName || "unknown",
          tags: s.tags?.slice(0, 3).map(t => `${t.key}:${t.value}`) || []
        })));
      }
      return spans;
    } catch (error) {
      console.error("Error processing spans:", error);
      console.error("Trace details:", traceDetails);
      return [];
    }
  }, [traceDetails]);

  const traceStatus = useMemo(() => {
    if (!traceDetails) return { status: "success" as const, message: "Completed" };
    return getTraceStatus(traceDetails);
  }, [traceDetails]);

  // Build span map and parent-child relationships for tag merging
  const spanRelationships = useMemo(() => {
    if (!traceDetails || !traceDetails.spans) {
      return { 
        spanMap: new Map<string, Span>(), 
        spanToParent: new Map<string, string>(),
        childSpans: new Map<string, string[]>()
      };
    }
    
    const spanMap = new Map<string, Span>();
    const spanToParent = new Map<string, string>();
    const childSpans = new Map<string, string[]>(); // parentSpanID -> [childSpanIDs]
    
    traceDetails.spans.forEach((span: Span) => {
      spanMap.set(span.spanID, span);
      
      if (span.references && span.references.length > 0) {
        const parentRef = span.references.find(ref => ref.refType === "CHILD_OF");
        if (parentRef) {
          spanToParent.set(span.spanID, parentRef.spanID);
          // Build child spans map
          if (!childSpans.has(parentRef.spanID)) {
            childSpans.set(parentRef.spanID, []);
          }
          childSpans.get(parentRef.spanID)!.push(span.spanID);
        }
      }
    });
    
    return { spanMap, spanToParent, childSpans };
  }, [traceDetails]);

  // Extract primary error message from the most descriptive failed span
  const primaryErrorMessage = useMemo(() => {
    if (!processedSpans || processedSpans.length === 0) return null;
    
    // Helper function to check if an error message is trivial/not useful
    const isTrivialError = (msg: string | undefined): boolean => {
      if (!msg) return true;
      const msgLower = msg.toLowerCase().trim();
      // Filter out boolean values, single characters, very short messages, or generic status codes
      return msgLower === "true" || 
             msgLower === "false" || 
             msgLower.length <= 3 ||
             msgLower === "error" ||
             /^status:\s*\d+$/.test(msgLower) ||
             /^\d+$/.test(msgLower);
    };
    
    // Collect all error messages with their spans
    const errorSpans = processedSpans
      .filter((p: ProcessedSpan) => p.hasError && p.errorMessage && !isTrivialError(p.errorMessage))
      .map((p: ProcessedSpan) => ({
        span: p,
        errorMessage: p.errorMessage!,
        priority: 0, // Higher priority = better
      }));
    
    // If we have non-trivial errors, prioritize them
    if (errorSpans.length > 0) {
      // Prioritize error messages:
      // 1. Reject operations (most specific)
      // 2. Longer, more descriptive messages
      // 3. Messages from top-level spans
      errorSpans.forEach((item: { span: ProcessedSpan; errorMessage: string; priority: number }) => {
        if (item.span.category === "error" || item.span.displayName.includes("Rejection")) {
          item.priority += 10; // Highest priority for rejections
        }
        if (item.span.isTopLevel) {
          item.priority += 5; // Higher priority for top-level spans
        }
        if (item.errorMessage.length > 20) {
          item.priority += 3; // Prefer longer, more descriptive messages
        }
        if (item.errorMessage.length > 10) {
          item.priority += 1; // Slight boost for medium-length messages
        }
      });
      
      // Sort by priority (descending) and return the best one
      errorSpans.sort((a: { span: ProcessedSpan; errorMessage: string; priority: number }, b: { span: ProcessedSpan; errorMessage: string; priority: number }) => b.priority - a.priority);
      return errorSpans[0]?.errorMessage || null;
    }
    
    // Fallback: if all errors are trivial, try to find any error message
    // But still prefer rejection operations
    const anyError = processedSpans.find((p: ProcessedSpan) => 
      p.hasError && p.errorMessage && (p.category === "error" || p.displayName.includes("Rejection"))
    );
    if (anyError && anyError.errorMessage) {
      return anyError.errorMessage;
    }
    
    // Last resort: return first error message even if trivial
    const firstError = processedSpans.find((p: ProcessedSpan) => p.hasError && p.errorMessage);
    return firstError?.errorMessage || null;
  }, [processedSpans]);

  // Calculate trace startTime and duration from spans if not provided
  const traceStartTime = useMemo(() => {
    if (!traceDetails || !traceDetails.spans || traceDetails.spans.length === 0) {
      return traceDetails?.startTime;
    }
    
    // If startTime is already provided and valid, use it
    if (traceDetails.startTime && traceDetails.startTime > 0) {
      return traceDetails.startTime;
    }
    
    // Otherwise, calculate from spans: find the earliest start
    const spans = traceDetails.spans;
    const startTimes = spans.map((s: Span) => s.startTime).filter((t: number) => t > 0);
    
    if (startTimes.length > 0) {
      const earliestStart = Math.min(...startTimes);
      console.log("Calculated trace startTime from spans:", earliestStart);
      return earliestStart;
    }
    
    return traceDetails.startTime;
  }, [traceDetails]);

  // Calculate trace duration from spans if not provided
  const traceDuration = useMemo(() => {
    if (!traceDetails || !traceDetails.spans || traceDetails.spans.length === 0) {
      return traceDetails?.duration;
    }
    
    // If duration is already provided and valid, use it
    if (traceDetails.duration && traceDetails.duration > 0) {
      return traceDetails.duration;
    }
    
    // Otherwise, calculate from spans: find the earliest start and latest end
    const spans = traceDetails.spans;
    const startTimes = spans.map((s: Span) => s.startTime).filter((t: number) => t > 0);
    const endTimes = spans.map((s: Span) => s.startTime + s.duration).filter((t: number) => t > 0);
    
    if (startTimes.length === 0 || endTimes.length === 0) {
      return traceDetails.duration;
    }
    
    const earliestStart = Math.min(...startTimes);
    const latestEnd = Math.max(...endTimes);
    
    const calculatedDuration = latestEnd - earliestStart;
    
    if (calculatedDuration > 0) {
      console.log("Calculated trace duration from spans:", calculatedDuration, "microseconds (", (calculatedDuration / 1000000).toFixed(2), "s)");
      return calculatedDuration;
    }
    
    return traceDetails.duration;
  }, [traceDetails]);

  const getServiceName = (trace: Trace) => {
    if (trace.processes && Object.keys(trace.processes).length > 0) {
      const firstProcess = Object.values(trace.processes)[0];
      return firstProcess.serviceName || "Unknown";
    }
    return "Unknown";
  };

  const getMainOperation = (trace: Trace) => {
    if (!trace.spans || trace.spans.length === 0) return "Unknown Operation";
    const rootSpan = trace.spans.find(s => !s.references || s.references.length === 0) || trace.spans[0];
    return rootSpan.operationName;
  };

  // Extract client IP address from trace spans
  const getClientIP = (trace: Trace): string | null => {
    if (!trace.spans || trace.spans.length === 0) return null;
    
    // Look for IP in any span (usually in the root HTTP request span)
    for (const span of trace.spans) {
      const tags = span.tags || [];
      // Check for client.ip or http.client_ip attributes
      const ipTag = tags.find(t => 
        t.key === "client.ip" || 
        t.key === "http.client_ip" ||
        t.key.toLowerCase() === "client.ip" ||
        t.key.toLowerCase() === "http.client_ip"
      );
      if (ipTag && ipTag.value && String(ipTag.value) !== "unknown") {
        return String(ipTag.value);
      }
    }
    return null;
  };

  return (
    <>
      <Head>
        <title>Trace Viewer - AI4Inclusion Console</title>
        <meta name="description" content="View and analyze request traces" />
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full" align="stretch" maxW="100%">
          {/* Page Header */}
          <Box textAlign="center" mb={2}>
            <Heading size="lg" color="gray.800" mb={1}>
              Trace Viewer
            </Heading>
            <Text color="gray.600" fontSize="sm">
              View and analyze request execution traces
            </Text>
          </Box>

          {/* Show auth warning if not authenticated */}
          {!authLoading && !isAuthenticated && (
            <Alert status="warning">
              <AlertIcon />
              <AlertDescription>
                Please log in to view traces.{" "}
                <Button
                  size="sm"
                  colorScheme="blue"
                  ml={4}
                  onClick={() => router.push("/auth")}
                >
                  Log In
                </Button>
              </AlertDescription>
            </Alert>
          )}

          {/* Trace ID Search */}
          <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full">
            <CardBody>
              <FormControl>
                <FormLabel fontWeight="medium" color="gray.700" mb={2}>
                  Search by Trace ID
                </FormLabel>
                  <HStack spacing={2}>
                    <Input
                    placeholder="Enter trace ID (e.g., 741229d83d4d22e4de3e9abddaf37e01)..."
                      value={traceIdSearch}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTraceIdSearch(e.target.value)}
                      bg="white"
                      fontFamily="mono"
                      fontSize="sm"
                    size="lg"
                    onKeyPress={(e: React.KeyboardEvent<HTMLInputElement>) => {
                        if (e.key === "Enter") {
                          handleSearchByTraceId();
                        }
                      }}
                    />
                    <Button
                    colorScheme="blue"
                      onClick={handleSearchByTraceId}
                      isDisabled={!traceIdSearch.trim()}
                      leftIcon={<SearchIcon />}
                    size="lg"
                    >
                    Load Trace
                    </Button>
                  </HStack>
                </FormControl>
            </CardBody>
          </Card>

          {/* Trace Details */}
          {traceDetailsLoading ? (
            <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full">
              <CardBody>
                <Flex justify="center" align="center" py={12}>
                  <Spinner size="xl" />
                  <Text ml={4}>Loading trace details...</Text>
                </Flex>
              </CardBody>
            </Card>
          ) : traceError ? (
            <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full">
              <CardBody>
                <Alert status="error">
                  <AlertIcon />
                  <AlertDescription>
                    Failed to load trace. {(traceError as any)?.message || "Trace not found or not accessible."}
                  </AlertDescription>
                </Alert>
              </CardBody>
            </Card>
          ) : traceDetails ? (
            <VStack spacing={4} w="full" align="stretch">
              {/* Trace Summary Header */}
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
                      <Box minH="50px">
                        <Text fontSize="xs" color="gray.600" mb={1}>
                          Started
                        </Text>
                        <Text fontSize="sm" fontWeight="medium" color="gray.700">
                          {formatTimestamp(traceStartTime)}
                        </Text>
                      </Box>
                      <Box minH="50px">
                        <Text fontSize="xs" color="gray.600" mb={1}>
                          Duration
                        </Text>
                        <Text fontSize="sm" fontWeight="medium" color="gray.700">
                          {formatDuration(traceDuration)}
                        </Text>
                      </Box>
                      <Box minH="50px">
                        <Text fontSize="xs" color="gray.600" mb={1}>
                          Steps
                        </Text>
                        <Text fontSize="sm" fontWeight="medium" color="gray.700">
                          {processedSpans.length}
                        </Text>
                      </Box>
                      {getClientIP(traceDetails) && (
                        <Box minH="50px">
                          <Text fontSize="xs" color="gray.600" mb={1}>
                            Client IP
                          </Text>
                          <Text fontSize="sm" fontWeight="medium" color="gray.700" fontFamily="mono">
                            {getClientIP(traceDetails)}
                          </Text>
                        </Box>
                      )}
                      <Box minH="50px" display="flex" flexDirection="column" flex={1} minW="200px">
                        <Text fontSize="xs" color="gray.600" mb={1}>
                          Status
                        </Text>
                        <HStack spacing={2} align="center" flexWrap="wrap">
                          <Badge
                            colorScheme={traceStatus.status === "success" ? "green" : traceStatus.status === "error" ? "red" : "yellow"}
                            fontSize="sm"
                            px={2}
                            py={1}
                            display="inline-flex"
                            alignItems="center"
                            height="fit-content"
                            lineHeight="1.5"
                          >
                            {traceStatus.status === "success" && <Icon as={CheckCircleIcon} mr={1} boxSize={3} />}
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

              {/* Main Content: Two Column Layout */}
              <Grid templateColumns={{ base: "1fr", lg: "1fr 1fr" }} gap={6} w="full">
                {/* Left Column: User Interface (What the user sees) */}
            <GridItem minW="0">
                  <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" h="full">
                    <CardBody>
                      <VStack spacing={4} align="stretch">
                        <Box>
                          <HStack spacing={2} align="center" mb={1}>
                            <Icon as={FiEye} color="blue.500" boxSize={5} />
                            <Heading size="sm" color="gray.700">
                              User Interface
                            </Heading>
                          </HStack>
                          <Text fontSize="xs" color="gray.500" pl={7}>
                            (What the user sees)
                    </Text>
                  </Box>

                        <Divider />

                        {/* Request Summary */}
                        <Box>
                          <HStack mb={2} align="center">
                            <Icon as={FiInfo} color="blue.500" boxSize={4} />
                            <Text fontSize="sm" fontWeight="medium" color="gray.600">
                              Request Summary
                            </Text>
                          </HStack>
                          <Box p={4} bg="blue.50" borderRadius="md" border="1px" borderColor="blue.200" boxShadow="sm">
                            <VStack align="start" spacing={2}>
                              <HStack spacing={2} align="center">
                                <Icon as={FiGlobe} color="blue.600" boxSize={4} />
                                <Text fontSize="sm" fontWeight="semibold" color="blue.800">
                                  {getServiceName(traceDetails)}: {getMainOperation(traceDetails)}
                                </Text>
                              </HStack>
                              <HStack spacing={2} align="center" pl={6}>
                                <Text fontSize="xs" color="blue.600" fontFamily="mono">
                                  ID: {traceDetails.traceID.slice(0, 16)}...
                                </Text>
                              </HStack>
                            </VStack>
                          </Box>
                        </Box>

                        {/* Activity Log */}
                        <Box>
                          <HStack mb={2} align="center">
                            <Icon as={FiClock} color="orange.500" boxSize={4} />
                            <Text fontSize="sm" fontWeight="medium" color="gray.600">
                              Activity Log
                            </Text>
                          </HStack>
                          <VStack spacing={2} align="stretch" maxH="400px" overflowY="auto">
                            {processedSpans && processedSpans.length > 0 ? (
                              processedSpans.map((processed: ProcessedSpan, idx: number) => {
                                const relativeTime = formatRelativeTime(processed.relativeStart);
                                const duration = formatDuration(processed.effectiveDuration ?? processed.span.duration);
                                return (
                                  <Box
                                    key={idx}
                            p={3}
                                    bg={processed.hasError ? "red.50" : "white"}
                                    borderRadius="md"
                                    borderLeft="4px solid"
                                    borderLeftColor={
                                      processed.hasError || processed.category === "error" ? "red.500" :
                                      processed.category === "auth" ? "green.500" :
                                      processed.category === "processing" ? "blue.500" :
                                      processed.category === "routing" ? "purple.500" :
                                      "gray.400"
                                    }
                                    boxShadow="sm"
                                    _hover={{ boxShadow: "md", transform: "translateX(2px)" }}
                            transition="all 0.2s"
                          >
                                    <HStack justify="space-between" mb={2} align="start">
                                      <HStack spacing={2} align="center">
                                        <Icon
                                          as={processed.icon}
                                          color={
                                            processed.hasError || processed.category === "error" ? "red.500" :
                                            processed.category === "auth" ? "green.500" :
                                            processed.category === "processing" ? "blue.500" :
                                            processed.category === "routing" ? "purple.500" :
                                            "gray.500"
                                          }
                                          boxSize={4}
                                        />
                                        <VStack align="start" spacing={0}>
                                          <HStack spacing={2} align="center" flexWrap="wrap">
                                            <Text fontSize="sm" color={processed.hasError ? "red.700" : "gray.700"} fontWeight="semibold">
                                              {processed.displayName}
                                            </Text>
                                            {processed.hasError && (
                                              <>
                                                <Badge colorScheme="red" fontSize="xx-small" px={1.5} py={0.5} borderRadius="full">
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
                                                  >
                                                    {processed.errorMessage}
                                                  </Text>
                                                )}
                                              </>
                                            )}
                                          </HStack>
                                          <Text fontSize="xs" color="gray.500" fontFamily="mono">
                                            +{relativeTime} since start
                                </Text>
                                        </VStack>
                                      </HStack>
                                      <Badge fontSize="xs" colorScheme={processed.hasError ? "red" : "orange"} px={2} py={1} borderRadius="full" textTransform="none">
                                        {duration}
                                  </Badge>
                                </HStack>
                                    <Text fontSize="xs" color={processed.hasError ? "red.700" : "gray.600"} pl={6} fontWeight={processed.hasError ? "medium" : "normal"}>
                                      {processed.hasError && processed.errorMessage
                                        ? `❌ ${processed.errorMessage}`
                                        : getUserFriendlyDescription(processed)}
                                </Text>
                          </Box>
                                );
                              })
                            ) : traceDetails?.spans && traceDetails.spans.length > 0 ? (
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
                                Waiting for activity...
                      </Text>
                      )}
                    </VStack>
                    </Box>
                      </VStack>
                </CardBody>
              </Card>
            </GridItem>

                {/* Right Column: Behind the Scenes (What the orchestrator does) */}
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

                        {/* Step-by-step visualization */}
                        <VStack spacing={3} align="stretch">
                          {processedSpans && processedSpans.length > 0 ? (
                            processedSpans.map((processed: ProcessedSpan, idx: number) => {
                            const duration = formatDuration(processed.effectiveDuration ?? processed.span.duration);
                            
                            // Merge tags from current span and all ancestor spans
                            // Parent tags are useful for input-related info (e.g., nmt.input.* on parent nmt.inference)
                            // But filter out redundant tags to avoid repetition
                            let allTags = [...(processed.span.tags || [])];
                            const childTagKeys = new Set(allTags.map(t => t.key.toLowerCase()));
                            
                            // Tags to exclude from parent spans (redundant HTTP metadata)
                            const redundantHttpTags = new Set([
                              'http.host', 'http.method', 'http.route', 'http.server_name', 
                              'http.target', 'http.url', 'http.user_agent', 'correlation.header'
                            ]);
                            
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
                              if (redundantHttpTags.has(tagKey)) return false;

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

                            return (
                              <Card
                                key={idx}
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
                          })) : traceDetails?.spans && traceDetails.spans.length > 0 ? (
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
              </Grid>
            </VStack>
              ) : (
            <Card bg={cardBg} border="1px" borderColor={borderColor} boxShadow="sm" w="full">
                  <CardBody>
                <Flex direction="column" align="center" justify="center" py={12}>
                      <Text fontSize="lg" color="gray.500" fontWeight="medium" mb={2}>
                    No Trace Loaded
                      </Text>
                      <Text fontSize="sm" color="gray.400" textAlign="center">
                    Enter a trace ID above to view trace details
                      </Text>
                    </Flex>
                  </CardBody>
                </Card>
              )}
        </VStack>
      </ContentLayout>
    </>
  );
};

export default TracesPage;
