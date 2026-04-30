from __future__ import annotations
from enum import Enum
from typing import List


class MaskType(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    REDACT = "redact"

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]


class LanguageCode(str, Enum):
    EN = "en"
    HI = "hi"

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]


ALLOWED_MASK_TYPES: List[str] = MaskType.values()
ALLOWED_LANGUAGE_CODES: List[str] = LanguageCode.values()

