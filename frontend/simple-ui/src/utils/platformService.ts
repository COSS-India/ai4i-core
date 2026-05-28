/**
 * Helpers for normalizing platform-core service records in inference adapters.
 */

import type { LanguageRecord, Service } from '../types/platform';

export function resolveServiceId(service: Pick<Service, 'serviceId' | 'service_id'>): string {
  return service.serviceId || service.service_id || '';
}

export function resolveModelId(service: Pick<Service, 'modelId' | 'model_id'>): string {
  return service.modelId || service.model_id || '';
}

export function resolveModelVersion(
  service: Pick<Service, 'modelVersion' | 'model_version'>
): string {
  return service.modelVersion || service.model_version || '';
}

export function resolveEndpoint(service: Pick<Service, 'endpoint' | 'endpoint_url'>): string {
  return service.endpoint || service.endpoint_url || '';
}

export function stripEndpointProtocol(endpoint: string): string {
  return endpoint.replace(/^https?:\/\//, '');
}

function readStringField(record: LanguageRecord, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return undefined;
}

/**
 * Extract language codes from platform service.languages.
 * - `simple`: code or language (TTS, LLM, OCR, …)
 * - `broad`: also sourceLanguage, targetLanguage (ASR, NMT list views)
 */
export function extractLanguageCodes(
  languages?: LanguageRecord[],
  mode: 'simple' | 'broad' = 'simple'
): string[] {
  if (!languages?.length) return [];

  const codes: string[] = [];
  for (const lang of languages) {
    if (typeof lang === 'string') {
      codes.push(lang);
      continue;
    }
    if (!lang || typeof lang !== 'object') continue;

    const simple = readStringField(lang, 'code', 'language');
    if (simple) codes.push(simple);

    if (mode === 'broad') {
      for (const key of ['sourceLanguage', 'source_language', 'targetLanguage', 'target_language']) {
        const value = readStringField(lang, key);
        if (value && !codes.includes(value)) codes.push(value);
      }
    }
  }

  return Array.from(new Set(codes));
}

export interface LanguagePairRecord {
  sourceLanguage: string;
  targetLanguage: string;
  sourceScriptCode?: string;
  targetScriptCode?: string;
}

/** NMT-style source/target pairs from service.languages. */
export function extractLanguagePairs(languages?: LanguageRecord[]): LanguagePairRecord[] {
  if (!languages?.length) return [];

  const pairs: LanguagePairRecord[] = [];
  for (const lang of languages) {
    if (!lang || typeof lang !== 'object') continue;
    const src = readStringField(lang, 'sourceLanguage', 'source_language');
    const tgt = readStringField(lang, 'targetLanguage', 'target_language');
    if (!src || !tgt) continue;
    pairs.push({
      sourceLanguage: src,
      targetLanguage: tgt,
      sourceScriptCode: readStringField(lang, 'sourceScriptCode', 'source_script_code') ?? '',
      targetScriptCode: readStringField(lang, 'targetScriptCode', 'target_script_code') ?? '',
    });
  }
  return pairs;
}

export function findServiceById(services: Service[], serviceId: string): Service | undefined {
  return services.find((s) => resolveServiceId(s) === serviceId);
}

export function findServiceByModelId(services: Service[], modelId: string): Service | undefined {
  return services.find((s) => resolveModelId(s) === modelId);
}
