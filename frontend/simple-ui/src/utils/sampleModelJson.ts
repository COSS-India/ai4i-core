/**
 * Sample model registration file offered by the "Download Sample JSON" action.
 *
 * Held as raw text rather than an object literal so the explanatory comments survive into
 * the downloaded file — `JSON.stringify` would drop them, since they are only source
 * comments once an object is parsed. Users keep the comments while editing; the upload path
 * strips them again via `stripJsonComments` before parsing.
 *
 * The JSON body below is one complete, working LLM example — every field a model can carry,
 * correctly filled in, based on ModelCreateRequest
 * (platform-core-service/app/schemas/model_management/model.py).
 *
 * A model only needs to carry ONE task type, so the trailing "TASK TYPE REFERENCE" comment
 * block below the JSON gives the equivalent `task`/`schema`/`adapterConfig`/`languages`
 * shape for every other supported task type — text (nmt, transliteration,
 * language-detection, ocr, ner) and audio (asr, tts, speaker-diarization,
 * audio-lang-detection, language-diarization) — copy the block for the task type you need
 * over the corresponding keys in the JSON below. Every non-LLM shape there is taken from a
 * real seeded model already serving a working Service on this platform (see
 * infrastructure/databases/migrations/postgres/alembic/versions/ai4iplatform_core/
 * d3e850228f7e_seed_default_data.py and a1f2e3d4c5b6_seed_adapter_configs_and_endpoints.py),
 * so following it exactly (task.type + schema.taskType + adapterConfig tensor names all
 * consistent) is what actually lets a Service later created against the model pass its live
 * endpoint probe — not just pass model registration.
 */
export const SAMPLE_MODEL_JSON = `{
  // ── Identity ───────────────────────────────────────────────────────────────

  "version": "v1",
  // Required. Version for the model. 1–20 characters.
  // Example: "v1", "v2.0"

  "name": "test-llm-2",
  // Required. Model name that you want your users to see. 5–100 characters.
  // Alphanumeric, hyphens (-), and forward slashes (/) only — no spaces.
  // Example: "org/model-name"

  "description": "A sample LLM model for demonstration purposes. Description must be at least 25 characters.",
  // Required. Brief description about the model and its goal. 25–1000 characters.

  "refUrl": "https://github.com/example/example-model",
  // Optional. GitHub link or URL giving further info about the model. 5–200 characters.

  // ── Task ───────────────────────────────────────────────────────────────────

  "task": {
    "type": "llm"
    // Required. The inference task this model performs.
    // Enum — one of: nmt | tts | asr | llm | transliteration |
    //   language-detection | speaker-diarization | audio-lang-detection |
    //   language-diarization | ocr | ner | pipeline
    // Case-insensitive on input.
    // IMPORTANT: must agree with "schema.taskType" below — model registration rejects a
    // mismatch (nmt <-> translation and language-detection <-> txt-lang-detection count
    // as the same thing; every other task type needs an exact literal match).
  },

  // ── Language support ───────────────────────────────────────────────────────

  "languages": [
    {
      "sourceLanguage": "hi",
      // Required. Indic language code (ISO-639-1/2), or 'en'.
      // Accepted values: en | hi | mr | ta | te | kn | gu | pa | bn | ml | as
      //   and other ULCA-supported Indic codes.

      "sourceLanguageName": "Hindi",
      // Optional in general — but for task types nmt / transliteration / llm, this and
      // every other sub-field below become REQUIRED once "languages" is non-empty
      // (enforced by ModelCreateRequest — see _require_full_pair). For single-language
      // tasks (asr, tts, ocr, ner, ...), these stay optional. For llm, if you don't need
      // to declare a language pair at all, you can instead omit "languages" entirely.

      "sourceScriptCode": "Deva",
      // Required for nmt / transliteration / llm (see above). ISO-15924 script code.
      // Enum — one of: Beng | Deva | Thaa | Gujr | Aran | Orya | Guru | Arab |
      //   Sinh | Knda | Mlym | Taml | Telu | Mtei | Olck | Latn

      "targetLanguage": "en",
      // Required for nmt / transliteration / llm; omit or set null for single-language
      // models (ASR, TTS, OCR, NER, ...). Same values as sourceLanguage.

      "targetLanguageName": "English",
      // Required for nmt / transliteration / llm (see above).

      "targetScriptCode": "Latn"
      // Required for nmt / transliteration / llm (see above). Same enum as sourceScriptCode.
    }
  ],

  "isLangDetectionEnabled": false,
  // Optional. Default: false.
  // Specify true if the same model is capable of detecting languages automatically
  // without passing any additional parameters.

  "isMultilingual": false,
  // Optional. Default: false.
  // Specify true if the same model is capable of handling multiple languages.

  // ── Licensing ──────────────────────────────────────────────────────────────

  "license": "mit",
  // Required. License under which this model is published.
  // Enum — one of (case-insensitive):
  //   cc-by-4.0 | cc-by-sa-4.0 | cc-by-nd-2.0 | cc-by-nd-4.0 |
  //   cc-by-nc-3.0 | cc-by-nc-4.0 | cc-by-nc-sa-4.0 | cc0 | mit |
  //   gpl-3.0 | bsd-3-clause | private-commercial | unknown-license | custom-license

  "licenseUrl": "https://opensource.org/licenses/MIT",
  // Optional. URL of the custom license text. Max 500 characters.
  // Recommended when license is "custom-license".

  // ── Domain ─────────────────────────────────────────────────────────────────

  "domain": ["general"],
  // Required. At least one value. Business area(s) this model covers.
  // Enum — one or more of:
  //   general | news | education | legal | government-press-release |
  //   healthcare | agriculture | automobile | tourism | financial |
  //   movies | subtitles | sports | technology | lifestyle | entertainment |
  //   parliamentary | art-and-culture | economy | history | philosophy |
  //   religion | national-security-and-defence | literature | geography

  // ── Inference endpoint ─────────────────────────────────────────────────────

  "callbackUrl": "https://inference.example.com",
  // Optional. This value on the model card isn't itself live-probed — it's informational,
  // and is NOT what a Service created against this model actually calls (a Service has
  // its own separate inferenceEndPoint.callbackUrl, set at Service-creation time, which
  // IS what gets live-probed). For task.type "llm", the convention is host:port only, with
  // NO path — "/v1/chat/completions" is attached automatically at inference time by
  // inference-service, so if you copy this value into a Service's callbackUrl later,
  // leave the path off there or the call will double up and fail. For every other task
  // type, this is conventionally the model's full Triton inference URL, e.g.
  // "https://inference.example.com/v2/models/example-model/infer".

  "inferenceApiKey": {
    "name": "Authorization",
    // Optional. HTTP header name the callbackUrl expects the API key under.
    // "Authorization" is used as the default if value is provided without a name.
    // Example: "apiKey"

    "value": "<your-api-key>"
    // Required if inferenceApiKey is provided.
    // The API key / token value sent in that header to fetch output.
  },

  "isSyncApi": true,
  // Optional. Boolean.
  // Specify true if the inference is a sync API, false otherwise.
  // When false, "asyncApiDetails" below is now REQUIRED (with pollingUrl + pollInterval)
  // — omitting it used to validate silently and fall back to a sync probe at Service
  // creation time, giving the wrong behavior with no error anywhere; model creation now
  // rejects isSyncApi:false without asyncApiDetails outright.

  "asyncApiDetails": null,
  // Required when isSyncApi is false (see above); otherwise optional/omit. Replace null with:
  // {
  //   "pollingUrl":   "https://...",  // Required if asyncApiDetails is provided.
  //   "pollInterval": 1000            // Required if asyncApiDetails is provided.
  // }

  // ── Adapter config (platform-specific Triton mapping) ──────────────────────

  "adapterConfig": {
    // Optional overall. When provided, "version", non-empty "inputs", and non-empty
    // "outputs" are all REQUIRED — this mirrors inference-service's own
    // AdapterMappingConfig, which rejects an empty/missing version or empty tensor lists
    // at real call time (RuntimeError), so it's now checked here too instead of only
    // failing once someone actually calls the model. Each input needs "tensor"/"dtype"/
    // "shape" plus a "value_path" (dot-path into the ULCA request body, e.g.
    // "input.source") or a static "value" — inference-service has nothing to fill the
    // tensor from otherwise. Each output needs "tensor"/"dtype"/"maps_to" (maps Triton's
    // tensor name back onto a ULCA response key). See the TASK TYPE REFERENCE block below
    // for real per-task-type tensor examples (Triton-backed tasks genuinely use this
    // mapping at inference time; llm mostly doesn't — see "model_name" below).
    //
    // LLM RULE: "model_name" is REQUIRED inside adapterConfig for task.type "llm" — the
    // OpenAI-compatible proxy uses it as the real upstream model name; omit it and the
    // client's raw service ID gets sent upstream instead, which the real LLM server
    // almost certainly 404s on. "inputs"/"outputs" are functionally unused for llm
    // (inference-service never Triton-maps an llm call) but are still required by the
    // check above — a single placeholder entry each, as below, is the convention every
    // real LLM model on this platform already follows.
    "version": "1.0",
    "model_name": "google/gemma-5-E4B-it",
    "inputs": [
      {
        "tensor": "INPUT_TEXT",
        "dtype": "BYTES",
        "shape": [-1, 1],
        "value_path": "input.source"
      }
    ],
    "outputs": [
      {
        "tensor": "OUTPUT_TEXT",
        "dtype": "BYTES",
        "maps_to": "target"
      }
    ]
  },

  // ── Schema ─────────────────────────────────────────────────────────────────

  "schema": {
    // Required whenever "schema" is provided at all: "model_name", "taskType", "request",
    // and "response" must ALL be present, or model registration is rejected. A Service
    // later created against this model derives its own inferenceEndPoint.schema from
    // these same four keys — an incomplete schema here can't be filled in afterward.
    //
    // "taskType" MUST match "task.type" above (nmt <-> translation and language-detection
    // <-> txt-lang-detection are treated as equivalent; every other task type needs an
    // exact literal match) — model registration rejects a mismatch.
    //
    // "model_name" is used to construct the Triton URL for non-LLM task types — for llm
    // it isn't used to build the call (adapterConfig.model_name is, see above) but is
    // still required as part of schema completeness; any placeholder string is fine.
    //
    // For llm, "request"/"response" are the OpenAI-compatible chat-completion shape
    // directly (no "triton" wrapper) — the live probe talks to callbackUrl's
    // chat/completions endpoint, not a Triton server.
    "taskType": "llm",
    "model_name": "example-model",
    "request": {
      "model": "google/gemma-5-E4B-it",
      "messages": [
        {
          "role": "user",
          "content": "Hello"
        }
      ]
    },
    "response": {
      "choices": [
        {
          "message": {
            "content": "Hi there! How can I help you today?"
          }
        }
      ]
    }
  },

  "classInstance": null,
  // Optional per the schema, but NOT cosmetic — for every task type EXCEPT llm, this is
  // what inference-service actually uses at call time to pick which processing class
  // handles the request (orchestrator.py looks it up in TASK_SERVICE_REGISTRY). Leave it
  // unset/null and every real inference call for that model fails at runtime with
  // "No class_instance set on model...", even though model AND Service creation both
  // succeed — so this is one more thing that "looks fine until you actually call it".
  // llm models (like this one) skip this entirely — llm calls go through a separate
  // OpenAI-compatible proxy that doesn't consult classInstance, so it's fine to leave
  // this null here. For every other task type, set it to the matching value from the
  // TASK TYPE REFERENCE block below (e.g. "NMTTaskService" for nmt, "ASRTaskService" for
  // asr, ...) — these are literal class-registry names, not free text.

  // ── Training data ──────────────────────────────────────────────────────────

  "trainingDataset": {
    "description": "Sample training dataset description for the example LLM model registration.",
    // Required. Explain the dataset you used to train this model.

    "datasetId": "example-LLM-corpus-v1"
    // Optional. Dataset identifier exported from the ULCA system.
    // Providing this enriches your model with further information for the community.
  },

  // ── Benchmarks ─────────────────────────────────────────────────────────────

  "benchmarks": [
    {
      "benchmarkId": "example-benchmark-001",
      "name": "Example Benchmark",
      "description": "Sample benchmark for evaluation",
      "domain": "general",
      "createdOn": "2025-01-15T10:00:00.000Z", // ISO 8601 datetime string.
      "languages": {
        "sourceLanguage": "hi",
        "targetLanguage": "en"
      },
      "score": [
        {
          "metricName": "WER", // Metric name, e.g. WER, BLEU, CER.
          "score": "7.5"       // Score value as a string.
        }
      ]
    }
  ],
  // Optional. Default: []. Performance benchmark entries for this model.

  // ── Submitter ──────────────────────────────────────────────────────────────

  "submitter": {
    "name": "Example Org",
    // Required. Name of the model provider or organization. 3–50 characters.

    "aboutMe": "An example organization",
    // Optional. Short description of the submitter.

    "team": [
      {
        "name": "John Doe",
        // Required. Contributor name. 5–50 characters.

        "aboutMe": "Lead Researcher",
        // Optional. Short bio for this contributor.

        "oauthId": {
          "oauthId": "1234567890",
          // Optional. Social/OAuth identifier returned after auth.

          "provider": "google"
          // Optional. Auth provider used.
          // Enum — one of: custom | github | facebook | instagram | google | yahoo
        }
      }
    ]
    // Optional. Default: []. Contributors on the submitting team.
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   TASK TYPE REFERENCE — every other text & audio task type
   ═══════════════════════════════════════════════════════════════════════════
   The JSON above is a full LLM example. To register a model for a different
   task, replace "task", "languages", "adapterConfig", and "schema" with the
   matching block below — everything else (name/description/license/domain/
   submitter/trainingDataset/callbackUrl shape/...) stays the same shape.
   Every snippet below is taken from a real seeded model on this platform
   (see infrastructure/databases/migrations/postgres/alembic/versions/
   ai4iplatform_core/d3e850228f7e_seed_default_data.py and
   a1f2e3d4c5b6_seed_adapter_configs_and_endpoints.py), so following it
   exactly is known to work end-to-end (model creation -> Service creation ->
   live endpoint probe), not just pass model registration. Unlike llm, all of
   these are Triton-served: "callbackUrl" for them is the model's full Triton
   inference URL (e.g. "https://inference.example.com/v2/models/<name>/infer"),
   not host:port only, and "schema.response" is wrapped in a "triton" key
   instead of being the direct OpenAI chat-completion shape.

   ── TEXT task types ──────────────────────────────────────────────────────

   nmt (machine translation, source language -> target language):
     "task": { "type": "nmt" }
     "languages": [{ "sourceLanguage": "en", "sourceLanguageName": "English",
       "sourceScriptCode": "Latn", "targetLanguage": "hi",
       "targetLanguageName": "Hindi", "targetScriptCode": "Deva" }]
       // full pair required, same rule as llm/transliteration.
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source" },
         { "tensor": "INPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1, 1], "value_path": "request.config.language.source_language" },
         { "tensor": "OUTPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1, 1], "value_path": "request.config.language.target_language" }
       ], "outputs": [{ "tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "target" }] }
     "schema": { "taskType": "nmt", "model_name": "nmt",
       "request": { "input": [{ "source": "Hello, how are you?" }],
         "config": { "language": { "sourceLanguage": "en", "targetLanguage": "hi" } } },
       "response": { "triton": { "inputs": [
           { "name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1, 1], "data": ["Hello, how are you?"] },
           { "name": "INPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1, 1], "data": ["en"] },
           { "name": "OUTPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1, 1], "data": ["hi"] }
         ], "outputs": [{ "name": "OUTPUT_TEXT" }] } } }
     "classInstance": "NMTTaskService"
     // "nmt" and "translation" are treated as equivalent taskType values.

   transliteration (English <-> Indic script, single word/short text):
     "task": { "type": "transliteration" }
     "languages": [{ "sourceLanguage": "hi", "sourceLanguageName": "Hindi",
       "sourceScriptCode": "Deva", "targetLanguage": "en",
       "targetLanguageName": "English", "targetScriptCode": "Latn" }]
       // full pair required, same rule as nmt/llm.
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1], "value_path": "input.source" },
         { "tensor": "INPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1], "value_path": "request.config.language.sourceLanguage" },
         { "tensor": "OUTPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1], "value_path": "request.config.language.targetLanguage" },
         { "tensor": "IS_WORD_LEVEL", "dtype": "BOOL", "shape": [-1], "value_path": "request.config.is_word_level" },
         { "tensor": "TOP_K", "dtype": "UINT8", "shape": [-1], "value_path": "request.config.top_k" }
       ], "outputs": [{ "tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "target" }] }
     "schema": { "taskType": "transliteration", "model_name": "transliteration",
       "request": { "input": [{ "source": "namaste" }],
         "config": { "language": { "sourceLanguage": "hi", "targetLanguage": "en" } } },
       "response": { "triton": { "inputs": [
           { "name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1], "data": ["namaste"] },
           { "name": "INPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1], "data": ["hi"] },
           { "name": "OUTPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1], "data": ["en"] },
           { "name": "IS_WORD_LEVEL", "datatype": "BOOL", "shape": [1], "data": [false] },
           { "name": "TOP_K", "datatype": "UINT8", "shape": [1], "data": [0] }
         ], "outputs": [{ "name": "OUTPUT_TEXT" }] } } }
     "classInstance": "TransliterationTaskService"

   language-detection (text -> language code; single-language, no target):
     "task": { "type": "language-detection" }
     "languages": [{ "sourceLanguage": "hi" }]   // sourceLanguageName/scriptCode not required.
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source" }
       ], "outputs": [{ "tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "langPrediction" }] }
     "schema": { "taskType": "language-detection", "model_name": "indiclid",
       "request": { "input": [{ "source": "नमस्ते, यह एक उदाहरण वाक्य है।" }], "config": {} },
       "response": { "triton": { "inputs": [
           { "name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1, 1], "data": ["नमस्ते, यह एक उदाहरण वाक्य है।"] }
         ], "outputs": [{ "name": "OUTPUT_TEXT" }] } } }
     "classInstance": "LanguageDetectionTaskService"
     // "language-detection" and "txt-lang-detection" are treated as equivalent taskType values.

   ocr (image -> text):
     "task": { "type": "ocr" }
     "languages": [{ "sourceLanguage": "hi" }]
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "IMAGE_DATA", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.image_content" }
       ], "outputs": [{ "tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "text" }] }
     "schema": { "taskType": "ocr", "model_name": "surya_ocr",
       "request": { "image": [{ "imageContent": "<base64-encoded-image>" }],
         "config": { "language": { "sourceLanguage": "hi" } } },
       "response": { "triton": { "inputs": [
           { "name": "IMAGE_DATA", "datatype": "BYTES", "shape": [1, 1] }
         ], "outputs": [{ "name": "OUTPUT_TEXT" }] } } }
     "classInstance": "OCRTaskService"

   ner (named entity recognition, text -> text):
     "task": { "type": "ner" }
     "languages": [{ "sourceLanguage": "hi" }]
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source" },
         { "tensor": "LANG_ID", "dtype": "BYTES", "shape": [-1, 1], "value_path": "request.config.language.sourceLanguage" }
       ], "outputs": [{ "tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "target", "transform": "json_parse" }] }
       // "transform": "json_parse" is REQUIRED for ner specifically — NERTaskService expects
       // the mapped "target" value to already be parsed JSON, not a raw string; omit this
       // and every real NER call raises ValueError("model returned non-JSON output").
     "schema": { "taskType": "ner", "model_name": "ner",
       "request": { "input": [{ "source": "राम दिल्ली गए।" }],
         "config": { "language": { "sourceLanguage": "hi" } } },
       "response": { "triton": { "inputs": [
           { "name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1, 1], "data": ["राम दिल्ली गए।"] },
           { "name": "LANG_ID", "datatype": "BYTES", "shape": [1, 1], "data": ["hi"] }
         ], "outputs": [{ "name": "OUTPUT_TEXT" }] } } }
     "classInstance": "NERTaskService"

   ── AUDIO task types ─────────────────────────────────────────────────────
   Audio inputs are base64-encoded in "audioContent"; adapterConfig's audio tensor is
   typically FP32 raw samples (with a paired sample-count tensor) or a BYTES blob,
   depending on what your Triton model actually expects — match your own model's inputs,
   these are just the platform's own seeded examples.

   asr (speech -> text):
     // ASR is the one task type whose input value_paths are "audio.samples" /
     // "audio.num_samples" (raw PCM float context) — every OTHER audio task type below
     // uses "audio.audio_content" (base64) instead. Copy-pasting one convention onto the
     // wrong task type resolves to nothing at request time and raises RuntimeError("Path
     // '...' not found") on every real call — match the convention for YOUR task type below.
     "task": { "type": "asr" }
     "languages": [{ "sourceLanguage": "hi" }]
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "AUDIO_SIGNAL", "dtype": "FP32", "shape": [-1, -1], "value_path": "audio.samples" },
         { "tensor": "NUM_SAMPLES", "dtype": "INT32", "shape": [-1, 1], "value_path": "audio.num_samples" },
         { "tensor": "LANG_ID", "dtype": "BYTES", "shape": [-1, 1], "value_path": "request.config.language.source_language" }
       ], "outputs": [{ "tensor": "TRANSCRIPTS", "dtype": "BYTES", "maps_to": "transcript" }] }
     "schema": { "taskType": "asr", "model_name": "asr_am_ensemble",
       "request": { "audio": [{ "audioContent": "<base64-encoded-audio>" }],
         "config": { "language": { "sourceLanguage": "hi" } } },
       "response": { "triton": { "inputs": [
           { "name": "AUDIO_SIGNAL", "datatype": "FP32", "shape": [1, 4000], "data": [0.0] },
           { "name": "NUM_SAMPLES", "datatype": "INT32", "shape": [1, 1], "data": [4000] },
           { "name": "LANG_ID", "datatype": "BYTES", "shape": [1, 1], "data": ["hi"] }
         ], "outputs": [{ "name": "TRANSCRIPTS" }] } } }
     "classInstance": "ASRTaskService"

   tts (text -> speech):
     "task": { "type": "tts" }
     "languages": [{ "sourceLanguage": "hi" }]
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [1], "value_path": "input.source" },
         { "tensor": "INPUT_SPEAKER_ID", "dtype": "BYTES", "shape": [1], "value_path": "input.gender" },
         { "tensor": "INPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [1], "value_path": "input.language_id" }
       ], "outputs": [{ "tensor": "OUTPUT_GENERATED_AUDIO", "dtype": "FP32", "maps_to": "audio_data" }] }
       // The output tensor name "OUTPUT_GENERATED_AUDIO" is REQUIRED verbatim for tts —
       // TTSTaskService reads that exact literal name out of the raw Triton response and
       // ignores "maps_to" entirely; any other name means every real TTS call raises
       // RuntimeError("OUTPUT_GENERATED_AUDIO not found"), even though this adapterConfig
       // otherwise looks perfectly valid.
     "schema": { "taskType": "tts", "model_name": "tts",
       "request": { "input": [{ "source": "नमस्ते" }],
         "config": { "language": { "sourceLanguage": "hi" }, "gender": "female" } },
       "response": { "triton": { "inputs": [
           { "name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1], "data": ["namaste"] },
           { "name": "INPUT_SPEAKER_ID", "datatype": "BYTES", "shape": [1], "data": ["female"] },
           { "name": "INPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1], "data": ["hi"] }
         ], "outputs": [{ "name": "OUTPUT_GENERATED_AUDIO" }] } } }
     "classInstance": "TTSTaskService"

   speaker-diarization (audio -> who-spoke-when):
     "task": { "type": "speaker-diarization" }
     "languages": [{ "sourceLanguage": "mixed" }]   // For a language-agnostic model, use the
       // enum's "mixed" value — NOT "*". The platform's own seed data does use "*" for one
       // speaker-diarization row, but that's a DB-only value inserted by bypassing this
       // validation entirely; submitted through this API, "*" is rejected outright
       // (not a SupportedLanguagesEnum member) — "mixed" is the actual valid equivalent.
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "AUDIO_DATA", "dtype": "BYTES", "shape": [1, 1], "value_path": "audio.audio_content" },
         { "tensor": "NUM_SPEAKERS", "dtype": "BYTES", "shape": [1, 1], "value_path": "request.config.num_speakers" }
       ], "outputs": [{ "tensor": "DIARIZATION_RESULT", "dtype": "BYTES", "maps_to": "diarization_json" }] }
     "schema": { "taskType": "speaker-diarization", "model_name": "speaker_diarization",
       "request": { "audio": [{ "audioContent": "<base64-encoded-audio>" }], "config": {} },
       "response": { "triton": { "inputs": [
           { "name": "AUDIO_DATA", "datatype": "BYTES", "shape": [1, 1] },
           { "name": "NUM_SPEAKERS", "datatype": "BYTES", "shape": [1, 1], "data": [""] }
         ], "outputs": [{ "name": "DIARIZATION_RESULT" }] } } }
     "classInstance": "SpeakerDiarizationTaskService"
     // No default expected-response shape exists for this task type — Service creation's
     // response-shape check is skipped unless you supply an explicit expectedResponseSchema.

   audio-lang-detection (audio -> language code):
     "task": { "type": "audio-lang-detection" }
     "languages": [{ "sourceLanguage": "hi" }]
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "AUDIO_DATA", "dtype": "BYTES", "shape": [1, 1], "value_path": "audio.audio_content" }
       ], "outputs": [
         { "tensor": "LANGUAGE_CODE", "dtype": "BYTES", "maps_to": "language_code" },
         { "tensor": "CONFIDENCE", "dtype": "FP32", "maps_to": "confidence" },
         { "tensor": "ALL_SCORES", "dtype": "BYTES", "maps_to": "all_scores" }
       ] }
     "schema": { "taskType": "audio-lang-detection", "model_name": "ald",
       "request": { "audio": [{ "audioContent": "<base64-encoded-audio>" }], "config": {} },
       "response": { "triton": { "inputs": [
           { "name": "AUDIO_DATA", "datatype": "BYTES", "shape": [1, 1] }
         ], "outputs": [
           { "name": "LANGUAGE_CODE" }, { "name": "CONFIDENCE" }, { "name": "ALL_SCORES" }
         ] } } }
     "classInstance": "AudioLanguageDetectionTaskService"
     // No default expected-response shape for this task type either — same note as above.

   language-diarization (audio, multiple languages -> per-segment language):
     "task": { "type": "language-diarization" }
     "languages": [{ "sourceLanguage": "hi" }, { "sourceLanguage": "en" }]
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "AUDIO_DATA", "dtype": "BYTES", "shape": [1, 1], "value_path": "audio.audio_content" },
         { "tensor": "LANGUAGE", "dtype": "BYTES", "shape": [1, 1], "value_path": "request.config.target_language" }
       ], "outputs": [{ "tensor": "DIARIZATION_RESULT", "dtype": "BYTES", "maps_to": "diarization_json" }] }
     "schema": { "taskType": "language-diarization", "model_name": "lang_diarization",
       "request": { "audio": [{ "audioContent": "<base64-encoded-audio>" }], "config": {} },
       "response": { "triton": { "inputs": [
           { "name": "AUDIO_DATA", "datatype": "BYTES", "shape": [1, 1] },
           { "name": "LANGUAGE", "datatype": "BYTES", "shape": [1, 1], "data": [""] }
         ], "outputs": [{ "name": "DIARIZATION_RESULT" }] } } }
     "classInstance": "LanguageDiarizationTaskService"
     // No default expected-response shape for this task type either — same note as above.

   ── Notes that apply across every task type above ───────────────────────
   - "schema.taskType" MUST equal "task.type" (or its ULCA-equivalent spelling) exactly —
     model registration rejects a mismatch.
   - If you provide "schema" at all, "model_name"/"taskType"/"request"/"response" must ALL
     be present.
   - If you provide "adapterConfig" at all, "inputs"/"outputs" must both be present.
   - "response.triton" (when present) is what lets a Service created against this model
     probe the real Triton server directly instead of falling back to a generic guess.
`;
