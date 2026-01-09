// Custom Tracing UI - Complete request lifecycle view (Jaeger-like)
// Access via: /tracing/{traceId}
// Shows all spans at once in hierarchical timeline view

import React, { useMemo, useState, useEffect, useRef } from 'react';
import Head from 'next/head';
import { useRouter } from 'next/router';
import {
  Box,
  Button,
  VStack,
  HStack,
  Text,
  useColorModeValue,
  Alert,
  AlertIcon,
  Spinner,
  Code,
  Badge,
  Divider,
  Tooltip,
  Grid,
  GridItem,
  Collapse,
} from '@chakra-ui/react';
import { useQuery } from '@tanstack/react-query';
import { jaegerService } from '../../services/jaegerService';
import { getTraceStatistics } from '../../utils/traceTransformer';
import { JaegerTrace, JaegerSpan, JaegerReference, JaegerProcess } from '../../types/tracing';

interface SpanNode {
  span: JaegerSpan;
  children: SpanNode[];
  level: number;
}

const TraceViewPage: React.FC = () => {
  const router = useRouter();
  const { traceId } = router.query;
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [expandedCategories, setExpandedCategories] = useState<Record<string, boolean>>({});
  const [expandedStepTags, setExpandedStepTags] = useState<Record<string, boolean>>({});
  
  // Interactive step-by-step state (like demo)
  const [currentStepIndex, setCurrentStepIndex] = useState<number>(-1);
  const [visibleLogEntries, setVisibleLogEntries] = useState<number>(0);
  const activityLogRef = useRef<HTMLDivElement>(null);

  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');
  const timelineBg = useColorModeValue('gray.50', 'gray.900');
  const hoverBg = useColorModeValue('gray.50', 'gray.700');
  
  // Demo-aligned colors
  const gradientBg = useColorModeValue('linear-gradient(135deg, #eff6ff 0%, #e0e7ff 100%)', 'gray.900');
  const panelBg = useColorModeValue('white', 'gray.800');
  const panelShadow = useColorModeValue('0 4px 6px rgba(0,0,0,0.1)', '0 4px 6px rgba(0,0,0,0.3)');

  // Fetch single trace
  const { data: traceData, isLoading: traceLoading, error: traceError } = useQuery({
    queryKey: ['jaeger-trace', traceId],
    queryFn: () => jaegerService.getTrace(traceId as string),
    enabled: !!traceId && typeof traceId === 'string',
  });

  // Build hierarchical span tree
  const spanTree = useMemo(() => {
    if (!traceData || !traceData.spans || traceData.spans.length === 0) return null;

    const spans = traceData.spans;
    const spanMap = new Map<string, SpanNode>();
    const rootSpans: SpanNode[] = [];

    // Create nodes for all spans
    spans.forEach((span) => {
      if (span && span.spanID) {
        spanMap.set(span.spanID, {
          span,
          children: [],
          level: 0,
        });
      }
    });

    // Build tree structure
    spans.forEach((span) => {
      if (!span || !span.spanID) return;
      
      const node = spanMap.get(span.spanID);
      if (!node) return;
      
      // Check parentSpanID first, then references
      let parentId = span.parentSpanID;
      if (!parentId && span.references && span.references.length > 0) {
        const childOfRef = span.references.find((r: JaegerReference) => r.refType === 'CHILD_OF');
        if (childOfRef) {
          parentId = childOfRef.spanID;
        }
      }

      if (parentId && spanMap.has(parentId)) {
        const parent = spanMap.get(parentId);
        if (parent) {
          parent.children.push(node);
          node.level = parent.level + 1;
        }
      } else {
        rootSpans.push(node);
      }
    });

    // Sort children by start time
    const sortChildren = (node: SpanNode) => {
      node.children.sort((a, b) => a.span.startTime - b.span.startTime);
      node.children.forEach(sortChildren);
    };
    rootSpans.forEach(sortChildren);

    return rootSpans;
  }, [traceData]);

  // Calculate timeline bounds
  const timelineBounds = useMemo(() => {
    if (!traceData || !traceData.spans || traceData.spans.length === 0) {
      return { min: 0, max: 0, total: 0 };
    }

    const spans = traceData.spans.filter((s) => s && s.startTime !== undefined && s.duration !== undefined);
    if (spans.length === 0) {
      return { min: 0, max: 0, total: 0 };
    }
    
    const startTimes = spans.map((s) => s.startTime);
    const endTimes = spans.map((s) => s.startTime + s.duration);

    const min = Math.min(...startTimes);
    const max = Math.max(...endTimes);
    const total = max - min;

    return { min, max, total };
  }, [traceData]);

  // Helper functions - MUST be defined before hooks that use them
  // Format duration
  const formatDuration = (microseconds: number): string => {
    if (microseconds < 1000) return `${microseconds.toFixed(0)}µs`;
    if (microseconds < 1000000) return `${(microseconds / 1000).toFixed(2)}ms`;
    return `${(microseconds / 1000000).toFixed(2)}s`;
  };

  // Format timestamp
  const formatTimestamp = (microseconds: number): string => {
    const date = new Date(microseconds / 1000);
    return date.toLocaleString();
  };

  // Get friendly step name
  // Detect service type dynamically from service name or tags
  const detectServiceType = (serviceName: string, tags?: Array<{ key: string; value: string }>): { type: string; label: string; action: string } => {
    const serviceLower = serviceName.toLowerCase();
    const serviceId = tags?.find(t => t.key.includes('service_id') || t.key.includes('serviceId'))?.value?.toLowerCase() || '';
    
    // Check service name patterns
    if (serviceLower.includes('nmt') || serviceLower.includes('translation') || serviceId.includes('nmt')) {
      return { type: 'nmt', label: 'Translation Request', action: 'Translate' };
    }
    if (serviceLower.includes('ocr') || serviceId.includes('ocr')) {
      return { type: 'ocr', label: 'OCR Request', action: 'Extract text from' };
    }
    if (serviceLower.includes('asr') || serviceLower.includes('transcribe') || serviceId.includes('asr')) {
      return { type: 'asr', label: 'ASR Request', action: 'Transcribe' };
    }
    if (serviceLower.includes('tts') || serviceLower.includes('synthesize') || serviceId.includes('tts')) {
      return { type: 'tts', label: 'TTS Request', action: 'Synthesize' };
    }
    if (serviceLower.includes('ner') || serviceId.includes('ner')) {
      return { type: 'ner', label: 'NER Request', action: 'Extract entities from' };
    }
    if (serviceLower.includes('transliteration') || serviceId.includes('transliteration')) {
      return { type: 'transliteration', label: 'Transliteration Request', action: 'Transliterate' };
    }
    
    // Default fallback
    return { type: 'generic', label: 'Request', action: 'Process' };
  };

  const getFriendlyStepName = (operationName: string, serviceName: string): string => {
    // Clean up operation names for business users
    let friendly = operationName
      .replace(/^POST\s+/i, '')
      .replace(/^GET\s+/i, '')
      .replace(/^PUT\s+/i, '')
      .replace(/^DELETE\s+/i, '')
      .replace(/\/api\/v\d+\//g, '')
      .replace(/\//g, ' → ')
      .replace(/_/g, ' ')
      .replace(/\b\w/g, l => l.toUpperCase());
    
    // Add emoji based on operation type
    if (friendly.toLowerCase().includes('auth') || friendly.toLowerCase().includes('authorization')) {
      return `🔐 ${friendly}`;
    }
    if (friendly.toLowerCase().includes('validation')) {
      return `✓ ${friendly}`;
    }
    if (friendly.toLowerCase().includes('processing') || friendly.toLowerCase().includes('inference')) {
      return `⚙️ ${friendly}`;
    }
    if (friendly.toLowerCase().includes('response') || friendly.toLowerCase().includes('construction')) {
      return `📤 ${friendly}`;
    }
    if (friendly.toLowerCase().includes('policy') || friendly.toLowerCase().includes('evaluation')) {
      return `📋 ${friendly}`;
    }
    if (friendly.toLowerCase().includes('routing') || friendly.toLowerCase().includes('decision')) {
      return `🧭 ${friendly}`;
    }
    // Dynamic icons based on service type
    if (friendly.toLowerCase().includes('translation') || friendly.toLowerCase().includes('nmt')) {
      return `🌐 ${friendly}`;
    }
    if (friendly.toLowerCase().includes('ocr') || friendly.toLowerCase().includes('text-recognition')) {
      return `📄 ${friendly}`;
    }
    if (friendly.toLowerCase().includes('asr') || friendly.toLowerCase().includes('transcribe') || friendly.toLowerCase().includes('speech')) {
      return `🎤 ${friendly}`;
    }
    if (friendly.toLowerCase().includes('tts') || friendly.toLowerCase().includes('synthesize')) {
      return `🔊 ${friendly}`;
    }
    if (friendly.toLowerCase().includes('ner') || friendly.toLowerCase().includes('entity')) {
      return `🏷️ ${friendly}`;
    }
    
    return `🔷 ${friendly}`;
  };

  // Filter out technical tags - only show business-relevant tags
  const isBusinessRelevantTag = (tagKey: string, tagValue: string): boolean => {
    const key = tagKey.toLowerCase();
    
    // Exclude technical/OpenTelemetry tags
    const technicalPatterns = [
      'sdk.',
      'otel.',
      'telemetry.',
      'instrumentation.',
      'version',
      'api.key.length',
      'api.key.present',
      'action', // Too generic
      'span.kind',
      'internal',
      'component',
      'library',
      'framework',
      'runtime.',
      'process.',
      'host.',
      'container.',
      'k8s.',
      'kubernetes.',
      'deployment.',
      'service.version',
      'service.namespace',
      'peer.',
      'network.',
      'rpc.',
      'messaging.',
      'faas.',
      'db.',
      'exception.',
      'error.type',
      'error.message',
      'sampler.',
      'sampling.',
    ];
    
    // Check if key matches any technical pattern
    if (technicalPatterns.some(pattern => key.includes(pattern))) {
      return false;
    }
    
    // Exclude if value is just a version number or technical identifier
    if (key.includes('version') && /^\d+\.\d+\.\d+/.test(tagValue)) {
      return false;
    }
    
    // Include business-relevant tags
    const businessPatterns = [
      'budget',
      'quota',
      'policy',
      'tenant',
      'organization',
      'user',
      'cost',
      'quality',
      'latency',
      'provider',
      'model',
      'language',
      'source',
      'target',
      'service',
      'purpose',
      'residency',
      'compliance',
      'tier',
      'envelope',
      'route',
      'decision',
      'input',
      'output',
      'token',
      'request',
      'response',
      'http.method',
      'http.url',
      'http.status',
      'http.target',
      'correlation',
      'trace',
      'audit',
      'governance',
      'check',
      'evaluation',
      'adapter',
      'fallback',
      'primary',
      'selected',
    ];
    
    // Include if it matches business patterns
    return businessPatterns.some(pattern => key.includes(pattern));
  };

  // Generate business-friendly description from span tags (fully dynamic)
  const getBusinessFriendlyDescription = (span: JaegerSpan, process: JaegerProcess | undefined): string => {
    if (!span.tags) return '';
    
    const tags = span.tags;
    const operationName = span.operationName.toLowerCase();
    const descriptionParts: string[] = [];
    
    // Use purpose tag if available (most dynamic) - declared once at top
    const purposeTag = tags.find((t: any) => t.key === 'purpose');
    if (purposeTag) {
      descriptionParts.push(purposeTag.value);
    }
    
    // Policy Check description - fully dynamic from tags
    if (operationName.includes('policy') || operationName.includes('check') || operationName.includes('evaluation')) {
      // Find all policy/governance related tags dynamically
      const policyTags = tags.filter((t: any) => 
        t.key.includes('budget') || 
        t.key.includes('quota') || 
        t.key.includes('residency') ||
        t.key.includes('policy') ||
        (t.key.includes('language') && (t.key.includes('source') || t.key.includes('target')))
      );
      
      if (policyTags.length > 0) {
        // Build description from actual tag keys and values
        const checkItems: string[] = [];
        
        policyTags.forEach((tag: any) => {
          const key = tag.key.toLowerCase();
          let displayKey = tag.key.replace(/^[^.]+\./, '').replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase());
          let value = tag.value;
          let status = '';
          
          // Determine status dynamically
          if (key.includes('status') && (value === 'OK' || value === 'ok' || value === 'true')) {
            status = ' (OK)';
          } else if (key.includes('budget') || key.includes('quota')) {
            // Check if value indicates OK status
            if (!value.includes('exceeded') && !value.includes('failed') && !value.includes('error')) {
              status = ' (OK)';
            }
          } else if (key.includes('residency')) {
            status = ' (enforced)';
          }
          
          // Format based on tag type
          if (key.includes('budget') && (key.includes('remaining') || key.includes('balance'))) {
            checkItems.push(`✓ Budget remaining: ${value}${status}`);
          } else if (key.includes('quota')) {
            if (key.includes('used') || key.includes('remaining')) {
              checkItems.push(`✓ Daily quota: ${value}${status}`);
            } else {
              checkItems.push(`✓ ${displayKey}: ${value}${status}`);
            }
          } else if (key.includes('residency')) {
              checkItems.push(`✓ Data residency: ${value} (enforced)`);
          } else if (key.includes('language') && key.includes('source') && tags.find((t: any) => t.key.includes('target_language') || t.key.includes('targetLanguage'))) {
            const targetLangTag = tags.find((t: any) => t.key.includes('target_language') || t.key.includes('targetLanguage'));
            if (targetLangTag) {
              checkItems.push(`✓ Language policy: ${value}→${targetLangTag.value} allowed${status}`);
            }
          } else if (key.includes('language') && key.includes('policy')) {
            checkItems.push(`✓ Language policy: ${value}${status}`);
          } else {
            // Generic policy tag
            checkItems.push(`✓ ${displayKey}: ${value}${status || ''}`);
          }
        });
        
        if (checkItems.length > 0) {
          // Use purpose tag or build from operation name
          const intro = purposeTag ? purposeTag.value : 'Enforcing governance rules from identity context';
          return `${intro}: ${checkItems.join('. ')}.`;
        }
      }
      
      // Fallback if no tags found
      return purposeTag ? purposeTag.value : 'Policy check completed';
    }
    
    // Routing Decision description - fully dynamic
    if (operationName.includes('routing') || operationName.includes('decision') || operationName.includes('select')) {
      // Find all routing-related tags dynamically
      const routingTags = tags.filter((t: any) => 
        t.key.includes('primary') || 
        t.key.includes('provider') || 
        t.key.includes('selected') ||
        t.key.includes('fallback') || 
        t.key.includes('backup') ||
        t.key.includes('quality') || 
        t.key.includes('latency') || 
        t.key.includes('cost') ||
        t.key.includes('target') ||
        t.key.includes('circuit')
      );
      
      if (routingTags.length > 0 || purposeTag) {
        const routingItems: string[] = [];
        
        routingTags.forEach((tag: any) => {
          const key = tag.key.toLowerCase();
          const displayKey = tag.key.replace(/^[^.]+\./, '').replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase());
          let value = tag.value;
          
          if (key.includes('primary') || (key.includes('provider') && !key.includes('fallback'))) {
            routingItems.push(`Primary: ${value}`);
          } else if (key.includes('fallback') || key.includes('backup')) {
            routingItems.push(`Fallback: ${value} (sovereign backup)`);
            // Check if circuit breaker info exists
            const circuitTag = tags.find((t: any) => t.key.includes('circuit') || t.key.includes('breaker'));
            if (circuitTag) {
              routingItems.push(`Circuit breaker: ${circuitTag.value}`);
            }
          } else if (key.includes('quality')) {
            routingItems.push(`Quality target: ${value}+`);
          } else if (key.includes('latency')) {
            routingItems.push(`Latency target: <${value}`);
          } else if (key.includes('cost')) {
            routingItems.push(`Cost estimate: ${value}`);
          } else {
            routingItems.push(`${displayKey}: ${value}`);
          }
        });
        
        if (routingItems.length > 0) {
          const intro = purposeTag ? purposeTag.value : 'Planning execution strategy';
          return `${intro}: ${routingItems.join('. ')}.`;
        }
      }
      
      return purposeTag ? purposeTag.value : 'Routing decision completed';
    }
    
    // Identity & Context description - Fully dynamic extraction from tags
    if (operationName.includes('identity') || operationName.includes('context') || operationName.includes('auth')) {
      // Use purpose tag if available, otherwise use default
      const intro = purposeTag ? purposeTag.value : 'Three-layer context model establishes who, what, and how';
      descriptionParts.push(intro + ':');
      
      // Layer 1: Authentication/Identity tags (from auth)
      const authTags = tags.filter((t: any) => 
        t.key.includes('tenant') || 
        t.key.includes('user') || 
        t.key.includes('budget') ||
        t.key.includes('quota') ||
        (t.key.includes('policy') && !t.key.includes('envelope'))
      );
      
      if (authTags.length > 0) {
        const layer1Items: string[] = [];
        authTags.forEach((tag: any) => {
          const displayKey = tag.key.replace(/^[^.]+\./, '').replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase());
          layer1Items.push(`${displayKey}: ${tag.value}`);
        });
        if (layer1Items.length > 0) {
          descriptionParts.push(`Layer 1: Caller Identity - From Authentication. ${layer1Items.join(', ')}`);
        }
      }
      
      // Layer 2: Contract/Metadata tags (from app onboarding)
      const contractTags = tags.filter((t: any) =>
        t.key.includes('channel') ||
        t.key.includes('use_case') ||
        t.key.includes('useCase') ||
        t.key.includes('sensitivity') ||
        t.key.includes('sla') ||
        t.key.includes('contract') ||
        t.key.includes('policy_envelope') ||
        t.key.includes('policyEnvelope')
      );
      
      if (contractTags.length > 0) {
        const layer2Items: string[] = [];
        contractTags.forEach((tag: any) => {
          const displayKey = tag.key.replace(/^[^.]+\./, '').replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase());
          let value = tag.value;
          if (tag.key.includes('policy_envelope') || tag.key.includes('policyEnvelope')) {
            value = `${value} tier`;
          }
          layer2Items.push(`${displayKey}: ${value}`);
        });
        if (layer2Items.length > 0) {
          descriptionParts.push(`Layer 2: Integration Contract - From App Onboarding. ${layer2Items.join(', ')}`);
        }
      }
      
      // Layer 3: Runtime Inference tags (from request analysis)
      const inferenceTags = tags.filter((t: any) =>
        t.key.includes('language') ||
        t.key.includes('detected') ||
        t.key.includes('confidence') ||
        t.key.includes('length') ||
        (t.key.includes('type') && !t.key.includes('error'))
      );
      
      if (inferenceTags.length > 0) {
        const layer3Items: string[] = [];
        inferenceTags.forEach((tag: any) => {
          const displayKey = tag.key.replace(/^[^.]+\./, '').replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase());
          let value = tag.value;
          if (tag.key.includes('confidence')) {
            value = `${value}% conf.`;
          }
          layer3Items.push(`${displayKey}: ${value}`);
        });
        if (layer3Items.length > 0) {
          descriptionParts.push(`Layer 3: Runtime Inference - From Request Analysis. ${layer3Items.join(', ')}`);
        }
      }
      
      return descriptionParts.join(' ');
    }
    
    // Execute/Processing description - fully dynamic
    if (operationName.includes('execute') || operationName.includes('inference') || operationName.includes('process')) {
      const providerTag = tags.find((t: any) => t.key.includes('provider') || t.key.includes('model') || t.key.includes('service'));
      const adapterTag = tags.find((t: any) => t.key.includes('adapter'));
      const actionTag = tags.find((t: any) => t.key.includes('action') && isBusinessRelevantTag(t.key, t.value));
      
      // Detect service type for dynamic messaging
      const serviceName = process?.serviceName || '';
      const serviceType = detectServiceType(serviceName, tags);
      
      if (purposeTag) {
        descriptionParts.push(purposeTag.value);
      } else if (providerTag) {
        // Dynamic action based on service type
        const actionVerb = serviceType.type === 'ocr' ? 'Sending image to'
          : serviceType.type === 'asr' ? 'Sending audio to'
          : serviceType.type === 'tts' ? 'Sending text to'
          : serviceType.type === 'nmt' ? 'Sending text to'
          : 'Sending request to';
        descriptionParts.push(`${actionVerb} ${providerTag.value} API`);
      } else if (actionTag) {
        descriptionParts.push(actionTag.value);
      } else {
        // Build from available tags
        const processTags = tags.filter((t: any) => 
          t.key.includes('provider') || 
          t.key.includes('model') || 
          t.key.includes('service') ||
          t.key.includes('adapter')
        );
        if (processTags.length > 0) {
          const provider = processTags.find((t: any) => t.key.includes('provider') || t.key.includes('model'));
          if (provider) {
            const actionVerb = serviceType.type === 'ocr' ? 'Sending image to'
              : serviceType.type === 'asr' ? 'Sending audio to'
              : serviceType.type === 'tts' ? 'Sending text to'
              : serviceType.type === 'nmt' ? 'Sending text to'
              : 'Sending request to';
            descriptionParts.push(`${actionVerb} ${provider.value} API`);
          }
        } else {
          descriptionParts.push('Processing request');
        }
      }
      
      if (adapterTag) {
        const adapterDesc = adapterTag.value || 'Adapter normalizes request format and handles provider-specific requirements';
        descriptionParts.push(adapterDesc);
      }
      
      return descriptionParts.join('. ') + '.';
    }
    
    // Monitor & Meter description - fully dynamic
    if (operationName.includes('monitor') || operationName.includes('meter') || operationName.includes('track')) {
      // Find all metric-related tags
      const metricTags = tags.filter((t: any) => 
        t.key.includes('cost') || 
        t.key.includes('latency') || 
        t.key.includes('duration') ||
        t.key.includes('quality') || 
        t.key.includes('score') ||
        t.key.includes('token') ||
        t.key.includes('metric')
      );
      
      if (metricTags.length > 0 || purposeTag) {
        const metricItems: string[] = [];
        
        metricTags.forEach((tag: any) => {
          const key = tag.key.toLowerCase();
          const displayKey = tag.key.replace(/^[^.]+\./, '').replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase());
          let value = tag.value;
          let suffix = '';
          
          if (key.includes('cost')) {
            suffix = ' (deducted from budget)';
          } else if (key.includes('latency') || key.includes('duration')) {
            suffix = ' (within SLA)';
          } else if (key.includes('quality') || key.includes('score')) {
            suffix = ' (meets target)';
          }
          
          metricItems.push(`${displayKey}: ${value}${suffix}`);
        });
        
        if (metricItems.length > 0) {
          const intro = purposeTag ? purposeTag.value : 'Recording metrics';
          return `${intro}: ${metricItems.join('. ')}.`;
        }
      }
      
      return purposeTag ? purposeTag.value : 'Metrics recorded';
    }
    
    // Audit Trail description - fully dynamic
    if (operationName.includes('audit') || operationName.includes('log') || operationName.includes('record')) {
      // Find all audit-related tags
      const auditTags = tags.filter((t: any) => 
        t.key.includes('tenant') || 
        t.key.includes('organization') ||
        t.key.includes('operation') || 
        t.key.includes('action') ||
        t.key.includes('provider') || 
        t.key.includes('model') ||
        t.key.includes('cost') ||
        t.key.includes('compliance') || 
        t.key.includes('tier') ||
        t.key.includes('audit') ||
        t.key.includes('who') ||
        t.key.includes('what') ||
        t.key.includes('which')
      );
      
      if (auditTags.length > 0 || purposeTag) {
        const auditItems: string[] = [];
        
        auditTags.forEach((tag: any) => {
          const key = tag.key.toLowerCase();
          const displayKey = tag.key.replace(/^[^.]+\./, '').replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase());
          let value = tag.value;
          let prefix = '';
          
          if (key.includes('tenant') || key.includes('organization') || key.includes('who')) {
            prefix = 'Who: ';
          } else if (key.includes('operation') || key.includes('action') || key.includes('what')) {
            prefix = 'What: ';
          } else if ((key.includes('provider') || key.includes('model')) && key.includes('which')) {
            prefix = 'Which AI: ';
          } else if (key.includes('compliance') || key.includes('tier')) {
            prefix = 'Compliance flags: ';
          } else if (key.includes('cost')) {
            prefix = 'Cost: ';
          }
          
          auditItems.push(`${prefix}${value}`);
        });
        
        if (auditItems.length > 0) {
          const intro = purposeTag ? purposeTag.value : 'Immutable evidence logged';
          return `${intro}: ${auditItems.join('. ')}.`;
        }
      }
      
      return purposeTag ? purposeTag.value : 'Audit trail created';
    }
    
    // Default: use purpose tag if available (already declared at top)
    if (purposeTag) {
      return purposeTag.value;
    }
    
    // Fallback to basic description
    return '';
  };

  // Extract and organize tags from selected span or all spans (business-relevant only)
  // NOTE: This hook MUST be called before any conditional returns
  const allTags = useMemo(() => {
    if (!traceData || !traceData.spans) return [];
    
    const tagMap = new Map<string, string>();
    
    if (selectedSpanId) {
      // Show tags from selected span only
      const selectedSpan = traceData.spans?.find((s) => s && s.spanID === selectedSpanId);
      if (selectedSpan && selectedSpan.tags) {
        selectedSpan.tags.forEach((tag: { key: string; value: string }) => {
          if (tag && tag.key && tag.value && isBusinessRelevantTag(tag.key, String(tag.value))) {
            tagMap.set(tag.key, tag.value);
          }
        });
        // Also include process tags
        const process = traceData.processes?.[selectedSpan.processID];
        if (process && process.tags) {
          process.tags.forEach((tag: { key: string; value: string }) => {
            if (tag && tag.key && tag.value && isBusinessRelevantTag(tag.key, String(tag.value)) && !tagMap.has(tag.key)) {
              tagMap.set(tag.key, tag.value);
            }
          });
        }
      }
    } else {
      // Show tags from all spans (default view)
      if (traceData.spans && Array.isArray(traceData.spans)) {
        traceData.spans.forEach((span) => {
          if (span && span.tags && Array.isArray(span.tags)) {
            span.tags.forEach((tag: { key: string; value: string }) => {
              if (tag && tag.key && tag.value && isBusinessRelevantTag(tag.key, String(tag.value)) && !tagMap.has(tag.key)) {
                tagMap.set(tag.key, tag.value);
              }
            });
          }
          // Also include process tags
          const process = traceData.processes?.[span.processID];
          if (process && process.tags && Array.isArray(process.tags)) {
            process.tags.forEach((tag: { key: string; value: string }) => {
              if (tag && tag.key && tag.value && isBusinessRelevantTag(tag.key, String(tag.value)) && !tagMap.has(tag.key)) {
                tagMap.set(tag.key, tag.value);
              }
            });
          }
        });
      }
    }
    
    return Array.from(tagMap.entries()).map(([key, value]) => ({ key, value }));
  }, [traceData, selectedSpanId]);

  // Flatten span tree into steps for progressive display
  // NOTE: This hook MUST be called before any conditional returns
  const flatSteps = useMemo(() => {
    if (!spanTree) return [];
    
    const steps: Array<{ node: SpanNode; index: number }> = [];
    let stepIndex = 0;
    
    const walkTree = (nodes: SpanNode[]) => {
      nodes.forEach((node) => {
        if (node && node.span) {
          steps.push({ node, index: stepIndex++ });
        }
        if (node.children && node.children.length > 0) {
          walkTree(node.children);
        }
      });
    };
    
    walkTree(spanTree);
    return steps;
  }, [spanTree]);

  // Extract user request from trace tags
  // NOTE: This hook MUST be called before any conditional returns
  const userRequest = useMemo(() => {
    if (!traceData || !traceData.spans) return null;
    
    const rootSpan = traceData.spans?.find((s) => s && !s.parentSpanID && !s.references?.[0]) || null;
    const rootProcess = rootSpan ? traceData.processes?.[rootSpan.processID] : null;
    
    // Look for input-related tags in root span or first span
    const firstSpan = rootSpan || traceData.spans[0];
    if (!firstSpan) return null;

    // Try to find input text from multiple sources:
    // 1. Check span tags for input text
    // 2. Check span events/logs for input text
    // 3. Check all spans in the trace for input-related data
    
    let requestText = '';
    let sourceLang: any = null;
    let targetLang: any = null;
    
    // Search through all spans to find input text (it might be in a child span)
    for (const span of traceData.spans) {
      if (!span) continue;
      
      const process = traceData.processes?.[span.processID];
      
      // Check span tags for input text - prioritize nmt.input_text
      const inputTag = span.tags?.find((t: any) => 
        t.key === 'nmt.input_text' || // NMT service stores input text here
        t.key === 'ocr.input_text' || // OCR service
        t.key === 'asr.input_text' || // ASR service
        (t.key.includes('input') && !t.key.includes('count') && !t.key.includes('length') && !t.key.includes('_count') && !t.key.includes('input_count')) ||
        (t.key.includes('text') && !t.key.includes('preprocess') && !t.key.includes('total') && !t.key.includes('total_characters')) ||
        t.key.includes('source_text') ||
        t.key.includes('sourceText') ||
        t.key === 'request.input'
      );
      
      // Also check process tags
      const processInputTag = process?.tags?.find((t: any) => 
        t.key === 'nmt.input_text' ||
        t.key === 'ocr.input_text' ||
        t.key === 'asr.input_text'
      );
      
      // Check events/logs for input text - but only look for specific fields
      if (span.logs && span.logs.length > 0) {
        for (const logEntry of span.logs) {
          if (logEntry.fields && Array.isArray(logEntry.fields)) {
            // Only look for specific field keys that contain input text
            // Ignore log messages, event names, etc.
            for (const field of logEntry.fields) {
              if (!field || !field.value) continue;
              
              const fieldKey = String(field.key || '').toLowerCase();
              const fieldValue = String(field.value);
              
              // Only check for specific input text field keys (not generic "text" or "message")
              if (
                fieldKey === 'input_text' ||
                fieldKey === 'nmt.input_text' ||
                fieldKey === 'ocr.input_text' ||
                fieldKey === 'asr.input_text' ||
                fieldKey === 'source_text' ||
                fieldKey === 'source' ||
                (fieldKey === 'input' && fieldValue.length > 10) // Only if it's actually an input field, not a count
              ) {
                // Make sure it's actual text content, not a log message
                if (fieldValue.length > 5 && 
                    !fieldValue.match(/^\d+$/) && // Not just a number
                    !fieldValue.match(/^\[.*\]$/) && // Not a JSON array string
                    !fieldValue.match(/^(Auth|Validation|Processing|Error|Success|Failed)/i) && // Not a log message
                    !fieldValue.match(/^(POST|GET|PUT|DELETE)\s+/i) && // Not an HTTP method
                    fieldValue.trim().length > 0) {
                  requestText = fieldValue.trim();
                  break;
                }
              }
            }
            
            if (requestText) break;
          }
        }
      }
      
      // If we found input text in span tags, use it (prioritize this)
      if (inputTag && inputTag.value) {
        const value = String(inputTag.value);
        // Validate it's actual input text, not a log message
        if (value.length > 0 && 
            value !== 'undefined' && 
            value !== 'null' &&
            !value.match(/^(Auth|Validation|Processing|Error|Success|Failed|POST|GET|PUT|DELETE)/i) && // Not a log message
            value.length > 5) { // Must be meaningful text
          requestText = value;
        }
      }
      
      // If we found input text in process tags, use it
      if (!requestText && processInputTag && processInputTag.value) {
        const value = String(processInputTag.value);
        // Validate it's actual input text, not a log message
        if (value.length > 0 && 
            value !== 'undefined' && 
            value !== 'null' &&
            !value.match(/^(Auth|Validation|Processing|Error|Success|Failed|POST|GET|PUT|DELETE)/i) && // Not a log message
            value.length > 5) { // Must be meaningful text
          requestText = value;
        }
      }
      
      // Get language info from any span
      if (!sourceLang) {
        sourceLang = span.tags?.find((t: any) => 
          t.key.includes('source_language') || 
          t.key.includes('sourceLanguage') ||
          t.key.includes('from_language') ||
          t.key === 'nmt.source_language'
        );
      }
      
      if (!targetLang) {
        targetLang = span.tags?.find((t: any) => 
          t.key.includes('target_language') || 
          t.key.includes('targetLanguage') ||
          t.key.includes('to_language') ||
          t.key === 'nmt.target_language'
        );
      }
      
      // If we found input text, stop searching
      if (requestText) break;
    }
    
    // If still no input text found, try to extract from operation name or use fallback
    if (!requestText || requestText.length === 0) {
      // Check if operation name contains useful info
      const opName = firstSpan.operationName || '';
      if (opName && !opName.includes('POST') && !opName.includes('GET') && !opName.includes('/api/') && !opName.includes('inference')) {
        requestText = opName;
      } else {
        // For traces created before backend change, show a helpful message
        // The backend now stores input text in nmt.input_text tag
        requestText = 'Input text not available in this trace';
      }
    } else {
      // Truncate long inputs for display (but keep more characters for better context)
      if (requestText.length > 200) {
        requestText = requestText.substring(0, 200) + '...';
      }
    }
    
    const serviceId = firstSpan.tags?.find((t: any) => 
      t.key.includes('service_id') || 
      t.key.includes('serviceId') ||
      t.key === 'nmt.service_id'
    );

    // Detect service type
    const serviceType = detectServiceType(rootProcess?.serviceName || '', firstSpan.tags);
    
    // Build language/config info dynamically based on service type
    let languageInfo = '';
    if (serviceType.type === 'nmt' || serviceType.type === 'transliteration') {
      // Translation/Transliteration: show source → target
      if (sourceLang && targetLang) {
        languageInfo = `${serviceType.type === 'nmt' ? 'Translate' : 'Transliterate'} from ${sourceLang.value} to ${targetLang.value}`;
      } else if (sourceLang) {
        languageInfo = `Source: ${sourceLang.value}`;
      } else if (targetLang) {
        languageInfo = `Target: ${targetLang.value}`;
      }
    } else if (serviceType.type === 'ocr') {
      // OCR: show source language if available
      if (sourceLang) {
        languageInfo = `Language: ${sourceLang.value}`;
      }
    } else if (serviceType.type === 'asr') {
      // ASR: show language if available
      if (sourceLang) {
        languageInfo = `Language: ${sourceLang.value}`;
      }
    } else if (serviceType.type === 'tts') {
      // TTS: show target language
      if (targetLang) {
        languageInfo = `Language: ${targetLang.value}`;
      }
    }

    return {
      text: requestText,
      languageInfo,
      serviceId: serviceId?.value || rootProcess?.serviceName || 'Unknown Service',
      operation: firstSpan.operationName || 'Request',
      serviceType: serviceType.type,
      serviceLabel: serviceType.label,
      serviceAction: serviceType.action,
    };
  }, [traceData]);

  // Generate activity log from actual trace data (logs, events, tags)
  // NOTE: This hook MUST be called before any conditional returns
  const activityLog = useMemo(() => {
    if (!traceData || !flatSteps || flatSteps.length === 0) return [];
    
    const logs: Array<{ time: string; duration: string; message: string; timestamp: number }> = [];
    const traceStartTime = timelineBounds.min;
    
    flatSteps.forEach((stepData) => {
      const { node } = stepData;
      if (!node || !node.span) return;
      
      const process = traceData.processes?.[node.span.processID];
      const serviceName = process?.serviceName || 'System';
      const span = node.span;
      
      // Calculate actual timestamp and duration
      // Jaeger timestamps are in microseconds, so we need to handle precision carefully
      const spanStartTime = span.startTime;
      const spanDuration = span.duration || 0;
      
      // Convert microseconds to milliseconds for Date object
      const millisecondsSinceEpoch = Math.floor(spanStartTime / 1000);
      const actualTime = new Date(millisecondsSinceEpoch);
      const relativeTime = ((spanStartTime - traceStartTime) / 1000).toFixed(3); // Time since trace start in seconds
      
      // Format time with milliseconds
      const hours = actualTime.getHours().toString().padStart(2, '0');
      const minutes = actualTime.getMinutes().toString().padStart(2, '0');
      const seconds = actualTime.getSeconds().toString().padStart(2, '0');
      const milliseconds = actualTime.getMilliseconds().toString().padStart(3, '0');
      
      // Extract microseconds (last 3 digits of the microsecond timestamp)
      // This gives us precision beyond JavaScript Date's millisecond limit
      const microseconds = (spanStartTime % 1000).toString().padStart(3, '0');
      const formattedTime = `${hours}:${minutes}:${seconds}.${milliseconds}.${microseconds}`;
      
      const durationStr = formatDuration(spanDuration);
      
      // First, try to use actual span logs/events if available
      if (span.logs && span.logs.length > 0) {
        span.logs.forEach((logEntry: any) => {
          const logTimestamp = logEntry.timestamp || spanStartTime;
          
          // Convert microseconds to milliseconds for Date object
          const logMillisecondsSinceEpoch = Math.floor(logTimestamp / 1000);
          const logDate = new Date(logMillisecondsSinceEpoch);
          
          // Format time with milliseconds
          const logHours = logDate.getHours().toString().padStart(2, '0');
          const logMinutes = logDate.getMinutes().toString().padStart(2, '0');
          const logSeconds = logDate.getSeconds().toString().padStart(2, '0');
          const logMilliseconds = logDate.getMilliseconds().toString().padStart(3, '0');
          
          // Extract microseconds (last 3 digits of the microsecond timestamp)
          const logMicroseconds = (logTimestamp % 1000).toString().padStart(3, '0');
          const logFormattedTime = `${logHours}:${logMinutes}:${logSeconds}.${logMilliseconds}.${logMicroseconds}`;
          
          const logRelativeTime = ((logTimestamp - traceStartTime) / 1000).toFixed(3);
          
          // Extract message from log fields
          let logMessage = '';
          if (logEntry.fields && Array.isArray(logEntry.fields)) {
            const messageField = logEntry.fields.find((f: any) => f.key === 'message' || f.key === 'event');
            const eventField = logEntry.fields.find((f: any) => f.key === 'event');
            
            if (messageField) {
              logMessage = messageField.value;
            } else if (eventField) {
              logMessage = eventField.value;
            } else {
              // Build message from all fields
              const fieldMessages = logEntry.fields
                .filter((f: any) => f.key !== 'level' && f.key !== 'timestamp')
                .map((f: any) => `${f.key}: ${f.value}`)
                .join(', ');
              logMessage = fieldMessages || 'Event occurred';
            }
          }
          
          if (logMessage) {
            logs.push({
              time: `${logFormattedTime} (+${logRelativeTime}s)`,
              duration: durationStr,
              message: logMessage,
              timestamp: logTimestamp,
            });
          }
        });
      }
      
      // If no logs, use tags to build dynamic message
      if (logs.length === 0 || !span.logs || span.logs.length === 0) {
        let message = '';
        
        // Build message from relevant tags
        const httpMethod = span.tags?.find((t: any) => t.key === 'http.method')?.value;
        const httpUrl = span.tags?.find((t: any) => t.key === 'http.url' || t.key === 'http.target')?.value;
        const httpStatus = span.tags?.find((t: any) => t.key === 'http.status_code')?.value;
        const errorTag = span.tags?.find((t: any) => t.key === 'error')?.value;
        const purposeTag = span.tags?.find((t: any) => t.key === 'purpose')?.value;
        const userVisibleTag = span.tags?.find((t: any) => t.key === 'user_visible')?.value;
        const inputCount = span.tags?.find((t: any) => t.key?.includes('input_count') || t.key?.includes('inputCount'))?.value;
        const serviceId = span.tags?.find((t: any) => t.key?.includes('service_id') || t.key?.includes('serviceId'))?.value;
        const sourceLang = span.tags?.find((t: any) => t.key?.includes('source_language') || t.key?.includes('sourceLanguage'))?.value;
        const targetLang = span.tags?.find((t: any) => t.key?.includes('target_language') || t.key?.includes('targetLanguage'))?.value;
        
        // Build dynamic message from actual trace data
        if (purposeTag) {
          message = purposeTag;
        } else if (httpMethod && httpUrl) {
          const urlPath = httpUrl.split('?')[0]; // Remove query params
          message = `${httpMethod} ${urlPath}`;
          if (httpStatus) {
            message += ` → ${httpStatus}`;
          }
        } else if (span.operationName) {
          // Use operation name and enrich with tags
          const opName = span.operationName.replace(/^POST\s+/i, '').replace(/^GET\s+/i, '').replace(/^PUT\s+/i, '').replace(/^DELETE\s+/i, '');
          message = opName;
          
          // Add context from tags
          const contextParts: string[] = [];
          if (inputCount) contextParts.push(`${inputCount} inputs`);
          if (serviceId) contextParts.push(`service: ${serviceId}`);
          if (sourceLang && targetLang) contextParts.push(`${sourceLang} → ${targetLang}`);
          else if (sourceLang) contextParts.push(`from ${sourceLang}`);
          else if (targetLang) contextParts.push(`to ${targetLang}`);
          
          if (contextParts.length > 0) {
            message += ` (${contextParts.join(', ')})`;
          }
        } else {
          message = `${serviceName} processing`;
        }
        
        // Add error info if present
        if (errorTag === 'true') {
          message += ' [ERROR]';
        }
        
        logs.push({
          time: `${formattedTime} (+${relativeTime}s)`,
          duration: durationStr,
          message: message || `${serviceName}: ${span.operationName || 'Operation'}`,
          timestamp: spanStartTime,
        });
      }
    });
    
    // Sort by timestamp
    logs.sort((a, b) => a.timestamp - b.timestamp);
    
    return logs;
  }, [traceData, flatSteps, timelineBounds]);

  // Auto-scroll activity log when visibleLogEntries changes
  useEffect(() => {
    if (activityLogRef.current && visibleLogEntries > 0) {
      // Small delay to ensure DOM has updated
      const timeoutId = setTimeout(() => {
        if (activityLogRef.current) {
          activityLogRef.current.scrollTop = activityLogRef.current.scrollHeight;
        }
      }, 150);
      return () => clearTimeout(timeoutId);
    }
  }, [visibleLogEntries, activityLog.length]);

  // Organize tags into categories dynamically based on key prefixes (business-relevant only)
  // NOTE: This hook MUST be called before any conditional returns
  const organizedTags = useMemo(() => {
    const categories: Record<string, Array<{ key: string; value: string }>> = {
      contract: [],
      policy: [],
      organization: [],
      http: [],
      other: [],
    };

    // Filter to only business-relevant tags
    const businessTags = allTags.filter(tag => isBusinessRelevantTag(tag.key, tag.value));

    businessTags.forEach((tag) => {
      const key = tag.key.toLowerCase();
      // Dynamic categorization based on key patterns
      if (key.startsWith('contract.') || key.includes('contract')) {
        categories.contract.push(tag);
      } else if (key.startsWith('policy.') || key.includes('policy')) {
        categories.policy.push(tag);
      } else if (key.includes('organization') || key.includes('owner') || key.includes('tenant') || key.includes('org')) {
        categories.organization.push(tag);
      } else if (key.startsWith('http.') || key.includes('http')) {
        categories.http.push(tag);
      } else {
        categories.other.push(tag);
      }
    });

    // Only return categories that have tags
    const filteredCategories: Record<string, Array<{ key: string; value: string }>> = {};
    Object.keys(categories).forEach((cat) => {
      if (categories[cat].length > 0) {
        filteredCategories[cat] = categories[cat];
      }
    });

    return filteredCategories;
  }, [allTags]);

  // Determine current status based on step progression
  // NOTE: This hook MUST be called before any conditional returns
  const currentStatus = useMemo(() => {
    if (currentStepIndex === -1) return 'idle';
    if (currentStepIndex >= flatSteps.length - 1) {
      // All steps complete - need to check statistics safely
      if (!traceData) return 'success';
      const stats = getTraceStatistics(traceData);
      if (stats.errorCount > 0) return 'error';
      return 'success';
    }
    return 'processing';
  }, [currentStepIndex, flatSteps.length, traceData]);

  // Get current step for display
  // NOTE: This hook MUST be called before any conditional returns
  const currentStep = useMemo(() => {
    return currentStepIndex >= 0 && currentStepIndex < flatSteps.length 
      ? flatSteps[currentStepIndex] 
      : null;
  }, [currentStepIndex, flatSteps]);

  // Auto-scroll to active step
  // NOTE: This hook MUST be called before any conditional returns
  const stepRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  
  useEffect(() => {
    if (currentStepIndex >= 0 && stepRefs.current.has(currentStepIndex)) {
      const element = stepRefs.current.get(currentStepIndex);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [currentStepIndex]);

  // Get position and width for a span in timeline
  const getSpanTimelineProps = (span: JaegerSpan) => {
    const start = ((span.startTime - timelineBounds.min) / timelineBounds.total) * 100;
    const width = (span.duration / timelineBounds.total) * 100;
    return { start: `${start}%`, width: `${width}%` };
  };

  // Get span color based on status
  const getSpanColor = (span: JaegerSpan): string => {
    const httpStatus = span.tags.find((t) => t.key === 'http.status_code');
    if (httpStatus) {
      const status = parseInt(httpStatus.value);
      if (status >= 500) return 'red.400';
      if (status >= 400) return 'orange.400';
      if (status >= 300) return 'yellow.400';
    }
    const isError = span.tags.some((t) => t.key === 'error' && t.value === 'true');
    if (isError) return 'red.400';
    return 'blue.400';
  };

  // Render span node recursively
  const renderSpanNode = (node: SpanNode, index: number) => {
    if (!traceData || !node || !node.span) return null;
    const process = traceData.processes?.[node.span.processID];
    const serviceName = process?.serviceName || 'unknown';
    const operationName = node.span.operationName;
    const friendlyName = getFriendlyStepName(operationName, serviceName);
    const duration = formatDuration(node.span.duration);
    const timelineProps = getSpanTimelineProps(node.span);
    const spanColor = getSpanColor(node.span);
    const isError = spanColor.includes('red') || spanColor.includes('orange');
    const isSelected = selectedSpanId === node.span.spanID;

    return (
      <Box key={node.span.spanID} mb={3}>
        <HStack
          spacing={3}
          align="center"
          py={3}
          px={4}
          borderRadius="10px"
          bg={isSelected ? 'blue.50' : node.level === 0 ? 'blue.50' : 'white'}
          border={isSelected ? '2px solid' : '2px solid'}
          borderColor={isSelected ? 'blue.400' : node.level === 0 ? 'blue.300' : 'gray.200'}
          borderLeft={node.level === 0 ? '4px solid' : '2px solid'}
          borderLeftColor={isSelected ? 'blue.600' : isError ? 'red.400' : node.level === 0 ? 'blue.500' : 'gray.300'}
          boxShadow={isSelected ? '0 4px 6px rgba(59, 130, 246, 0.2)' : '0 2px 4px rgba(0,0,0,0.05)'}
          _hover={{ 
            bg: isSelected ? 'blue.50' : 'gray.50', 
            transform: 'scale(1.02)',
            boxShadow: '0 4px 8px rgba(0,0,0,0.1)'
          }}
          cursor="pointer"
          transition="all 0.3s"
          onClick={() => setSelectedSpanId(node.span.spanID)}
        >
          {/* Indentation for hierarchy */}
          {node.level > 0 && (
            <Box w={`${(node.level - 1) * 24}px`} display="flex" alignItems="center">
              <Text fontSize="sm" color="gray.400">└─</Text>
            </Box>
          )}
          
          {/* Step name */}
          <Box flex={1} minW="350px">
            <Text fontSize="14px" fontWeight={node.level === 0 ? '700' : '600'} color="gray.800">
              {friendlyName}
            </Text>
            {node.level > 0 && (
              <Text fontSize="12px" color="gray.500" mt={1}>
                {serviceName}
              </Text>
            )}
          </Box>

          {/* Duration */}
          <Box w="120px">
            <Badge 
              colorScheme={isError ? 'red' : duration.includes('ms') && parseFloat(duration) > 100 ? 'orange' : 'gray'} 
              fontSize="12px" 
              px={3}
              py={1.5}
              borderRadius="full"
              fontWeight="600"
            >
              {duration}
            </Badge>
          </Box>

          {/* Timeline bar */}
          <Box flex={1} position="relative" h="24px" bg={timelineBg} borderRadius="sm" overflow="hidden" border="1px solid" borderColor="gray.200">
            <Tooltip label={`This step took ${duration} and started at ${((node.span.startTime - timelineBounds.min) / timelineBounds.total * 100).toFixed(1)}% of the total request time`}>
              <Box
                position="absolute"
                left={timelineProps.start}
                w={timelineProps.width}
                h="100%"
                bg={spanColor}
                borderRadius="sm"
                opacity={0.8}
                _hover={{ opacity: 1, transform: 'scaleY(1.2)' }}
                cursor="pointer"
                transition="all 0.2s"
              />
            </Tooltip>
          </Box>
        </HStack>

        {/* Render children */}
        {node.children.length > 0 && (
          <Box ml={node.level === 0 ? '0' : `${node.level * 24}px`} mt={1}>
            {node.children.map((child, idx) => renderSpanNode(child, idx))}
          </Box>
        )}
      </Box>
    );
  };

  // Show loading state
  if (traceLoading) {
    return (
      <>
        <Head>
          <title>Loading Trace - AI4Inclusion</title>
        </Head>
        <Box
          bgGradient={gradientBg}
          minH="100vh"
          py={5}
          px={4}
        >
          <Box maxW="1600px" mx="auto">
            <VStack spacing={6} align="center" justify="center" minH="60vh">
              <Spinner size="xl" color="blue.500" />
              <Text color="gray.600" fontSize="16px">Loading trace {traceId}...</Text>
            </VStack>
          </Box>
        </Box>
      </>
    );
  }

  // Show error state
  if (traceError) {
    // Extract error details from axios error response
    const errorDetails = (traceError as any)?.response?.data || {};
    const errorMessage = errorDetails.message || (traceError instanceof Error ? traceError.message : 'Unknown error');
    const jaegerUrl = errorDetails.jaegerUrl || 'http://localhost:16686';
    const errorCode = (traceError as any)?.code || errorDetails.details;
    
    return (
      <>
        <Head>
          <title>Trace Error - AI4Inclusion</title>
        </Head>
        <Box
          bgGradient={gradientBg}
          minH="100vh"
          py={5}
          px={4}
        >
          <Box maxW="1600px" mx="auto">
          <VStack spacing={6} align="center" justify="center" minH="60vh">
            <Alert status="error" maxW="700px">
              <AlertIcon />
              <VStack align="start" spacing={3} w="full">
                <Text fontWeight="bold">Error loading trace</Text>
                <Box>
                  <Text fontSize="sm" fontWeight="600">Trace ID:</Text>
                  <Code fontSize="xs" p={1} borderRadius="sm" bg="gray.100">
                    {traceId}
                  </Code>
                </Box>
                <Box>
                  <Text fontSize="xs" fontWeight="600" color="gray.700">Error Message:</Text>
                  <Text fontSize="xs" color="gray.600" fontFamily="mono" mt={1} p={2} bg="gray.50" borderRadius="sm">
                    {errorMessage}
                  </Text>
                </Box>
                {errorCode && (
                  <Box>
                    <Text fontSize="xs" fontWeight="600" color="gray.700">Error Code:</Text>
                    <Text fontSize="xs" color="gray.600" fontFamily="mono">
                      {errorCode}
                    </Text>
                  </Box>
                )}
                <Box>
                  <Text fontSize="xs" fontWeight="600" color="gray.700">Jaeger URL:</Text>
                  <Text fontSize="xs" color="gray.600" fontFamily="mono">
                    {jaegerUrl}
                  </Text>
                </Box>
                <Alert status="info" fontSize="xs" mt={2}>
                  <AlertIcon />
                  <VStack align="start" spacing={1}>
                    <Text fontSize="xs" fontWeight="bold">
                      Troubleshooting steps:
                    </Text>
                    <VStack as="ul" align="start" pl={4} fontSize="xs" spacing={1}>
                      <Box as="li">Make sure Jaeger is running: <Code fontSize="xs">docker-compose up jaeger</Code></Box>
                      <Box as="li">Check if Jaeger UI is accessible: <Code fontSize="xs">{jaegerUrl}</Code></Box>
                      <Box as="li"><strong>Important:</strong> Jaeger uses in-memory storage - traces are lost on restart</Box>
                      <Box as="li">Generate new traces by making requests to your services</Box>
                      <Box as="li">Use the trace selection dropdown on the <Code fontSize="xs">/tracing</Code> page to find valid trace IDs</Box>
                    </VStack>
                  </VStack>
                </Alert>
                <HStack spacing={2} mt={2}>
                  <Button size="sm" onClick={() => router.push('/tracing')}>
                    Go to Tracing
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => window.location.reload()}>
                    Retry
                  </Button>
                  <Button 
                    size="sm" 
                    variant="outline" 
                    onClick={() => window.open(jaegerUrl, '_blank')}
                  >
                    Open Jaeger UI
                  </Button>
                </HStack>
              </VStack>
            </Alert>
          </VStack>
          </Box>
        </Box>
      </>
    );
  }

  // Show error if no data after loading
  if (!traceLoading && !traceData) {
    return (
      <>
        <Head>
          <title>Trace Not Found - AI4Inclusion</title>
        </Head>
        <Box
          bgGradient={gradientBg}
          minH="100vh"
          py={5}
          px={4}
        >
          <Box maxW="1600px" mx="auto">
          <VStack spacing={6} align="center" justify="center" minH="60vh">
            <Alert status="warning" maxW="600px">
              <AlertIcon />
              <VStack align="start" spacing={2}>
                <Text fontWeight="bold">Trace not found</Text>
                <Text fontSize="sm">Could not load trace: {traceId}</Text>
                <Text fontSize="xs" color="gray.500">
                  The trace may have expired or the trace ID is incorrect.
                </Text>
                <Button size="sm" mt={2} onClick={() => router.push('/tracing')}>
                  Go to Tracing
                </Button>
              </VStack>
            </Alert>
          </VStack>
          </Box>
        </Box>
      </>
    );
  }

  // Step control handlers
  const handleStartDemo = () => {
    setCurrentStepIndex(0);
    setVisibleLogEntries(1);
    // Auto-scroll activity log to bottom after state update
    setTimeout(() => {
      if (activityLogRef.current) {
        activityLogRef.current.scrollTop = activityLogRef.current.scrollHeight;
      }
    }, 100);
  };

  const handleNextStep = () => {
    if (currentStepIndex < flatSteps.length - 1) {
      setCurrentStepIndex(currentStepIndex + 1);
      setVisibleLogEntries(Math.min(visibleLogEntries + 1, activityLog.length));
    }
  };

  const handlePreviousStep = () => {
    if (currentStepIndex > 0) {
      setCurrentStepIndex(currentStepIndex - 1);
      setVisibleLogEntries(Math.max(visibleLogEntries - 1, 0));
      // Auto-scroll activity log to bottom after state update
      setTimeout(() => {
        if (activityLogRef.current) {
          activityLogRef.current.scrollTop = activityLogRef.current.scrollHeight;
        }
      }, 100);
    }
  };

  const handleResetDemo = () => {
    setCurrentStepIndex(-1);
    setVisibleLogEntries(0);
  };

  // Ensure traceData exists before rendering
  if (!traceData) {
    return null;
  }

  const statistics = getTraceStatistics(traceData);
  const rootSpan = traceData.spans?.find((s) => s && !s.parentSpanID && !s.references?.[0]) || null;
  const rootProcess = rootSpan ? traceData.processes?.[rootSpan.processID] : null;
  const traceStartTime = formatTimestamp(timelineBounds.min);
  const traceDuration = formatDuration(timelineBounds.total);

  return (
    <>
      <Head>
        <title>Trace {traceId?.toString().substring(0, 16)}... - AI4Inclusion</title>
      </Head>

      <Box
        bgGradient={gradientBg}
        minH="100vh"
        py={5}
        px={4}
      >
        <Box maxW="1600px" mx="auto">
          <VStack spacing={6} align="stretch">
            {/* Header - Demo Style */}
            <Box
              bg={panelBg}
              borderRadius="15px"
              p={8}
              boxShadow={panelShadow}
              textAlign="center"
            >
              <Text fontSize="32px" fontWeight="bold" color="gray.800" mb={2}>
                🎯 AI4I-Orchestrator Live Demo
              </Text>
              <Text fontSize="16px" color="gray.600">
                Interactive step-by-step visualization with manual control
              </Text>
            </Box>

            {/* Controls - Demo Style */}
            <HStack
              justify="center"
              align="center"
              gap={4}
              flexWrap="wrap"
              bg={panelBg}
              borderRadius="15px"
              p={4}
              boxShadow={panelShadow}
            >
              <Button
                colorScheme="green"
                onClick={handleStartDemo}
                isDisabled={currentStepIndex >= 0}
                size="lg"
                px={6}
                borderRadius="10px"
                fontWeight="600"
                boxShadow="0 2px 4px rgba(0,0,0,0.1)"
                _hover={{ transform: 'translateY(-2px)', boxShadow: '0 4px 8px rgba(0,0,0,0.15)' }}
              >
                ▶️ Start Demo
              </Button>
              
              <Box
                bg="white"
                border="2px solid"
                borderColor="blue.400"
                borderRadius="10px"
                px={5}
                py={2}
                fontWeight="600"
                color="gray.800"
                fontSize="14px"
              >
                Step {currentStepIndex >= 0 ? currentStepIndex + 1 : 0} of {flatSteps.length}
              </Box>
              
              <Button
                colorScheme="gray"
                onClick={handlePreviousStep}
                isDisabled={currentStepIndex <= 0}
                size="lg"
                px={6}
                borderRadius="10px"
                fontWeight="600"
                boxShadow="0 2px 4px rgba(0,0,0,0.1)"
                _hover={{ transform: 'translateY(-2px)', boxShadow: '0 4px 8px rgba(0,0,0,0.15)' }}
              >
                ◀️ Previous
              </Button>
              
              <Button
                colorScheme="blue"
                onClick={handleNextStep}
                isDisabled={currentStepIndex >= flatSteps.length - 1}
                size="lg"
                px={6}
                borderRadius="10px"
                fontWeight="600"
                fontSize="16px"
                boxShadow="0 2px 4px rgba(0,0,0,0.1)"
                _hover={{ transform: 'translateY(-2px)', boxShadow: '0 4px 8px rgba(0,0,0,0.15)' }}
              >
                Next Step ▶️
              </Button>
              
              <Button
                colorScheme="red"
                onClick={handleResetDemo}
                size="lg"
                px={6}
                borderRadius="10px"
                fontWeight="600"
                boxShadow="0 2px 4px rgba(0,0,0,0.1)"
                _hover={{ transform: 'translateY(-2px)', boxShadow: '0 4px 8px rgba(0,0,0,0.15)' }}
              >
                🔄 Reset
              </Button>
            </HStack>

            {/* Request Summary - Demo Style */}
            <Box
              bg={panelBg}
              borderRadius="15px"
              p={6}
              boxShadow={panelShadow}
            >
              <VStack align="stretch" spacing={4}>
                <HStack justify="space-between" flexWrap="wrap">
                  <VStack align="start" spacing={2} flex={1}>
                    <Text fontSize="20px" fontWeight="700" color="gray.800">
                      📋 Request Summary
                    </Text>
                    <Box>
                      <Text fontSize="13px" color="gray.600" mb={1} fontWeight="600">
                        What was requested:
                      </Text>
                      <Text fontSize="16px" fontWeight="600" color="blue.700">
                        {rootProcess?.serviceName || 'Unknown Service'}: {rootSpan?.operationName || 'Unknown Operation'}
                      </Text>
                    </Box>
                    <Box>
                      <Text fontSize="12px" color="gray.500" fontFamily="mono">
                        Request ID: {traceId}
                      </Text>
                    </Box>
                  </VStack>
                  <HStack spacing={4} flexWrap="wrap">
                    <VStack align="center" spacing={1} bg="gray.50" p={4} borderRadius="10px" minW="120px" boxShadow="sm">
                      <Text fontSize="12px" color="gray.600" fontWeight="600">⏰ Started</Text>
                      <Text fontSize="14px" fontWeight="bold" color="gray.800">{traceStartTime}</Text>
                    </VStack>
                    <VStack align="center" spacing={1} bg="gray.50" p={4} borderRadius="10px" minW="120px" boxShadow="sm">
                      <Text fontSize="12px" color="gray.600" fontWeight="600">⏱️ Duration</Text>
                      <Text fontSize="18px" fontWeight="bold" color="green.600">{traceDuration}</Text>
                    </VStack>
                    <VStack align="center" spacing={1} bg="gray.50" p={4} borderRadius="10px" minW="120px" boxShadow="sm">
                      <Text fontSize="12px" color="gray.600" fontWeight="600">🔧 Steps</Text>
                      <Text fontSize="18px" fontWeight="bold" color="blue.600">{statistics.totalSpans}</Text>
                    </VStack>
                    <VStack align="center" spacing={1} bg="gray.50" p={4} borderRadius="10px" minW="120px" boxShadow="sm">
                      <Text fontSize="12px" color="gray.600" fontWeight="600">✅ Status</Text>
                      <Text fontSize="18px" fontWeight="bold" color={statistics.errorCount > 0 ? 'red.600' : 'green.600'}>
                        {statistics.errorCount > 0 ? '❌ Errors' : '✓ Success'}
                      </Text>
                    </VStack>
                  </HStack>
                </HStack>
              </VStack>
            </Box>

          {/* Split View: User Interface and System View - Demo Style */}
          <Grid templateColumns={{ base: '1fr', lg: '1fr 1fr' }} gap={6} mb={6}>
            {/* Left Panel: User Interface */}
            <GridItem>
              <Box
                bg={panelBg}
                borderRadius="15px"
                p={6}
                boxShadow={panelShadow}
              >
                {/* Panel Header with Indicator - Demo Style */}
                <HStack spacing={3} mb={5} pb={4} borderBottom="2px solid" borderColor="gray.200">
                  <Box
                    w="12px"
                    h="12px"
                    borderRadius="50%"
                    bg="green.500"
                    animation="pulse 2s infinite"
                    sx={{
                      '@keyframes pulse': {
                        '0%, 100%': { opacity: 1 },
                        '50%': { opacity: 0.5 },
                      },
                    }}
                  />
                  <VStack align="start" spacing={0}>
                    <Text fontSize="20px" fontWeight="700" color="gray.800">
                      User Interface
                    </Text>
                    <Text fontSize="13px" color="gray.600">
                      (What the officer sees)
                    </Text>
                  </VStack>
                </HStack>

                <VStack align="stretch" spacing={4}>
                  {/* Dynamic Request Section */}
                  <Box>
                    <Text fontSize="13px" fontWeight="600" color="gray.700" mb={2}>
                      {userRequest?.serviceLabel || 'Request'}
                    </Text>
                    <Box
                      bg="gray.50"
                      border="2px solid"
                      borderColor="gray.200"
                      borderRadius="8px"
                      p={4}
                      minH="100px"
                      fontSize="14px"
                      color="gray.800"
                    >
                      {userRequest ? (
                        <VStack align="start" spacing={2}>
                          <Text fontWeight="500">
                            {userRequest.serviceAction && userRequest.text
                              ? `${userRequest.serviceAction}: "${userRequest.text}"`
                              : userRequest.text}
                          </Text>
                          {userRequest.languageInfo && (
                            <Text fontSize="12px" color="gray.600">
                              {userRequest.languageInfo}
                            </Text>
                          )}
                        </VStack>
                      ) : (
                        <Text color="gray.400" fontStyle="italic">
                          Request details not available
                        </Text>
                      )}
                    </Box>
                  </Box>

                  {/* Status Box - Updates based on current step */}
                  <Box id="statusBox">
                    {currentStepIndex === -1 ? (
                      <Box
                        bg="gray.50"
                        border="2px solid"
                        borderColor="gray.200"
                        borderRadius="8px"
                        p={4}
                      >
                        <Text fontSize="13px" color="gray.500" fontStyle="italic">
                          Click &quot;Start Demo&quot; to begin...
                        </Text>
                      </Box>
                    ) : currentStatus === 'success' ? (
                      <Box
                        bg="green.50"
                        border="2px solid"
                        borderColor="green.200"
                        borderRadius="8px"
                        p={4}
                      >
                        <HStack spacing={2} mb={2}>
                          <Text fontSize="20px">✅</Text>
                          <Text fontWeight="600" color="green.700">Success!</Text>
                        </HStack>
                        <Text fontSize="13px" color="green.700" mb={2}>
                          {userRequest?.serviceAction 
                            ? `${userRequest.serviceAction.charAt(0).toUpperCase() + userRequest.serviceAction.slice(1)} complete! Your request has been processed successfully.`
                            : 'Request complete! Your request has been processed successfully.'}
                        </Text>
                        <Box
                          bg="white"
                          border="1px solid"
                          borderColor="green.200"
                          borderRadius="6px"
                          p={3}
                          fontFamily="mono"
                          fontSize="13px"
                        >
                          Result: Request completed successfully
                        </Box>
                      </Box>
                    ) : currentStatus === 'error' ? (
                      <Box
                        bg="red.50"
                        border="2px solid"
                        borderColor="red.200"
                        borderRadius="8px"
                        p={4}
                      >
                        <HStack spacing={2} mb={2}>
                          <Text fontSize="20px">❌</Text>
                          <Text fontWeight="600" color="red.700">Error</Text>
                        </HStack>
                        <Text fontSize="13px" color="red.700">
                          {statistics.errorCount} error(s) detected during processing
                        </Text>
                      </Box>
                    ) : (
                      <Box
                        bg="blue.50"
                        borderLeft="4px solid"
                        borderColor="blue.400"
                        borderRadius="8px"
                        p={4}
                      >
                        <HStack spacing={2} mb={2}>
                          <Box
                            as="span"
                            animation="spin 1s linear infinite"
                            sx={{
                              '@keyframes spin': {
                                from: { transform: 'rotate(0deg)' },
                                to: { transform: 'rotate(360deg)' },
                              },
                            }}
                          >
                            ⚡
                          </Box>
                          <Text fontWeight="600" color="blue.700">Processing...</Text>
                        </HStack>
                        <Text fontSize="13px" color="blue.700">
                          {currentStep 
                            ? getFriendlyStepName(currentStep.node.span.operationName, traceData?.processes?.[currentStep.node.span.processID]?.serviceName || 'System')
                            : 'Your request is being handled securely and efficiently'}
                        </Text>
                      </Box>
                    )}
                  </Box>

                  {/* Activity Log Section */}
                  <Box>
                    <Text fontSize="13px" fontWeight="600" color="gray.700" mb={2}>
                      Activity Log
                    </Text>
                    <Box
                      ref={activityLogRef}
                      bg="gray.900"
                      color="green.400"
                      borderRadius="8px"
                      p={4}
                      fontFamily="mono"
                      fontSize="12px"
                      h="180px"
                      overflowY="auto"
                      css={{
                        '&::-webkit-scrollbar': {
                          width: '8px',
                        },
                        '&::-webkit-scrollbar-track': {
                          background: '#1a202c',
                        },
                        '&::-webkit-scrollbar-thumb': {
                          background: '#4a5568',
                          borderRadius: '4px',
                        },
                        '&::-webkit-scrollbar-thumb:hover': {
                          background: '#718096',
                        },
                      }}
                    >
                      {currentStepIndex === -1 ? (
                        <Text color="gray.500">Waiting for activity...</Text>
                      ) : activityLog.length > 0 ? (
                        <VStack align="stretch" spacing={2}>
                          {activityLog.slice(0, visibleLogEntries).map((log, idx) => (
                            <Box key={idx} borderLeft="3px solid" borderColor="green.500" pl={3} py={1}>
                              <HStack spacing={3} align="start" flexWrap="wrap">
                                <VStack align="start" spacing={1} minW="260px">
                                  <VStack align="start" spacing={0}>
                                    <HStack spacing={1}>
                                      <Text color="cyan.400" fontSize="10px" fontFamily="mono" fontWeight="600">
                                        🕐 {log.time.split(' (')[0]}
                                      </Text>
                                    </HStack>
                                    <HStack spacing={1} mt={0.5} bg="blue.900" px={2} py={0.5} borderRadius="3px">
                                      <Text color="cyan.200" fontSize="9px" fontFamily="mono" fontWeight="600">
                                        {log.time.match(/\(([^)]+)\)/)?.[1] || ''}
                                      </Text>
                                      <Text color="cyan.300" fontSize="8px" fontStyle="italic">
                                        since start
                                      </Text>
                                    </HStack>
                                  </VStack>
                                  <HStack spacing={2} align="center" bg="yellow.900" px={2} py={1} borderRadius="4px">
                                    <Text color="yellow.300" fontSize="12px" fontFamily="mono" fontWeight="700">
                                      ⏱️ {log.duration}
                                    </Text>
                                    <Text color="yellow.200" fontSize="9px" fontWeight="600">
                                      STEP DURATION
                                    </Text>
                                  </HStack>
                                </VStack>
                                <Text color="green.400" flex={1} fontSize="12px" lineHeight="1.5">{log.message}</Text>
                              </HStack>
                            </Box>
                          ))}
                        </VStack>
                      ) : (
                        <Text color="gray.500">Waiting for activity...</Text>
                      )}
                    </Box>
                  </Box>
                </VStack>
              </Box>
            </GridItem>

            {/* Right Panel: Behind the Scenes */}
            <GridItem>
              <Box
                bg={panelBg}
                borderRadius="15px"
                p={6}
                boxShadow={panelShadow}
                maxH="800px"
                overflowY="auto"
              >
                {/* Panel Header with Indicator - Demo Style */}
                <HStack spacing={3} mb={5} pb={4} borderBottom="2px solid" borderColor="gray.200">
                  <Box
                    w="12px"
                    h="12px"
                    borderRadius="50%"
                    bg="blue.500"
                    animation="pulse 2s infinite"
                    sx={{
                      '@keyframes pulse': {
                        '0%, 100%': { opacity: 1 },
                        '50%': { opacity: 0.5 },
                      },
                    }}
                  />
                  <VStack align="start" spacing={0}>
                    <Text fontSize="20px" fontWeight="700" color="gray.800">
                      Behind the Scenes
                    </Text>
                    <Text fontSize="13px" color="gray.600">
                      (What the orchestrator does)
                    </Text>
                  </VStack>
                </HStack>

                {/* Steps Container - Demo Style with Progressive Display */}
                <VStack align="stretch" spacing={3}>
                  {flatSteps.length > 0 ? (
                    flatSteps.map((stepData, idx) => {
                      const { node } = stepData;
                      if (!traceData || !node || !node.span) return null;
                      
                      const process = traceData.processes?.[node.span.processID];
                      const serviceName = process?.serviceName || 'unknown';
                      const operationName = node.span.operationName;
                      const friendlyName = getFriendlyStepName(operationName, serviceName);
                      const duration = formatDuration(node.span.duration);
                      const isError = getSpanColor(node.span).includes('red') || getSpanColor(node.span).includes('orange');
                      
                      // Determine step state
                      const isActive = idx === currentStepIndex;
                      const isComplete = idx < currentStepIndex;
                      const isPending = idx > currentStepIndex;
                      
                      // Only show steps up to current step
                      if (currentStepIndex >= 0 && idx > currentStepIndex) {
                        return null;
                      }

                      // Get all business-relevant tags for this step (span + process tags)
                      const stepTags: Array<{ key: string; value: string }> = [];
                      if (node.span.tags && Array.isArray(node.span.tags)) {
                        node.span.tags.forEach((tag: any) => {
                          if (tag && tag.key && tag.value && isBusinessRelevantTag(tag.key, String(tag.value))) {
                            stepTags.push({ key: tag.key, value: String(tag.value) });
                          }
                        });
                      }
                      if (process && process.tags && Array.isArray(process.tags)) {
                        process.tags.forEach((tag: any) => {
                          if (tag && tag.key && tag.value && isBusinessRelevantTag(tag.key, String(tag.value)) && !stepTags.find(t => t.key === tag.key)) {
                            stepTags.push({ key: tag.key, value: String(tag.value) });
                          }
                        });
                      }

                      return (
                        <Box
                          key={node.span.spanID}
                          ref={(el) => {
                            if (el) stepRefs.current.set(idx, el);
                          }}
                          border="2px solid"
                          borderColor={isActive ? "blue.400" : isComplete ? "gray.300" : "gray.200"}
                          borderRadius="10px"
                          p={4}
                          bg={isActive ? "blue.50" : isComplete ? "gray.50" : "white"}
                          opacity={isPending ? 0.4 : isComplete ? 0.7 : 1}
                          transform={isActive ? "scale(1.02)" : "scale(1)"}
                          boxShadow={isActive ? "0 4px 6px rgba(59, 130, 246, 0.2)" : "none"}
                          transition="all 0.3s"
                          _hover={!isPending ? {
                            transform: "scale(1.02)",
                            boxShadow: "0 4px 6px rgba(59, 130, 246, 0.2)",
                          } : {}}
                          mb={4}
                        >
                          <HStack spacing={3} align="start" mb={stepTags.length > 0 ? 3 : 0}>
                            <Box
                              fontSize="24px"
                              flexShrink={0}
                              sx={isActive ? {
                                animation: "bounce 1s ease-in-out infinite",
                                '@keyframes bounce': {
                                  '0%, 100%': { transform: 'translateY(0)' },
                                  '50%': { transform: 'translateY(-10px)' },
                                },
                              } : {}}
                            >
                              {friendlyName.match(/^[^\s]+/)?.[0] || '🔷'}
                            </Box>
                            <VStack align="start" spacing={1} flex={1}>
                              <HStack spacing={2} align="center">
                                <Text fontSize="14px" fontWeight="700" color="gray.800">
                                  {friendlyName.replace(/^[^\s]+\s/, '')}
                                </Text>
                                {isActive && (
                                  <Box
                                    as="span"
                                    fontSize="14px"
                                    animation="spin 1s linear infinite"
                                    sx={{
                                      '@keyframes spin': {
                                        from: { transform: 'rotate(0deg)' },
                                        to: { transform: 'rotate(360deg)' },
                                      },
                                    }}
                                  >
                                    ⚡
                                  </Box>
                                )}
                                {isComplete && (
                                  <Text fontSize="14px" color="green.600">✓</Text>
                                )}
                              </HStack>
                              <Text fontSize="13px" color="gray.600" lineHeight="1.5">
                                {(() => {
                                  // Get business-friendly description
                                  const businessDesc = getBusinessFriendlyDescription(node.span, process);
                                  
                                  if (businessDesc) {
                                    return businessDesc;
                                  }
                                  
                                  // Fallback: Generate description from span tags
                                  const descParts: string[] = [];
                                  if (node.span.tags) {
                                    const statusTag = node.span.tags.find((t: any) => t.key === 'http.status_code');
                                    if (statusTag) {
                                      descParts.push(`HTTP Status: ${statusTag.value}`);
                                    }
                                    const costTag = node.span.tags.find((t: any) => t.key.includes('cost'));
                                    if (costTag) {
                                      descParts.push(`Cost: ${costTag.value}`);
                                    }
                                  }
                                  if (descParts.length === 0) {
                                    return `Completed in ${duration}`;
                                  }
                                  return descParts.join('. ') + `. Duration: ${duration}`;
                                })()}
                              </Text>
                            </VStack>
                          </HStack>

                          {/* Show tags for this step - Collapsible */}
                          {stepTags.length > 0 && (() => {
                            const filteredTags = stepTags.filter((tag) => isBusinessRelevantTag(tag.key, tag.value));
                            const stepId = node.span.spanID;
                            const isTagsExpanded = expandedStepTags[stepId] || false;
                            const previewTags = filteredTags.slice(0, 2);
                            const remainingCount = filteredTags.length - previewTags.length;

                            return (
                              <Box mt={3} pt={3} borderTop="1px solid" borderColor="gray.200">
                                {/* Collapsible Header */}
                                <Box
                                  as="button"
                                  onClick={() => setExpandedStepTags(prev => ({ ...prev, [stepId]: !prev[stepId] }))}
                                  w="100%"
                                  textAlign="left"
                                  mb={isTagsExpanded ? 2 : 0}
                                  _hover={{ opacity: 0.8 }}
                                  transition="all 0.2s"
                                >
                                  <HStack justify="space-between" align="center">
                                    <HStack spacing={2}>
                                      <Text fontSize="12px" fontWeight="600" color="gray.700">
                                        📋 Details ({filteredTags.length} {filteredTags.length === 1 ? 'tag' : 'tags'})
                                      </Text>
                                      {!isTagsExpanded && previewTags.length > 0 && (
                                        <Text fontSize="11px" color="gray.500" fontStyle="italic" noOfLines={1}>
                                          {previewTags.map(t => {
                                            const displayKey = t.key
                                              .replace(/^[^.]+\./, '')
                                              .replace(/_/g, ' ')
                                              .replace(/\b\w/g, (l) => l.toUpperCase());
                                            return `${displayKey}: ${String(t.value).substring(0, 20)}${String(t.value).length > 20 ? '...' : ''}`;
                                          }).join(', ')}
                                          {remainingCount > 0 && ` +${remainingCount} more`}
                                        </Text>
                                      )}
                                    </HStack>
                                    <Text fontSize="11px" color="gray.500">
                                      {isTagsExpanded ? '▼' : '▶'}
                                    </Text>
                                  </HStack>
                                </Box>

                                {/* Collapsible Content */}
                                <Collapse in={isTagsExpanded} animateOpacity>
                                  <VStack align="stretch" spacing={2}>
                                    {filteredTags.map((tag, tagIdx) => {
                                      // Clean up tag key for display
                                      const displayKey = tag.key
                                        .replace(/^[^.]+\./, '') // Remove prefix like "http."
                                        .replace(/_/g, ' ')
                                        .replace(/\b\w/g, (l) => l.toUpperCase());

                                      return (
                                        <HStack key={tagIdx} spacing={2} align="start">
                                          <Text fontSize="11px" fontWeight="600" color="gray.600" minW="120px">
                                            {displayKey}:
                                          </Text>
                                          <Text fontSize="12px" color="gray.800" flex={1}>
                                            {String(tag.value).length > 100 
                                              ? String(tag.value).substring(0, 100) + '...' 
                                              : String(tag.value)}
                                          </Text>
                                        </HStack>
                                      );
                                    })}
                                  </VStack>
                                </Collapse>
                              </Box>
                            );
                          })()}
                        </Box>
                      );
                    })
                  ) : (
                    <Text color="gray.500" textAlign="center" py={8}>
                      No steps found
                    </Text>
                  )}
                </VStack>
              </Box>
            </GridItem>
          </Grid>


          </VStack>
        </Box>
      </Box>
    </>
  );
};

// Helper function to get max depth of tree
function getMaxDepth(node: SpanNode): number {
  if (node.children.length === 0) return node.level;
  return Math.max(...node.children.map(getMaxDepth));
}

export default TraceViewPage;
