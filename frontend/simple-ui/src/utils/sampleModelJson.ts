/**
 * Sample model registration files offered by the "Download sample" action on the NLP and
 * LLM cards of the Create Model drawer. NLP (ULCA) and LLM (OpenAI) models are defined
 * with different structures, so each kind gets its own sample.
 *
 * Held as raw text rather than object literals so the explanatory comments survive into
 * the downloaded file — `JSON.stringify` would drop them, since they are only source
 * comments once an object is parsed. Users keep the comments while editing; the upload path
 * strips them again via `stripJsonComments` before parsing.
 *
 * Comments in these files are written for someone filling in the form who has no knowledge
 * of how the platform is built internally — plain language, no code/file references, no
 * internal function names.
 */

export type ModelSampleKind = "nlp" | "llm";

export const SAMPLE_NLP_MODEL_JSON = `{
  // Sample registration for an NLP model (translation, speech, OCR, ...), following the
  // ULCA model specification. Comments starting with // are ignored on upload, so you
  // can leave them in. Change "name" or "version" before uploading — the same pair
  // cannot be registered twice.

  "version": "v6",
  // Required. Version for the model, 1–20 characters. Example: "v1", "v2.0"

  "name": "indictrans",
  // Required. Name shown for this model, 5–100 characters.
  // Letters, numbers, hyphens (-) and forward slashes (/) only — no spaces.

  "description": "IndicTrans NMT model supporting multiple Indic languages.",
  // Required. What this model does, 25–1000 characters.

  "task": {
    "type": "nmt"
    // Required. One of: nmt | tts | asr | transliteration | language-detection |
    //   speaker-diarization | audio-lang-detection | language-diarization | ocr | ner
    // Must be the same as "taskType" inside "schema" below.
  },

  "classInstance": "NMTTaskService",
  // Required for NLP models. Tells the platform how to run this model. Use the value
  // that matches "task" -> "type":
  //   nmt                  -> NMTTaskService
  //   asr                  -> ASRTaskService
  //   tts                  -> TTSTaskService
  //   transliteration      -> TransliterationTaskService
  //   language-detection   -> LanguageDetectionTaskService
  //   audio-lang-detection -> AudioLanguageDetectionTaskService
  //   speaker-diarization  -> SpeakerDiarizationTaskService
  //   language-diarization -> LanguageDiarizationTaskService
  //   ocr                  -> OCRTaskService
  //   ner                  -> NERTaskService

  "languages": [
    {
      "sourceLanguage": "en",
      "sourceLanguageName": "English",
      "sourceScriptCode": "Latn",
      "targetLanguage": "hi",
      "targetLanguageName": "Hindi",
      "targetScriptCode": "Deva"
      // Language codes: en | hi | mr | ta | te | kn | gu | pa | bn | ml | as | ...
      // Script codes: Beng | Deva | Thaa | Gujr | Aran | Orya | Guru | Arab |
      //   Sinh | Knda | Mlym | Taml | Telu | Mtei | Olck | Latn
      // For nmt and transliteration, every field in this block is required.
    }
  ],

  "license": "mit",
  // Required. One of: cc-by-4.0 | cc-by-sa-4.0 | cc-by-nd-2.0 | cc-by-nd-4.0 |
  //   cc-by-nc-3.0 | cc-by-nc-4.0 | cc-by-nc-sa-4.0 | cc0 | mit | gpl-3.0 |
  //   bsd-3-clause | private-commercial | unknown-license | custom-license

  "domain": ["general"],
  // Required. One or more of: general | news | education | legal |
  //   government-press-release | healthcare | agriculture | automobile | tourism |
  //   financial | movies | subtitles | sports | technology | lifestyle | entertainment |
  //   parliamentary | art-and-culture | economy | history | philosophy | religion |
  //   national-security-and-defence | literature | geography

  "adapterConfig": {
    // How requests are turned into the model's inputs and how its outputs are read back.
    // "version", at least one "inputs" entry and at least one "outputs" entry are required.
    // Each input needs "tensor", "dtype", "shape" and a "value_path" (where in the request
    // the value comes from). Each output needs "tensor", "dtype" and "maps_to".
    // "tensor" names must match the names the model is served with.
    // For tts, one output must use the tensor "OUTPUT_GENERATED_AUDIO".
    // For ner, the output that maps to "target" must also have "transform": "json_parse".
    "version": "6.0",
    "model_name": "nmt",
    "inputs": [
      {
        "tensor": "INPUT_TEXT",
        "dtype": "BYTES",
        "shape": [-1, 1],
        "value_path": "input.source"
      },
      {
        "tensor": "INPUT_LANGUAGE_ID",
        "dtype": "BYTES",
        "shape": [-1, 1],
        "value_path": "request.config.language.source_language"
      },
      {
        "tensor": "OUTPUT_LANGUAGE_ID",
        "dtype": "BYTES",
        "shape": [-1, 1],
        "value_path": "request.config.language.target_language"
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

  "schema": {
    // A real example request and the response it returned. Used to test the model.
    // "taskType", "model_name", "request" and "response" are all required.
    // "taskType" must be the same as "task" -> "type" above.
    "taskType": "nmt",
    "model_name": "nmt",
    "request": {
      "input": [
        {
          "source": "Hello, how are you?"
        }
      ],
      "config": {
        "language": {
          "sourceLanguage": "en",
          "targetLanguage": "hi"
        }
      }
    },
    "response": {
      // The raw Triton request used to test the model's endpoint.
      // "inputs" must match the tensors in "adapterConfig" above.
      "triton": {
        "inputs": [
          {
            "data": [
              "Hello, how are you?"
            ],
            "name": "INPUT_TEXT",
            "shape": [
              1,
              1
            ],
            "datatype": "BYTES"
          },
          {
            "data": [
              "en"
            ],
            "name": "INPUT_LANGUAGE_ID",
            "shape": [
              1,
              1
            ],
            "datatype": "BYTES"
          },
          {
            "data": [
              "hi"
            ],
            "name": "OUTPUT_LANGUAGE_ID",
            "shape": [
              1,
              1
            ],
            "datatype": "BYTES"
          }
        ],
        "outputs": [
          {
            "name": "OUTPUT_TEXT"
          }
        ]
      }
    }
  },

  "trainingDataset": {
    "description": "Sample training dataset description for the example NMT model registration."
    // Required. The data this model was trained on.
  },

  "submitter": {
    "name": "Example Org"
    // Required. Person or organization submitting the model, 3–50 characters.
  }
}
`;

export const SAMPLE_LLM_MODEL_JSON = `{
  // Sample registration for a chat/LLM model, following the OpenAI specification.
  // Comments starting with // are ignored on upload, so you can leave them in.
  // Change "name" or "version" before uploading — the same pair cannot be registered twice.

  "version": "v1",
  // Required. Version for the model, 1–20 characters. Example: "v1", "v2.0"

  "name": "google/gemma-4-31B-it",
  // Required. Name shown for this model, 5–100 characters.
  // Letters, numbers, hyphens (-) and forward slashes (/) only — no spaces.

  "description": "A sample LLM model for demonstration purposes. Description must be at least 25 characters.",
  // Required. What this model does, 25–1000 characters.

  "task": {
    "type": "llm"
    // Required. Always "llm" for chat/LLM models.
    // Must be the same as "taskType" inside "schema" below.
  },

  "languages": [
    {
      "sourceLanguage": "hi",
      "sourceLanguageName": "Hindi",
      "sourceScriptCode": "Deva",
      "targetLanguage": "en",
      "targetLanguageName": "English",
      "targetScriptCode": "Latn"
      // Language codes: en | hi | mr | ta | te | kn | gu | pa | bn | ml | as | ...
      // Script codes: Beng | Deva | Thaa | Gujr | Aran | Orya | Guru | Arab |
      //   Sinh | Knda | Mlym | Taml | Telu | Mtei | Olck | Latn
    }
  ],

  "license": "mit",
  // Required. One of: cc-by-4.0 | cc-by-sa-4.0 | cc-by-nd-2.0 | cc-by-nd-4.0 |
  //   cc-by-nc-3.0 | cc-by-nc-4.0 | cc-by-nc-sa-4.0 | cc0 | mit | gpl-3.0 |
  //   bsd-3-clause | private-commercial | unknown-license | custom-license

  "domain": ["general"],
  // Required. One or more of: general | news | education | legal |
  //   government-press-release | healthcare | agriculture | automobile | tourism |
  //   financial | movies | subtitles | sports | technology | lifestyle | entertainment |
  //   parliamentary | art-and-culture | economy | history | philosophy | religion |
  //   national-security-and-defence | literature | geography

  "adapterConfig": {
    // How requests are built for the model. "version", at least one "inputs" entry and
    // at least one "outputs" entry are required.
    // For chat/LLM models, "model_name" is required and must exactly match the model name
    // the AI server knows. The "inputs"/"outputs" below are the standard placeholders for
    // chat/LLM models — keep them as they are.
    "version": "1.0",
    "model_name": "google/gemma-4-31B-it",
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

  "schema": {
    // A real example request and the response it returned. Used to test the model.
    // "taskType", "model_name", "request" and "response" are all required.
    // "taskType" must be the same as "task" -> "type" above.
    "taskType": "llm",
    "model_name": "google/gemma-4-31B-it",
    "request": {
      "messages": [
        {
          "role": "user",
          "content": "Say hello in one line"
        }
      ],
      "max_tokens": 256
    },
    "response": {
      "id": "chatcmpl-ac15bfd6d66df036",
      "object": "chat.completion",
      "created": 1789465507,
      "model": "google/gemma-4-31B-it",
      "choices": [
        {
          "index": 0,
          "message": {
            "role": "assistant",
            "content": "Hello!",
            "refusal": null,
            "annotations": null,
            "audio": null,
            "function_call": null,
            "reasoning": null
          },
          "logprobs": null,
          "finish_reason": "stop",
          "stop_reason": 106,
          "token_ids": null,
          "routed_experts": null
        }
      ],
      "service_tier": null,
      "system_fingerprint": "vllm-0.27.1-133468d7",
      "usage": {
        "prompt_tokens": 18,
        "total_tokens": 21,
        "completion_tokens": 3,
        "prompt_tokens_details": null
      },
      "prompt_logprobs": null,
      "prompt_token_ids": null,
      "prompt_text": null,
      "kv_transfer_params": null,
      "ec_transfer_params": null,
      "metrics": null
    }
  },

  "trainingDataset": {
    "description": "Sample training dataset description for the example LLM model registration."
    // Required. The data this model was trained on.
  },

  "submitter": {
    "name": "Example Org"
    // Required. Person or organization submitting the model, 3–50 characters.
  }
}
`;

/** Download payload per model kind, keyed by the card the admin downloads it from. */
export const MODEL_SAMPLES: Record<ModelSampleKind, { json: string; fileName: string }> = {
  nlp: { json: SAMPLE_NLP_MODEL_JSON, fileName: "sample-nlp-model.json" },
  llm: { json: SAMPLE_LLM_MODEL_JSON, fileName: "sample-llm-model.json" },
};
