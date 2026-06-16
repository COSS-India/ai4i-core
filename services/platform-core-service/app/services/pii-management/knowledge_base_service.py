"""
KnowledgeBaseService — loads and caches regex patterns and geo terms from the
PII database at startup.

Thread-safety: refresh() is called once during lifespan startup (before any
request is served) and is never mutated during normal operation.  A manual
refresh can be triggered by calling refresh() again (e.g. after a migration).
"""

import logging
import re
from typing import Dict, List, Set

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.pii_management.pattern_repository import PatternRepository

logger = logging.getLogger(__name__)

# Languages that "all" lang_code expands to.
_ALL_LANGS = ("en", "hi", "mr", "ta")


class KnowledgeBaseService:
    """
    In-memory cache of compiled regex patterns and geo reference data.

    Attributes
    ----------
    patterns : Dict[lang, Dict[entity_label, compiled_regex]]
    suffixes : Dict[lang, List[str]]   — location suffixes per language
    safe_geo : Dict[lang, Set[str]]    — safe city names (lower-cased) per language
    ready    : bool                    — True after a successful refresh()
    """

    def __init__(self) -> None:
        self.patterns: Dict[str, Dict[str, re.Pattern]] = {}
        self.suffixes: Dict[str, List[str]] = {}
        self.safe_geo: Dict[str, Set[str]] = {}
        self.ready: bool = False

    async def refresh(self, db: AsyncSession) -> None:
        """
        Load (or reload) all active patterns and geo terms from the database.
        Safe to call multiple times — replaces in-memory data atomically.
        """
        repo = PatternRepository(db)

        new_patterns: Dict[str, Dict[str, re.Pattern]] = {}
        new_suffixes: Dict[str, List[str]] = {}
        new_safe_geo: Dict[str, Set[str]] = {}

        # ── Regex patterns ────────────────────────────────────────────────
        pattern_rows = await repo.get_active_patterns()
        for row in pattern_rows:
            langs = list(_ALL_LANGS) if row.lang_code == "all" else [row.lang_code]
            for lang in langs:
                new_patterns.setdefault(lang, {})
                try:
                    new_patterns[lang][row.entity_label] = re.compile(
                        row.regex_pattern, re.UNICODE | re.IGNORECASE
                    )
                except re.error as exc:
                    logger.warning(
                        "Skipping invalid pattern entity=%s lang=%s: %s",
                        row.entity_label, row.lang_code, exc,
                    )

        # ── Geo terms ─────────────────────────────────────────────────────
        geo_rows = await repo.get_active_geo_terms()
        for row in geo_rows:
            lang = row.lang_code
            if row.term_type == "SUFFIX":
                new_suffixes.setdefault(lang, []).append(row.term_text)
            elif row.term_type == "SAFE_CITY":
                new_safe_geo.setdefault(lang, set()).add(row.term_text.lower())

        # Atomic replace
        self.patterns = new_patterns
        self.suffixes = new_suffixes
        self.safe_geo = new_safe_geo
        self.ready = True

        logger.info(
            "KnowledgeBase loaded: %d pattern entries, %d geo terms",
            sum(len(v) for v in self.patterns.values()),
            sum(len(v) for v in self.suffixes.values()) + sum(len(v) for v in self.safe_geo.values()),
        )
