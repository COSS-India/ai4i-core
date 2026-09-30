# Adapter Config Quick Guide

A short guide to writing the `adapterConfig` section when you register a new model.

## 1. What is the adapter config and why do we use it?

Most of our models run on **NVIDIA Triton**, a model server. Triton does not understand a normal platform request such as “translate this text from English to Hindi”. It only accepts a list of named data slots, called **tensors**. Each tensor has an exact name, a data type and a size.

The **adapter config** is the mapping between the two. It tells the platform:

- **Inputs:** which values to take from the user's request and which Triton tensor to put each one in
- **Outputs:** which Triton tensor holds the answer, and what to call it in the response sent back to the user

Because of this mapping, a new model can be added by writing JSON, with no code changes. It lives in the model JSON as the `adapterConfig` section.

## 2. Inputs and outputs

Here is the NMT (translation) adapter config. It has three inputs and one output:

```json
"adapterConfig": {
  "version": "1.0",
  "inputs": [
    { "tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1],
      "value_path": "input.source" },
    { "tensor": "INPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1, 1],
      "value_path": "request.config.language.source_language" },
    { "tensor": "OUTPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1, 1],
      "value_path": "request.config.language.target_language" }
  ],
  "outputs": [
    { "tensor": "OUTPUT_TEXT", "dtype": "BYTES", "maps_to": "target" }
  ]
}
```

- **inputs:** the data sent **to** the model, one entry per Triton input tensor. Here those are the text, the source language and the target language.
- **outputs:** the data read **from** the model's reply, one entry per Triton output tensor. Here that is the translated text, returned to the user as `target`.
- **version:** always `"1.0"`.

You need at least one input and one output. The tensor names, their types and their count come from the model itself. Ask the person who deployed it, or open the model's config URL:

- Latest model version: `<triton-server>/v2/models/<model-name>/config`
- A specific model version: `<triton-server>/v2/models/<model-name>/versions/<model-version>/config`

`v2` in these URLs is the version of Triton's API (the KServe v2 protocol), **not** the model version. It is always `v2`, so do not change it. `<model-version>` is the model's own version number, for example `1`.

## 3. What each field means

Take one input entry:

```json
{
  "tensor": "INPUT_TEXT",
  "dtype": "BYTES",
  "shape": [-1, 1],
  "value_path": "input.source"
}
```

| Field | What it is | In this example |
|---|---|---|
| `tensor` | The exact name of the model's input slot. It must match Triton letter for letter, including capital letters. | The model has an input called `INPUT_TEXT`. |
| `dtype` | The type of data in the slot, such as text, decimal number, whole number or true/false. See section 4. | `BYTES` means text. |
| `shape` | The size of the slot. `-1` means “any number”. `[-1, 1]` means any number of items, one value each. | Any number of sentences, one sentence per item. |
| `value_path` | Where to find the value in the user's request, written as a dotted path. | `input.source` is the text the user sent. |

**Output entries** use `tensor` and `dtype` in the same way, plus `maps_to` instead of `value_path`. `maps_to` is the name the value gets in the response (for example `target`). Use the same `maps_to` names as the sample file for your model type.

**Common value_path values**

| value_path | Value it picks |
|---|---|
| `input.source` | The input text |
| `input.image_content` | The input image (OCR) |
| `audio.audio_content` | The input audio file (audio models) |
| `request.config.language.source_language` | Source language code, e.g. "en" |
| `request.config.language.target_language` | Target language code, e.g. "hi" |

**Common shape values**

| shape | Meaning | Typical use |
|---|---|---|
| `[-1, 1]` | Any number of items, one value each | Text models (safe default) |
| `[1, 1]` | Exactly one item with one value | Audio models (one file per request) |
| `[-1]` | A flat list of values | Models that do not batch |
| `[-1, -1]` | Any number of items, each a list of any length | Raw audio samples (ASR) |

## 4. Data types (dtype)

There are **13** supported dtypes. Write them exactly as shown, in capital letters:

| dtype | Meaning | Typical use |
|---|---|---|
| `BYTES` | Text or raw content | Sentences, language codes, audio/image files, JSON results. **The most common.** |
| `BOOL` | True / false | On/off switches |
| `FP16` | Decimal number, low precision | Half-precision models |
| `FP32` | Decimal number, normal precision | Audio samples, scores |
| `FP64` | Decimal number, high precision | Rarely used |
| `INT8` | Whole number, small | Rarely used |
| `INT16` | Whole number, medium | Rarely used |
| `INT32` | Whole number | Counts, e.g. number of audio samples |
| `INT64` | Whole number, very large | Token IDs |
| `UINT8` | Positive whole number, 0 to 255 | Small settings, e.g. top-k |
| `UINT16` | Positive whole number, medium | Rarely used |
| `UINT32` | Positive whole number, large | Rarely used |
| `UINT64` | Positive whole number, very large | Rarely used |

## 5. Tensor data types supported by Triton

Triton supports **14** tensor data types. Each type has two names: one in the model's `config.pbtxt` file, and the name used in requests (the one you write as `dtype`). Our platform accepts 13 of them. Only `BF16` is not supported yet.

| Triton config name | dtype to write | Meaning | Supported by our platform? |
|---|---|---|---|
| `TYPE_BOOL` | `BOOL` | True / false | Yes |
| `TYPE_UINT8` | `UINT8` | Positive whole number (8-bit) | Yes |
| `TYPE_UINT16` | `UINT16` | Positive whole number (16-bit) | Yes |
| `TYPE_UINT32` | `UINT32` | Positive whole number (32-bit) | Yes |
| `TYPE_UINT64` | `UINT64` | Positive whole number (64-bit) | Yes |
| `TYPE_INT8` | `INT8` | Whole number (8-bit) | Yes |
| `TYPE_INT16` | `INT16` | Whole number (16-bit) | Yes |
| `TYPE_INT32` | `INT32` | Whole number (32-bit) | Yes |
| `TYPE_INT64` | `INT64` | Whole number (64-bit) | Yes |
| `TYPE_FP16` | `FP16` | Decimal number (16-bit) | Yes |
| `TYPE_FP32` | `FP32` | Decimal number (32-bit) | Yes |
| `TYPE_FP64` | `FP64` | Decimal number (64-bit) | Yes |
| `TYPE_STRING` | `BYTES` | Text or raw bytes | Yes |
| `TYPE_BF16` | `BF16` | Decimal number (16-bit “brain float”, used by some LLMs) | **No.** Rejected when you save the model. |

**How to read it:** open the model config URL from section 2 and look at `data_type` for each input and output. Drop `TYPE_`, and write `TYPE_STRING` as `BYTES`. The dtype must match the model exactly, otherwise Triton rejects the request.

If a model uses `BF16`, ask the model team to expose that tensor as `FP16` or `FP32` instead. Supporting BF16 on the platform would need a code change.
