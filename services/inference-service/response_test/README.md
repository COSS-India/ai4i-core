# Load-test stubs

Canned responses that let the inference service run with **no model in the
loop**, so a load test measures orchestrator overhead rather than GPU time.

Everything here is gated on one flag:

```bash
TRITON_STUB_MODE=true
```

Off by default. With it off, nothing in this package is reachable and the
service behaves exactly as it does without the package present.

The stub replaces the **model call only**. Validation, preprocessing, payload
build, spans, token counts, billing and postprocessing all still run, against
the stub output. That is deliberate: those stages are what the load test is
measuring.

---

## LLM

Most of the stubbed entry points are LLM. They are the main reason this package
exists.

| Endpoint | Stubbed in | Body |
|---|---|---|
| `POST /api/v1/chat` | `OpenAIProxyService.forward` | OpenAI chat completion |
| `POST /api/v1/chat/completions` | `OpenAIProxyService.forward` | OpenAI chat completion |
| the same two with `"stream": true` | `OpenAIProxyService.proxy_stream` | OpenAI SSE chunk sequence |
| `POST /api/v1/audio/transcriptions` | `OpenAIProxyService.proxy_multipart` | OpenAI speech-to-text |
| `POST /api/v1/audio/translations` | `OpenAIProxyService.proxy_multipart` | OpenAI speech-to-text |

Every guard sits at the **innermost seam**, the method that actually talks to
the upstream. MMS resolution, the tier gate and the upstream model-name
injection all still run for a stubbed request; only the network call to vLLM is
replaced.

That placement is deliberate and load-bearing. The guards used to sit at the top
of `proxy_traced` / `proxy_multipart`, which returned before the `model` and
`ai-inference` spans were ever opened. The PPU Kafka consumer bills off the
`ai-inference` span, so every stubbed LLM request came back 200 and was silently
unbilled, with Prometheus labelled by the fixture's literal `"stub"` model. Do
not "optimise" a guard upwards.

Each transport needs its own guard because each is a separate method.
`proxy_multipart` is not `forward`, and `proxy_stream` is not either. Guarding
only the chat path leaves `/audio/*` on the live upstream, which is what
happened on the earlier 2.2 stub branch, and leaves `stream: true` on it too.

### Chat: `/chat` and `/chat/completions`

Sized on the concatenated string content of `messages`. Non-string
(multimodal) parts are ignored for sizing.

| Prompt length | Reply | `usage` prompt/completion |
|---|---|---|
| < 200 chars | 32 chars | 8 / 9 |
| 200 – 999 chars | 205 chars | 120 / 44 |
| >= 1000 chars | 1196 chars | 620 / 210 |

The body carries a real `usage` block and a `model` field. The chat route reads
both (`set_billed_state` off `usage`, `set_metric_labels` off `model`), so
billing and Prometheus labels stay populated under load. A stub without them
would silently bill zero.

Fixture: `responses/llm_responses.py`.

### Streaming chat: the same routes with `"stream": true`

`_run_llm_chat` sends any payload with a truthy `stream` down a different path
(`proxy_traced_stream` → `proxy_stream`) that never touches `forward`, so it
needs its own guard or it reaches the live model.

The stubbed stream is the **same fixture** as the buffered reply, re-expressed
as the SSE chunk sequence a vLLM-style server would emit:

1. an opening `{"role": "assistant"}` delta
2. one content delta per word, so the chunk count scales with the reply
3. a `finish_reason: "stop"` chunk
4. a chunk with `"choices": []` carrying the fixture's `usage` block
5. `data: [DONE]`

Because both views come off one fixture, a stubbed stream bills exactly what the
stubbed buffered call bills for the same prompt. Concatenating the deltas
reproduces the buffered reply byte for byte.

**Step 4 is not optional.** `_record_stream_usage` reads the token counts off
that chunk onto the `ai-inference` span; `traced_inference` seeds those at zero,
and the PPU consumer skips any message whose total is zero. A stream without a
usage chunk returns 200 and bills nothing, with no error anywhere.

Two consequences worth knowing before you read the numbers:

- **The client must drain the whole stream.** The spans open lazily inside the
  returned generator and only close when it is exhausted. A load-test client
  that disconnects early loses the span and the bill. This is release-2.4's
  streaming design, not a stub artifact: real traffic behaves the same way.
- **Chunk bodies carry the fixture's `"stub"` model name**, unlike the buffered
  stub which echoes the resolved one. Nothing observable reads it:
  `proxy_traced_stream` sets the span and the Prometheus label from the
  `adapter_config` name resolved in `_prepare_request` and never parses the
  stream body for it. The lines are framed once at import and replayed, so a
  load test is not charged for JSON serialisation a real model host would do.

`_STREAM_CHUNK_DELAY_S` in `stub_dispatcher.py` (default `0.0`) paces the chunks.
It is a module constant, not an env var: it describes the load-test rig, not the
environment. Leave it at zero for throughput work. Raise it only when measuring
something client-side, such as time-to-first-token or render smoothness.

Fixture: `responses/llm_responses.py` (`chat_completion_chunks`).

### Audio: `/audio/transcriptions` and `/audio/translations`

The body shape depends on the `response_format` form field, because
`_proxy_audio_upload` picks the response type from what it gets back: a `dict`
becomes `JSONResponse`, a `str` becomes `PlainTextResponse`. Returning the
wrong type changes the response content type.

| `response_format` | Returns | Shape |
|---|---|---|
| `json` (default) | `dict` | `{"text": ...}` |
| `verbose_json` | `dict` | `task`, `language`, `duration`, `text`, `segments[]` |
| `text` | `str` | bare transcript |
| `srt` | `str` | SubRip cues, `,` millisecond separator |
| `vtt` | `str` | WebVTT cues, `.` millisecond separator |

An unrecognised value falls back to `json`, matching the route default.

Sizing is the **uploaded file's byte length**, not a character count. The
200/1000 character text thresholds are useless for audio: one second of 16 kHz
16-bit mono is already ~32 KB, so every real upload would classify as LARGE.

| Upload size | Transcript | Duration | Segments |
|---|---|---|---|
| < 100 KB | 25 chars | 2.5 s | 1 |
| 100 KB – 1 MB | 211 chars | 14.0 s | 2 |
| >= 1 MB | 682 chars | 48.0 s | 6 |

Fixture: `responses/audio_transcription_responses.py`.

---

## Triton task services

The same flag also stubs the ten Triton-backed services, short-circuiting
`BaseTaskService._call_triton_inference` before the HTTP call. Each fixture is
a KServe v2 response mirroring what that model's Triton endpoint returns.

| Service | Output tensor(s) |
|---|---|
| `NMTTaskService` | `OUTPUT_TEXT` |
| `ASRTaskService` | `TRANSCRIPTS` |
| `TTSTaskService` | `OUTPUT_GENERATED_AUDIO` (FP32) |
| `OCRTaskService` | `OUTPUT_TEXT` |
| `NERTaskService` | `OUTPUT_TEXT` |
| `LanguageDetectionTaskService` | `OUTPUT_TEXT` |
| `AudioLanguageDetectionTaskService` | `LANGUAGE_CODE`, `CONFIDENCE`, `ALL_SCORES` |
| `LanguageDiarizationTaskService` | `DIARIZATION_RESULT` |
| `SpeakerDiarizationTaskService` | `DIARIZATION_RESULT` |
| `TransliterationTaskService` | `OUTPUT_TEXT` |

`PIITaskService` has no stub by design: it raises not-implemented before any
call.

Sizing uses the first non-empty input tensor: raw byte length for binary
tensors (`_raw`, e.g. ASR audio), element count for numeric arrays, character
length otherwise. Thresholds are the 200 / 1000 constants in
`base_response_test.py`.

**These fixtures must stay in sync with the registered `adapter_config`.**
`convert_triton_output_to_task_format` is config-driven, and a declared tensor
that the stub does not emit raises `RuntimeError`, which surfaces as a 500 on
every request. Worse for a load test, the error path short-circuits before
conversion, so it is *faster* than the success path: a drifted stub produces a
fast, clean-looking run that measures nothing.

`tests/test_stub_adapter_config_contract.py` guards against exactly this.

---

## What still makes real network calls

Both by design, since the stub replaces the model call only:

- **MMS resolution.** Every Triton-backed request does a real GET to
  platform-core. TTL-cached, and it is what `resolve_ms`, `mms_http_ms` and
  `cache_hit` measure. The LLM paths skip it entirely.
- **Audio and image URI downloads,** when a request passes a URI instead of
  base64. Measured by `audio_fetch_ms`. Send base64 for zero external fetches.

---

## Running a load test against this

```bash
TRITON_STUB_MODE=true      # stubs on
PHASE_TIMING_ENABLED=true  # per-stage *_ms + TIMING log line (default)
```

Two things worth knowing before reading the numbers:

- **Discard warm-up.** The fixtures import lazily on first use, so the first
  request after start is roughly 200 ms slower and that cost lands inside
  `triton_ms`. Every later request is under 0.15 ms. With `WORKERS=2` you get
  one such outlier per worker process.
- **`KAFKA_ENABLED` is false by default.** Spans are still created and the
  TIMING line still logs, but nothing is exported, so there is no OpenSearch
  ingestion and no input to the PPU billing consumer. Set `KAFKA_ENABLED=true`
  with `KAFKA_SERVER=kafka:29092` from inside a container if billing needs to
  be exercised end to end.

---

## Layout

```
response_test/
├── stub_dispatcher.py                    ← the flag, sizing, SSE framing, and every entry point
├── responses/
│   ├── llm_responses.py                  ← chat completions, buffered and as SSE chunks
│   ├── audio_transcription_responses.py  ← speech-to-text, all 5 response_formats
│   └── *_triton_responses.py             ← one per Triton task service
├── base_response_test.py                 ← SMALL/MEDIUM threshold constants
└── ner_response_test.py                  ← legacy standalone NER demo (predates the
                                             stub layer; not part of TRITON_STUB_MODE)
```

Entry points, all returning `None` when the flag is off so callers fall through
to the real upstream:

| Function | Serves |
|---|---|
| `get_llm_stub_response(payload)` | `/chat`, `/chat/completions` |
| `get_llm_stream_stub(payload)` | the same two with `"stream": true` |
| `get_audio_stub_response(files, data)` | `/audio/transcriptions`, `/audio/translations` |
| `get_stub_response(task_name, triton_inputs)` | the ten Triton services |

`get_llm_stream_stub` is sync and returns an async generator, not a coroutine:
the caller needs a `None` check before committing to a stream, and an async
generator cannot return a value to signal "not stubbed".

The flag is checked inside the dispatcher rather than at each call site, so it
has one home and every call site reads as a plain lookup.
