# Model Creation Guide

How to register a new model on the platform using a model JSON file.

## Steps

1. Open **Model Management** in the UI and click **Download Sample JSON** to get a starting template.
2. Pick the reference file for your model type (see [Reference files](#reference-files)) and copy it.
3. Fill in your model's details. Fields marked `Required` in the comments must be set; `Optional` fields can be deleted.
4. Write the `adapterConfig` section using the tensor names, types and shapes from your model's Triton config (`<triton-server>/v2/models/<model-name>/config`). See the [adapter config guides](#adapter-config-guides).
5. Upload the `.json` file. Comments (`//`) can stay in; they are stripped before the file is validated.
6. Run a real test inference once the model is saved. Tensor names, value paths and shapes are only checked when the model is called.

## Reference files

| File | Use it for |
|---|---|
| [reference_llm_model.json](reference_llm_model.json) | Chat / LLM models (task `llm`) |
| [reference_nlp_models.json](reference_nlp_models.json) | NLP models. The main example is translation (`nmt`); the **PICK YOUR MODEL TYPE** section at the end has blocks for transliteration, language detection, OCR, NER and the audio models |

Both files are annotated with comments that explain every field.

## Adapter config guides

| Guide | Audience |
|---|---|
| [ADAPTER-CONFIG-QUICK-GUIDE.md](ADAPTER-CONFIG-QUICK-GUIDE.md) | Anyone registering a model. Explains inputs, outputs, fields and data types in plain terms |
| [ADAPTER-CONFIG-TECHNICAL-GUIDE.md](ADAPTER-CONFIG-TECHNICAL-GUIDE.md) | Engineers and DevOps / MLOps. Full schema, request/response mapping, validation rules, onboarding procedure and troubleshooting |

## Checklist before saving

- `task.type` and `schema.taskType` are the same.
- `schema` has all four of `model_name`, `taskType`, `request` and `response`.
- `adapterConfig` has `version` and at least one entry in both `inputs` and `outputs`.
- `classInstance` is set to the value for your model type (for example `NMTTaskService`). Only LLM models use `null`.
- For LLM models, `adapterConfig.model_name` exactly matches the model name on the AI server, and `callbackUrl` is the base address only (no `/v1/chat/completions`).
- Each `dtype` matches the model's Triton config exactly (`TYPE_STRING` becomes `BYTES`; drop the `TYPE_` prefix for the others).
