/**
 * Sample model registration file offered by the "Download Sample JSON" action.
 *
 * Held as raw text rather than an object literal so the explanatory comments survive into
 * the downloaded file — `JSON.stringify` would drop them, since they are only source
 * comments once an object is parsed. Users keep the comments while editing; the upload path
 * strips them again via `stripJsonComments` before parsing.
 *
 * Comments in this file are written for someone filling in the form who has no knowledge of
 * how the platform is built internally — plain language, no code/file references, no
 * internal class or function names.
 */
export const SAMPLE_MODEL_JSON = `{
  // Sample registration for a chat/LLM model. Comments starting with // are ignored
  // on upload, so you can leave them in.

  "version": "v1",
  // Required. Version for the model, 1–20 characters. Example: "v1", "v2.0"

  "name": "google/gemma-4-31B-it",
  // Required. Name shown for this model, 5–100 characters.
  // Letters, numbers, hyphens (-) and forward slashes (/) only — no spaces.

  "description": "A sample LLM model for demonstration purposes. Description must be at least 25 characters.",
  // Required. What this model does, 25–1000 characters.

  "task": {
    "type": "llm"
    // Required. One of: nmt | tts | asr | llm | transliteration | language-detection |
    //   speaker-diarization | audio-lang-detection | language-diarization | ocr | ner | pipeline
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
