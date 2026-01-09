// Transform Jaeger traces into step-by-step format for visualization

import { JaegerTrace, JaegerSpan, JaegerProcess, TraceStep, ContextLayer } from '../types/tracing';

/**
 * Get icon for operation based on service/operation name
 */
function getOperationIcon(serviceName: string, operationName: string): string {
  const service = serviceName.toLowerCase();
  const operation = operationName.toLowerCase();

  if (service.includes('auth')) return '🔐';
  if (service.includes('config')) return '⚙️';
  if (operation.includes('policy') || operation.includes('check')) return '⚖️';
  if (operation.includes('route') || operation.includes('select')) return '🧭';
  if (operation.includes('execute') || operation.includes('inference')) return '⚡';
  if (operation.includes('monitor') || operation.includes('meter')) return '📊';
  if (operation.includes('audit') || operation.includes('log')) return '📝';
  if (operation.includes('response') || operation.includes('deliver')) return '✅';
  if (operation.includes('request') || operation.includes('receive')) return '📨';
  
  return '🔷';
}

/**
 * Extract context layers from span tags
 */
function extractContextLayers(span: JaegerSpan, process: JaegerProcess): ContextLayer[] {
  const layers: ContextLayer[] = [];

  // Layer 1: Authentication/Identity
  const authTags = span.tags.filter(t => 
    t.key.includes('tenant') || 
    t.key.includes('user') || 
    t.key.includes('budget') ||
    t.key.includes('quota') ||
    t.key.includes('policy')
  );
  
  if (authTags.length > 0) {
    layers.push({
      type: 'auth',
      badge: 'Layer 1: Caller Identity',
      title: 'From Authentication',
      items: authTags.map(t => `${t.key}: ${t.value}`),
      note: 'Deterministic, authoritative — inherited from authentication'
    });
  }

  // Layer 2: Contract/Metadata
  const contractTags = span.tags.filter(t =>
    t.key.includes('channel') ||
    t.key.includes('use_case') ||
    t.key.includes('sensitivity') ||
    t.key.includes('sla') ||
    t.key.includes('contract')
  );

  if (contractTags.length > 0) {
    layers.push({
      type: 'contract',
      badge: 'Layer 2: Integration Contract',
      title: 'From App Onboarding',
      items: contractTags.map(t => `${t.key}: ${t.value}`),
      note: 'Deterministic — defined during app registration'
    });
  }

  // Layer 3: Runtime Inference
  const inferenceTags = span.tags.filter(t =>
    t.key.includes('language') ||
    t.key.includes('detected') ||
    t.key.includes('confidence') ||
    t.key.includes('length') ||
    t.key.includes('type')
  );

  if (inferenceTags.length > 0) {
    layers.push({
      type: 'inference',
      badge: 'Layer 3: Runtime Inference',
      title: 'From Request Analysis',
      items: inferenceTags.map(t => `${t.key}: ${t.value}`),
      note: 'Probabilistic but cannot override Layers 1 & 2 policies'
    });
  }

  return layers;
}

/**
 * Generate user-friendly title from operation name
 */
function generateTitle(operationName: string, serviceName: string): string {
  // Clean up operation names
  let title = operationName
    .replace(/^POST\s+/i, '')
    .replace(/^GET\s+/i, '')
    .replace(/^PUT\s+/i, '')
    .replace(/^DELETE\s+/i, '')
    .replace(/\/api\/v\d+\//g, '')
    .replace(/\//g, ' → ')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, l => l.toUpperCase());

  // Add service context if needed
  if (title.length < 10) {
    title = `${serviceName} - ${title}`;
  }

  return title;
}

/**
 * Generate description from span data
 */
function generateDescription(span: JaegerSpan, process: JaegerProcess): string {
  const parts: string[] = [];

  // Add HTTP status if available
  const httpStatus = span.tags.find(t => t.key === 'http.status_code');
  if (httpStatus) {
    parts.push(`Status: ${httpStatus.value}`);
  }

  // Add duration
  const durationMs = (span.duration / 1000).toFixed(2);
  parts.push(`Duration: ${durationMs}ms`);

  // Add key tags
  const importantTags = span.tags.filter(t =>
    t.key.includes('method') ||
    t.key.includes('route') ||
    t.key.includes('service')
  ).slice(0, 3);

  if (importantTags.length > 0) {
    parts.push(importantTags.map(t => `${t.key}: ${t.value}`).join(', '));
  }

  return parts.join('. ');
}

/**
 * Generate user action message
 */
function generateUserAction(span: JaegerSpan, process: JaegerProcess): string {
  const service = process.serviceName;
  const operation = span.operationName.toLowerCase();

  if (operation.includes('auth') || operation.includes('validate')) {
    return 'Authenticating and capturing request context';
  }
  if (operation.includes('policy') || operation.includes('check')) {
    return 'Verifying permissions and compliance';
  }
  if (operation.includes('route') || operation.includes('select')) {
    return 'Selecting best AI service based on context';
  }
  if (operation.includes('execute') || operation.includes('inference')) {
    return 'Processing your request';
  }
  if (operation.includes('monitor') || operation.includes('meter')) {
    return 'Tracking usage and performance';
  }
  if (operation.includes('audit') || operation.includes('log')) {
    return 'Creating permanent record for accountability';
  }
  if (operation.includes('response') || operation.includes('deliver')) {
    return 'Complete! Your request is ready';
  }

  return `${service} is processing your request`;
}

/**
 * Build span hierarchy and sort by start time
 */
function buildSpanHierarchy(spans: JaegerSpan[]): JaegerSpan[] {
  // Sort by start time
  return [...spans].sort((a, b) => a.startTime - b.startTime);
}

/**
 * Transform Jaeger trace into step-by-step format
 */
export function transformTraceToSteps(trace: JaegerTrace): TraceStep[] {
  const spans = buildSpanHierarchy(trace.spans);
  const steps: TraceStep[] = [];

  spans.forEach((span, index) => {
    const process = trace.processes[span.processID];
    if (!process) return;

    const contextLayers = extractContextLayers(span, process);
    const hasContextLayers = contextLayers.length > 0;

    // Determine status
    const httpStatus = span.tags.find(t => t.key === 'http.status_code');
    const isError = httpStatus && parseInt(httpStatus.value) >= 400;
    const status: 'pending' | 'active' | 'complete' | 'error' = isError ? 'error' : 'complete';

    const step: TraceStep = {
      id: index,
      title: generateTitle(span.operationName, process.serviceName),
      description: generateDescription(span, process),
      userAction: generateUserAction(span, process),
      icon: getOperationIcon(process.serviceName, span.operationName),
      serviceName: process.serviceName,
      operationName: span.operationName,
      duration: span.duration,
      startTime: span.startTime,
      status,
      hasContextLayers,
      contextLayers: hasContextLayers ? contextLayers : undefined,
      span,
    };

    steps.push(step);
  });

  return steps;
}

/**
 * Get trace statistics
 */
export function getTraceStatistics(trace: JaegerTrace) {
  const spans = trace.spans;
  const services = new Set(spans.map(s => trace.processes[s.processID]?.serviceName).filter(Boolean));
  
  const durations = spans.map(s => s.duration);
  const totalDuration = durations.reduce((a, b) => a + b, 0);
  
  const errorSpans = spans.filter(s => {
    const status = s.tags.find(t => t.key === 'http.status_code');
    return status && parseInt(status.value) >= 400;
  });

  const slowestSpan = spans.reduce((max, span) => 
    span.duration > max.duration ? span : max, spans[0]
  );

  const fastestSpan = spans.reduce((min, span) => 
    span.duration < min.duration ? span : min, spans[0]
  );

  return {
    totalSpans: spans.length,
    totalDuration,
    serviceCount: services.size,
    errorCount: errorSpans.length,
    slowestSpan,
    fastestSpan,
  };
}

