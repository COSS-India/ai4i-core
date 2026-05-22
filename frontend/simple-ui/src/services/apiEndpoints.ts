/**
 * Centralized API path constants (gateway-relative, no origin).
 * Use with axios baseURL or prefix fetch URLs with API_BASE_URL.
 */

export const API_V1 = '/api/v1' as const;

export const apiEndpoints = {
  auth: {
    base: `${API_V1}/auth`,
    oauthGoogleAuthorize: `${API_V1}/auth/oauth2/google/authorize`,
    rolesBase: `${API_V1}/auth/roles`,
    user: (userId: string) => `${API_V1}/auth/users/${userId}`,
    /** Relative to `base` (prefix: `${API_BASE_URL}${auth.base}`). */
    paths: {
      register: '/register',
      login: '/login',
      guestLogin: '/guest/login',
      rolesListGuestServices: '/roles/list/guest/services',
      refresh: '/refresh',
      validate: '/validate',
      me: '/me',
      logout: '/logout',
      changePassword: '/change-password',
      forgotPassword: '/forgot-password',
      resetPassword: '/reset-password',
      setPassword: '/set-password',
      setPasswordStatus: (token: string) =>
        `/set-password/status?token=${encodeURIComponent(token)}`,
      verifyEmail: '/verify-email',
      resendVerification: '/resend-verification',
      resendSetupLink: '/resend-setup-link',
      apiKeys: '/api-keys',
      apiKeysAll: '/api-keys/all',
      apiKeyById: (keyId: number) => `/api-keys/${keyId}`,
      oauth2Providers: '/oauth2/providers',
      oauth2Exchange: '/oauth2/exchange',
      usersInitial: '/users?limit=500&offset=0',
      usersPage: (offset: number, limit: number) =>
        `/users?limit=${limit}&offset=${offset}`,
      userById: (userId: string) => `/users/${userId}`,
      inferencePermissions: '/inference/permissions',
      permissions: '/permissions/',
    },
    /** Relative to `rolesBase`. */
    rolePaths: {
      list: '/list',
      user: (userId: string) => `/user/${userId}`,
      assign: '/assign',
      remove: '/remove',
    },
  },

  tenants: {
    base: `${API_V1}/tenants`,
  },

  alerts: {
    base: `${API_V1}/alerts`,
    /** Relative to `alerts.base`. */
    paths: {
      definitions: '/definitions',
      definition: (id: number) => `/definitions/${id}`,
      definitionEnabled: (id: number) => `/definitions/${id}/enabled`,
      receivers: '/receivers',
      receiver: (id: number) => `/receivers/${id}`,
      routingRules: '/routing-rules',
      routingRule: (id: number) => `/routing-rules/${id}`,
      routingRulesTiming: '/routing-rules/timing',
      history: '/history',
    },
  },

  platform: {
    models: {
      base: `${API_V1}/models`,
      byId: (modelId: string) => `${API_V1}/models/${encodeURIComponent(modelId)}`,
    },
    services: {
      base: `${API_V1}/services`,
      byId: (serviceId: string) => `${API_V1}/services/${serviceId}`,
      /** Public gateway route (no JWT) — see apisix model-management-try-it-service-list-public-route */
      tryItList: `${API_V1}/model-management/services/try-it-service-list`,
    },
    tryIt: {
      execute: `${API_V1}/try-it`,
    },
  },

  telemetry: {
    base: `${API_V1}/telemetry`,
    logsSearch: `${API_V1}/telemetry/logs/search`,
    logsAggregate: `${API_V1}/telemetry/logs/aggregate`,
    logsServices: `${API_V1}/telemetry/logs/services`,
    tracesSearch: `${API_V1}/telemetry/traces/search`,
    traceById: (traceId: string) => `${API_V1}/telemetry/traces/${traceId}`,
    tracesServices: `${API_V1}/telemetry/traces/services`,
    traceServiceOperations: (serviceName: string) =>
      `${API_V1}/telemetry/traces/services/${serviceName}/operations`,
  },

  featureFlags: {
    evaluate: `${API_V1}/feature-flags/evaluate`,
    evaluateBoolean: `${API_V1}/feature-flags/evaluate/boolean`,
    evaluateBulk: `${API_V1}/feature-flags/evaluate/bulk`,
    byName: (name: string) => `${API_V1}/feature-flags/${name}`,
    list: `${API_V1}/feature-flags`,
    sync: `${API_V1}/feature-flags/sync`,
  },

  pipeline: {
    inference: `${API_V1}/pipeline/inference`,
    info: `${API_V1}/pipeline/info`,
    health: `${API_V1}/pipeline/health`,
  },

  asr: {
    inference: `${API_V1}/asr/inference`,
    models: `${API_V1}/asr/models`,
    health: `${API_V1}/asr/health`,
    streamingInfo: `${API_V1}/asr/streaming/info`,
    config: `${API_V1}/asr/config`,
    streaming:
      process.env.NEXT_PUBLIC_ASR_STREAM_URL || 'ws://localhost:8087/socket.io',
  },
  tts: {
    inference: `${API_V1}/tts/inference`,
    voices: `${API_V1}/tts/voices`,
    health: `${API_V1}/tts/health`,
    config: `${API_V1}/tts/config`,
  },
  nmt: {
    inference: `${API_V1}/nmt/inference`,
    models: `${API_V1}/nmt/models`,
    services: `${API_V1}/nmt/services`,
    languages: `${API_V1}/nmt/languages`,
    health: `${API_V1}/nmt/health`,
    config: `${API_V1}/nmt/config`,
  },
  llm: {
    inference: `${API_V1}/llm/inference`,
    models: `${API_V1}/llm/models`,
    health: `${API_V1}/llm/health`,
  },
  ocr: {
    inference: `${API_V1}/ocr/inference`,
    health: `${API_V1}/ocr/health`,
  },
  transliteration: {
    inference: `${API_V1}/transliteration/inference`,
    health: `${API_V1}/transliteration/health`,
  },
  'language-detection': {
    inference: `${API_V1}/language-detection/inference`,
    health: `${API_V1}/language-detection/health`,
  },
  'speaker-diarization': {
    inference: `${API_V1}/speaker-diarization/inference`,
    health: `${API_V1}/speaker-diarization/health`,
  },
  'language-diarization': {
    inference: `${API_V1}/language-diarization/inference`,
    health: `${API_V1}/language-diarization/health`,
  },
  'audio-language-detection': {
    inference: `${API_V1}/audio-lang-detection/inference`,
    health: `${API_V1}/audio-lang-detection/health`,
  },
  ner: {
    inference: `${API_V1}/ner/inference`,
    health: `${API_V1}/ner/health`,
  },
  pii: {
    base: `${API_V1}/pii`,
    redact: `${API_V1}/pii/redact`,
    domains: `${API_V1}/pii/domains`,
    policyByDomain: (domainId: string) =>
      `${API_V1}/pii/policy/${encodeURIComponent(domainId)}`,
    admin: {
      allDomains: `${API_V1}/pii/admin/all-domains`,
      activateDomains: `${API_V1}/pii/admin/activate-domains`,
      domain: `${API_V1}/pii/admin/domain`,
      deploy: `${API_V1}/pii/admin/deploy`,
      generateRegex: `${API_V1}/pii/admin/generate-regex`,
      tenantDomains: `${API_V1}/pii/admin/tenant-domains`,
      tenantDomain: `${API_V1}/pii/admin/tenant-domain`,
      tenantDomainDelete: `${API_V1}/pii/admin/tenant-domain/delete`,
      auditLogs: `${API_V1}/pii/admin/audit-logs`,
    },
  },
  policy: {
    /** Gateway prefix; service mounts routes at /v1 (see policy-service main.py). */
    base: `${API_V1}/policy-service`,
    health: `${API_V1}/policy-service/health`,
    piiTypes: `${API_V1}/policy-service/pii-types`,
    piiTypeById: (id: string) => `${API_V1}/policy-service/pii-types/${id}`,
    policies: `${API_V1}/policy-service/policies`,
    policyById: (id: string) => `${API_V1}/policy-service/policies/${id}`,
    policyStatus: (id: string) => `${API_V1}/policy-service/policies/${id}/status`,
    auditLogs: `${API_V1}/policy-service/audit-logs`,
    auditLogById: (id: string) => `${API_V1}/policy-service/audit-logs/${id}`,
  },
} as const;

/** `/api/v1/{service}` prefix derived from inference routes (substring checks in interceptors). */
const inferenceServicePrefix = (inferencePath: string) =>
  inferencePath.replace(/\/inference$/, '');

/** Substrings matched against lowercase request URLs in axios interceptors */
export const API_URL_PATH_MARKERS = {
  modelManagement: '/model-management',
  asr: inferenceServicePrefix(apiEndpoints.asr.inference),
  nmt: inferenceServicePrefix(apiEndpoints.nmt.inference),
  tts: inferenceServicePrefix(apiEndpoints.tts.inference),
  llm: inferenceServicePrefix(apiEndpoints.llm.inference),
  pipeline: inferenceServicePrefix(apiEndpoints.pipeline.inference),
  ner: inferenceServicePrefix(apiEndpoints.ner.inference),
  ocr: inferenceServicePrefix(apiEndpoints.ocr.inference),
  transliteration: inferenceServicePrefix(apiEndpoints.transliteration.inference),
  languageDetection: inferenceServicePrefix(apiEndpoints['language-detection'].inference),
  speakerDiarization: inferenceServicePrefix(apiEndpoints['speaker-diarization'].inference),
  languageDiarization: inferenceServicePrefix(apiEndpoints['language-diarization'].inference),
  audioLangDetection: inferenceServicePrefix(
    apiEndpoints['audio-language-detection'].inference
  ),
} as const;

/** HTTP paths for inference calls — used by trace/log UI filters */
export const INFERENCE_TRACE_PATHS: readonly string[] = [
  apiEndpoints.ocr.inference,
  apiEndpoints.nmt.inference,
  apiEndpoints.transliteration.inference,
  apiEndpoints.tts.inference,
  apiEndpoints.asr.inference,
  apiEndpoints.ner.inference,
];
