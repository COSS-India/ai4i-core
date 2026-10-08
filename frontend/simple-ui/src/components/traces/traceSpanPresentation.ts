import {
  FiCheckCircle,
  FiCpu,
  FiDatabase,
  FiGlobe,
  FiImage,
  FiSettings,
  FiShield,
} from "react-icons/fi";
import { API_V1, INFERENCE_TRACE_PATHS } from "../../services/apiEndpoints";
import {
  Trace,
  Span,
} from "../../services/observabilityService";

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
      const status = Number.parseInt(String(httpStatus.value), 10);
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
    } else if (authResponseStatus && Number.parseInt(authResponseStatus, 10) >= 400) {
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
           INFERENCE_TRACE_PATHS.some((p) => opName.toLowerCase().includes(p)) ||
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
    if (imageSize) descParts.push(`(${(Number.parseInt(imageSize, 10) / 1024).toFixed(1)} KB)`);
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
    if (outputCount) descParts.push(`(${outputCount} output${Number.parseInt(outputCount, 10) !== 1 ? "s" : ""})`);
    if (processingTime) descParts.push(`in ${Number.parseFloat(processingTime).toFixed(2)}s`);
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
    displayName = span.operationName.replace("middleware.", "").replaceAll("_", " ");
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
    if (outputCount) descParts.push(`→ ${outputCount} result${Number.parseInt(outputCount, 10) !== 1 ? "s" : ""}`);
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
    else if (parseErrors && Number.parseInt(parseErrors, 10) > 0) {
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
             (!parseErrors || Number.parseInt(parseErrors, 10) === 0) &&
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
    if (totalImages) descParts.push(`(${totalImages} image${Number.parseInt(totalImages, 10) !== 1 ? "s" : ""})`);
    if (resultsCount) descParts.push(`→ ${resultsCount} result${Number.parseInt(resultsCount, 10) !== 1 ? "s" : ""}`);
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
    if (outputCount) descParts.push(`(${outputCount} output${Number.parseInt(outputCount, 10) !== 1 ? "s" : ""})`);
    if (responseSize) descParts.push(`- ${(Number.parseInt(responseSize, 10) / 1024).toFixed(1)} KB`);
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
      displayName = span.operationName.replaceAll(".", " ").replaceAll("_", " ");
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
          if (isAsrPreprocess && !parentSpan.hasError && chunksCount && Number.parseInt(String(chunksCount.value), 10) === 1) {
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
  // span is its nearest displayed ancestor (walking up the parent span chain).
  // Then: effectiveDuration = span.duration − Σ(displayed direct children durations)
  const computeEffectiveDurations = (spanList: ProcessedSpan[]): void => {
    const displayedIds = new Set(spanList.map(p => p.span.spanID));
    const processedById = new Map<string, ProcessedSpan>(
      spanList.map(p => [p.span.spanID, p])
    );

    // For each displayed span, walk up the parent span chain to find the
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
  if (!microseconds || Number.isNaN(microseconds)) return "N/A";
  if (microseconds < 1000) return `${microseconds}μs`;
  if (microseconds < 1000000) return `${(microseconds / 1000).toFixed(2)}ms`;
  return `${(microseconds / 1000000).toFixed(2)}s`;
};

const formatTimestamp = (microseconds: number | undefined) => {
  if (!microseconds || Number.isNaN(microseconds)) return "N/A";
  try {
    const milliseconds = microseconds / 1000;
    const date = new Date(milliseconds);
    if (Number.isNaN(date.getTime())) return "Invalid Date";
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
  const numValue = typeof value === 'number' ? value : Number.parseFloat(String(value));

  // Special handling for database statements - make them more readable
  if (keyLower === 'db.statement') {
    const sqlStatement = String(value);

    // Truncate very long SQL statements
    if (sqlStatement.length > 500) {
      // Show first 500 chars with proper SQL formatting
      const truncated = sqlStatement.substring(0, 500);
      const formattedSql = truncated
        .replaceAll(/\s+/g, ' ') // Collapse multiple spaces
        .replaceAll(/(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|JOIN|LEFT JOIN|RIGHT JOIN|INNER JOIN|ORDER BY|GROUP BY|VALUES|SET|AND|OR)/gi, '\n$1')
        .trim();
      return `${formattedSql}\n\n... (truncated, ${sqlStatement.length} total chars)`;
    }

    // Format SQL for readability
    return sqlStatement
      .replaceAll(/\s+/g, ' ') // Collapse multiple spaces
      .replaceAll(/(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|JOIN|LEFT JOIN|RIGHT JOIN|INNER JOIN|ORDER BY|GROUP BY|VALUES|SET|AND|OR)/gi, '\n$1')
      .trim();
  }

  // Special handling for status descriptions - format for readability
  if (keyLower === 'otel.status_description') {
    let description = String(value);

    // Clean up the Python class prefix
    description = description.replace(/^<class ['"]([^'"]+)['"]>:\s*/, '$1:\n');

    // Format DETAIL sections on new lines
    description = description.replaceAll(/ {1,100}DETAIL: {1,100}/g, '\n\nDETAIL:\n  ');

    // Format constraint violations nicely
    description = description.replaceAll(/duplicate key value violates unique constraint/gi,
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
    if (!Number.isNaN(numValue)) {
      return `${numValue} ms`;
    }
  }

  // Check for seconds - look for _seconds, .seconds, or keys ending with seconds
  if (keyLower.includes('_seconds') || keyLower.includes('.seconds') ||
      keyLower.endsWith('seconds') || keyLower.includes('audio_length_seconds') ||
      keyLower.includes('length_seconds') || keyLower.includes('duration_seconds') ||
      keyLower.includes('total_duration') || keyLower.includes('processing_time_seconds')) {
    if (!Number.isNaN(numValue)) {
      return `${numValue} s`;
    }
  }

  // Check for bytes - look for _bytes, .bytes, or keys ending with bytes
  if (keyLower.includes('_bytes') || keyLower.includes('.bytes') ||
      keyLower.endsWith('bytes') || keyLower.includes('size_bytes')) {
    if (!Number.isNaN(numValue)) {
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
    const exceptionMatch = errorMessage.match(/([A-Za-z]{1,50}(?:Error|Exception)):/);
    if (exceptionMatch) {
      fields.push({ key: "Exception Type", value: exceptionMatch[1] });
    }

    // Extract constraint name
    const constraintMatch = errorMessage.match(/unique constraint ["']([^"']+)["']/i);
    if (constraintMatch) {
      fields.push({ key: "Constraint Violated", value: constraintMatch[1] });
    }

    // Extract the duplicate key information from DETAIL
    const detailMatch = errorMessage.match(/Details?:\s*([^\n]+)/i);
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
    const operationMatch = errorMessage.match(/Operation:\s{0,10}(\w+)\s{1,10}on\s{1,10}table\s{1,10}["']?(\w+)["']?/i);
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
    const exceptionMatch = errorMessage.match(/([A-Za-z]{1,50}(?:Error|Exception)):/);
    if (exceptionMatch) {
      fields.push({ key: "Exception Type", value: exceptionMatch[1] });
    }

    fields.push({ key: "Root Cause", value: "Attempted to use database session after rollback" });
    fields.push({ key: "Fix Required", value: "Move db.refresh() inside try block or use a new session" });

    // Try to extract the specific error message
    const msgMatch = errorMessage.match(/(?:Error|Exception):\s*([^\n]+)/);
    if (msgMatch) {
      fields.push({ key: "Error Message", value: msgMatch[1].trim() });
    }
  }
  // Parse operational/connection errors
  else if (errorMsgLower.includes("operationalerror") || errorMsgLower.includes("connection")) {
    errorType = "Database Connection Error";
    summary = "Failed to connect to or communicate with the database.";

    // Extract exception class
    const exceptionMatch = errorMessage.match(/([A-Za-z]{1,50}(?:Error|Exception)):/);
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
    const msgMatch = errorMessage.match(/(?:Error|Exception):\s*([^\n]+)/);
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
    const exceptionMatch = errorMessage.match(/([A-Za-z]{1,50}(?:Error|Exception)):/);
    if (exceptionMatch) {
      fields.push({ key: "Exception Type", value: exceptionMatch[1] });
      errorType = exceptionMatch[1];
    }

    // Extract error message
    const msgMatch = errorMessage.match(/(?:Error|Exception):\s*([^\n]+)/);
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
    INFERENCE_TRACE_PATHS.some((p) => opLc.includes(p)) ||
    (opLc.includes("post") && opLc.includes("inference") && opLc.includes(API_V1));

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
        if (imageCount) desc += `It analyzes ${imageCount} image${Number.parseInt(imageCount, 10) !== 1 ? "s" : ""}. `;
        if (serviceId) desc += `The processing is done using the ${serviceId} service. `;
        if (outputCount) desc += `Successfully extracted text from ${outputCount} image${Number.parseInt(outputCount, 10) !== 1 ? "s" : ""}.`;
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
        if (batchSize) desc += `Processing ${batchSize} item${Number.parseInt(batchSize, 10) !== 1 ? "s" : ""} in a batch. `;
        desc += "This typically takes the longest time as it involves complex AI computations.";
        return desc.trim();
      } else if (processed.displayName.includes("Image Processing")) {
        const imageSize = getTag("ocr.image_size_bytes");
        const imageSource = getTag("ocr.image_source");
        let desc = "This step prepares the image for processing. ";
        if (imageSource === "uri") desc += "It downloads the image from the provided URL. ";
        if (imageSize) desc += `The image size is ${(Number.parseInt(imageSize, 10) / 1024).toFixed(1)} KB. `;
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
      if (outputCount) desc += `It packages ${outputCount} result${Number.parseInt(outputCount, 10) !== 1 ? "s" : ""} into the response.`;
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
      const statusCode = Number.parseInt(String(httpStatusTag.value), 10);
      if (!Number.isNaN(statusCode) && statusCode > 0) {
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

export type { ErrorDetails, ProcessedSpan };
export {
  categorizeSpan,
  extractImportantSpans,
  formatDuration,
  formatRelativeTime,
  formatTagValue,
  formatTimestamp,
  getTraceStatus,
  getUserFriendlyDescription,
  parseErrorDetails,
};
