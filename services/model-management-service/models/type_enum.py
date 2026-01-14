from enum import Enum

class TaskTypeEnum(str, Enum):
    
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


class LicenseEnum(str, Enum):
    """Enumeration of valid license types for models."""
    # Permissive Licenses
    MIT = "MIT"
    APACHE_2_0 = "Apache-2.0"
    BSD_2_CLAUSE = "BSD-2-Clause"
    BSD_3_CLAUSE = "BSD-3-Clause"
    ISC = "ISC"
    UNLICENSE = "Unlicense"
    ZLIB = "Zlib"
    
    # Copyleft Licenses
    GPL_2_0 = "GPL-2.0"
    GPL_3_0 = "GPL-3.0"
    LGPL_2_1 = "LGPL-2.1"
    LGPL_3_0 = "LGPL-3.0"
    AGPL_3_0 = "AGPL-3.0"
    MPL_2_0 = "MPL-2.0"
    EPL_2_0 = "EPL-2.0"
    CDDL_1_0 = "CDDL-1.0"
    
    # Microsoft Licenses
    MS_PL = "Ms-PL"
    MS_RL = "Ms-RL"
    
    # Creative Commons Licenses
    CC0_1_0 = "CC0-1.0"
    CC_BY_4_0 = "CC-BY-4.0"
    CC_BY_SA_4_0 = "CC-BY-SA-4.0"
    CC_BY_NC_4_0 = "CC-BY-NC-4.0"
    CC_BY_NC_SA_4_0 = "CC-BY-NC-SA-4.0"
    CC_BY_ND_4_0 = "CC-BY-ND-4.0"
    CC_BY_NC_ND_4_0 = "CC-BY-NC-ND-4.0"
    
    # AI/ML Specific Licenses
    OPENRAIL_M = "OpenRAIL-M"
    OPENRAIL_S = "OpenRAIL-S"
    BIGSCIENCE_OPENRAIL_M = "BigScience-OpenRAIL-M"
    CREATIVEML_OPENRAIL_M = "CreativeML-OpenRAIL-M"
    APACHE_2_0_WITH_LLM_EXCEPTION = "Apache-2.0-with-LLM-exception"
    
    # Academic/Research Licenses
    ACADEMIC_FREE_LICENSE_3_0 = "AFL-3.0"
    
    # Other Common Licenses
    ARTISTIC_LICENSE_2_0 = "Artistic-2.0"
    ECLIPSE_PUBLIC_LICENSE_1_0 = "EPL-1.0"
    
    # Special Categories
    PROPRIETARY = "Proprietary"
    CUSTOM = "Custom"
    OTHER = "Other"