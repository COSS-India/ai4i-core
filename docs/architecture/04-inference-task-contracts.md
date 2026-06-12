# Inference task-type contracts

Purpose: pin the standard request and response JSON for each inference task type. These
are the formats that flow into and out of `run_inference`, independent of which model
serves the request. They are the target the config mapper maps to and from: task-type
input to model/Triton input, and model/Triton output to task-type output.

This document is the reference for AI4IDS-1981 (config-driven JSON transformation via
JSONata). The mapper's job is "model output to the task-type output below"; every model
of a task type, present or future, must map to the same contract. Per-model differences
live in `adapter_config`, not here.

Scope: the 11 task types in `SUPPORTED_TASK_TYPES` (`models/common.py`). LLM chat
(`/chat`, `/chat/completions`, `/audio/*`) is a separate OpenAI-compatible passthrough and
is not covered here.

## Conventions

- A request is the unified envelope: a `task_type`, a model selector (`serviceId` top
  level or `config.serviceId`), one modality array (`input`, `audio`, or `image`), and a
  `config` block. Per-task convenience routes default the `task_type`.
- camelCase and snake_case are both accepted on the way in (the mapper resolves either).
  Responses are shown in the casing the service currently emits.
- "Standard output" is the canonical task-type response. Where the current `adapter_config`
  in the DB diverges from the standard, it is called out under Notes. Closing those gaps
  is part of the AI4IDS-1981 migration.

---

## NMT (text translation)

**Input**
```json
{
  "serviceId": "<id>",
  "input": [{ "source": "hello world" }],
  "config": { "language": { "sourceLanguage": "en", "targetLanguage": "hi" } }
}
```
**Output**
```json
{ "output": [{ "source": "hello world", "target": "<translation>" }] }
```
Notes: the `/nmt/inference` route excludes `config` from the response. One output item per
input item.

---

## NER (named entity recognition)

**Input**
```json
{
  "serviceId": "<id>",
  "input": [{ "source": "John lives in New York" }],
  "config": { "language": { "sourceLanguage": "en" } }
}
```
**Output**
```json
{
  "taskType": "ner",
  "output": [{
    "source": "John lives in New York",
    "nerPrediction": [
      { "token": "John", "tag": "PER", "tokenIndex": 0, "tokenStartIndex": 0, "tokenEndIndex": 4 }
    ]
  }],
  "config": null
}
```
Notes: the model returns a JSON prediction blob (adapter `transform: json_parse`); the
BPE-subword-to-word alignment that produces `nerPrediction` is a service-side algorithm,
not a JSON transformation, and stays in code.

---

## Transliteration

**Input**
```json
{
  "serviceId": "<id>",
  "input": [{ "source": "namaste" }],
  "config": {
    "language": { "sourceLanguage": "hi", "targetLanguage": "en" },
    "numSuggestions": 0,
    "isSentence": false
  }
}
```
**Output**
```json
{ "output": [{ "source": "namaste", "target": "<transliteration>" }] }
```
Notes: `config` excluded from the response (`response.include_config: false`). Top-k
suggestions arrive as extra output items and pair with `""` once inputs run out.
`numSuggestions` and `isSentence` drive derived tensors (`is_word_level`, `top_k`);
`numSuggestions > 0` with `isSentence: true` is rejected.

---

## Language Detection (text)

**Input**
```json
{
  "serviceId": "<id>",
  "input": [{ "source": "hello world" }],
  "config": {}
}
```
**Output**
```json
{ "output": [{ "source": "hello world", "langPrediction": [ { "<model prediction>": "..." } ] }] }
```
Notes: language is detected, not supplied (any `config.language` is ignored). The
prediction string is parsed and wrapped (`transform: [json_parse, wrap_list]`) and paired
with the input source. `config` excluded (`include_config: false`).

---

## ASR (speech to text)

**Input**
```json
{
  "serviceId": "<id>",
  "audio": [{ "audioContent": "<base64>", "audioFormat": "wav" }],
  "config": { "language": { "sourceLanguage": "en" } }
}
```
`audioUri` may replace `audioContent`. `sourceLanguage` is required.

**Standard output (ULCA)**
```json
{ "output": [{ "source": "<transcript>", "nBestTokens": null }], "config": { "language": { "sourceLanguage": "en" } } }
```
Notes: the standard ULCA ASR contract is `output[].source = transcript` plus a constant
`nBestTokens: null`. The current DB `adapter_config` has no response shaping, so it
currently emits `{ "output": [{ "transcript": "...", "source": "" }], "config": {...} }`.
Aligning the config to the standard above is part of the AI4IDS-1981 migration. Audio
preprocessing (decode, mono, resample to 16 kHz, equalize) is service-side DSP and stays
in code.

---

## TTS (text to speech)

**Input**
```json
{
  "serviceId": "<id>",
  "input": [{ "source": "यह एक परीक्षण है", "audioDuration": null }],
  "config": {
    "language": { "sourceLanguage": "hi" },
    "gender": "female",
    "samplingRate": 22050,
    "audioFormat": "mp3"
  }
}
```
**Output**
```json
{
  "audio": [{ "audioContent": "<base64>", "audioUri": null, "audioDuration": 1.23 }],
  "config": {
    "language": { "sourceLanguage": "hi", "sourceScriptCode": null },
    "audioFormat": "mp3",
    "encoding": "base64",
    "samplingRate": 22050,
    "audioDuration": 1.23
  }
}
```
Notes: text chunking and waveform DSP (FP32 to int16, resample, encode) are service-side
and stay in code; only the tensor extraction is mapper territory. The scalar
`config.audioDuration` is accurate for single-item requests; multi-item callers read
`audio[i].audioDuration`.

---

## Audio Language Detection

**Input**
```json
{
  "serviceId": "<id>",
  "audio": [{ "audioContent": "<base64>", "audioFormat": "wav" }],
  "config": {}
}
```
**Output**
```json
{
  "taskType": "audio-lang-detection",
  "output": [{ "language_code": "en", "confidence": 0.98, "all_scores": { "en": 0.98, "hi": 0.01 } }],
  "config": { "serviceId": "<id>" }
}
```
Notes: `all_scores` is parsed from a JSON blob (`transform: json_parse`). Fully
config-driven; no service code.

---

## Speaker Diarization

**Input**
```json
{
  "serviceId": "<id>",
  "audio": [{ "audioContent": "<base64>", "audioFormat": "wav" }],
  "config": { "numSpeakers": "2" }
}
```
`numSpeakers` is optional (`""` = auto).

**Output**
```json
{
  "taskType": "speaker-diarization",
  "output": [{
    "total_segments": 2,
    "num_speakers": 2,
    "speakers": ["spk_0", "spk_1"],
    "segments": [
      { "start": 0.0, "end": 1.5, "duration": 1.5, "speaker": "spk_0" },
      { "start": 1.5, "end": 3.0, "duration": 1.5, "speaker": "spk_1" }
    ]
  }],
  "config": { "serviceId": "<id>", "language": null }
}
```
Notes: the model returns raw segments; sorting, speaker dedup, counting, and
`duration = end - start` are aggregation. Today this is service code; under AI4IDS-1981 it
becomes a JSONata expression in `adapter_config`.

---

## Language Diarization

**Input**
```json
{
  "serviceId": "<id>",
  "audio": [{ "audioContent": "<base64>", "audioFormat": "wav" }],
  "config": { "targetLanguage": "" }
}
```
`targetLanguage` optional (`""` = all languages).

**Output**
```json
{
  "taskType": "language-diarization",
  "output": [{ "total_segments": 2, "segments": [ { "start": 0.0, "end": 2.0, "language": "en" } ] }],
  "config": { "serviceId": "<id>" }
}
```
Notes: the model emits the contract fields directly; the parsed JSON blob is splatted into
the item (`response_key: output[]`). Fully config-driven, no service code. This is the
target shape Speaker Diarization should also reach via config.

---

## OCR (image to text)

**Input**
```json
{
  "serviceId": "<id>",
  "image": [{ "imageContent": "<base64>", "imageFormat": "png" }],
  "config": { "language": { "sourceLanguage": "en" } }
}
```
**Output**
```json
{ "output": [{ "source": "<full_text>", "target": "" }] }
```
Notes: Surya's JSON envelope is unwrapped (`json_field: full_text`), renamed to
`output[].source` (`response_key`), and a constant empty `target` is added
(`static_item_fields`). Fully config-driven, no service code.

---

## PII

Listed in `SUPPORTED_TASK_TYPES` but not implemented: requests return HTTP 501. No
contract until a model and shape are defined.

---

## Summary: where transformation lives today

| Task | Output shaping today | Stays in service code (non-JSON) |
|------|----------------------|----------------------------------|
| NMT | config-driven (default) | none |
| NER | config-driven decode | BPE-to-word alignment |
| Transliteration | config-driven (pair, top-k) | numSuggestions/isSentence validation |
| Language Detection | config-driven (json_parse, wrap_list, pair) | none |
| ASR | config-driven (gap: no response_key yet) | float-PCM preprocessing |
| TTS | service code | text chunking + waveform DSP |
| Audio Language Detection | config-driven | none |
| Speaker Diarization | service code (aggregation) | none after migration |
| Language Diarization | config-driven (splat) | none |
| OCR | config-driven (json_field, rename, static) | none |

Under AI4IDS-1981 the output shaping column collapses to "JSONata expression in
adapter_config" for every task; only the non-JSON column remains in service files.
