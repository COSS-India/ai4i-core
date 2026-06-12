# Inference Adapter Config Schemas

## NMT

```json
{
  "schema_version": "2.0", "model_version": "1",
  "inputs": [
    {"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"},
    {"tensor": "INPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1, 1], "value_path": "request.config.language.sourceLanguage"},
    {"tensor": "OUTPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1, 1], "value_path": "request.config.language.targetLanguage"}
  ],
  "outputs": [{"tensor": "OUTPUT_TEXT"}]
}
```

`output_transform`:

```
( $inp := inputs; { "output": [ $map(tensors.OUTPUT_TEXT, function($t, $i) { {"source": $inp[$i].source, "target": $t} }) ] } )
```

## Language Detection

```json
{
  "schema_version": "2.0", "model_version": "1",
  "inputs": [
    {"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"}
  ],
  "outputs": [{"tensor": "OUTPUT_TEXT", "is_json": true}]
}
```

`output_transform`:

```
( $inp := inputs; { "output": [ $map(tensors.OUTPUT_TEXT, function($p,$i){ {"source": $inp[$i].source, "langPrediction": [$p]} }) ] } )
```

## Transliteration

```json
{
  "schema_version": "2.0", "model_version": "1",
  "inputs": [
    {"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1], "value_path": "input.source"},
    {"tensor": "INPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1], "value_path": "request.config.language.sourceLanguage"},
    {"tensor": "OUTPUT_LANGUAGE_ID", "dtype": "BYTES", "shape": [-1], "value_path": "request.config.language.targetLanguage"},
    {"tensor": "IS_WORD_LEVEL", "dtype": "BOOL", "shape": [-1], "value_path": "request.config.is_word_level"},
    {"tensor": "TOP_K", "dtype": "UINT8", "shape": [-1], "value_path": "request.config.numSuggestions", "value": 0}
  ],
  "outputs": [{"tensor": "OUTPUT_TEXT"}]
}
```

`output_transform`:

```
( $inp := inputs; { "output": [ $map(tensors.OUTPUT_TEXT, function($t,$i){ {"source": ($exists($inp[$i].source) ? $inp[$i].source : ""), "target": $t} }) ] } )
```

## NER

```json
{
  "schema_version": "2.0", "model_version": "1",
  "inputs": [
    {"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"},
    {"tensor": "LANG_ID", "dtype": "BYTES", "shape": [-1, 1], "value_path": "request.config.language.sourceLanguage"}
  ],
  "outputs": [{"tensor": "OUTPUT_TEXT", "is_json": true}]
}
```

No `output_transform` (code-output service).

## OCR

```json
{
  "schema_version": "2.0", "model_version": "1",
  "inputs": [
    {"tensor": "IMAGE_DATA", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.image_content"}
  ],
  "outputs": [{"tensor": "OUTPUT_TEXT"}]
}
```

`output_transform`:

```
{ "output": [ $map(tensors.OUTPUT_TEXT, function($t){ {"source": $t, "target": ""} }) ], "config": request.config }
```

## ASR

```json
{
  "schema_version": "2.0", "model_version": "1",
  "inputs": [
    {"tensor": "AUDIO_SIGNAL", "dtype": "FP32", "shape": [-1, -1], "value_path": "input.samples"},
    {"tensor": "NUM_SAMPLES", "dtype": "INT32", "shape": [-1, 1], "value_path": "input.num_samples"},
    {"tensor": "LANG_ID", "dtype": "BYTES", "shape": [-1, 1], "value_path": "request.config.language.sourceLanguage"}
  ],
  "outputs": [{"tensor": "TRANSCRIPTS"}]
}
```

`output_transform`:

```
{ "output": [ $map(tensors.TRANSCRIPTS, function($t){ {"source": $t, "nBestTokens": null} }) ] }
```

## Audio Language Detection

```json
{
  "schema_version": "2.0", "model_version": "1",
  "inputs": [
    {"tensor": "AUDIO_DATA", "dtype": "BYTES", "shape": [1, 1], "value_path": "input.audioContent"}
  ],
  "outputs": [{"tensor": "LANGUAGE_CODE"}, {"tensor": "CONFIDENCE"}, {"tensor": "ALL_SCORES", "is_json": true}]
}
```

`output_transform`:

```
{ "taskType": "audio-lang-detection", "output": [ $map(tensors.LANGUAGE_CODE, function($lc,$i){ {"language_code": $lc, "confidence": tensors.CONFIDENCE[$i], "all_scores": tensors.ALL_SCORES[$i]} }) ], "config": { "serviceId": request.config.serviceId } }
```

## Language Diarization

```json
{
  "schema_version": "2.0", "model_version": "1",
  "inputs": [
    {"tensor": "AUDIO_DATA", "dtype": "BYTES", "shape": [1, 1], "value_path": "input.audioContent"},
    {"tensor": "LANGUAGE", "dtype": "BYTES", "shape": [1, 1], "value_path": "request.config.targetLanguage", "value": ""}
  ],
  "outputs": [{"tensor": "DIARIZATION_RESULT", "is_json": true}]
}
```

`output_transform`:

```
{ "taskType": "language-diarization", "output": [ tensors.DIARIZATION_RESULT ], "config": { "serviceId": request.config.serviceId } }
```

## Speaker Diarization

```json
{
  "schema_version": "2.0", "model_version": "1",
  "inputs": [
    {"tensor": "AUDIO_DATA", "dtype": "BYTES", "shape": [1, 1], "value_path": "input.audioContent"},
    {"tensor": "NUM_SPEAKERS", "dtype": "BYTES", "shape": [1, 1], "value_path": "request.config.numSpeakers", "value": ""}
  ],
  "outputs": [{"tensor": "DIARIZATION_RESULT", "is_json": true}]
}
```

`output_transform`:

```
{ "taskType": "speaker-diarization", "output": [ $map(tensors.DIARIZATION_RESULT, function($dr){ ( $segs := $sort($dr.segments, function($a,$b){$a.start_time > $b.start_time}).{"start": start_time, "end": end_time, "duration": ($exists(duration) ? duration : end_time - start_time), "speaker": speaker}; {"total_segments": $count($segs), "num_speakers": $count($distinct($segs.speaker)), "speakers": $sort($distinct($segs.speaker)), "segments": $segs} ) }) ], "config": { "serviceId": request.config.serviceId, "language": ($exists(request.config.language) ? request.config.language : null) } }
```
