/**
 * Sample model registration file offered by the "Download Sample JSON" action.
 *
 * Held as raw text rather than an object literal so the explanatory comments survive into
 * the downloaded file — `JSON.stringify` would drop them, since they are only source
 * comments once an object is parsed. Users keep the comments while editing; the upload path
 * strips them again via `stripJsonComments` before parsing.
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
    //   language-diarization | ocr | ner
    // Case-insensitive on input.
  },

  // ── Language support ───────────────────────────────────────────────────────

  "languages": [
    {
      "sourceLanguage": "hi",
      // Required. Indic language code (ISO-639-1/2), or 'en'.
      // Accepted values: en | hi | mr | ta | te | kn | gu | pa | bn | ml | as
      //   and other ULCA-supported Indic codes.

      "sourceLanguageName": "Hindi",
      // Optional. Human-readable name for the source language.

      "sourceScriptCode": "Deva",
      // Optional (required for nmt / transliteration tasks). ISO-15924 script code.
      // Enum — one of: Beng | Deva | Thaa | Gujr | Aran | Orya | Guru | Arab |
      //   Sinh | Knda | Mlym | Taml | Telu | Mtei | Olck | Latn

      "targetLanguage": "en",
      // Optional. Omit or set null for single-language models (ASR, TTS, OCR).
      // Same values as sourceLanguage.

      "targetLanguageName": "English",
      // Optional. Human-readable name for the target language.

      "targetScriptCode": "Latn"
      // Optional (required for nmt / transliteration tasks). Same enum as sourceScriptCode.
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

  "callbackUrl": "https://inference.example.com/v2/models/example-model/infer",
  // Required for inference. Full HTTP(S) URL where inference requests are POSTed.
  // This is the hosted location that defines the endpoint of the model inference.

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
  // When false, fill in asyncApiDetails below.

  "asyncApiDetails": null,
  // Optional. Required when isSyncApi is false. Replace null with:
  // {
  //   "pollingUrl":   "https://...",  // Required. Endpoint for polling in async calls.
  //   "pollInterval": 1000            // Required. Polling interval in milliseconds.
  // }

  // ── Adapter config (platform-specific Triton mapping) ──────────────────────

  "adapterConfig": {
    // Optional. Platform-specific Triton I/O tensor mapping.
    // When provided, must include both "inputs" and "outputs".
    "version": "1.0",
    "model_name": "example-model",
    "inputs": [
      {
        "tensor": "INPUT_TEXT",      // Triton input tensor name.
        "dtype": "BYTES",            // Tensor data type.
        "shape": [-1, 1],            // Tensor shape; -1 denotes dynamic batch size.
        "value_path": "input.source" // Dot-path into the ULCA request body to read from.
      }
    ],
    "outputs": [
      {
        "tensor": "OUTPUT_TEXT",     // Triton output tensor name.
        "dtype": "BYTES",
        "maps_to": "target"          // Key in the ULCA response output object to write to.
      }
    ]
  },

  // ── Schema ─────────────────────────────────────────────────────────────────

  "schema": {
    // Required whenever "schema" is provided at all: "model_name",
    // "taskType", "request", and "response" must ALL be present, or
    // model registration is rejected. A Service later created against
    // this model derives its own inferenceEndPoint.schema from these
    // same four keys — an incomplete schema here can't be filled in
    // afterward.
    // taskType — discriminator: translation | transliteration | asr | tts |
    //   ocr | txt-lang-detection | ner | llm
    // "model_name" — used to construct the Triton URL.
    "taskType": "llm",
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
    },
    "model_name": "example-model",
    "modelProcessingType": null
  },

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
`;
