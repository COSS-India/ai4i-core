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
 * internal class or function names. Only the exact values that must be copied verbatim
 * (e.g. a classInstance name) are technical-looking, and each of those is explained in
 * plain terms next to it.
 */
export const SAMPLE_MODEL_JSON = `{
  // ═══════════════════════════════════════════════════════════════════════
  // HOW TO USE THIS FILE
  // ═══════════════════════════════════════════════════════════════════════
  // This is a filled-in example for one kind of model (a chat/LLM model). If you're
  // registering a different kind of model — a translator, a speech-to-text model, a
  // text-to-speech model, and so on — scroll to the very bottom of this file. There's a
  // "PICK YOUR MODEL TYPE" section with a ready-to-copy block for every other kind of
  // model. Copy that block over the "task", "languages", "adapterConfig", and "schema"
  // sections below, and leave everything else in this file as it is.
  //
  // Fields marked "Required" must be filled in or the platform will refuse to save the
  // model. Fields marked "Optional" can be left out entirely (just delete the line).

  // ── Basic details ───────────────────────────────────────────────────────

  "version": "v1",
  // Required. A short label for this version of the model, 1–20 characters.
  // Example: "v1", "v2.0"

  "name": "test-llm-2",
  // Required. The name people will see for this model, 5–100 characters.
  // Letters, numbers, hyphens (-), and forward slashes (/) only — no spaces.
  // Example: "org/model-name"

  "description": "A sample LLM model for demonstration purposes. Description must be at least 25 characters.",
  // Required. A short explanation of what this model does, 25–1000 characters.

  "refUrl": "https://github.com/example/example-model",
  // Optional. A link with more information about the model, 5–200 characters.

  // ── What kind of model is this? ────────────────────────────────────────

  "task": {
    "type": "llm"
    // Required. What this model actually does.
    // Choose one of: nmt | tts | asr | llm | transliteration |
    //   language-detection | speaker-diarization | audio-lang-detection |
    //   language-diarization | ocr | ner | pipeline
    // (nmt = translation, tts = text-to-speech, asr = speech-to-text,
    //  llm = chat/AI assistant, ocr = read text from an image)
    // Capitalization doesn't matter here.
    //
    // IMPORTANT: this value and the "taskType" value inside "schema" further down MUST be
    // the same thing. If they don't match, the platform will refuse to save the model.
  },

  // ── Languages this model supports ──────────────────────────────────────

  "languages": [
    {
      "sourceLanguage": "hi",
      // Required. The language code the model reads or listens to.
      // Common values: en | hi | mr | ta | te | kn | gu | pa | bn | ml | as
      //   (plus other supported Indian language codes)

      "sourceLanguageName": "Hindi",
      // The plain-language name of that language, e.g. "Hindi".
      // For translation-style models (nmt, transliteration, llm with a language pair),
      // this and every field below it in this block are REQUIRED once you include a
      // "languages" entry at all. For models that only work with a single language
      // (speech-to-text, text-to-speech, read-text-from-image, etc.), these can be left
      // out. For a chat/AI model like this one, if you don't need to declare a language
      // pair, you can remove the whole "languages" section instead.

      "sourceScriptCode": "Deva",
      // The writing system the source language uses (only needed for translation-style
      // models — see note above).
      // Choose one of: Beng | Deva | Thaa | Gujr | Aran | Orya | Guru | Arab |
      //   Sinh | Knda | Mlym | Taml | Telu | Mtei | Olck | Latn

      "targetLanguage": "en",
      // The language the model translates INTO. Leave this whole section's "target..."
      // fields out for a model that only reads/listens (it doesn't translate to anything).
      // Same list of codes as "sourceLanguage".

      "targetLanguageName": "English",
      // The plain-language name of the target language.

      "targetScriptCode": "Latn"
      // The writing system of the target language. Same list as "sourceScriptCode".
    }
  ],

  "isLangDetectionEnabled": false,
  // Optional. Default: false.
  // Set to true if this model can automatically figure out what language it's looking at,
  // without being told in advance.

  "isMultilingual": false,
  // Optional. Default: false.
  // Set to true if this one model can handle several languages by itself.

  // ── License ─────────────────────────────────────────────────────────────

  "license": "mit",
  // Required. The license this model is published under.
  // Choose one of (capitalization doesn't matter):
  //   cc-by-4.0 | cc-by-sa-4.0 | cc-by-nd-2.0 | cc-by-nd-4.0 |
  //   cc-by-nc-3.0 | cc-by-nc-4.0 | cc-by-nc-sa-4.0 | cc0 | mit |
  //   gpl-3.0 | bsd-3-clause | private-commercial | unknown-license | custom-license

  "licenseUrl": "https://opensource.org/licenses/MIT",
  // Optional. A link to the full license text, up to 500 characters.
  // Good to include if you chose "custom-license" above.

  // ── Subject area ────────────────────────────────────────────────────────

  "domain": ["general"],
  // Required. Pick at least one area this model is relevant to.
  // Choose one or more of:
  //   general | news | education | legal | government-press-release |
  //   healthcare | agriculture | automobile | tourism | financial |
  //   movies | subtitles | sports | technology | lifestyle | entertainment |
  //   parliamentary | art-and-culture | economy | history | philosophy |
  //   religion | national-security-and-defence | literature | geography

  // ── Where the model actually runs ──────────────────────────────────────

  "callbackUrl": "https://inference.example.com",
  // Optional, but the model can't actually be used for anything without it eventually
  // being set (here or later, when someone connects this model to a live service). This
  // is the web address requests get sent to.
  //
  // For a chat/AI model (task "llm"): give just the base address, like
  // "https://inference.example.com" — do NOT add anything like "/v1/chat/completions"
  // after it. That part gets added automatically behind the scenes; adding it yourself
  // would make requests fail.
  //
  // For every other kind of model: this is usually the model's complete address,
  // including its specific path, e.g.
  // "https://inference.example.com/v2/models/example-model/infer".

  "inferenceApiKey": {
    "name": "Authorization",
    // Optional. The name of the security header the address above expects an API key
    // under. If you don't set this, "Authorization" is used automatically.
    // Example: "apiKey"

    "value": "<your-api-key>"
    // Required if you're including this section at all.
    // The actual API key / secret token that gets sent with each request.
  },

  "isSyncApi": true,
  // Optional. True/false.
  // Set to true if a request to this model gets an answer back immediately.
  // Set to false if it's a "come back later and check" kind of model — and if you do
  // set it to false, you must also fill in "asyncApiDetails" below (see next field).

  "asyncApiDetails": null,
  // Required if "isSyncApi" above is false — otherwise leave it as null or remove it.
  // Replace null with:
  // {
  //   "pollingUrl":   "https://...",  // Required. Where to check for the result.
  //   "pollInterval": 1000            // Required. How often to check, in milliseconds.
  // }

  // ── Advanced: how requests get built for this model ────────────────────

  "adapterConfig": {
    // Optional overall — but if you include this section at all, "version" plus at least
    // one entry in "inputs" and one entry in "outputs" are all required, or the platform
    // will refuse to save the model.
    //
    // What this section is for: most models expect their input in a very specific
    // technical format. This section tells the platform exactly how to build that format
    // from a normal request, and how to read the model's raw answer back into a normal
    // response. You won't need this at all for many simpler models — it matters most for
    // models connected through the platform's own inference engine.
    //
    // Each entry under "inputs" needs:
    //   "tensor"     — the exact input name the model expects (ask whoever built/deployed
    //                  the model if you're not sure).
    //   "dtype"      — the data type of that input (common ones: BYTES for text, FP32 for
    //                  numbers with decimals, INT32 for whole numbers, BOOL for true/false).
    //   "shape"      — the size/dimensions of that input; [-1, 1] is a safe default for a
    //                  single text value.
    //   "value_path" — where to pull that value from in the request being sent. See the
    //                  "PICK YOUR MODEL TYPE" section at the bottom for the exact paths
    //                  each model type expects — using the wrong one means the model
    //                  simply won't receive the value it needs.
    //
    // Each entry under "outputs" needs:
    //   "tensor"   — the exact output name the model returns.
    //   "dtype"    — same as above.
    //   "maps_to"  — the name this value should be given in the response sent back to
    //                whoever called the model.
    //
    // FOR CHAT/AI MODELS (task "llm") ONLY: "model_name" below is required — it's the
    // real, exact model name the AI server itself expects to see. This is NOT the same as
    // the "name" field near the top of this file (that one is just this model's label on
    // the platform) — "model_name" here must match the original model's own name exactly,
    // as the AI server that hosts it knows it. Leaving it out, or getting it wrong, means
    // requests get sent with the wrong model name and are rejected by the AI server, even
    // though this model saved successfully. "inputs"/"outputs" aren't actually used for
    // chat/AI models, but the platform still requires at least one placeholder entry in
    // each — the ones below are the standard placeholder every chat/AI model on this
    // platform uses.
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

  // ── Advanced: an example request and response for this model ──────────

  "schema": {
    // Optional overall — but if you include this section at all, "model_name",
    // "taskType", "request", and "response" must ALL be present, or the platform will
    // refuse to save the model. This is a real, working example of a request you'd send
    // this model and the answer you'd get back — it's used later to test that the model
    // actually works before anyone can use it for real.
    //
    // "taskType" MUST be the same value as "task" -> "type" further up this file.
    //
    // "model_name" here is just an identifying label — for a chat/AI model any short
    // name works; for other model types, it usually matches your model's real name.
    //
    // For chat/AI models (task "llm"), "request" and "response" look exactly like a
    // normal AI chat message and reply, as shown below.
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
  // Optional according to the platform, but genuinely important — please don't skip
  // this for anything except a chat/AI model.
  //
  // What this does: behind the scenes, the platform needs to know which internal
  // component should actually handle requests for this model. If this is left blank (or
  // set to the wrong value) for anything except a chat/AI model, the model will save
  // successfully and even look fine — but every single real request to it will fail.
  // This is easy to miss because nothing warns you about it until someone actually tries
  // to use the model.
  //
  // For a chat/AI model (task "llm", like this example), leave this as null — it isn't
  // needed. For every other kind of model, scroll to the "PICK YOUR MODEL TYPE" section
  // at the bottom of this file and copy the exact value shown there for your model type
  // (e.g. "ASRTaskService" for a speech-to-text model). These are fixed labels — copy
  // them exactly as written, don't make up your own.

  // ── About the training data ─────────────────────────────────────────────

  "trainingDataset": {
    "description": "Sample training dataset description for the example LLM model registration.",
    // Required. A short explanation of the data this model was trained on.

    "datasetId": "example-LLM-corpus-v1"
    // Optional. A reference ID for the dataset, if it's already registered on the
    // platform elsewhere. Including this adds more detail to the model's profile.
  },

  // ── Benchmark results (optional) ───────────────────────────────────────

  "benchmarks": [
    {
      "benchmarkId": "example-benchmark-001",
      "name": "Example Benchmark",
      "description": "Sample benchmark for evaluation",
      "domain": "general",
      "createdOn": "2025-01-15T10:00:00.000Z", // Date and time, in this exact format.
      "languages": {
        "sourceLanguage": "hi",
        "targetLanguage": "en"
      },
      "score": [
        {
          "metricName": "WER", // The name of the measurement, e.g. WER, BLEU, CER.
          "score": "7.5"       // The score, written as text (in quotes).
        }
      ]
    }
  ],
  // Optional. Leave as an empty list [] or remove entirely if you have no benchmark
  // results to share yet.

  // ── Who's submitting this model ────────────────────────────────────────

  "submitter": {
    "name": "Example Org",
    // Required. The name of the person or organization submitting this model,
    // 3–50 characters.

    "aboutMe": "An example organization",
    // Optional. A short description of the submitter.

    "team": [
      {
        "name": "John Doe",
        // Required if you include a team member at all. Their name, 5–50 characters.

        "aboutMe": "Lead Researcher",
        // Optional. A short bio for this person.

        "oauthId": {
          "oauthId": "1234567890",
          // Optional. Leave this whole "oauthId" section out unless you know you need it.

          "provider": "google"
          // Optional. Choose one of: custom | github | facebook | instagram | google | yahoo
        }
      }
    ]
    // Optional. Leave as an empty list [] or remove entirely if there's no team to list.
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   PICK YOUR MODEL TYPE
   ═══════════════════════════════════════════════════════════════════════════
   Everything above this line is one complete example for a chat/AI model. A model can
   only be ONE type at a time, so if you're registering a different kind of model, find
   it in the list below and copy that whole block over the "task", "languages",
   "adapterConfig", and "schema" sections above (leave everything else — name,
   description, license, submitter, and so on — as it already is).

   Each block below is taken from a real model already working successfully on this
   platform, so it shows the exact shape (task type + the matching taskType inside
   "schema" + the matching classInstance) your own model of that type needs to actually
   work once someone starts using it, not just save successfully. The block itself won't
   make YOUR model work as-is, though — it describes that other, specific model. Copy the
   block for reference and then replace its values (model_name, callbackUrl, tensor
   value_paths where relevant, and so on) with the real details of your own model.

   Note: in several blocks below, "schema" -> "model_name" happens to be spelled exactly
   like the task type (e.g. "nmt", "tts", "ner") — that's just because those particular
   real models were named that way on the server that hosts them, not a rule to follow.
   Set "model_name" to whatever your own model is actually called there instead.

   ── TEXT-BASED MODELS ────────────────────────────────────────────────────

   Translation (source language -> target language):
     "task": { "type": "nmt" }
     "languages": [{ "sourceLanguage": "en", "sourceLanguageName": "English",
       "sourceScriptCode": "Latn", "targetLanguage": "hi",
       "targetLanguageName": "Hindi", "targetScriptCode": "Deva" }]
       // All the fields shown above are required for a translation model.
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

   Transliteration (rewrite words in a different script, e.g. Hindi written in English
   letters):
     "task": { "type": "transliteration" }
     "languages": [{ "sourceLanguage": "hi", "sourceLanguageName": "Hindi",
       "sourceScriptCode": "Deva", "targetLanguage": "en",
       "targetLanguageName": "English", "targetScriptCode": "Latn" }]
       // All the fields shown above are required for this model type.
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

   Language detection (figure out what language a piece of text is written in):
     "task": { "type": "language-detection" }
     "languages": [{ "sourceLanguage": "hi" }]   // Only this one field is needed here.
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source" }
       ], "outputs": [{ "tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "langPrediction" }] }
     "schema": { "taskType": "language-detection", "model_name": "indiclid",
       "request": { "input": [{ "source": "नमस्ते, यह एक उदाहरण वाक्य है।" }], "config": {} },
       "response": { "triton": { "inputs": [
           { "name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1, 1], "data": ["नमस्ते, यह एक उदाहरण वाक्य है।"] }
         ], "outputs": [{ "name": "OUTPUT_TEXT" }] } } }
     "classInstance": "LanguageDetectionTaskService"

   Read text from an image (OCR):
     "task": { "type": "ocr" }
     "languages": [{ "sourceLanguage": "hi" }]
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "IMAGE_DATA", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.image_content" }
       ], "outputs": [{ "tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "text" }] }
     "schema": { "taskType": "ocr", "model_name": "surya_ocr",
       "request": { "image": [{ "imageContent": "<the image, as base64-encoded text>" }],
         "config": { "language": { "sourceLanguage": "hi" } } },
       "response": { "triton": { "inputs": [
           { "name": "IMAGE_DATA", "datatype": "BYTES", "shape": [1, 1] }
         ], "outputs": [{ "name": "OUTPUT_TEXT" }] } } }
     "classInstance": "OCRTaskService"

   Named entity recognition (pick out names of people, places, organizations, etc. from
   text):
     "task": { "type": "ner" }
     "languages": [{ "sourceLanguage": "hi" }]
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source" },
         { "tensor": "LANG_ID", "dtype": "BYTES", "shape": [-1, 1], "value_path": "request.config.language.sourceLanguage" }
       ], "outputs": [{ "tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "target", "transform": "json_parse" }] }
       // The "transform": "json_parse" part shown above is required specifically for
       // this model type — without it, every real request to this model will fail, even
       // though the model itself saves and looks completely fine.
     "schema": { "taskType": "ner", "model_name": "ner",
       "request": { "input": [{ "source": "राम दिल्ली गए।" }],
         "config": { "language": { "sourceLanguage": "hi" } } },
       "response": { "triton": { "inputs": [
           { "name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1, 1], "data": ["राम दिल्ली गए।"] },
           { "name": "LANG_ID", "datatype": "BYTES", "shape": [1, 1], "data": ["hi"] }
         ], "outputs": [{ "name": "OUTPUT_TEXT" }] } } }
     "classInstance": "NERTaskService"

   ── AUDIO-BASED MODELS ───────────────────────────────────────────────────
   For these, the audio itself is sent as base64-encoded text (a long string of letters
   and numbers representing the sound file), inside "audioContent".

   Speech-to-text (turn spoken audio into written text):
     // Note: this is the one audio model type below where the request paths are
     // "audio.samples" / "audio.num_samples" instead of "audio.audio_content" — every
     // other audio model type below uses "audio.audio_content". Using the wrong one for
     // your model type means the model receives nothing useful and every real request
     // fails, so double check you're copying the right block for what you're building.
     "task": { "type": "asr" }
     "languages": [{ "sourceLanguage": "hi" }]
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "AUDIO_SIGNAL", "dtype": "FP32", "shape": [-1, -1], "value_path": "audio.samples" },
         { "tensor": "NUM_SAMPLES", "dtype": "INT32", "shape": [-1, 1], "value_path": "audio.num_samples" },
         { "tensor": "LANG_ID", "dtype": "BYTES", "shape": [-1, 1], "value_path": "request.config.language.source_language" }
       ], "outputs": [{ "tensor": "TRANSCRIPTS", "dtype": "BYTES", "maps_to": "transcript" }] }
     "schema": { "taskType": "asr", "model_name": "asr_am_ensemble",
       "request": { "audio": [{ "audioContent": "<the audio, as base64-encoded text>" }],
         "config": { "language": { "sourceLanguage": "hi" } } },
       "response": { "triton": { "inputs": [
           { "name": "AUDIO_SIGNAL", "datatype": "FP32", "shape": [1, 4000], "data": [0.0] },
           { "name": "NUM_SAMPLES", "datatype": "INT32", "shape": [1, 1], "data": [4000] },
           { "name": "LANG_ID", "datatype": "BYTES", "shape": [1, 1], "data": ["hi"] }
         ], "outputs": [{ "name": "TRANSCRIPTS" }] } } }
     "classInstance": "ASRTaskService"

   Text-to-speech (turn written text into spoken audio):
     "task": { "type": "tts" }
     "languages": [{ "sourceLanguage": "hi" }]
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [1], "value_path": "input.source" },
         { "tensor": "INPUT_SPEAKER_ID", "dtype": "BYTES", "shape": [1], "value_path": "input.gender" },
         { "tensor": "INPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [1], "value_path": "input.language_id" }
       ], "outputs": [{ "tensor": "OUTPUT_GENERATED_AUDIO", "dtype": "FP32", "maps_to": "audio_data" }] }
       // The output name "OUTPUT_GENERATED_AUDIO" shown above must be typed exactly like
       // that — it's a fixed label the platform looks for by that exact name for this
       // model type. Any other spelling means every real request to this model fails.
     "schema": { "taskType": "tts", "model_name": "tts",
       "request": { "input": [{ "source": "नमस्ते" }],
         "config": { "language": { "sourceLanguage": "hi" }, "gender": "female" } },
       "response": { "triton": { "inputs": [
           { "name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1], "data": ["namaste"] },
           { "name": "INPUT_SPEAKER_ID", "datatype": "BYTES", "shape": [1], "data": ["female"] },
           { "name": "INPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1], "data": ["hi"] }
         ], "outputs": [{ "name": "OUTPUT_GENERATED_AUDIO" }] } } }
     "classInstance": "TTSTaskService"

   Speaker diarization (work out who spoke when, in an audio recording with multiple
   people):
     "task": { "type": "speaker-diarization" }
     "languages": [{ "sourceLanguage": "mixed" }]   // Use "mixed" for a model that isn't
       // tied to one specific language.
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "AUDIO_DATA", "dtype": "BYTES", "shape": [1, 1], "value_path": "audio.audio_content" },
         { "tensor": "NUM_SPEAKERS", "dtype": "BYTES", "shape": [1, 1], "value_path": "request.config.num_speakers" }
       ], "outputs": [{ "tensor": "DIARIZATION_RESULT", "dtype": "BYTES", "maps_to": "diarization_json" }] }
     "schema": { "taskType": "speaker-diarization", "model_name": "speaker_diarization",
       "request": { "audio": [{ "audioContent": "<the audio, as base64-encoded text>" }], "config": {} },
       "response": { "triton": { "inputs": [
           { "name": "AUDIO_DATA", "datatype": "BYTES", "shape": [1, 1] },
           { "name": "NUM_SPEAKERS", "datatype": "BYTES", "shape": [1, 1], "data": [""] }
         ], "outputs": [{ "name": "DIARIZATION_RESULT" }] } } }
     "classInstance": "SpeakerDiarizationTaskService"

   Audio language detection (figure out what language is being spoken in an audio clip):
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
       "request": { "audio": [{ "audioContent": "<the audio, as base64-encoded text>" }], "config": {} },
       "response": { "triton": { "inputs": [
           { "name": "AUDIO_DATA", "datatype": "BYTES", "shape": [1, 1] }
         ], "outputs": [
           { "name": "LANGUAGE_CODE" }, { "name": "CONFIDENCE" }, { "name": "ALL_SCORES" }
         ] } } }
     "classInstance": "AudioLanguageDetectionTaskService"

   Language diarization (figure out which language is being spoken at each point in an
   audio clip that switches between languages):
     "task": { "type": "language-diarization" }
     "languages": [{ "sourceLanguage": "hi" }, { "sourceLanguage": "en" }]
     "adapterConfig": { "version": "1.0", "inputs": [
         { "tensor": "AUDIO_DATA", "dtype": "BYTES", "shape": [1, 1], "value_path": "audio.audio_content" },
         { "tensor": "LANGUAGE", "dtype": "BYTES", "shape": [1, 1], "value_path": "request.config.target_language" }
       ], "outputs": [{ "tensor": "DIARIZATION_RESULT", "dtype": "BYTES", "maps_to": "diarization_json" }] }
     "schema": { "taskType": "language-diarization", "model_name": "lang_diarization",
       "request": { "audio": [{ "audioContent": "<the audio, as base64-encoded text>" }], "config": {} },
       "response": { "triton": { "inputs": [
           { "name": "AUDIO_DATA", "datatype": "BYTES", "shape": [1, 1] },
           { "name": "LANGUAGE", "datatype": "BYTES", "shape": [1, 1], "data": [""] }
         ], "outputs": [{ "name": "DIARIZATION_RESULT" }] } } }
     "classInstance": "LanguageDiarizationTaskService"

   ── Quick checklist before you save ─────────────────────────────────────
   - "task" -> "type" and "schema" -> "taskType" must say the same thing.
   - If you're using "schema" at all, it needs "model_name", "taskType", "request", AND
     "response" — all four, or the platform will refuse to save the model.
   - If you're using "adapterConfig" at all, it needs "version" and at least one entry in
     both "inputs" and "outputs".
   - Set "classInstance" for every model type EXCEPT chat/AI models — see the note next
     to that field further up.
   ═══════════════════════════════════════════════════════════════════════════ */
`;
