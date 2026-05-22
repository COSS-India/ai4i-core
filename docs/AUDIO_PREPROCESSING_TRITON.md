# Audio Preprocessing Before Triton Inference

## Overview

This document explains the audio preprocessing pipeline used before sending data to Triton Inference Server, and clarifies why these steps vary across different models.

---

## Preprocessing Pipeline

```
Raw bytes (base64 decode or URI download)
       ↓
soundfile.read()  →  float64 numpy array + sample rate
       ↓
stereo → mono  (average channels if stereo)
       ↓
resample to 16000 Hz  (scipy.signal.resample)
       ↓
amplitude normalization  (pydub equalize_amplitude)
       ↓
dequantize  →  float64 ndarray, shape [num_samples]
       ↓
[if VAD in preProcessors]
  Triton VAD call (silero_vad_chunking)
  → List of audio chunks + speech timestamps
[else]
  Single chunk = full audio
  Timestamp: {start:0, end:num_samples, start_secs:0, end_secs:duration}
```

---

## Step-by-Step Explanation

### Step 1: Raw bytes → Decoded audio
Audio arrives as either base64-encoded bytes or a URI. This step gets the raw binary data into memory.  
**Universal for all audio models.**

---

### Step 2: `soundfile.read()` → numpy array
Decodes the audio container (WAV, MP3, FLAC, etc.) into:
- A numerical array of audio samples
- The original sample rate (e.g., 44100 Hz, 48000 Hz)

---

### Step 3: Stereo → Mono
Averages the left and right channels into a single channel.

---

### Step 4: Resample to 16000 Hz
Converts whatever the original sample rate was to 16kHz using `scipy.signal.resample`.

---

### Step 5: Amplitude Normalization
Normalizes the loudness using `pydub equalize_amplitude` so quiet/loud audio produces consistent model inputs.

---

### Step 6: Dequantize
Ensures samples are in float64 range (typically `-1.0` to `+1.0`), producing a final ndarray of shape `[num_samples]`.

---

### Step 7: VAD — Voice Activity Detection (Optional)
If `VAD` is listed in `preProcessors`, a Triton VAD call (`silero_vad_chunking`) is made to split audio into speech-only chunks, removing silence.

Otherwise, the full audio is treated as a single chunk with timestamps:
```json
{ "start": 0, "end": num_samples, "start_secs": 0, "end_secs": duration }
```

---

## Why These Steps Differ Across Models

> **Core Principle: Preprocessing must match the model's training conditions.**
> Mismatched preprocessing = degraded model performance, even if the model runs without errors.

| Step | Varies? | Why |
|------|---------|-----|
| **base64 decode / URI download** | ❌ No | Always required regardless of model type |
| **soundfile.read()** | ❌ No | Always needed to decode audio containers |
| **Stereo → Mono** | ✅ Yes | Some models (music separation, spatial audio) are trained on stereo and expect 2 channels |
| **Resampling** | ✅ Yes | Tied to the **training data sample rate**:<br>- ASR/NMT: **16kHz**<br>- Phone/Telecom: **8kHz**<br>- Music: **44.1kHz or 48kHz** |
| **Amplitude normalization** | ✅ Yes | If training data wasn't normalized, applying it at inference will **hurt** performance |
| **float64 vs float32** | ✅ Yes | Triton model config defines the expected `dtype`. Some models need `FP32`, not `FP64` |
| **VAD chunking** | ✅ Yes | Only needed for models that:<br>- Can't handle long audio (memory limits)<br>- Were trained on short speech segments<br>- Need word-level alignment |

---

## Model-Specific Examples

| Model Type | Sample Rate | Channels | Normalization | VAD |
|------------|-------------|----------|---------------|-----|
| ASR (Speech-to-Text) | 16kHz | Mono | Yes | Optional |
| NMT (with audio input) | 16kHz | Mono | Yes | Optional |
| Phone/Telecom models | 8kHz | Mono | Yes | Optional |
| Music Classification | 44.1kHz | Stereo | No | No |
| Emotion Detection | 16kHz | Mono | Yes | Yes |
| Speaker Diarization | 16kHz | Mono | Yes | Yes |

---

## Triton Request Shape Reference

When sending data to Triton, the `shape` field must use **actual positive integers** (not `-1`):

| Field | Model Config | Triton Request |
|-------|-------------|----------------|
| `shape` | `[-1, 1]` (dynamic batch) | `[2, 1]` (actual batch size) |

- **First dimension**: batch size (number of samples)
- **Second dimension**: elements per sample (usually `1` for single strings/arrays)

> Triton requires explicit shape in requests for memory allocation and validation. The `-1` in model config means "accept any batch size" but individual requests must specify the concrete size.

---

## Related Files
- Model config schemas: check each service's `model_config.json` or `config.pbtxt`
- VAD integration: `silero_vad_chunking` in the inference-service preprocessors
