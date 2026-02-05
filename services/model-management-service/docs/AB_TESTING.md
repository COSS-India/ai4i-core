# A/B Testing for Models

## Overview

The A/B testing feature allows platform administrators to evaluate alternative models or versions using live traffic. Traffic is split and compared at the platform level without modifying application logic, enabling evidence-based production rollout decisions.

## Features

- **Define experiments** with multiple model variants
- **Configure traffic distribution** percentages (must sum to 100%)
- **Filter experiments** by task type, language, or duration
- **View comparative metrics** for each variant (via observability portal)
- **Stop or conclude** experiments without service disruption

## Database Schema

### Tables

1. **experiments** - Main experiment configuration
   - `id` (UUID) - Primary key
   - `name` - Experiment name
   - `description` - Optional description
   - `status` - DRAFT, RUNNING, PAUSED, COMPLETED, CANCELLED
   - `task_type` (JSONB) - Optional list of task types to filter
   - `languages` (JSONB) - Optional list of language codes to filter
   - `start_date` - Optional start date
   - `end_date` - Optional end date
   - `created_by`, `updated_by` - User tracking
   - Timestamps: `created_at`, `updated_at`, `started_at`, `completed_at`

2. **experiment_variants** - Model/service variants in the experiment
   - `id` (UUID) - Primary key
   - `experiment_id` - Foreign key to experiments
   - `variant_name` - Name of variant (e.g., "control", "variant-a")
   - `service_id` - Foreign key to services
   - `traffic_percentage` - Traffic percentage (0-100)
   - `description` - Optional description

3. **experiment_metrics** - Metrics tracking per variant
   - `id` (UUID) - Primary key
   - `experiment_id` - Foreign key to experiments
   - `variant_id` - Foreign key to experiment_variants
   - `request_count`, `success_count`, `error_count`
   - `avg_latency_ms`, `p50_latency_ms`, `p95_latency_ms`, `p99_latency_ms`
   - `custom_metrics` (JSONB) - Additional flexible metrics
   - `metric_date` - Date for daily aggregation

## API Endpoints

### Experiment Management (Authenticated)

All endpoints require authentication via `AuthProvider`.

#### Create Experiment
```
POST /experiments
Content-Type: application/json

{
  "name": "ASR Model Comparison",
  "description": "Compare v1 vs v2 of ASR model",
  "task_type": ["asr"],
  "languages": ["hi", "en"],
  "start_date": "2024-01-01T00:00:00Z",
  "end_date": "2024-01-31T23:59:59Z",
  "variants": [
    {
      "variant_name": "control",
      "service_id": "service-id-1",
      "traffic_percentage": 50,
      "description": "Current production model"
    },
    {
      "variant_name": "variant-a",
      "service_id": "service-id-2",
      "traffic_percentage": 50,
      "description": "New model version"
    }
  ]
}
```

**Requirements:**
- At least 2 variants required
- Traffic percentages must sum to 100
- Variant names must be unique
- All services must exist and be published

#### List Experiments
```
GET /experiments?status=RUNNING&task_type=asr&created_by=user123
```

**Query Parameters:**
- `status` (optional) - Filter by status
- `task_type` (optional) - Filter by task type
- `created_by` (optional) - Filter by creator

#### Get Experiment
```
GET /experiments/{experiment_id}
```

#### Update Experiment
```
PATCH /experiments/{experiment_id}
Content-Type: application/json

{
  "name": "Updated Name",
  "variants": [...]
}
```

**Note:** Cannot update variants of a RUNNING experiment.

#### Update Experiment Status
```
POST /experiments/{experiment_id}/status
Content-Type: application/json

{
  "action": "start"  // or "stop", "pause", "resume", "cancel"
}
```

Updates experiment status based on action:
- `start`: Changes DRAFT → RUNNING
- `stop`: Changes RUNNING → COMPLETED
- `pause`: Changes RUNNING → PAUSED
- `resume`: Changes PAUSED → RUNNING
- `cancel`: Changes any non-RUNNING status → CANCELLED

#### Delete Experiment
```
DELETE /experiments/{experiment_id}
```

**Note:** Cannot delete a RUNNING experiment. Stop it first.

### Variant Selection (Public/Internal)

This endpoint is used by the API gateway or services to determine which variant to route a request to.

#### Select Variant
```
POST /experiments/select-variant
Content-Type: application/json

{
  "task_type": "asr",
  "language": "hi",
  "request_id": "optional-request-id"
}
```

**Response:**
```json
{
  "experiment_id": "uuid",
  "variant_id": "uuid",
  "variant_name": "control",
  "service_id": "service-id",
  "model_id": "model-id",
  "model_version": "v1.0",
  "endpoint": "http://service:port",
  "api_key": "api-key",
  "is_experiment": true
}
```

If no matching experiment:
```json
{
  "is_experiment": false
}
```

## Traffic Routing Logic

The variant selection uses **deterministic consistent hashing**:

1. If `request_id` is provided, it's used for hashing (ensures same request always routes to same variant)
2. Otherwise, a hash is generated from `task_type:language`
3. The hash is mapped to a bucket (0-99)
4. Variants are selected based on cumulative traffic percentages

**Example:**
- Variant A: 30% traffic (buckets 0-29)
- Variant B: 70% traffic (buckets 30-99)

## Experiment Lifecycle

1. **DRAFT** - Experiment created but not active
2. **RUNNING** - Experiment is active and routing traffic
3. **PAUSED** - Experiment temporarily paused (can be resumed)
4. **COMPLETED** - Experiment finished (can be deleted)
5. **CANCELLED** - Experiment cancelled (can be deleted)

## Filtering

Experiments can be filtered by:

- **Task Type**: Only route requests matching specified task types
  - If `task_type` is `null` or empty array, matches all tasks
  - Example: `["asr", "tts"]` - only ASR and TTS requests

- **Language**: Only route requests matching specified languages
  - **Language filtering is per-experiment** - each experiment has its own language filter
  - **To match ALL languages**: Set `languages` to `null` or `[]` (empty array)
    - Both `null` and `[]` are treated identically - they mean "no language filter" = "match all languages"
    - **Recommended**: Use `null` (or omit the field) for clarity - it means "not filtering by language"
    - **Alternative**: Use `[]` if you want to explicitly indicate "empty filter = all languages"
    - **Do NOT** list all supported languages explicitly (e.g., `["hi", "en", "ta", ...]`) because:
      - You'd need to know all supported languages upfront
      - If new languages are added, you'd need to update the experiment
      - It's error-prone and harder to maintain
      - `null`/`[]` is semantically clearer and future-proof
  - **To match specific languages**: Set `languages` to a list of language codes (e.g., `["hi", "en"]`)
    - The experiment **only matches** requests with those specific languages
    - Example: `languages: ["hi"]` only affects Hindi requests
    - Example: `languages: ["hi", "en"]` only affects Hindi and English requests
  - Multiple experiments can have different language filters simultaneously
    - Example: Experiment A with `["hi"]` only affects Hindi requests
    - Example: Experiment B with `["en"]` only affects English requests
    - Example: Experiment C with `null` or `[]` affects all languages
  - **Services without language concept**: For services/models that don't use language (e.g., OCR, general-purpose models), pass `language=None` when selecting variants. These will only match experiments with `languages: null` or `languages: []`. Experiments with specific language filters (e.g., `["hi"]`) will NOT match when `language=None`.

- **Duration**: Start and end dates
  - If `start_date` is `null`, experiment starts immediately
  - If `end_date` is `null`, experiment runs indefinitely
  - Experiment only routes traffic within the date range

## Duplicate Experiment Prevention

The system allows creating duplicate experiments with identical configurations, but **prevents two identical experiments from being RUNNING simultaneously**:

- **Creation**: You can create multiple experiments with the same configuration (same service IDs, task_type, languages, dates)
  - Useful for scheduling experiments at different times
  - Useful for creating backup/alternative experiment configurations
  
- **Running Validation**: When starting or resuming an experiment to RUNNING status, the system checks if another RUNNING experiment exists with:
  - Same service IDs (exact match of all variant service IDs)
  - Same task_type filter
  - Same languages filter
  - Overlapping date ranges
  
- **Blocking**: If a duplicate RUNNING experiment is detected, the start/resume action fails with an error message

- **Status States**: Multiple experiments with identical configurations can exist in DRAFT, PAUSED, COMPLETED, or CANCELLED states simultaneously

**Example:**
- ✅ **Allowed**: Create Experiment A and Experiment B with identical configs (both in DRAFT)
- ✅ **Allowed**: Start Experiment A (now RUNNING), Experiment B remains in DRAFT
- ❌ **Blocked**: Try to start Experiment B while Experiment A is RUNNING (same config)
- ✅ **Allowed**: Stop Experiment A (now COMPLETED), then start Experiment B (now RUNNING)
- ✅ **Allowed**: Experiment A with `task_type: ["asr"]` and Experiment B with `task_type: ["tts"]` can both be RUNNING (different filters)

## Integration with Services

To integrate A/B testing into your services:

1. **Before processing a request**, call the variant selection endpoint:
   
   **For services with language support:**
   ```python
   response = await http_client.post(
       "http://model-management-service:8091/experiments/select-variant",
       json={
           "task_type": "asr",
           "language": request.language,  # e.g., "hi", "en"
           "request_id": request.id  # Optional, for consistent routing
       }
   )
   ```
   
   **For services without language concept (e.g., OCR, general-purpose models):**
   ```python
   response = await http_client.post(
       "http://model-management-service:8091/experiments/select-variant",
       json={
           "task_type": "ocr",
           "language": None,  # Explicitly set to None for non-language services
           "request_id": request.id  # Optional, for consistent routing
       }
   )
   ```
   
   **Note:** When `language=None`, only experiments with `languages: null` or `languages: []` will match. This ensures language-specific experiments don't interfere with non-language services.

2. **If `is_experiment: true`**, use the returned `endpoint` and `api_key` instead of the default service

3. **Track metrics** for the experiment variant (integrate with observability service)

## Language Filtering: Best Practices

### When to Use `null` vs `[]` vs Specific Languages

**Use `null` (or omit the field) when:**
- ✅ You want to experiment on **ALL languages**
- ✅ You want the experiment to be **future-proof** (automatically includes new languages)
- ✅ You don't want to maintain a list of languages
- ✅ **Recommended approach** for "all languages" experiments

**Use `[]` (empty array) when:**
- ✅ You want to explicitly indicate "empty filter = all languages"
- ✅ You prefer explicit over implicit (some teams prefer this)
- ⚠️ Functionally identical to `null` - both match all languages

**Use specific language list (e.g., `["hi", "en"]`) when:**
- ✅ You want to experiment on **specific languages only**
- ✅ You want to isolate the experiment to certain languages
- ✅ You want to run parallel experiments for different languages

### Examples

**Example 1: Experiment on ALL languages**
```json
{
  "name": "ASR Model v2 Test - All Languages",
  "task_type": ["asr"],
  "languages": null,  // ← Matches ALL languages (recommended)
  "variants": [...]
}
```

**Example 2: Experiment on ALL languages (alternative)**
```json
{
  "name": "ASR Model v2 Test - All Languages",
  "task_type": ["asr"],
  "languages": [],  // ← Also matches ALL languages (functionally same as null)
  "variants": [...]
}
```

**Example 3: Experiment on specific languages only**
```json
{
  "name": "ASR Model v2 Test - Hindi Only",
  "task_type": ["asr"],
  "languages": ["hi"],  // ← Only matches Hindi requests
  "variants": [...]
}
```

**Example 4: Experiment on multiple specific languages**
```json
{
  "name": "ASR Model v2 Test - Hindi and English",
  "task_type": ["asr"],
  "languages": ["hi", "en"],  // ← Only matches Hindi and English requests
  "variants": [...]
}
```

**Example 5: What NOT to do (listing all languages)**
```json
{
  "name": "ASR Model v2 Test - All Languages",
  "task_type": ["asr"],
  "languages": ["hi", "en", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi", "mai", "brx", "mni"],  // ❌ DON'T DO THIS
  "variants": [...]
}
```
**Why this is bad:**
- ❌ You must know all supported languages upfront
- ❌ If new languages are added, experiment won't include them
- ❌ Harder to maintain and error-prone
- ❌ Use `null` or `[]` instead

### Difference Between `null` and `[]`

**Functionally:** They are **identical** - both mean "match all languages"

**Semantically:**
- `null` = "not specified" / "no filter" (more common in APIs)
- `[]` = "empty filter" / "explicitly all languages"

**In duplicate detection:** Both are treated as equivalent - an experiment with `null` and an experiment with `[]` are considered duplicates if other fields match.

**Recommendation:** Use `null` (or omit the field) as it's the standard way to indicate "no filter" in JSON/APIs.

## Best Practices

1. **Start Small**: Begin with low traffic percentages (e.g., 10% to new variant)
2. **Monitor Metrics**: Track latency, error rates, and custom metrics
3. **Gradual Rollout**: Increase traffic percentage over time
4. **Consistent Routing**: Use `request_id` for deterministic routing when needed
5. **Clean Up**: Delete completed experiments to keep database clean
6. **Language Filtering**: Use `null` for "all languages" experiments, specific lists only when needed

## Example Workflow

1. Create two services for model v1 and v2
2. Publish both services
3. Create experiment with 50/50 split
4. Start experiment
5. Monitor metrics via observability portal
6. After evaluation period, stop experiment
7. Promote winning variant to production
8. Delete experiment

## Error Handling

- If variant selection fails, the system gracefully falls back to default service routing
- Experiments in DRAFT or PAUSED status do not route traffic
- Only RUNNING experiments with valid date ranges route traffic
- Services must be published to be used in experiments
