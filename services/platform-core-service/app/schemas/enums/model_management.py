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
    """Permitted license identifiers for registered models (ULCA ``License`` schema)."""

    CC_BY_4_0 = "cc-by-4.0"
    CC_BY_SA_4_0 = "cc-by-sa-4.0"
    CC_BY_ND_2_0 = "cc-by-nd-2.0"
    CC_BY_ND_4_0 = "cc-by-nd-4.0"
    CC_BY_NC_3_0 = "cc-by-nc-3.0"
    CC_BY_NC_4_0 = "cc-by-nc-4.0"
    CC_BY_NC_SA_4_0 = "cc-by-nc-sa-4.0"
    CC0 = "cc0"
    MIT = "mit"
    GPL_3_0 = "gpl-3.0"
    BSD_3_CLAUSE = "bsd-3-clause"
    PRIVATE_COMMERCIAL = "private-commercial"
    UNKNOWN_LICENSE = "unknown-license"
    CUSTOM_LICENSE = "custom-license"


class DomainEnum(str, Enum):
    """Business area a model is relevant to (ULCA ``Domain`` schema)."""

    GENERAL = "general"
    NEWS = "news"
    EDUCATION = "education"
    LEGAL = "legal"
    GOVERNMENT_PRESS_RELEASE = "government-press-release"
    HEALTHCARE = "healthcare"
    AGRICULTURE = "agriculture"
    AUTOMOBILE = "automobile"
    TOURISM = "tourism"
    FINANCIAL = "financial"
    MOVIES = "movies"
    SUBTITLES = "subtitles"
    SPORTS = "sports"
    TECHNOLOGY = "technology"
    LIFESTYLE = "lifestyle"
    ENTERTAINMENT = "entertainment"
    PARLIAMENTARY = "parliamentary"
    ART_AND_CULTURE = "art-and-culture"
    ECONOMY = "economy"
    HISTORY = "history"
    PHILOSOPHY = "philosophy"
    RELIGION = "religion"
    NATIONAL_SECURITY_AND_DEFENCE = "national-security-and-defence"
    LITERATURE = "literature"
    GEOGRAPHY = "geography"


class SupportedLanguagesEnum(str, Enum):
    """ULCA-supported language codes, iso-639-1/2 (ULCA ``SupportedLanguages`` schema)."""

    EN = "en"
    HI = "hi"
    MR = "mr"
    TA = "ta"
    TE = "te"
    KN = "kn"
    GU = "gu"
    PA = "pa"
    BN = "bn"
    ML = "ml"
    ASSAMESE = "as"
    BRX = "brx"
    DOI = "doi"
    KS = "ks"
    KOK = "kok"
    MAI = "mai"
    MNI = "mni"
    NE = "ne"
    ODIA = "or"
    SD = "sd"
    SI = "si"
    UR = "ur"
    SAT = "sat"
    LUS = "lus"
    NJZ = "njz"
    PNR = "pnr"
    KHA = "kha"
    GRT = "grt"
    SA = "sa"
    RAJ = "raj"
    BHO = "bho"
    GOM = "gom"
    AWA = "awa"
    HNE = "hne"
    MAG = "mag"
    MWR = "mwr"
    SJP = "sjp"
    GBM = "gbm"
    TCY = "tcy"
    HLB = "hlb"
    BIH = "bih"
    ANP = "anp"
    BNS = "bns"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class SupportedScriptsEnum(str, Enum):
    """ULCA-supported script codes, ISO 15924 (ULCA ``SupportedScripts`` schema)."""

    BENG = "Beng"
    DEVA = "Deva"
    THAA = "Thaa"
    GUJR = "Gujr"
    ARAN = "Aran"
    ORYA = "Orya"
    GURU = "Guru"
    ARAB = "Arab"
    SINH = "Sinh"
    KNDA = "Knda"
    MLYM = "Mlym"
    TAML = "Taml"
    TELU = "Telu"
    MTEI = "Mtei"
    OLCK = "Olck"
    LATN = "Latn"


class OAuthProviderEnum(str, Enum):
    """Auth provider for a contributor/submitter's OAuth identity (ULCA ``OAuthIdentity``)."""

    CUSTOM = "custom"
    GITHUB = "github"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    GOOGLE = "google"
    YAHOO = "yahoo"


class InferenceServerTypeEnum(str, Enum):
    """Supported inference server types for Service.endpoint."""

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
