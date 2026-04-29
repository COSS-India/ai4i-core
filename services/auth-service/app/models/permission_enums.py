"""
Permission enums mirrored from ai4iplatform_auth seeder.
"""

import enum


class PermissionName(str, enum.Enum):
    USERS_CREATE = "users.create"
    USERS_READ = "users.read"
    USERS_UPDATE = "users.update"
    USERS_DELETE = "users.delete"

    CONFIGS_CREATE = "configs.create"
    CONFIGS_READ = "configs.read"
    CONFIGS_UPDATE = "configs.update"
    CONFIGS_DELETE = "configs.delete"

    METRICS_READ = "metrics.read"
    METRICS_EXPORT = "metrics.export"

    ALERTS_CREATE = "alerts.create"
    ALERTS_READ = "alerts.read"
    ALERTS_UPDATE = "alerts.update"
    ALERTS_DELETE = "alerts.delete"

    DASHBOARDS_CREATE = "dashboards.create"
    DASHBOARDS_READ = "dashboards.read"
    DASHBOARDS_UPDATE = "dashboards.update"
    DASHBOARDS_DELETE = "dashboards.delete"

    APIKEY_CREATE = "apiKey.create"
    APIKEY_READ = "apiKey.read"
    APIKEY_DELETE = "apiKey.delete"
    APIKEY_UPDATE = "apiKey.update"

    SERVICE_CREATE = "service.create"
    SERVICE_DELETE = "service.delete"
    SERVICE_UPDATE = "service.update"
    SERVICE_READ = "service.read"

    MODEL_CREATE = "model.create"
    MODEL_READ = "model.read"
    MODEL_UPDATE = "model.update"
    MODEL_DELETE = "model.delete"
    MODEL_PUBLISH = "model.publish"
    MODEL_UNPUBLISH = "model.unpublish"

    ROLES_ASSIGN = "roles.assign"
    ROLES_REMOVE = "roles.remove"
    ROLES_READ = "roles.read"

    ASR_INFERENCE = "asr.inference"
    ASR_READ = "asr.read"
    TTS_INFERENCE = "tts.inference"
    TTS_READ = "tts.read"
    NMT_INFERENCE = "nmt.inference"
    NMT_READ = "nmt.read"

    AUDIO_LANG_DETECTION_READ = "audio-lang-detection.read"
    AUDIO_LANG_DETECTION_INFERENCE = "audio-lang-detection.inference"
    LANGUAGE_DETECTION_READ = "language-detection.read"
    LANGUAGE_DETECTION_INFERENCE = "language-detection.inference"
    LANGUAGE_DIARIZATION_READ = "language-diarization.read"
    LANGUAGE_DIARIZATION_INFERENCE = "language-diarization.inference"
    NER_INFERENCE = "ner.inference"
    OCR_READ = "ocr.read"
    OCR_INFERENCE = "ocr.inference"
    SPEAKER_DIARIZATION_READ = "speaker-diarization.read"
    SPEAKER_DIARIZATION_INFERENCE = "speaker-diarization.inference"
    TRANSLITERATION_READ = "transliteration.read"
    TRANSLITERATION_INFERENCE = "transliteration.inference"
    PIPELINE_READ = "pipeline.read"
    PIPELINE_INFERENCE = "pipeline.inference"
    LLM_READ = "llm.read"
    LLM_INFERENCE = "llm.inference"
    MODEL_MANAGEMENT_READ = "model-management.read"
    MODEL_MANAGEMENT_INFERENCE = "model-management.inference"

    LOGS_READ = "logs.read"
    TRACES_READ = "traces.read"

    TENANT_CREATE = "tenant.create"
    TENANT_READ = "tenant.read"
    TENANT_UPDATE = "tenant.update"
    TENANT_USERS_READ = "tenant.users.read"
    TENANT_USERS_UPDATE = "tenant.users.update"

    PII_GUARD_INFERENCE = "pii_guard.inference"
    PII_GUARD_ADMIN = "pii_guard.admin"
