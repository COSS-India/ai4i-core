# Triton Request Parameters

## NMT Service
```python
inputs, outputs = triton_client.get_translation_io_for_triton(
    batch,
    source_lang,
    target_lang
)
```

## Transliteration Service
```python
inputs, outputs = self.triton_client.get_transliteration_io_for_triton(
    batch,
    source_lang,
    target_lang,
    not is_sentence,        # word-level flag
    top_k,                  # number of suggestions
)
```

## Main Difference

**Transliteration** sends additional parameters during inference:
- `not is_sentence` — word-level flag (enables word-level transliteration mode)
- `top_k` — number of suggestions (returns multiple candidate results)

**NMT** uses only language pair parameters and returns a single translation result.