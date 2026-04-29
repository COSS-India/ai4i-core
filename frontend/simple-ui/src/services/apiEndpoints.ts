/** Shared REST path prefix for routes behind the API gateway */
export const API_V1_PREFIX = '/api/v1' as const;

export const apiEndpoints = {
  asr: {
    base: '/api/v1/asr',
    inference: '/api/v1/asr/inference',
    models: '/api/v1/asr/models',
    health: '/api/v1/asr/health',
    config: '/api/v1/asr/config',
    streamingInfo: '/api/v1/asr/streaming/info',
    streaming:
      process.env.NEXT_PUBLIC_ASR_STREAM_URL || 'ws://localhost:8087/socket.io',
  },
  tts: {
    base: '/api/v1/tts',
    inference: '/api/v1/tts/inference',
    voices: '/api/v1/tts/voices',
    health: '/api/v1/tts/health',
    config: '/api/v1/tts/config',
  },
  nmt: {
    base: '/api/v1/nmt',
    inference: '/api/v1/nmt/inference',
    models: '/api/v1/nmt/models',
    services: '/api/v1/nmt/services',
    languages: '/api/v1/nmt/languages',
    health: '/api/v1/nmt/health',
    config: '/api/v1/nmt/config',
  },
  llm: {
    base: '/api/v1/llm',
    inference: '/api/v1/llm/inference',
    models: '/api/v1/llm/models',
    health: '/api/v1/llm/health',
  },
  ocr: {
    base: '/api/v1/ocr',
    inference: '/api/v1/ocr/inference',
    health: '/api/v1/ocr/health',
  },
  transliteration: {
    base: '/api/v1/transliteration',
    inference: '/api/v1/transliteration/inference',
    health: '/api/v1/transliteration/health',
  },
  'language-detection': {
    base: '/api/v1/language-detection',
    inference: '/api/v1/language-detection/inference',
    health: '/api/v1/language-detection/health',
  },
  'speaker-diarization': {
    base: '/api/v1/speaker-diarization',
    inference: '/api/v1/speaker-diarization/inference',
    health: '/api/v1/speaker-diarization/health',
  },
  'language-diarization': {
    base: '/api/v1/language-diarization',
    inference: '/api/v1/language-diarization/inference',
    health: '/api/v1/language-diarization/health',
  },
  'audio-language-detection': {
    base: '/api/v1/audio-lang-detection',
    inference: '/api/v1/audio-lang-detection/inference',
    health: '/api/v1/audio-lang-detection/health',
  },
  ner: {
    base: '/api/v1/ner',
    inference: '/api/v1/ner/inference',
    health: '/api/v1/ner/health',
  },
  pii: {
    base: '/api/v1/pii',
    redact: '/api/v1/pii/redact',
    domains: '/api/v1/pii/domains',
    /** GET with /{domainId} appended. */
    policy: '/api/v1/pii/policy',
    admin: {
      allDomains: '/api/v1/pii/admin/all-domains',
      activateDomains: '/api/v1/pii/admin/activate-domains',
      domain: '/api/v1/pii/admin/domain',
      deploy: '/api/v1/pii/admin/deploy',
      generateRegex: '/api/v1/pii/admin/generate-regex',
      tenantDomains: '/api/v1/pii/admin/tenant-domains',
      tenantDomain: '/api/v1/pii/admin/tenant-domain',
      tenantDomainDelete: '/api/v1/pii/admin/tenant-domain/delete',
      auditLogs: '/api/v1/pii/admin/audit-logs',
    },
  },
  policy: {
    /** Gateway prefix; service mounts routes at /v1 (see policy-service main.py). */
    base: '/api/v1/policy-service',
    health: '/api/v1/policy-service/health',
    piiTypes: '/api/v1/policy-service/pii-types',
    policies: '/api/v1/policy-service/policies',
    auditLogs: '/api/v1/policy-service/audit-logs',
  },
  pipeline: {
    base: '/api/v1/pipeline',
    inference: '/api/v1/pipeline/inference',
    info: '/api/v1/pipeline/info',
    health: '/api/v1/pipeline/health',
  },
  auth: {
    base: '/api/v1/auth',
    roles: '/api/v1/auth/roles',
    /** Relative to `auth.roles` (used by `roleService`). */
    rolesPaths: {
      list: '/list',
      user: '/user',
      assign: '/assign',
      remove: '/remove',
    },
    /** Relative to `auth.base` (used by `authService`). */
    paths: {
      register: '/register',
      login: '/login',
      guestLogin: '/guest/login',
      guestServices: '/roles/list/guest/services',
      logout: '/logout',
      refresh: '/refresh',
      validate: '/validate',
      me: '/me',
      changePassword: '/change-password',
      requestPasswordReset: '/request-password-reset',
      resetPassword: '/reset-password',
      apiKeys: '/api-keys',
      apiKeysAll: '/api-keys/all',
      oauth2Providers: '/oauth2/providers',
      oauth2Exchange: '/oauth2/exchange',
      oauth2GoogleAuthorize: '/oauth2/google/authorize',
      users: '/users',
      inferencePermissions: '/inference/permissions',
    },
  },
  alerts: {
    base: '/api/v1/alerts',
    /** Relative to `alerts.base` (used by `alertingService`). */
    paths: {
      definitions: '/definitions',
      receivers: '/receivers',
      routingRules: '/routing-rules',
      routingRulesTiming: '/routing-rules/timing',
      history: '/history',
    },
  },
  'multi-tenant': {
    base: '/api/v1/multi-tenant',
    admin: {
      listTenants: '/api/v1/multi-tenant/admin/list/tenants',
      listUsers: '/api/v1/multi-tenant/admin/list/users',
      viewTenant: '/api/v1/multi-tenant/admin/view/tenant',
      viewUser: '/api/v1/multi-tenant/admin/view/user',
      updateTenantsStatus: '/api/v1/multi-tenant/admin/update/tenants/status',
      updateUsersStatus: '/api/v1/multi-tenant/admin/update/users/status',
      updateTenant: '/api/v1/multi-tenant/admin/update/tenant',
      registerTenant: '/api/v1/multi-tenant/admin/register/tenant',
      registerUsers: '/api/v1/multi-tenant/admin/register/users',
      updateUser: '/api/v1/multi-tenant/admin/update/user',
      deleteUser: '/api/v1/multi-tenant/admin/delete/user',
      emailSendVerification: '/api/v1/multi-tenant/admin/email/send/verification',
    },
    listServices: '/api/v1/multi-tenant/list/services',
    tenantSubscriptionsAdd: '/api/v1/multi-tenant/tenant/subscriptions/add',
    tenantSubscriptionsRemove: '/api/v1/multi-tenant/tenant/subscriptions/remove',
    userSubscriptionsAdd: '/api/v1/multi-tenant/user/subscriptions/add',
    userSubscriptionsRemove: '/api/v1/multi-tenant/user/subscriptions/remove',
    emailResend: '/api/v1/multi-tenant/email/resend',
    emailVerify: '/api/v1/multi-tenant/email/verify',
    /** GET with /{userId} appended. */
    resolveTenantFromUser: '/api/v1/multi-tenant/resolve/tenant/from/user',
  },
  'model-management': {
    base: '/api/v1/model-management',
    models: '/api/v1/model-management/models',
    modelsUnpublish: '/api/v1/model-management/models/unpublish',
    modelsPublish: '/api/v1/model-management/models/publish',
    services: '/api/v1/model-management/services',
    tryItServiceList: '/api/v1/model-management/services/try-it-service-list',
  },
  'try-it': {
    inference: '/api/v1/try-it',
  },
  'feature-flags': {
    base: '/api/v1/feature-flags',
    evaluate: '/api/v1/feature-flags/evaluate',
    evaluateBoolean: '/api/v1/feature-flags/evaluate/boolean',
    evaluateBulk: '/api/v1/feature-flags/evaluate/bulk',
    sync: '/api/v1/feature-flags/sync',
  },
  telemetry: {
    base: '/api/v1/telemetry',
    logsSearch: '/api/v1/telemetry/logs/search',
    logsAggregate: '/api/v1/telemetry/logs/aggregate',
    logsServices: '/api/v1/telemetry/logs/services',
    tracesSearch: '/api/v1/telemetry/traces/search',
    tracesRoot: '/api/v1/telemetry/traces',
    tracesServices: '/api/v1/telemetry/traces/services',
  },
} as const;

/**
 * URL builders for endpoints that require path params.
 * Keeping these here avoids hardcoding `/api/...` routes outside `apiEndpoints`.
 */
export const apiEndpointBuilders = {
  telemetry: {
    traceById: (traceId: string) =>
      `${apiEndpoints.telemetry.tracesRoot}/${encodeURIComponent(traceId)}`,
    operationsForService: (serviceName: string) =>
      `${apiEndpoints.telemetry.tracesServices}/${encodeURIComponent(
        serviceName
      )}/operations`,
  },
} as const;

/**
 * Non-REST URL defaults used by UI flows/observability integrations.
 * Keeping these in one place avoids hardcoded localhost URLs in components/pages.
 */
export const appUrlDefaults = {
  authCallback:
    process.env.NEXT_PUBLIC_AUTH_CALLBACK_URL ||
    'http://localhost:3000/auth/callback',
  jaegerBase:
    process.env.NEXT_PUBLIC_JAEGER_URL || 'http://localhost:16686',
} as const;
