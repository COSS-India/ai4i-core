"""
Shared enums for request/response schemas.
"""

from enum import Enum


class TaskTypeEnum(str, Enum):
    """Inference task types supported by the platform."""

    nmt = "nmt"
    tts = "tts"
    asr = "asr"
    llm = "llm"
    transliteration = "transliteration"
    language_detection = "language-detection"
    speaker_diarization = "speaker-diarization"
    audio_lang_detection = "audio-lang-detection"
    language_diarization = "language-diarization"
    ocr = "ocr"
    ner = "ner"


def resolve_task_type(value: str) -> str:
    """Case-insensitively resolve a string to its canonical TaskTypeEnum value.

    Single source of truth for "normalize + validate" so callers can't drift
    out of sync (e.g. one comparing .lower() values, another relying on
    TaskTypeEnum(x.lower()) — those only agree today because every member
    happens to already be lowercase).
    """
    v_normalized = value.lower()
    for member in TaskTypeEnum:
        if member.value.lower() == v_normalized:
            return member.value
    valid = [m.value for m in TaskTypeEnum]
    raise ValueError(f"Invalid task type '{value}'. Valid types: {', '.join(valid)}")


class LicenseEnum(str, Enum):
    """Permitted license identifiers for registered models."""

    # Permissive
    MIT = "MIT"
    APACHE_2_0 = "Apache-2.0"
    BSD_2_CLAUSE = "BSD-2-Clause"
    BSD_3_CLAUSE = "BSD-3-Clause"
    ISC = "ISC"
    UNLICENSE = "Unlicense"
    ZLIB = "Zlib"
    # Copyleft
    GPL_2_0 = "GPL-2.0"
    GPL_3_0 = "GPL-3.0"
    LGPL_2_1 = "LGPL-2.1"
    LGPL_3_0 = "LGPL-3.0"
    AGPL_3_0 = "AGPL-3.0"
    MPL_2_0 = "MPL-2.0"
    EPL_2_0 = "EPL-2.0"
    CDDL_1_0 = "CDDL-1.0"
    # Microsoft
    MS_PL = "Ms-PL"
    MS_RL = "Ms-RL"
    # Creative Commons
    CC0_1_0 = "CC0-1.0"
    CC_BY_4_0 = "CC-BY-4.0"
    CC_BY_SA_4_0 = "CC-BY-SA-4.0"
    CC_BY_NC_4_0 = "CC-BY-NC-4.0"
    CC_BY_NC_SA_4_0 = "CC-BY-NC-SA-4.0"
    CC_BY_ND_4_0 = "CC-BY-ND-4.0"
    CC_BY_NC_ND_4_0 = "CC-BY-NC-ND-4.0"
    # AI/ML
    OPENRAIL_M = "OpenRAIL-M"
    OPENRAIL_S = "OpenRAIL-S"
    BIGSCIENCE_OPENRAIL_M = "BigScience-OpenRAIL-M"
    CREATIVEML_OPENRAIL_M = "CreativeML-OpenRAIL-M"
    APACHE_2_0_WITH_LLM_EXCEPTION = "Apache-2.0-with-LLM-exception"
    # Academic / other
    ACADEMIC_FREE_LICENSE_3_0 = "AFL-3.0"
    ARTISTIC_LICENSE_2_0 = "Artistic-2.0"
    ECLIPSE_PUBLIC_LICENSE_1_0 = "EPL-1.0"
    PROPRIETARY = "Proprietary"
    CUSTOM = "Custom"
    OTHER = "Other"


class InferenceServerTypeEnum(str, Enum):
    """Supported inference server types for Service.inferenceEndPoint.callbackUrl."""

    triton = "triton"
    custom = "custom"


class VersionStatusEnum(str, Enum):
    """Lifecycle state for a model version (mirrors ORM enum)."""

    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


class PolicyLatencyEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PolicyCostEnum(str, Enum):
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"


class PolicyAccuracyEnum(str, Enum):
    SENSITIVE = "sensitive"
    STANDARD = "standard"


class AudioFormatEnum(str, Enum):
    """ULCA AudioFormat — audio formats supported by an inference endpoint."""

    wav = "wav"
    pcm = "pcm"
    mp3 = "mp3"
    flac = "flac"
    sph = "sph"


class TextFormatEnum(str, Enum):
    """ULCA TextFormat — textual formats supported by an inference endpoint."""

    srt = "srt"
    transcript = "transcript"
    webvtt = "webvtt"
    alternatives = "alternatives"
