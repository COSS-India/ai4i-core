# Response-Size Load Testing Framework

A lightweight, isolated framework for simulating NER inference load based on
response size — **no model is invoked**.  The goal is to measure how the
service handles payloads of different sizes and to provide realistic stub
responses that mirror the real output contract.

---

## Directory Layout

```
response_test/
├── __init__.py
├── base_response_test.py   ← shared classification + timing logic
├── ner_response_test.py    ← NER tests and standalone demo
├── stubs/
│   ├── __init__.py
│   └── ner_stubs.py        ← pre-defined SMALL / MEDIUM / LARGE NER responses
└── README.md               ← this file
```

---

## How to Run

### With pytest

```bash
# From the inference-service root:
cd services/inference-service

# Run only the response tests:
pytest response_test/ner_response_test.py -v

# Run with live console output (print statements visible):
pytest response_test/ner_response_test.py -v -s
```

### Standalone (console demo)

```bash
python response_test/ner_response_test.py
```

Example output:

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

Each call to `NERResponseTest.run(payload)` returns an `(InferenceMetrics, response)` tuple.

`InferenceMetrics` fields:

| Field            | Type    | Description                        |
|------------------|---------|------------------------------------|
| `payload_size`   | `int`   | Character count of the input       |
| `response_size`  | `ResponseSize` | SMALL / MEDIUM / LARGE      |
| `start_time_ms`  | `float` | `perf_counter` timestamp (ms)      |
| `end_time_ms`    | `float` | `perf_counter` timestamp (ms)      |
| `duration_ms`    | `float` | `end_time_ms - start_time_ms`      |

`str(metrics)` produces a ready-to-print report:

```
Payload Size : 19 chars
Response Type: SMALL
Response Time: 0.003 ms
```

---

## Stub Response Format

Stubs mirror the output of `NERTaskService.postprocess_output`:

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

Three pre-defined stubs are in `stubs/ner_stubs.py`:

| Constant              | Entities | Source text                                    |
|-----------------------|----------|------------------------------------------------|
| `SMALL_NER_RESPONSE`  | 3 tokens | "John visited Paris."                         |
| `MEDIUM_NER_RESPONSE` | 20 tokens| Two-sentence office announcement               |
| `LARGE_NER_RESPONSE`  | 40 tokens| Multi-sentence research-paper abstract         |

---

## Extending to Other Inference Types

To add Image, Audio, or Text response tests:

1. Create `stubs/image_stubs.py` (or `audio_stubs.py`, `text_stubs.py`) with
   three stub constants following the appropriate response contract.

2. Create `image_response_test.py` that imports `BaseResponseTest` and
   overrides `stub_response()`:

   ```python
   from response_test.base_response_test import BaseResponseTest, ResponseSize
   from response_test.stubs.image_stubs import (
       SMALL_IMAGE_RESPONSE, MEDIUM_IMAGE_RESPONSE, LARGE_IMAGE_RESPONSE
   )

   class ImageResponseTest(BaseResponseTest):
       _stubs = {
           ResponseSize.SMALL:  SMALL_IMAGE_RESPONSE,
           ResponseSize.MEDIUM: MEDIUM_IMAGE_RESPONSE,
           ResponseSize.LARGE:  LARGE_IMAGE_RESPONSE,
       }

       def stub_response(self, size):
           return self._stubs[size]
   ```

3. Write pytest test classes following the same pattern as `ner_response_test.py`.

No existing files need to be modified.

---

## Design Constraints

- No production code is imported or modified.
- No existing test files are modified.
- The framework is entirely self-contained in `response_test/`.
- If this directory is not used, the rest of the test suite is unaffected.
