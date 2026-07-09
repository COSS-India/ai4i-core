# TTS Latency Analysis

Text-to-Speech has a different shape to its latency problem compared to ASR. ASR had one
audio decode per request; TTS has **one Triton call per chunk**, and those calls run one
after the other. That single design decision multiplies the model latency by however many
chunks the input produces. Everything else is secondary to fixing that.

---

## How a TTS request flows today

```
Request arrives
  │
  ├── preprocess_input
  │     └── split input into ≤400-char chunks   (e.g. 5 chunks for a 2000-char text)
  │
  ├── run_inference  ← THE BOTTLENECK
  │     ├── Triton call for chunk 1  (wait...)
  │     ├── Triton call for chunk 2  (wait...)
  │     ├── Triton call for chunk 3  (wait...)
  │     ├── Triton call for chunk 4  (wait...)
  │     └── Triton call for chunk 5  (wait...)
  │     Total time = chunk1 + chunk2 + chunk3 + chunk4 + chunk5
  │
  └── postprocess_output
        ├── merge chunk audio samples
        ├── resample (event loop)
        ├── encode to WAV/MP3 (event loop)
        └── base64 encode + response envelope
```

A single Triton call for a TTS chunk takes roughly **300–600 ms** depending on text length
and GPU load. For a 2000-character input that produces 5 chunks:

| Scenario | Latency |
|---|---|
| Today (sequential) | 5 × 450 ms = **2,250 ms** just in Triton |
| Parallel (all 5 at once) | max(450 ms each) = **450 ms** in Triton |

That is a **5× wall-clock improvement** from changing one line of code.

---

## Issue 1 — Sequential chunk loop (biggest impact)

**Where:** [task_service.py:301](../services/inference-service/services/base/task_service.py#L301)

```python
# Current code — sequential
for group in groups:
    ...
    raw_triton_output = await self._call_triton_inference(...)
```

`TRITON_CALL_MODE = "per_item"` in [tts_service.py:45](../services/inference-service/services/tts_service.py#L45)
means `run_inference` builds `groups = [[chunk1], [chunk2], ..., [chunkN]]` and then
iterates over them one-by-one in a `for` loop.

Every iteration is a separate `await` that suspends execution until Triton responds. The
next chunk does not start until the previous one finishes. The event loop is free during
the Triton wait, but no other work for *this request* progresses.

**Effect:** Total Triton time = sum of all chunk latencies, not the maximum.

**Fix:** Fan out all chunk calls concurrently with `asyncio.gather`.

The cleanest approach is to override `run_inference` in `TTSTaskService` to do:

```python
results = await asyncio.gather(*[self._run_one_chunk(chunk, config) for chunk in chunks])
```

All Triton calls in-flight simultaneously; total latency = slowest single chunk.

---

## Issue 2 — `np.array(audio_data)` blocks the event loop per chunk

**Where:** [tts_service.py:97](../services/inference-service/services/tts_service.py#L97)

```python
audio_fp32 = np.array(audio_data, dtype=np.float32).flatten()
```

`audio_data` is a Python list of floats that came directly from Triton's JSON response.
For a 3-second audio chunk at 22,050 Hz the list contains ~66,000 floats.
`np.array(list_of_66000_floats)` iterates the list in Python, boxing each float — this
takes **5–20 ms** and runs on the event loop because `convert_triton_output_to_task_format`
is called inside an `async with` block at line 320 of task_service.py with no thread
offload.

With sequential chunks this adds up silently:
- 5 chunks × 15 ms = **75 ms** of event-loop blocking you never see in Triton timing

With the parallel fix in Issue 1 this becomes a single-step conversion that still needs
offloading to a thread.

**Fix:** Move the `np.array` call into a thread:

```python
async def convert_triton_output_to_task_format(self, triton_output):
    audio_data = ...  # extract from Triton response
    return await asyncio.to_thread(self._convert_sync, audio_data)

def _convert_sync(self, audio_data):
    audio_fp32 = np.array(audio_data, dtype=np.float32).flatten()
    audio_int16 = np.clip(audio_fp32 * 32767, -32768, 32767).astype(np.int16)
    return [{"samples": audio_int16}]
```

---

## Issue 3 — `postprocess_output` runs all CPU work on the event loop

**Where:** [tts_service.py:105–163](../services/inference-service/services/tts_service.py#L105)

`postprocess_output` is an `async def` but contains no `await` — every operation runs
synchronously on the event loop, blocking all other requests from being served.

The operations inside it, from cheapest to most expensive:

### 3a. Resampling

[tts_service.py:230–235](../services/inference-service/services/tts_service.py#L230)

```python
def _resample_audio(self, audio, from_rate, to_rate):
    num_samples = round(len(audio) * float(to_rate) / from_rate)
    resampled = sps.resample(audio.astype(np.float32), num_samples)
    return np.clip(resampled, -32768, 32767).astype(np.int16)
```

For the common case of 22,050 Hz → 16,000 Hz:
- gcd(22050, 16000) = 50, so up=320, down=441
- down=441 > 20 → FFT resample is the right algorithm here (same conclusion as ASR 44.1kHz)
- The algorithm choice is correct. The problem is it runs on the event loop.
- For a 5-second speech output: ~110,000 samples → FFT over 110k points ≈ **30–80 ms** of blocking

`_stretch_audio` has the same issue — it also uses `sps.resample` on the event loop.

### 3b. WAV encoding

[tts_service.py:253–255](../services/inference-service/services/tts_service.py#L253)

```python
wav_buffer = BytesIO()
wav_io.write(wav_buffer, sample_rate, audio)
wav_bytes = wav_buffer.getvalue()
```

`scipy.io.wavfile.write` on a 5-second int16 array (160,000 samples × 2 bytes = 320 KB)
takes **2–10 ms** on the event loop. For most WAV responses, this is acceptable.

### 3c. pydub/ffmpeg for non-WAV formats (MP3, OGG, FLAC, etc.)

[tts_service.py:259–262](../services/inference-service/services/tts_service.py#L259)

```python
segment = AudioSegment.from_wav(BytesIO(wav_bytes))
out_buffer = BytesIO()
segment.export(out_buffer, format=audio_format)
```

This is the **worst case**. `AudioSegment.from_wav` decodes the WAV fully into pydub's
internal representation. `segment.export(format="mp3")` spawns an ffmpeg subprocess,
pipes the audio through it, and collects the output. For a 5-second audio clip:

- `AudioSegment.from_wav` ≈ **5–20 ms**
- `segment.export(format="mp3")` ≈ **80–400 ms** (ffmpeg subprocess overhead dominates
  for short clips; gets relatively cheaper for longer audio)

This entire block runs on the event loop. During an MP3 export the server cannot respond
to any other request.

**Fix for 3a/3b/3c:** Wrap `postprocess_output`'s CPU work in `asyncio.to_thread`:

```python
async def postprocess_output(self, result):
    # ... validate config, build merged dict (cheap) ...
    return await asyncio.to_thread(self._postprocess_sync, merged, target_rate, audio_format, ...)
```

---

## Issue 4 — No concurrency limit on preprocessing

**Where:** [tts_service.py:51–71](../services/inference-service/services/tts_service.py#L51)

`preprocess_input` is cheap for TTS (text chunking is pure Python string operations) so
this is not a bottleneck today. However, after the Issue 1 parallel-chunk fix, each request
will fire N concurrent Triton calls. Under a burst of simultaneous requests, this means
M requests × N chunks = M×N concurrent Triton calls. Triton handles this gracefully with
dynamic batching, but the Triton pod or network link can still become the saturation point.

Unlike ASR there is no semaphore controlling how many chunks execute simultaneously.
Adding one (similar to ASR's `_PREPROCESS_MAX_CONCURRENCY = 4`) avoids thundering-herd
when many requests arrive at the same time.

---

## Summary: what hurts RPS and what hurts latency

| Issue | Type | Latency impact | RPS impact |
|---|---|---|---|
| Sequential chunk Triton loop | Architecture | **High** — adds N×chunk_latency instead of 1×chunk_latency | **High** — event loop tied up waiting for each sequential Triton call |
| `np.array(list)` on event loop | Event loop blocking | Medium — 5–20 ms per chunk | Medium — blocks other requests per chunk |
| Resample + WAV write on event loop | Event loop blocking | Medium — 30–80 ms per request | Medium |
| pydub/ffmpeg export on event loop | Event loop blocking | **High** — 100–400 ms per MP3/OGG request | **High** — full event loop stall during ffmpeg |

---

## Recommended fix order

### Fix 1 — Parallelize chunks (highest leverage, ~5× improvement for long inputs)

Override `run_inference` in `TTSTaskService` to run all chunk Triton calls concurrently.

The base `run_inference` loop in task_service.py is sequential by design (generic;
supports stateful per-item patterns). TTS chunks are completely independent — the model
produces audio for each chunk with no dependency on others — so parallelism is safe.

```python
# In TTSTaskService:
async def run_inference(self, payload, serviceInfo):
    # ... setup from base class (model_name, endpoint, adapter_config) ...
    chunks = payload.get(self.payload_key) or []
    config = payload.get("config", {})

    async def _run_chunk(chunk):
        triton_inputs, triton_outputs = await self.convert_payload_to_triton_format(
            [chunk], config
        )
        raw = await self._call_triton_inference(
            triton_endpoint=triton_endpoint,
            triton_inputs=triton_inputs,
            triton_outputs=triton_outputs,
            api_key=api_key,
        )
        return await self.convert_triton_output_to_task_format(raw)

    results = await asyncio.gather(*[_run_chunk(c) for c in chunks])
    response_data = [item for chunk_result in results for item in chunk_result]
    return PostProcessFormat(payload=payload, response_data=response_data, source_texts=...)
```

### Fix 2 — Offload `postprocess_output` CPU work to a thread

Wrap the resample + encode block in `asyncio.to_thread`. The merge/sort logic (cheap
Python) stays on the event loop; only the numpy + scipy + pydub operations go to thread.

### Fix 3 — Offload `convert_triton_output_to_task_format` to a thread

Move `np.array(audio_data, ...)` into `_convert_sync` called via `asyncio.to_thread`.

### Fix 4 (optional) — Add a per-request chunk concurrency cap

After Fix 1 is in place, add a semaphore (e.g. 8) to cap concurrent in-flight Triton
calls across all chunk goroutines in a single request. Prevents one large request from
monopolizing the Triton connection pool.

---

## What NOT to change

- **`_resample_audio` algorithm** — `scipy.signal.resample` (FFT) is the right algorithm
  for 22,050→16,000 Hz (down=441 after GCD reduction, which is well above the 20-tap
  threshold where `resample_poly` would be faster). The algorithm is correct; only the
  thread-offloading is missing.

- **Chunk size (400 chars)** — this is constrained by the TTS model's context window, not
  a performance parameter. Larger chunks would degrade output quality or fail the model.

- **`_to_audio_bytes` WAV path** — `scipy.io.wavfile.write` is fine for WAV. The problem
  is only non-WAV formats that go through pydub/ffmpeg.
