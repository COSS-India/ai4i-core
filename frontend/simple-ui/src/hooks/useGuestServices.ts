import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import authService from '../services/authService';
import { useAuth } from './useAuth';

const SERVICE_ID_ALIASES: Record<string, string> = {
  asr: 'asr',
  tts: 'tts',
  nmt: 'nmt',
  llm: 'llm',
  ocr: 'ocr',
  ner: 'ner',
  pipeline: 'pipeline',
  transliteration: 'transliteration',
  'language-detection': 'language-detection',
  language_detection: 'language-detection',
  'speaker-diarization': 'speaker-diarization',
  speaker_diarization: 'speaker-diarization',
  'language-diarization': 'language-diarization',
  language_diarization: 'language-diarization',
  'audio-language-detection': 'audio-language-detection',
  audio_language_detection: 'audio-language-detection',
};

const normalizeServiceId = (value: string): string | null => {
  const normalized = value.trim().toLowerCase().replace(/[\s_/]+/g, '-');
  if (!normalized) return null;
  if (SERVICE_ID_ALIASES[normalized]) {
    return SERVICE_ID_ALIASES[normalized];
  }
  if (normalized.startsWith('service-') && SERVICE_ID_ALIASES[normalized.slice(8)]) {
    return SERVICE_ID_ALIASES[normalized.slice(8)];
  }
  if (SERVICE_ID_ALIASES[normalized.replace(/-service$/, '')]) {
    return SERVICE_ID_ALIASES[normalized.replace(/-service$/, '')];
  }
  return SERVICE_ID_ALIASES[normalized] ?? null;
};

const extractGuestServices = (payload: any): string[] => {
  if (Array.isArray(payload)) {
    return payload
      .map((entry) => {
        if (typeof entry === 'string') return normalizeServiceId(entry);
        if (entry && typeof entry === 'object') {
          const raw =
            entry.id ?? entry.service_id ?? entry.name ?? entry.service ?? entry.code;
          if (typeof raw === 'string') {
            const enabled = entry.enabled;
            if (enabled === false) return null;
            return normalizeServiceId(raw);
          }
        }
        return null;
      })
      .filter((item): item is string => Boolean(item));
  }

  if (payload && typeof payload === 'object') {
    const wrapped =
      payload.services ??
      payload.enabled_services ??
      payload.data ??
      payload.result ??
      payload.items;
    if (wrapped) return extractGuestServices(wrapped);

    return Object.entries(payload)
      .filter(([, value]) => value === true)
      .map(([key]) => normalizeServiceId(key))
      .filter((item): item is string => Boolean(item));
  }

  return [];
};

export const useGuestServices = () => {
  const { isAuthenticated, user } = useAuth();
  const roles = user?.roles;
  // `user` may be null; ensure we always end up with an array type.
  const userRoles: unknown[] = Array.isArray(roles) ? roles : [];
  const isGuest = userRoles.some((role) => String(role).toUpperCase() === 'GUEST');
  const userId = user?.user_id ?? null;

  const query = useQuery({
    queryKey: ['guest-enabled-services', userId],
    queryFn: async () => {
      const response = await authService.getGuestEnabledServices();
      return extractGuestServices(response);
    },
    enabled: isAuthenticated && isGuest,
    staleTime: 60 * 1000,
    gcTime: 5 * 60 * 1000,
    retry: 1,
    refetchOnWindowFocus: true,
  });

  const allowedServiceIds = useMemo(() => {
    if (!isGuest) return null;
    return new Set(query.data ?? []);
  }, [isGuest, query.data]);

  return {
    isGuest,
    isLoading: query.isLoading,
    error: query.error as Error | null,
    allowedServiceIds,
  };
};

