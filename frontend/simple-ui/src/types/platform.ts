/**
 * Platform-core API types (models & services).
 * Shapes mirror services/platform-core-service/app/schemas/*.py (camelCase contract).
 * Model Registry fields follow ULCA model-schema.yml (AI4IDS-2478).
 */

// ── Shared building blocks ──

export type OAuthProvider =
  | "custom"
  | "github"
  | "facebook"
  | "instagram"
  | "google"
  | "yahoo";

export interface OAuthId {
  identifier?: string;
  oauthId?: string;
  provider?: OAuthProvider;
}

export interface TeamMember {
  /** 5–50 chars when present */
  name: string;
  aboutMe?: string;
  oauthId?: OAuthId;
}

export interface Submitter {
  /** 3–50 chars */
  name: string;
  oauthId?: OAuthId;
  aboutMe?: string;
  team?: TeamMember[];
}

export interface InferenceApiKey {
  /** Defaults to "Authorization" */
  name?: string;
  /** Always "[REDACTED]" on every read */
  value: string;
}

export interface AsyncApiDetails {
  pollingUrl: string;
  /** Poll interval in milliseconds */
  pollInterval: number;
  asyncApiSchema?: Record<string, unknown>;
  asyncApiPollingSchema?: Record<string, unknown>;
}

/** ULCA inference endpoint (callbackUrl + schema required on create). */
export interface InferenceEndPoint {
  callbackUrl: string;
  inferenceApiKey?: InferenceApiKey;
  isMultilingualEnabled?: boolean;
  schema: Record<string, unknown>;
  isSyncApi?: boolean;
  asyncApiDetails?: AsyncApiDetails;
  /** Platform-specific Triton I/O mapping — not part of ULCA */
  adapterConfig?: Record<string, unknown>;
}

export type InferenceEndPointPatch = Partial<InferenceEndPoint>;

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

export interface TrainingDataset {
  description: string;
  datasetId?: string;
}

export type License =
  | "cc-by-4.0"
  | "cc-by-sa-4.0"
  | "cc-by-nd-2.0"
  | "cc-by-nd-4.0"
  | "cc-by-nc-3.0"
  | "cc-by-nc-4.0"
  | "cc-by-nc-sa-4.0"
  | "cc0"
  | "mit"
  | "gpl-3.0"
  | "bsd-3-clause"
  | "private-commercial"
  | "unknown-license"
  | "custom-license";

export type Domain =
  | "general"
  | "news"
  | "education"
  | "legal"
  | "government-press-release"
  | "healthcare"
  | "agriculture"
  | "automobile"
  | "tourism"
  | "financial"
  | "movies"
  | "subtitles"
  | "sports"
  | "technology"
  | "lifestyle"
  | "entertainment"
  | "parliamentary"
  | "art-and-culture"
  | "economy"
  | "history"
  | "philosophy"
  | "religion"
  | "national-security-and-defence"
  | "literature"
  | "geography";

/** ULCA SupportedLanguages — Indic + English only (45 codes). */
export type SupportedLanguage =
  | "en"
  | "hi"
  | "mr"
  | "ta"
  | "te"
  | "kn"
  | "gu"
  | "pa"
  | "bn"
  | "ml"
  | "as"
  | "brx"
  | "doi"
  | "ks"
  | "kok"
  | "mai"
  | "mni"
  | "ne"
  | "or"
  | "sd"
  | "si"
  | "ur"
  | "sat"
  | "lus"
  | "njz"
  | "pnr"
  | "kha"
  | "grt"
  | "sa"
  | "raj"
  | "bho"
  | "gom"
  | "awa"
  | "hne"
  | "mag"
  | "mwr"
  | "sjp"
  | "gbm"
  | "tcy"
  | "hlb"
  | "bih"
  | "anp"
  | "bns"
  | "mixed"
  | "unknown";

/** ULCA SupportedScripts — ISO 15924 (16 codes). */
export type SupportedScript =
  | "Beng"
  | "Deva"
  | "Thaa"
  | "Gujr"
  | "Aran"
  | "Orya"
  | "Guru"
  | "Arab"
  | "Sinh"
  | "Knda"
  | "Mlym"
  | "Taml"
  | "Telu"
  | "Mtei"
  | "Olck"
  | "Latn";

export interface LanguagePair {
  sourceLanguage: SupportedLanguage;
  sourceLanguageName?: string;
  sourceScriptCode?: SupportedScript;
  targetLanguage?: SupportedLanguage;
  targetLanguageName?: string;
  targetScriptCode?: SupportedScript;
}

/** Loose language bag for service list rows / legacy adapters. */
export type LanguageRecord = Record<string, unknown>;

// ── Model API ──

export type ModelVersionStatus = "ACTIVE" | "DEPRECATED" | string;

/** GET /models, GET /models/{id} — single model record. */
export interface ModelResponse {
  modelId: string;
  name: string;
  version: string;
  submittedOn?: number | null;
  versionStatus?: ModelVersionStatus | null;
  versionStatusUpdatedAt?: string | null;
  description?: string | null;
  languages?: LanguagePair[];
  isLangDetectionEnabled?: boolean;
  isMultilingual?: boolean;
  domain?: Domain[] | string[];
  submitter?: Submitter | null;
  license?: License | string | null;
  licenseUrl?: string | null;
  inferenceEndPoint?: InferenceEndPoint | null;
  /** GET/list returns refUrl as `source` — there is no `refUrl` key in responses. */
  source?: string | null;
  task?: TaskSpec;
  trainingDataset?: TrainingDataset | null;
  classInstance?: string | null;
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
  /** Comma-separated yaml task types → `task_types=` query param */
  taskTypes?: string;
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
  /** 5–100 chars; alphanumeric, -, / only — no spaces */
  name: string;
  /** 25–1000 chars */
  description: string;
  /** Optional (was required). 5–200 chars if provided. */
  refUrl?: string;
  task: TaskSpec;
  languages?: LanguagePair[];
  isLangDetectionEnabled?: boolean;
  isMultilingual?: boolean;
  license: License;
  licenseUrl?: string;
  domain: Domain[];
  inferenceEndPoint: InferenceEndPoint;
  trainingDataset: TrainingDataset;
  classInstance?: string;
  benchmarks?: Benchmark[];
  submitter: Submitter;
}

/** Partial update. Never include `name` — API returns 422 NAME_NOT_UPDATABLE. */
export interface ModelUpdateRequest {
  modelId: string;
  version: string;
  versionStatus?: ModelVersionStatus;
  description?: string;
  refUrl?: string;
  task?: TaskSpec;
  languages?: LanguagePair[];
  isLangDetectionEnabled?: boolean;
  isMultilingual?: boolean;
  license?: License;
  licenseUrl?: string;
  domain?: Domain[];
  inferenceEndPoint?: InferenceEndPointPatch;
  trainingDataset?: TrainingDataset;
  classInstance?: string;
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
  serviceDescription?: string | null;
  hardwareDescription?: string | null;
  modelId: string;
  modelVersion: string;
  endpoint?: string | null;
  inferenceServerType?: string;
  sslVerify?: boolean;
  api_key?: string | null;
  apiKey?: string | null;
  healthStatus?: ServiceStatus | null;
  benchmarks?: Record<string, unknown> | null;
  policy?: Record<string, unknown> | ServicePolicy | null;
  isPublished: boolean;
  /** When true, anonymous Try-It should prefer this service for its task type. */
  isTryItDefault?: boolean;
  publishedAt?: string | null;
  unpublishedAt?: string | null;
  createdBy?: string | null;
  updatedBy?: string | null;
  publishedOn?: number;
  status?: string;
  createdAt?: string | null;
  versionStatusUpdatedAt?: string | null;
}

/** GET /services list row — includes inline model task/languages snippet. */
export interface ServiceListItem extends ServiceResponse {
  task?: TaskSpec | { type?: string };
  languages?: LanguageRecord[];
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
  /** Comma-separated task types to include (frontend allowlist). */
  taskTypes?: string;
  isPublished?: boolean;
  createdBy?: string;
}

/** Legacy snake_case keys for backward compatibility. */
export interface ServiceLegacyFields {
  service_id?: string;
  description?: string;
  model_id?: string;
  model_version?: string;
  endpoint_url?: string;
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
  name: string;
  serviceDescription: string;
  hardwareDescription: string;
  modelId: string;
  modelVersion: string;
  endpoint: string;
  api_key?: string;
  inferenceServerType?: string;
  sslVerify?: boolean;
  healthStatus?: ServiceStatus;
  benchmarks?: Record<string, unknown>;
  isPublished?: boolean;
}

export interface ServiceUpdateRequest {
  serviceId: string;
  serviceDescription?: string;
  hardwareDescription?: string;
  endpoint?: string;
  api_key?: string;
  inferenceServerType?: string;
  sslVerify?: boolean;
  healthStatus?: string | ServiceStatus;
  benchmarks?: Record<string, unknown>;
  isPublished?: boolean;
  /** Mark this service as the anonymous Try-It default for its task type. */
  isTryItDefault?: boolean;
  policy?: ServicePolicy;
  taskType?: string;
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
