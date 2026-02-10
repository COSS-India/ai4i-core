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
  useToast,
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
}

const categorizeSpan = (span: Span, serviceName: string, traceStartTime: number): ProcessedSpan => {
  const opName = span.operationName.toLowerCase();
  const tags = span.tags || [];
  
  // Extract relevant tags
  const getTag = (key: string) => {
    const tag = tags.find(t => t.key.toLowerCase() === key.toLowerCase());
    return tag ? String(tag.value) : null;
  };

  // Determine category and importance
  let category = "other";
  let displayName = span.operationName;
  let description = "";
  let icon = FiSettings;
  let isImportant = false;
  let isTopLevel = false; // Flag for top-level operations
  let hasError = false;
  let errorMessage: string | undefined = undefined;

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
    
    // Priority 4: Check for generic error tags
    const errorTag = tags.find(t => t.key === "error" || (t.key.toLowerCase().includes("error") && !t.key.toLowerCase().includes("message") && !t.key.toLowerCase().includes("reason")));
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
    // Priority 3: Check for error tags (but skip boolean true values)
    else if (errorTag) {
      const errorValue = errorTag.value;
      // Skip if it's just a boolean true - not helpful
      if (errorValue !== true && errorValue !== "true" && String(errorValue).toLowerCase() !== "true") {
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
            f.key === "level" && String(f.value).toLowerCase() === "error" ||
            String(f.value).toLowerCase().includes("error") ||
            String(f.value).toLowerCase().includes("failed") ||
            String(f.value).toLowerCase().includes("reject")
          );
        }
        return false;
      });
      if (errorLog) {
        hasError = true;
        const errorField = errorLog.fields.find((f: any) => f.key === "error" || f.key === "message");
        errorMessage = errorField ? String(errorField.value) : "Error occurred during processing";
      }
    }
  };
  
  checkForErrors();

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
  // Skip nested auth decision spans - they're redundant
  else if (opName.includes("auth.decision") || (opName.includes("auth") && opName.includes("check"))) {
    category = "auth";
    isImportant = false; // Don't show nested auth decisions
    icon = FiShield;
    displayName = span.operationName;
    description = "Internal authentication check";
  }
  // Main service operations (OCR, NMT, etc.) - check for POST /api/v1/ocr/inference or ocr.inference
  else if (opName.includes("/api/v1/ocr/inference") || opName.includes("/api/v1/nmt/inference") ||
           opName === "ocr.inference" || opName === "nmt.inference" || 
           (opName.includes("post") && opName.includes("inference") && !serviceName.includes("gateway"))) {
    category = "processing";
    isImportant = true;
    isTopLevel = true;
    icon = FiCpu;
    const serviceId = getTag("ocr.service_id") || getTag("nmt.service_id") || getTag("service_id");
    const imageCount = getTag("ocr.image_count");
    const outputCount = getTag("ocr.output_count") || getTag("nmt.output_count");
    const sourceLang = getTag("ocr.source_language") || getTag("nmt.source_language");
    const targetLang = getTag("nmt.target_language");
    displayName = serviceName.includes("ocr") ? "OCR Processing" : serviceName.includes("nmt") ? "Translation Processing" : "Request Processing";
    let descParts = ["Processes the request"];
    if (serviceId) descParts.push(`using ${serviceId}`);
    if (imageCount) descParts.push(`(${imageCount} image${parseInt(imageCount) !== 1 ? "s" : ""})`);
    if (sourceLang && targetLang) descParts.push(`from ${sourceLang} to ${targetLang}`);
    else if (sourceLang) descParts.push(`(source: ${sourceLang})`);
    if (outputCount) descParts.push(`→ ${outputCount} output${parseInt(outputCount) !== 1 ? "s" : ""}`);
    description = descParts.join(" ");
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
  // Skip nested process_batch, resolve_images (plural), build_response - they're redundant
  else if (opName.includes("process_batch") || opName.includes("resolve_images") || 
           opName.includes("build_response")) {
    category = "processing";
    isImportant = false; // Don't show nested processing steps
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
    displayName = "AI Model Inference";
    let descParts = ["Runs AI model"];
    if (modelName) descParts.push(`(${modelName})`);
    if (batchSize) descParts.push(`on batch of ${batchSize}`);
    if (outputCount) descParts.push(`→ ${outputCount} result${parseInt(outputCount) !== 1 ? "s" : ""}`);
    if (status) descParts.push(`- ${status}`);
    description = descParts.join(" ");
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

  // Debug: Log how many spans are marked as important
  const importantCount = processed.filter(p => p.isImportant).length;
  console.log(`Processed ${processed.length} spans, ${importantCount} marked as important`);

  // Filter out child spans when we have a parent span of the same category
  const filtered: ProcessedSpan[] = [];
  const seenOperations = new Map<string, ProcessedSpan>(); // operationKey -> best span
  
  // First, collect top-level spans
  const topLevelSpans = processed.filter(p => p.isTopLevel && p.isImportant);
  
  // Then, collect other important spans that aren't children of top-level spans
  for (const processedSpan of processed) {
    if (!processedSpan.isImportant) continue;
    
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
    
    return [...sorted, ...additional].sort((a, b) => a.relativeStart - b.relativeStart);
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
    return finalSpans;
  }

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
  
  const hasError = trace.spans.some(span => {
    const tags = span.tags || [];
    return tags.some(t => 
      t.key === "error" || 
      t.key === "otel.status_code" && String(t.value) !== "OK" ||
      String(t.value).toLowerCase().includes("error")
    );
  });

  if (hasError) {
    return { status: "error", message: "Failed" };
  }

  return { status: "success", message: "Success" };
};

const TracesPage: React.FC = () => {
  const toast = useToast();
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading, user } = useAuth();
  const [traceIdSearch, setTraceIdSearch] = useState<string>("");
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [expandedTags, setExpandedTags] = useState<Set<string>>(new Set());

  const cardBg = useColorModeValue("white", "gray.800");
  const borderColor = useColorModeValue("gray.200", "gray.700");
  const bgGradient = useColorModeValue("linear(to-br, blue.50, purple.50)", "linear(to-br, gray.900, gray.800)");

  // Check if user is ADMIN
  const isAdmin = user?.roles?.includes('ADMIN') || false;

  // Redirect to login if not authenticated or not ADMIN
  useEffect(() => {
    if (!authLoading) {
      if (!isAuthenticated) {
        toast({
          title: "Authentication Required",
          description: "Please log in to view traces.",
          status: "warning",
          duration: 3000,
          isClosable: true,
        });
        router.push("/auth");
      } else if (!isAdmin) {
        toast({
          title: "Access Denied",
          description: "Only administrators can access the traces dashboard.",
          status: "error",
          duration: 3000,
          isClosable: true,
        });
        router.push("/");
      }
    }
  }, [isAuthenticated, authLoading, isAdmin, router, toast]);

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
    enabled: !!selectedTraceId && isAuthenticated && isAdmin,
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
      return { spanMap: new Map<string, Span>(), spanToParent: new Map<string, string>() };
    }
    
    const spanMap = new Map<string, Span>();
    const spanToParent = new Map<string, string>();
    
    traceDetails.spans.forEach((span: Span) => {
      spanMap.set(span.spanID, span);
      
      if (span.references && span.references.length > 0) {
        const parentRef = span.references.find(ref => ref.refType === "CHILD_OF");
        if (parentRef) {
          spanToParent.set(span.spanID, parentRef.spanID);
        }
      }
    });
    
    return { spanMap, spanToParent };
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

          {/* Show auth warning if not authenticated or not ADMIN */}
          {!authLoading && (!isAuthenticated || !isAdmin) && (
            <Alert status={!isAuthenticated ? "warning" : "error"}>
              <AlertIcon />
              <AlertDescription>
                {!isAuthenticated 
                  ? "Please log in to view traces."
                  : "Only administrators can access the traces dashboard."
                }{" "}
                {!isAuthenticated && (
                  <Button
                    size="sm"
                    colorScheme="blue"
                    ml={4}
                    onClick={() => router.push("/auth")}
                  >
                    Log In
                  </Button>
                )}
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
                                const duration = formatDuration(processed.span.duration);
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
                                      <Badge fontSize="xs" colorScheme={processed.hasError ? "red" : "orange"} px={2} py={1} borderRadius="full">
                                        {duration}
                                  </Badge>
                                </HStack>
                                    <Text fontSize="xs" color={processed.hasError ? "red.700" : "gray.600"} pl={6} fontWeight={processed.hasError ? "medium" : "normal"}>
                                      {processed.hasError && processed.errorMessage ? `❌ ${processed.errorMessage}` : processed.description}
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
                            const duration = formatDuration(processed.span.duration);
                            
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
                            
                            // Helper function to determine if a parent tag should be included
                            const shouldIncludeParentTag = (tagKey: string, spanCategory: string): boolean => {
                              // Always exclude redundant HTTP metadata from parent spans
                              if (redundantHttpTags.has(tagKey)) return false;
                              
                              // For processing spans, include input/output data from parents
                              if (spanCategory === 'processing') {
                                return tagKey.includes('.input.') || 
                                       tagKey.includes('input_count') || 
                                       tagKey.includes('input_size') ||
                                       tagKey.includes('request.size') ||
                                       tagKey.startsWith('http.request') ||
                                       tagKey.startsWith('nmt.') ||
                                       tagKey.startsWith('ocr.') ||
                                       tagKey.startsWith('tts.') ||
                                       tagKey.startsWith('asr.') ||
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
                            
                            const relevantTags = allTags.filter((t: { key: string; value: any }) => {
                              const key = t.key.toLowerCase();
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
                                // Highest priority: input-related tags (most important for understanding the request)
                                if (key.includes(".input.") || key.includes("input_count") || key.includes("input_size") || 
                                    key.includes("request.size") || key.startsWith("http.request")) return 1;
                                // High priority: client IP (important for request tracking)
                                if (key === "client.ip" || key === "http.client_ip") return 1.5;
                                // High priority: service-specific tags
                                if (key.startsWith("nmt.") || key.startsWith("ocr.") || key.startsWith("tts.") || key.startsWith("asr.")) return 2;
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
                                        >
                                          {formatDuration(processed.span.duration)}
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
