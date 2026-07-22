/**
 * Platform-core API types (models & services).
 * Shapes mirror services/platform-core-service/app/schemas/*.py (camelCase contract).
 */

// ── Shared building blocks ──

export interface OAuthId {
  oauthId: string;
  provider: string;
}

export interface TeamMember {
  name: string;
  aboutMe?: string;
  oauthId?: OAuthId;
}

export interface Submitter {
  name: string;
  aboutMe?: string;
  team?: TeamMember[];
}

export interface TaskSpec {
  type: string;
}

export interface BenchmarkLanguage {
  sourceLanguage?: string;
  targetLanguage?: string;
}

export interface BenchmarkScore {
  metricName: string;
  score: string;
}

export interface Benchmark {
  benchmarkId: string;
  name: string;
  description: string;
  domain: string;
  createdOn: string;
  languages: BenchmarkLanguage;
  score: BenchmarkScore[];
}

export type LanguageRecord = Record<string, unknown>;

export interface TrainingDataset {
  datasetId?: string;
  description: string;
}

export interface InferenceApiKey {
  name?: string;
  value: string;
}

export interface AsyncApiDetails {
  pollingUrl: string;
  pollInterval: number;
  asyncApiSchema?: Record<string, unknown>;
  asyncApiPollingSchema?: Record<string, unknown>;
}

/** ULCA AudioFormat enum. */
export type AudioFormat = "wav" | "pcm" | "mp3" | "flac" | "sph";

/** ULCA TextFormat enum. */
export type TextFormat = "srt" | "transcript" | "webvtt" | "alternatives";

export interface AudioFormats {
  audio: AudioFormat[];
}

export interface TextFormats {
  text: TextFormat[];
}

/** ULCA Service.inferenceEndPoint — how to actually invoke the deployed service. */
export interface InferenceAPIEndPoint {
  callbackUrl: string;
  inferenceApiKey?: InferenceApiKey;
  isMultilingualEnabled?: boolean;
  supportedInputFormats?: AudioFormats | TextFormats;
  supportedOutputFormats?: AudioFormats | TextFormats;
  /** ULCA InferenceSchemaArray — mandatory (may be an empty array). */
  schema: Record<string, unknown>[];
  isSyncApi?: boolean;
  asyncApiDetails?: AsyncApiDetails;
  /** minLength 5, maxLength 100 (ULCA). */
  providerName?: string;
  /** minLength 5, maxLength 100 (ULCA). */
  serviceId?: string;
  /** minLength 5, maxLength 100 (ULCA). */
  infraDescription?: string;
  /** minLength 5, maxLength 100 (ULCA). */
  inferenceModelId?: string;
  /** AI4Bharat extension (not part of ULCA): Triton tensor-mapping config. */
  adapterConfig?: Record<string, unknown>;
}

// ── Model API ──

export type ModelVersionStatus = string;

/** GET /models, GET /models/{id} — single model record. */
export interface ModelResponse {
  modelId: string;
  name: string;
  version: string;
  submittedOn?: number | null;
  versionStatus?: ModelVersionStatus | null;
  versionStatusUpdatedAt?: string | null;
  description?: string | null;
  languages?: LanguageRecord[];
  domain?: string[];
  submitter?: Submitter | null;
  license?: string | null;
  /** Alias for refUrl in API responses. */
  source?: string | null;
  refUrl?: string | null;
  task?: TaskSpec;
  benchmarks?: Benchmark[];
  createdBy?: string | null;
  updatedBy?: string | null;
  updatedOn?: number | null;
  createdAt?: string | null;
}

export type ModelListItem = ModelResponse;

/** Client-side paginated list (built from list endpoint + X-Total-Count). */
export interface PaginatedModels {
  items: ModelDetails[];
  total: number;
  offset: number;
  limit: number | null;
}

export interface ModelListParams {
  offset?: number;
  limit?: number;
  taskType?: string;
  versionStatus?: string;
  createdBy?: string;
}

/** Legacy snake_case keys still returned by some gateways or older rows. */
export interface ModelLegacyFields {
  model_id?: string;
  version_status?: string;
  task_type?: string;
  taskType?: string;
  modelVersion?: string;
  submitted_on?: string | number;
}

/** Model row as consumed by UI and inference service adapters. */
export type ModelDetails = ModelResponse & ModelLegacyFields;

export interface ModelCreateRequest {
  version: string;
  versionStatus?: ModelVersionStatus;
  submittedOn?: number;
  updatedOn?: number;
  name: string;
  description: string;
  refUrl: string;
  task: TaskSpec;
  languages: LanguageRecord[];
  license: string;
  domain: string[];
  benchmarks?: Benchmark[];
  submitter: Submitter;
}

export interface ModelUpdateRequest {
  modelId: string;
  version?: string;
  versionStatus?: ModelVersionStatus;
  description?: string;
  refUrl?: string;
  task?: TaskSpec;
  languages?: LanguageRecord[];
  license?: string;
  domain?: string[];
  benchmarks?: Benchmark[];
  submitter?: Submitter;
}

export interface UnpublishModelResponse {
  message: string;
  modelId: string;
  success: boolean;
}

export type ModelStatusUpdateResponse = ModelResponse;

// ── Service API ──

export interface ServiceStatus {
  status?: string | null;
  lastUpdated?: string | null;
}

export interface ServicePolicy {
  latency?: string | null;
  cost?: string | null;
  accuracy?: string | null;
}

/** GET /services/{id} — single service record. */
export interface ServiceResponse {
  serviceId: string;
  name: string;
  version?: string | null;
  description?: string | null;
  refUrl?: string | null;
  task?: TaskSpec | { type?: string } | null;
  languages?: LanguageRecord[];
  license?: string | null;
  domain?: string[];
  submitter?: Submitter | null;
  trainingDataset?: TrainingDataset | null;
  inferenceEndPoint?: InferenceAPIEndPoint | null;
  hardwareDescription?: string | null;
  modelId: string;
  modelVersion: string;
  inferenceServerType?: string;
  sslVerify?: boolean;
  healthStatus?: ServiceStatus | null;
  benchmarks?: Record<string, unknown> | null;
  policy?: Record<string, unknown> | ServicePolicy | null;
  isPublished: boolean;
  publishedAt?: string | null;
  unpublishedAt?: string | null;
  createdBy?: string | null;
  updatedBy?: string | null;
  publishedOn?: number;
  status?: string;
  createdAt?: string | null;
  versionStatusUpdatedAt?: string | null;
}

/** GET /services list row — includes the linked model's lifecycle status. */
export interface ServiceListItem extends ServiceResponse {
  versionStatus?: string | null;
  model?: ModelResponse | null;
}

export interface ServiceDetailResponse extends ServiceResponse {
  model?: ModelResponse | null;
}

/** Client-side paginated list (built from list endpoint + X-Total-Count). */
export interface PaginatedServices {
  items: Service[];
  total: number;
  offset: number;
  limit: number | null;
}

export interface ServiceListParams {
  offset?: number;
  limit?: number;
  taskType?: string;
  isPublished?: boolean;
  createdBy?: string;
}

/** Legacy snake_case keys for backward compatibility. */
export interface ServiceLegacyFields {
  service_id?: string;
  model_id?: string;
  model_version?: string;
  /** UI-only convenience alias, mapped client-side into `description`. */
  serviceDescription?: string;
  /** UI-only convenience alias, mapped client-side into inferenceEndPoint.callbackUrl. */
  endpoint?: string;
  /** UI-only convenience alias, mapped client-side into inferenceEndPoint.callbackUrl. */
  endpoint_url?: string;
  /** UI-only convenience alias, mapped client-side into inferenceEndPoint.inferenceApiKey.value. */
  api_key?: string;
  /** UI-only convenience alias, mapped client-side into inferenceEndPoint.inferenceApiKey.value. */
  apiKey?: string;
  task_type?: string;
  created_at?: string;
  updated_at?: string;
  /** UI-only: selected model display name (not sent to API). */
  modelName?: string;
  /** UI-only: derived from model submittedOn (not sent to API). */
  modelSubmissionDate?: string;
  /** Pay-per-use tier names assigned to this service. */
  tiers?: string[];
  /** Legacy single-tier field from mm_services.tier column. */
  tier?: string | null;
  /** Billing unit type (task type used for billing, e.g. "LLM", "ASR"). */
  billingUnitType?: string;
  /** Cost charged per billing unit. */
  costPerUnit?: number;
  /** Size of one billing unit. */
  unitSize?: number;
  /** IDs of tiers this service is available under. */
  tierIds?: string[] | null;
  /** Display names of tiers this service is available under (returned by list API). */
  tierNames?: string[] | null;
}

/** Service row as consumed by registry UI and inference adapters. */
export type Service = ServiceListItem & ServiceLegacyFields;

export interface ServiceCreateRequest {
  serviceId: string;
  /** ULCA: minLength 5, maxLength 100. */
  name: string;
  /** ULCA: minLength 1, maxLength 20. */
  version: string;
  /** ULCA: minLength 25, maxLength 1000. */
  description: string;
  /** ULCA: minLength 5, maxLength 200. */
  refUrl?: string;
  task: TaskSpec;
  languages: LanguageRecord[];
  license: string;
  domain: string[];
  submitter: Submitter;
  trainingDataset: TrainingDataset;
  inferenceEndPoint: InferenceAPIEndPoint;
  hardwareDescription: string;
  modelId: string;
  modelVersion: string;
  inferenceServerType?: string;
  sslVerify?: boolean;
  healthStatus?: ServiceStatus;
  benchmarks?: Record<string, unknown>;
  isPublished?: boolean;
  costPerUnit: number;
  unitSize: number;
  tierIds: string[];
}

export interface ServiceUpdateRequest {
  serviceId: string;
  version?: string;
  description?: string;
  refUrl?: string;
  task?: TaskSpec;
  languages?: LanguageRecord[];
  license?: string;
  domain?: string[];
  submitter?: Submitter;
  trainingDataset?: TrainingDataset;
  inferenceEndPoint?: InferenceAPIEndPoint;
  hardwareDescription?: string;
  inferenceServerType?: string;
  sslVerify?: boolean;
  healthStatus?: string | ServiceStatus;
  benchmarks?: Record<string, unknown>;
  isPublished?: boolean;
  policy?: ServicePolicy;
  costPerUnit?: number;
  unitSize?: number;
  tierIds?: string[];
}

export interface DeleteServiceResponse {
  message?: string;
  serviceId?: string;
  success?: boolean;
}

/** Platform list endpoint may wrap payloads in `{ success?, data }`. */
export interface PlatformEnvelope<T> {
  success?: boolean;
  data: T;
}
