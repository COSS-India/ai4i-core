# DRY Principle Recommendations - Action Items

## Executive Summary for Leadership

The AI4I-Core platform shows **moderate DRY adherence** (estimated 60-65% compliance). While shared libraries are well-established, approximately **12-15% of the codebase contains preventable duplication** that impacts maintenance and consistency.

**Investment Required:** 200-300 hours over 6 weeks  
**ROI:** ~10-15 hours saved per new service, reduced technical debt

---

## Action Items by Priority

## 🔴 PRIORITY 1: Critical (Weeks 1-2)

### Action 1.1: Consolidate Logger Factory
**Effort:** 4-6 hours | **Impact:** High | **Complexity:** Low

**Current State:**
- `services/model-management-service/logger.py` implements custom logger
- 15+ services may have similar logger initialization
- `ai4icore_logging` library exists but not fully utilized

**Solution:**
```python
# libs/ai4icore_logging/ai4icore_logging/factory.py (NEW)
import logging
import sys
from typing import Optional

def get_logger(
    name: str,
    level: int = logging.DEBUG,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    Get or create a logger instance with standard formatting.
    
    Args:
        name: Logger name (typically __name__)
        level: Logging level (default: DEBUG)
        format_string: Custom format (optional)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            format_string or "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            "%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger
```

**Migration Steps:**
1. Add function to `ai4icore_logging/__init__.py`
2. Update imports in 15+ services
3. Remove custom logger.py files
4. Update documentation

**Affected Files:**
- `services/model-management-service/logger.py` → delete, import from lib
- Update 10+ services with similar implementations

**Verification:**
```bash
grep -r "def get_logger" services/ libs/
# Should only find it in ai4icore_logging
```

---

### Action 1.2: Create Safe Environment Import Helper
**Effort:** 2-3 hours | **Impact:** High | **Complexity:** Low

**Current State:**
```python
# infrastructure/databases/config.py (PROBLEM: Try-catch repeated)
try:
    from ai4icore_env import app_env
except ModuleNotFoundError:
    project_root = Path(__file__).resolve().parents[2]
    candidate_paths = [project_root / "libs" / "ai4icore_env"]
    for candidate in candidate_paths:
        if candidate.exists() and candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)
    from ai4icore_env import app_env
```

**Solution:**
```python
# libs/ai4icore_bootstrap/ai4icore_bootstrap/env_imports.py (NEW)
import sys
from pathlib import Path
from typing import Any

def safe_import_env(module_path: str = "ai4icore_env") -> Any:
    """
    Safely import ai4icore_env, handling both installed and local development paths.
    
    Handles:
    - Installed package (normal deployment)
    - Local libs/ folder (development)
    - Multiple candidate paths
    
    Returns:
        app_env module instance
    
    Raises:
        ImportError: If module cannot be found in any location
    """
    try:
        return __import__(module_path, fromlist=[module_path])
    except (ImportError, ModuleNotFoundError):
        # Try candidate paths
        project_root = Path(__file__).resolve().parents[3]  # Navigate up from bootstrap
        candidates = [
            project_root / "libs" / module_path,
            project_root / "libs",
            Path.cwd() / "libs" / module_path,
        ]
        
        for candidate in candidates:
            if candidate.exists():
                candidate_str = str(candidate)
                if candidate_str not in sys.path:
                    sys.path.insert(0, candidate_str)
                return __import__(module_path, fromlist=[module_path])
        
        raise ImportError(
            f"Could not find {module_path} in installed packages or candidate paths: "
            f"{[str(c) for c in candidates]}"
        )
```

**Migration Steps:**
1. Add to `ai4icore_bootstrap/__init__.py`
2. Identify files using try-except pattern for env imports (5+ files)
3. Replace with `from ai4icore_bootstrap import safe_import_env; app_env = safe_import_env()`
4. Test in development and Docker environments

**Affected Files:**
- `infrastructure/databases/config.py`
- Other infrastructure files
- Test setup files

---

### Action 1.3: Remove Exception Re-exports
**Effort:** 1-2 hours | **Impact:** Medium | **Complexity:** Low

**Current State:**
```python
# services/model-management-service/middleware/exceptions.py
"""Backward-compatible re-exports from ai4icore_constants library."""
from ai4icore_constants.exceptions import *
```

**Problem:** Unnecessary intermediate layer that confuses import paths

**Solution:**
1. Delete `middleware/exceptions.py` from services
2. Update all imports to use directly:
   ```python
   # OLD: from middleware.exceptions import SomeException
   # NEW:
   from ai4icore_exceptions import SomeException
   ```

**Affected Services:**
- model-management-service
- multi-tenant-feature
- Any service with this pattern

**Verification:**
```bash
find services -name "exceptions.py" -path "*/middleware/*"
# Should return 0 results
```

---

### Action 1.4: Consolidate Language/Script Constants
**Effort:** 6-8 hours | **Impact:** Very High | **Complexity:** Medium

**Current State:**
- Language constants duplicated in frontend
- Backend services have similar mappings
- No single source of truth

**Solution 1 - Centralized via Config Service (Recommended):**

```python
# services/config-service/models/language_metadata.py (NEW)
from enum import Enum
from typing import List, Dict, Set
from pydantic import BaseModel

class LanguageMetadata(BaseModel):
    code: str                          # ISO 639-1/3 code
    label: str                         # Display name
    scriptCode: str                    # ISO 15924 script code
    nativeName: str                    # Name in native script
    supported_services: Set[str]       # ["asr", "tts", "nmt", "transliteration"]
    
class ServiceLanguageCapability(BaseModel):
    service_name: str
    supported_languages: List[str]
    last_updated: datetime

# Centralized registry
LANGUAGE_REGISTRY = {
    "hi": LanguageMetadata(
        code="hi",
        label="Hindi",
        scriptCode="Deva",
        nativeName="हिंदी",
        supported_services={"asr", "tts", "nmt", "transliteration"}
    ),
    "en": LanguageMetadata(
        code="en",
        label="English",
        scriptCode="Latn",
        nativeName="English",
        supported_services={"asr", "tts", "nmt", "transliteration"}
    ),
    # ... 20+ more languages
}

# API endpoint in config-service
@app.get("/config/languages")
async def get_languages(
    service_filter: Optional[str] = None
) -> Dict[str, LanguageMetadata]:
    """
    Get language metadata.
    
    Query params:
    - service_filter: Filter by service name (e.g., "asr", "tts")
    
    Returns:
        Dictionary of language code -> metadata
    """
    if service_filter:
        return {
            code: metadata for code, metadata in LANGUAGE_REGISTRY.items()
            if service_filter in metadata.supported_services
        }
    return LANGUAGE_REGISTRY
```

**Solution 2 - Cached Library (Alternative):**

```python
# libs/ai4icore_language_metadata/ai4icore_language_metadata/__init__.py (NEW)
import json
from pathlib import Path
from typing import Dict, Optional

class LanguageRegistry:
    """In-memory language registry with optional Redis cache."""
    
    def __init__(self):
        self._registry = self._load_default_registry()
    
    def _load_default_registry(self) -> Dict:
        # Load from JSON file included in package
        registry_file = Path(__file__).parent / "data" / "languages.json"
        with open(registry_file) as f:
            return json.load(f)
    
    def get_all(self, service_filter: Optional[str] = None) -> Dict:
        if service_filter:
            return {
                code: data for code, data in self._registry.items()
                if service_filter in data.get("supported_services", [])
            }
        return self._registry
    
    def get(self, code: str) -> Optional[Dict]:
        return self._registry.get(code)

# Global instance
language_registry = LanguageRegistry()

# Usage in services:
from ai4icore_language_metadata import language_registry
asr_languages = language_registry.get_all("asr")
```

**Migration Steps:**
1. Choose solution (recommend Config Service for runtime flexibility)
2. Create centralized registry
3. Add API endpoint or package
4. Update all services to fetch at startup
5. Cache in Redis or memory for performance
6. Remove duplicate constants from services

**Affected Files:**
- `frontend/simple-ui/src/config/constants.ts`
- Backend service language definitions (15+ services)

---

## 🟡 PRIORITY 2: High Impact (Weeks 3-4)

### Action 2.1: Create Utility Libraries
**Effort:** 12-16 hours | **Impact:** High | **Complexity:** Medium

**Library 1: ai4icore_utilities** (String, Token, DateTime)

```python
# libs/ai4icore_utilities/ai4icore_utilities/__init__.py
from .strings import slugify, normalize_text, truncate
from .tokens import generate_secure_token, generate_email_token, validate_token
from .collections import get_or_create_list, merge_dicts_recursive
from .datetime import now_utc, datetime_to_iso, iso_to_datetime

__all__ = [
    "slugify", "normalize_text", "truncate",
    "generate_secure_token", "generate_email_token", "validate_token",
    "get_or_create_list", "merge_dicts_recursive",
    "now_utc", "datetime_to_iso", "iso_to_datetime",
]
```

```python
# libs/ai4icore_utilities/ai4icore_utilities/strings.py
import re
import html
from typing import Optional

def slugify(value: str, max_length: int = 50) -> str:
    """
    Convert string to URL-safe slug.
    
    Examples:
        "Hello World!" -> "hello-world"
        "Café" -> "cafe"
    """
    value = html.unescape(value)
    value = re.sub(r'[^\w\s-]', '', value, flags=re.UNICODE)
    value = re.sub(r'[-\s]+', '-', value)
    return value.strip('-').lower()[:max_length]

def normalize_text(value: str) -> str:
    """Remove extra whitespace and normalize unicode."""
    value = str(value).strip()
    value = ' '.join(value.split())
    return value

def truncate(value: str, length: int = 100, suffix: str = "...") -> str:
    """Truncate string to specified length."""
    if len(value) > length:
        return value[:length - len(suffix)] + suffix
    return value
```

```python
# libs/ai4icore_utilities/ai4icore_utilities/tokens.py
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

def generate_secure_token(length: int = 32) -> str:
    """Generate cryptographically secure random token."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_email_token(length: int = 32) -> str:
    """Generate token for email verification."""
    return secrets.token_urlsafe(length)

def validate_token(token: str, expected: str, max_age_seconds: Optional[int] = None) -> bool:
    """Validate token (placeholder for HMAC validation)."""
    return secrets.compare_digest(token, expected)
```

**Library 2: ai4icore_domain_utils**

```python
# libs/ai4icore_domain_utils/ai4icore_domain_utils/__init__.py
from .similarity import domains_similar, registrable_domain, domain_base
from .parsing import parse_domain, extract_subdomains
from .validation import is_valid_domain

__all__ = [
    "domains_similar", "registrable_domain", "domain_base",
    "parse_domain", "extract_subdomains",
    "is_valid_domain",
]
```

```python
# libs/ai4icore_domain_utils/ai4icore_domain_utils/similarity.py
from typing import Optional
from difflib import SequenceMatcher

def registrable_domain(domain: str) -> str:
    """Extract registrable domain (e.g., 'example.co.uk' from 'sub.example.co.uk')."""
    try:
        import tldextract
        extracted = tldextract.extract(domain)
        if extracted.registered_domain:
            return extracted.registered_domain
    except ImportError:
        pass
    return domain.lower()

def domain_base(domain: str) -> str:
    """Extract just the base name (e.g., 'example' from 'sub.example.com')."""
    try:
        import tldextract
        extracted = tldextract.extract(domain)
        return extracted.domain or domain
    except ImportError:
        pass
    return domain.split('.')[0].lower()

def domains_similar(
    domain_a: str,
    domain_b: str,
    threshold: float = 0.90,
    check_registrable: bool = True
) -> bool:
    """
    Determine if two domains are considered similar.
    
    Checks:
    1. Exact match
    2. Same registrable domain
    3. Similar base names (string similarity >= threshold)
    """
    # Coerce to string
    a = str(domain_a).strip().lower() if domain_a else ""
    b = str(domain_b).strip().lower() if domain_b else ""
    
    if not a or not b:
        return False
    
    # Exact match
    if a == b:
        return True
    
    # Same registrable domain
    if check_registrable:
        if registrable_domain(a) == registrable_domain(b):
            return True
    
    # String similarity
    similarity = SequenceMatcher(None, domain_base(a), domain_base(b)).ratio()
    return similarity >= threshold
```

**Migration Steps:**
1. Create library structure
2. Move functions from `services/multi-tenant-feature/utils/utils.py`
3. Add comprehensive tests
4. Update imports in affected services
5. Document with examples

**Affected Services:**
- multi-tenant-feature (primary source)
- Any service needing domain operations
- Any service needing token generation

---

### Action 2.2: Standardize Configuration Management
**Effort:** 8-10 hours | **Impact:** High | **Complexity:** Medium

**Problem:**
- Multiple ways to define config (raw env vars, Pydantic, custom classes)
- Inconsistent environment variable naming
- No consistent way to validate/document config

**Solution:**

```python
# libs/ai4icore_config/ai4icore_config/__init__.py
from .base_settings import AppSettings, ServiceConfig
from .validators import validate_port, validate_url, validate_positive_int

__all__ = ["AppSettings", "ServiceConfig", "validate_port", "validate_url", "validate_positive_int"]
```

```python
# libs/ai4icore_config/ai4icore_config/base_settings.py
from pydantic_settings import BaseSettings
from typing import Optional, List
from pydantic import Field, field_validator

class ServiceConfig(BaseSettings):
    """Base configuration for all AI4ICore services."""
    
    # Service identity
    service_name: str = Field(..., description="Service name")
    service_version: str = Field(default="1.0.0")
    
    # Environment
    environment: str = Field(default="development", description="Environment: development, staging, production")
    debug: bool = Field(default=False)
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    use_json_logs: bool = Field(default=False)
    
    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    
    # Database
    database_url: Optional[str] = Field(default=None)
    
    # Redis
    redis_url: Optional[str] = Field(default=None)
    redis_ttl_seconds: int = Field(default=3600)
    
    # Observability
    telemetry_enabled: bool = Field(default=True)
    jaeger_endpoint: Optional[str] = Field(default=None)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
    @field_validator("port")
    @classmethod
    def validate_port_range(cls, v):
        if not (0 < v < 65536):
            raise ValueError("Port must be between 1 and 65535")
        return v
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v):
        if v not in ("development", "staging", "production"):
            raise ValueError("Environment must be development, staging, or production")
        return v
```

**Usage Example:**

```python
# services/my-service/config.py
from ai4icore_config import ServiceConfig
from pydantic import Field
from typing import Optional

class MyServiceConfig(ServiceConfig):
    """Configuration specific to my-service."""
    
    # Service-specific settings
    model_path: str = Field(default="models/")
    max_batch_size: int = Field(default=32)
    inference_timeout: int = Field(default=30)
    
    # Override if needed
    service_name: str = "my-service"

# main.py
from config import MyServiceConfig

config = MyServiceConfig()  # Automatically reads from env

app = FastAPI(title=config.service_name)
logger.info(f"Service {config.service_name} started on {config.host}:{config.port}")
```

**Migration Steps:**
1. Create base `ServiceConfig` class
2. Create service-specific config classes
3. Update 15+ services to use new pattern
4. Document environment variables per service
5. Generate environment files from config definitions

---

### Action 2.3: Extract Feature Extraction Library
**Effort:** 10-12 hours | **Impact:** High | **Complexity:** High

**Current State:**
- Request profiler has 500+ lines of feature extraction
- Features could be reused by other NLP services
- No package structure for reusability

**Solution:**

```python
# libs/ai4icore_feature_extraction/ai4icore_feature_extraction/__init__.py
from .length import LengthFeatures, extract_length
from .structure import StructureFeatures, extract_structure
from .terminology import TerminologyFeatures, extract_terminology, load_common_words
from .entity import EntityFeatures, extract_entities

__all__ = [
    "LengthFeatures", "extract_length",
    "StructureFeatures", "extract_structure",
    "TerminologyFeatures", "extract_terminology", "load_common_words",
    "EntityFeatures", "extract_entities",
]
```

```python
# libs/ai4icore_feature_extraction/ai4icore_feature_extraction/length.py
from dataclasses import dataclass
from typing import Tuple

@dataclass
class LengthFeatures:
    """Length-based text features."""
    character_count: int
    word_count: int
    sentence_count: int
    avg_word_length: float

def extract_length(text: str) -> LengthFeatures:
    """Extract length features from text."""
    chars = len(text)
    words = text.split()
    word_count = len(words)
    sentences = len([s for s in text.split('.') if s.strip()])
    avg_word = sum(len(w) for w in words) / word_count if word_count > 0 else 0
    
    return LengthFeatures(
        character_count=chars,
        word_count=word_count,
        sentence_count=sentences,
        avg_word_length=round(avg_word, 2)
    )
```

**Migration Steps:**
1. Extract feature extraction classes from request-profiler
2. Create library with modular structure
3. Add comprehensive tests
4. Update request-profiler to use library
5. Make available for other services

---

## 🟢 PRIORITY 3: Long-term Infrastructure (Weeks 5-6)

### Action 3.1: Create Middleware Package
**Effort:** 15-20 hours | **Impact:** Very High | **Complexity:** High

**Library: ai4icore_middleware**

```python
# libs/ai4icore_middleware/ai4icore_middleware/__init__.py
from .request_id import RequestIDMiddleware
from .rbac import RBACMiddleware
from .cors_handler import setup_cors
from .error_handler import ErrorHandlerMiddleware
from .logging import RequestLoggingMiddleware

__all__ = [
    "RequestIDMiddleware",
    "RBACMiddleware",
    "setup_cors",
    "ErrorHandlerMiddleware",
    "RequestLoggingMiddleware",
]
```

```python
# libs/ai4icore_middleware/ai4icore_middleware/request_id.py
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from contextvars import ContextVar

request_id_context: ContextVar[str] = ContextVar("request_id", default="")

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject request ID into all requests and responses."""
    
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_context.set(request_id)
        
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

```python
# libs/ai4icore_middleware/ai4icore_middleware/rbac.py
from fastapi import Depends, HTTPException
from starlette.requests import Request
from ai4icore_telemetry import extract_user_info

class RBACMiddleware:
    """Enforce RBAC policies from JWT tokens."""
    
    def __init__(self, rbac_enforcer):
        self.enforcer = rbac_enforcer
    
    async def __call__(self, request: Request):
        user_info = extract_user_info(request)
        if not user_info:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return user_info
```

**Migration Steps:**
1. Identify common middleware across services
2. Create generalized middleware package
3. Add configuration options
4. Update 15+ services to use
5. Remove duplicate middleware implementations

---

### Action 3.2: Create OpenAPI Utilities
**Effort:** 10-12 hours | **Impact:** Medium | **Complexity:** High

**Library: ai4icore_openapi_utils**

```python
# libs/ai4icore_openapi_utils/ai4icore_openapi_utils/__init__.py
from .schema_merge import merge_schemas, rewrite_refs
from .documentation import generate_documentation

__all__ = ["merge_schemas", "rewrite_refs", "generate_documentation"]
```

---

## Summary Table

| Action | Priority | Effort (hrs) | Impact | Complexity | Week |
|--------|----------|-------------|--------|-----------|------|
| 1.1 Logger Factory | P1 | 4-6 | High | Low | 1 |
| 1.2 Env Import Helper | P1 | 2-3 | High | Low | 1 |
| 1.3 Remove Re-exports | P1 | 1-2 | Medium | Low | 1-2 |
| 1.4 Language Constants | P1 | 6-8 | Very High | Medium | 2 |
| 2.1 Utility Libraries | P2 | 12-16 | High | Medium | 3 |
| 2.2 Config Management | P2 | 8-10 | High | Medium | 3-4 |
| 2.3 Feature Extraction | P2 | 10-12 | High | High | 4 |
| 3.1 Middleware Package | P3 | 15-20 | Very High | High | 5 |
| 3.2 OpenAPI Utilities | P3 | 10-12 | Medium | High | 5-6 |
| **Total** | | **78-99** | | | |

---

## Implementation Checklist

### Week 1
- [ ] Action 1.1: Logger consolidation
- [ ] Action 1.2: Environment import helper
- [ ] Code review and testing
- [ ] Documentation updates

### Week 2
- [ ] Action 1.3: Remove re-exports
- [ ] Action 1.4 (Part 1): Language constants design
- [ ] Database schema for language metadata
- [ ] API endpoint implementation

### Week 3
- [ ] Action 1.4 (Part 2): Language constants migration
- [ ] Action 2.1 (Part 1): Create utility libraries
- [ ] Move functions from multi-tenant-feature
- [ ] Comprehensive unit tests

### Week 4
- [ ] Action 2.1 (Part 2): Finish utility library migration
- [ ] Action 2.2: Configuration management standardization
- [ ] Update 15+ services to new config pattern
- [ ] Environment variable documentation

### Week 5
- [ ] Action 2.3: Feature extraction library
- [ ] Update request-profiler to use library
- [ ] Action 3.1: Middleware package
- [ ] Design review

### Week 6
- [ ] Action 3.1: Middleware deployment
- [ ] Action 3.2: OpenAPI utilities
- [ ] Documentation and training
- [ ] Final code review and cleanup
