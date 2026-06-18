# Response-Size Load Testing Framework

A lightweight, isolated framework for simulating inference load based on
response size — **no model is invoked**.  The goal is to measure how the
service handles payloads of different sizes and to provide realistic pre-defined
responses that mirror the real output contract.

Currently supported services: **NER**, **NMT**

---

## Directory Layout

```
response_test/
├── __init__.py
├── base_response_test.py    ← shared classification + timing logic
├── ner_response_test.py     ← NER tests and standalone demo
├── nmt_response_test.py     ← NMT tests and standalone demo
├── responses/
│   ├── __init__.py
│   ├── ner_responses.py     ← pre-defined SMALL / MEDIUM / LARGE NER responses
│   └── nmt_responses.py     ← pre-defined SMALL / MEDIUM / LARGE NMT responses
└── README.md                ← this file
```

---

## How to Run

### With pytest

```bash
# From the inference-service root:
cd services/inference-service

# Run NER response tests:
pytest response_test/ner_response_test.py -v

# Run NMT response tests:
pytest response_test/nmt_response_test.py -v

# Run all response tests:
pytest response_test/ -v

# Run with live console output (print statements visible):
pytest response_test/ -v -s
```

### Standalone (console demo)

```bash
python response_test/ner_response_test.py
python response_test/nmt_response_test.py
```

Example output (NER):

```
=======================================================
NER Response-Size Load Testing — Demo Run
=======================================================

[SMALL payload]
Payload Size : 19 chars
Response Type: SMALL
Response Time: 0.003 ms
Entities in response : 3
----------------------------------------

[MEDIUM payload]
Payload Size : 241 chars
Response Type: MEDIUM
Response Time: 0.001 ms
Entities in response : 20
----------------------------------------

[LARGE payload]
Payload Size : 812 chars
Response Type: LARGE
Response Time: 0.001 ms
Entities in response : 40
----------------------------------------

Done.
```

Example output (NMT):

```
=======================================================
NMT Response-Size Load Testing — Demo Run
=======================================================

[SMALL payload]
Payload Size : 17 chars
Response Type: SMALL
Response Time: 0.002 ms
Translated target length : 22 chars
----------------------------------------

[MEDIUM payload]
Payload Size : 269 chars
Response Type: MEDIUM
Response Time: 0.001 ms
Translated target length : 189 chars
----------------------------------------

[LARGE payload]
Payload Size : 1122 chars
Response Type: LARGE
Response Time: 0.001 ms
Translated target length : 612 chars
----------------------------------------

Done.
```

---

## How Response Size Is Determined

Payload size is determined by `len(payload)` (character count) and bucketed
using two thresholds defined in `base_response_test.py`:

| Payload length     | Response type |
|--------------------|---------------|
| < 200 chars        | `SMALL`       |
| 200 – 999 chars    | `MEDIUM`      |
| ≥ 1 000 chars      | `LARGE`       |

The thresholds are class-level constants (`small_threshold`, `medium_threshold`)
and can be overridden per subclass without touching the base class.

---

## How Timing Metrics Are Reported

Each call to `run(payload)` returns an `(InferenceMetrics, response)` tuple.

`InferenceMetrics` fields:

| Field            | Type           | Description                        |
|------------------|----------------|------------------------------------|
| `payload_size`   | `int`          | Character count of the input       |
| `response_size`  | `ResponseSize` | SMALL / MEDIUM / LARGE             |
| `start_time_ms`  | `float`        | `perf_counter` timestamp (ms)      |
| `end_time_ms`    | `float`        | `perf_counter` timestamp (ms)      |
| `duration_ms`    | `float`        | `end_time_ms - start_time_ms`      |

`str(metrics)` produces a ready-to-print report:

```
Payload Size : 19 chars
Response Type: SMALL
Response Time: 0.003 ms
```

---

## Response Formats

Pre-defined responses mirror the real dev instance output for each service.

### NER

```json
{
  "taskType": "ner",
  "output": [
    {
      "source": "<original text>",
      "nerPrediction": [
        {
          "token": "John",
          "tag": "PER",
          "tokenIndex": 0,
          "tokenStartIndex": 0,
          "tokenEndIndex": 4
        }
      ]
    }
  ],
  "config": null
}
```

Tags: `PER` (person), `LOC` (location), `ORG` (organisation), `DATE`, `O` (non-entity)

| Constant              | Tokens | Source text                                     |
|-----------------------|--------|-------------------------------------------------|
| `SMALL_NER_RESPONSE`  | 3      | "John visited Paris."                           |
| `MEDIUM_NER_RESPONSE` | 20     | Two-sentence office announcement                |
| `LARGE_NER_RESPONSE`  | 40     | Multi-sentence research-paper abstract          |

### NMT

```json
{
  "output": [
    {
      "source": "<original text>",
      "target": "<translated text>"
    }
  ],
  "smr_response": null
}
```

| Constant               | Source                       | Target language |
|------------------------|------------------------------|-----------------|
| `SMALL_NMT_RESPONSE`   | "Hello how are you"          | Hindi           |
| `MEDIUM_NMT_RESPONSE`  | 3-sentence meeting message   | Hindi           |
| `LARGE_NMT_RESPONSE`   | Multi-sentence AI paragraph  | Hindi           |

---

## Extending to Other Inference Types

To add Image, Audio, or Text response tests:

1. Create `responses/image_responses.py` (or `audio_responses.py`, `text_responses.py`) with
   three response constants following the appropriate response contract.

2. Create `image_response_test.py` that imports `BaseResponseTest` and
   overrides `get_response()`:

   ```python
   from response_test.base_response_test import BaseResponseTest, ResponseSize
   from response_test.responses.image_responses import (
       SMALL_IMAGE_RESPONSE, MEDIUM_IMAGE_RESPONSE, LARGE_IMAGE_RESPONSE
   )

   class ImageResponseTest(BaseResponseTest):
       _responses = {
           ResponseSize.SMALL:  SMALL_IMAGE_RESPONSE,
           ResponseSize.MEDIUM: MEDIUM_IMAGE_RESPONSE,
           ResponseSize.LARGE:  LARGE_IMAGE_RESPONSE,
       }

       def get_response(self, size):
           return self._responses[size]
   ```

3. Write pytest test classes following the same pattern as `ner_response_test.py`.

No existing files need to be modified.

---

## Design Constraints

- No production code is imported or modified.
- No existing test files are modified.
- The framework is entirely self-contained in `response_test/`.
- If this directory is not used, the rest of the test suite is unaffected.
