 ASR Latency Analysis — Why Is ASR Slow While Other Audio Services Are Fast?

> **Status:** Analysis only — no code changes made yet.
> **Branch:** `feat/triton-stubs-integration`
> **Observed numbers:** ASR → 1.58 RPS, 15,580 ms avg latency. Speaker Diarization → 48+ RPS.

---

## The Short Answer

ASR is the **only** audio service that decodes the audio file itself and does signal processing
on the raw samples — in Python — before sending anything to Triton. Every other audio service
(speaker diarization, audio language detection, language diarization) is a pure passthrough: it
receives the audio already encoded as a base64 string and ships that string straight to Triton
without touching it.

That design difference, plus a few follow-on problems it creates, accounts for nearly all the
gap between 1.58 RPS and 48+ RPS.

---

## How a Request Flows Through Each Service

### Speaker Diarization (48+ RPS) — what "fast" looks like

```
Client sends base64 audio string
         │
         ▼
  validate_request()         ← check fields exist, ~microseconds
         │
         ▼
  preprocess_input()         ← does nothing with the audio, returns immediately
         │
         ▼
  build Triton payload       ← {"audio": {"audio_content": "<base64 string>"}}
         │                      ← 1 Python dict, 1 string, ~microseconds
         ▼
  JSON serialise & POST      ← payload is ~2–3 MB (one base64 string)
         │
         ▼  ← await HTTP call; event loop is FREE for other requests here
  Triton decodes audio        ← Triton does the heavy lifting on its GPU
         │
         ▼
  return transcription
```

The event loop is only blocked during `validate_request` (microseconds). Everything else either
does nothing (preprocess) or is spent waiting on a network call (which yields the loop).
That is why 48 concurrent requests can be in flight simultaneously — while request A is waiting
on Triton, requests B through Z are all making progress.

---

### ASR (1.58 RPS) — what "slow" looks like

```
Client sends base64 audio string
         │
         ▼
  validate_request()          ← ~microseconds, fine
         │
         ▼
  preprocess_input()          ← ← ← THE MAIN PROBLEM
    base64.b64decode()              a few milliseconds
    soundfile.read()                100–500 ms  (CPU-bound, blocks the loop)
    _stereo_to_mono()               a few ms
    scipy.signal.resample()         500 ms – 5,000 ms  (CPU-bound, blocks the loop)
    _equalize_amplitude()           a few ms
    audio_data.tolist()             100–200 ms  (allocates 480,000 Python objects)
         │
         ▼
  build Triton payload        ← {"audio": {"samples": [0.001, -0.002, ... 480,000 numbers]}}
         │
         ▼
  config mapper runs          ← iterates 480,000 floats THREE separate times → ~1.44 million
         │                       Python function calls
         ▼
  JSON serialise & POST       ← 480,000 decimal numbers in plain text → 4–10 MB JSON
         │
         ▼  ← await HTTP call; event loop is FREE here (but we've already spent ~5–15 seconds above)
  Triton gets FP32 floats      ← Triton has to parse back the 4–10 MB JSON float array
         │
         ▼
  return transcription
```

The event loop is blocked for **several seconds** inside `preprocess_input` and the mapper on
every single request. While one request is stuck in `scipy.signal.resample`, every other
request that arrives is just sitting in the queue. There is no concurrency — it is effectively
single-threaded serial processing.

---

## Root Cause Breakdown (Ranked by Impact)

### 1. `scipy.signal.resample()` blocks the async event loop

**File:** [services/asr_service.py:201](../services/inference-service/services/asr_service.py#L201)

`scipy.signal.resample` is an FFT-based algorithm. For a 30-second audio clip recorded at
44,100 Hz (a very common microphone/phone recording rate), the input array is about 1.3 million
samples. The FFT over that array takes **500 ms to 5,000 ms** depending on the CPU.

Python's async event loop runs on a single thread. When `scipy.resample` starts, it holds the
CPU for its entire duration. No other async request can run until it finishes. The `await`
keywords in the function don't help here — they only yield the loop when waiting on I/O (network,
disk), not when doing CPU arithmetic.

**Analogy:** Imagine a restaurant where the waiter can serve many tables at once by putting
orders into the kitchen and moving on. But if the waiter decides to personally cook every dish
himself before moving to the next table, every other table waits. That is what `resample` does.

---

### 2. `soundfile.read()` also blocks the event loop

**File:** [services/asr_service.py:174](../services/inference-service/services/asr_service.py#L174)

`soundfile.read()` decompresses the audio file (WAV, FLAC, OGG, MP3 etc.) in C code. It is
fast compared to resample, but for a compressed 30-second file it can still take **100–500 ms**
and it blocks the event loop for that entire duration.

---

### 3. `audio_data.tolist()` allocates 480,000 Python objects

**File:** [services/asr_service.py:91](../services/inference-service/services/asr_service.py#L91)

After resampling, the audio is a compact NumPy array. The comment in the code says the config
mapper requires a plain Python list, so `.tolist()` is called. This creates **480,000
individual Python float objects** on the heap. It takes ~100–200 ms and inflates memory usage
significantly.

---

### 4. The config mapper triple-iterates 480,000 floats — ~1.44 million Python calls

**File:** [services/base/config_mapper.py](../services/inference-service/services/base/config_mapper.py)

The generic `GenericTritonMapper.render_inputs()` is designed for small text payloads. It runs
three separate passes over whatever data it receives:

| Pass | What it does | Calls for ASR |
|------|-------------|---------------|
| `_cast_dtype` pass 1 | calls `float(x)` on every element | 480,000 |
| `_flatten` | recursive walk to create a flat copy | 480,000 |
| `_cast_dtype` pass 2 | calls `float(x)` again on every element | 480,000 |
| **Total** | | **~1,440,000 Python function calls** |

For speaker diarization, all three passes iterate over exactly **one element** (the base64 string).
The same code path that takes microseconds for diarization takes hundreds of milliseconds for ASR.

---

### 5. JSON serialises 480,000 decimal numbers → 4–10 MB payload

**File:** [utils/http_client.py:89](../services/inference-service/utils/http_client.py#L89)

The Triton HTTP endpoint receives a JSON body. ASR sends:
```json
{"inputs": [{"name": "AUDIO_SAMPLES", "datatype": "FP32", "shape": [1, 480000],
             "data": [0.00012, -0.00034, 0.00056, ...480,000 numbers...]}]}
```

Each float becomes roughly 8–15 characters of ASCII text. The total payload is **4–10 MB**
just in the `data` array. Python's `json.dumps` must format every individual float. Triton then
has to parse all of that JSON text back into binary FP32 numbers on the other end.

Speaker diarization sends one base64 string. `json.dumps` calls once. Trivially fast.

---

### 6. No HTTP connection pooling

**File:** [utils/http_client.py:84](../services/inference-service/utils/http_client.py#L84)

```python
async with httpx.AsyncClient() as client:   # new TCP connection every time
    response = await client.post(...)
```

A new TCP connection (3-way handshake) is opened and immediately closed for every single Triton
call. On a loaded system this adds 1–10 ms per request. It compounds the other problems.

---

## Why This Is All Unique to ASR

The key architectural difference is that **ASR is the only service that does float-PCM
preprocessing in Python before sending to Triton**.

Every other audio service (speaker diarization, audio language detection, language diarization)
sends the raw base64 audio bytes directly to Triton. Triton — which is a C++/CUDA inference
server — does the audio decoding and preprocessing internally, on hardware-optimised code, without
ever touching Python.

ASR chose the PCM-over-HTTP path presumably because the Whisper model backend in Triton was
configured to accept raw float samples rather than raw audio bytes. The correct long-term fix is
to match how all the other services work: send the base64 bytes and let Triton handle decoding.
As a shorter-term fix, the heavy CPU work can be offloaded to a thread pool so the event loop
is not blocked.

---


## Proposed Fixes (Summary — No Code Changes Yet)

### Fix 1 — Offload CPU work to a thread pool (quick win, high impact)

Wrap `soundfile.read` and `scipy.signal.resample` in `asyncio.to_thread()`. This runs them on a
separate OS thread so the async event loop is not blocked. Multiple requests can then be
preprocessed in parallel.

```
# Conceptually:
audio_data, sr = await asyncio.to_thread(sf.read, BytesIO(audio_bytes), ...)
resampled = await asyncio.to_thread(sps.resample, data, num_samples)
```

This alone should bring stub-mode latency from ~15,000 ms to ~2,000–4,000 ms for a single
worker, and RPS should climb significantly with concurrency.

---

### Fix 2 — Send base64 bytes to Triton; do not decode in Python (architectural fix, maximum impact)

Instead of decoding audio → numpy → list → JSON floats, send the raw base64 audio bytes to
Triton exactly as speaker diarization does. Triton's model backend would need to accept raw
audio bytes (base64-encoded BYTES tensor) and handle decoding internally — which is the standard
Triton pattern for audio models.

This eliminates root causes 1, 2, 3, 4, and 5 entirely. ASR would behave identically to
speaker diarization at the orchestrator level, achieving comparable RPS.

---

### Fix 3 — Use `scipy.signal.resample_poly` instead of `resample` (medium impact)

`resample` uses a full FFT over the entire signal length (expensive, O(N log N)).
`resample_poly` uses a polyphase filter (much cheaper for common ratios like 44100→16000).
This can reduce resampling time by 3–5x without any architectural change.

---

### Fix 4 — Replace `audio_data.tolist()` + mapper triple-iteration with numpy base64 encoding

Instead of converting to a Python list and iterating 1.44 million times, encode the raw float
bytes as base64 and declare the tensor as BYTES. The mapper then iterates over **one string**
instead of 480,000 floats.

---

### Fix 5 — Singleton `httpx.AsyncClient` with connection pool (small but free)

Create one `httpx.AsyncClient` instance at service startup and reuse it. Eliminates TCP
handshake overhead on every Triton call.

---
