# DRY Principle - Developer's Guide

## When Code is Duplicated (and How to Avoid It)

This guide helps developers identify DRY violations and consolidate code properly in the AI4I-Core platform.

---

## 1. Identifying Duplication

### Pattern 1: Copy-Paste Functions

**🔴 Violation:**
```python
# services/service-a/utils.py
def generate_token(length: int = 32) -> str:
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# services/service-b/utils.py
def generate_token(length: int = 32) -> str:
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))
```

**✅ Solution:**
```python
# libs/ai4icore_utilities/ai4icore_utilities/tokens.py
def generate_token(length: int = 32) -> str:
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# All services import from shared library
from ai4icore_utilities import generate_token
```

---

### Pattern 2: Similar Logic in Different Classes

**🔴 Violation:**
```python
# services/pii-service/main.py
class KnowledgeBase:
    async def refresh(self):
        for attempt in range(1, 11):
            try:
                async with db_pool.acquire() as conn:
                    rows = await conn.fetch(query)
                    for row in rows:
                        self.patterns[row['lang']] = process(row)
                    break
            except Exception as e:
                if attempt == 10:
                    raise

# services/ner-service/main.py
class EntityCache:
    async def refresh(self):
        for attempt in range(1, 11):
            try:
                async with db_pool.acquire() as conn:
                    rows = await conn.fetch(query2)
                    for row in rows:
                        self.entities[row['type']] = process(row)
                    break
            except Exception as e:
                if attempt == 10:
                    raise
```

**✅ Solution:**
```python
# libs/ai4icore_utilities/ai4icore_utilities/db_helpers.py
async def retry_db_operation(
    operation,
    max_retries: int = 10,
    db_pool = None
):
    """Execute database operation with automatic retry."""
    for attempt in range(1, max_retries + 1):
        try:
            if db_pool:
                async with db_pool.acquire() as conn:
                    return await operation(conn)
            else:
                return await operation()
        except Exception as e:
            if attempt == max_retries:
                raise
            await asyncio.sleep(1 * (2 ** (attempt - 1)))  # exponential backoff

# services/pii-service/main.py
class KnowledgeBase:
    async def refresh(self):
        async def load_patterns(conn):
            rows = await conn.fetch("SELECT ...")
            for row in rows:
                self.patterns[row['lang']] = process(row)
        
        await retry_db_operation(load_patterns, db_pool=self.db_pool)
```

---

### Pattern 3: Repeated Configuration

**🔴 Violation:**
```python
# services/asr-service/config.py
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
SERVICE_NAME = os.getenv("SERVICE_NAME", "asr-service")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0.0")

# services/tts-service/config.py
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
SERVICE_NAME = os.getenv("SERVICE_NAME", "tts-service")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0.0")
```

**✅ Solution:**
```python
# libs/ai4icore_config/ai4icore_config/base_settings.py
class ServiceConfig(BaseSettings):
    service_name: str
    service_version: str = "1.0.0"
    log_level: str = "INFO"
    debug: bool = False

# services/asr-service/config.py
class ASRServiceConfig(ServiceConfig):
    service_name: str = "asr-service"

config = ASRServiceConfig()
```

---

### Pattern 4: Model/Schema Duplication

**🔴 Violation:**
```python
# services/nmt-service/models.py
class TranslationRequest(BaseModel):
    source_text: str
    source_lang: str
    target_lang: str
    quality: Optional[str] = "standard"

# services/tts-service/models.py
class SynthesisRequest(BaseModel):
    text: str
    language: str
    voice: Optional[str] = None
    quality: Optional[str] = "standard"
```

**✅ Solution:**
```python
# libs/ai4icore_base_models/ai4icore_base_models/__init__.py
class BaseServiceRequest(BaseModel):
    """Base request for all inference services."""
    input_data: str
    quality: Optional[str] = "standard"
    
    class Config:
        json_schema_extra = {
            "example": {
                "input_data": "example text",
                "quality": "standard"
            }
        }

class BaseServiceResponse(BaseModel):
    """Base response for all inference services."""
    request_id: str
    status: str  # "success", "error"
    result: Optional[Dict] = None
    error: Optional[str] = None

# services/nmt-service/models.py
class TranslationRequest(BaseServiceRequest):
    source_lang: str
    target_lang: str

class TranslationResponse(BaseServiceResponse):
    result: Optional[Dict] = None  # {"translated_text": "..."}
```

---

### Pattern 5: Middleware/Decorator Duplication

**🔴 Violation:**
```python
# services/auth-service/main.py
@app.middleware("http")
async def add_request_id(request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

# services/pipeline-service/main.py
@app.middleware("http")
async def add_request_id(request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
```

**✅ Solution:**
```python
# libs/ai4icore_middleware/ai4icore_middleware/request_id.py
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

# All services
from ai4icore_middleware import RequestIDMiddleware
app.add_middleware(RequestIDMiddleware)
```

---

## 2. Creating Shared Libraries

### When to Create a Shared Library

**Create a shared library when:**
- ✅ Code appears in 2+ services
- ✅ Logic is domain-agnostic (not service-specific)
- ✅ It's used during service initialization
- ✅ Multiple teams need it

**Don't create a shared library when:**
- ❌ It's used by only one service
- ❌ It's highly specific to one domain
- ❌ It changes frequently for one service
- ❌ It would create circular dependencies

---

### Library Structure Template

```
libs/ai4icore_<library_name>/
├── pyproject.toml              # Package metadata
├── setup.py                    # Alternative to pyproject.toml
├── README.md                   # Usage documentation
├── CHANGELOG.md                # Version history
├── ai4icore_<library_name>/
│   ├── __init__.py             # Public API exports
│   ├── core.py                 # Main implementation
│   ├── models.py               # Pydantic models (if needed)
│   ├── errors.py               # Custom exceptions
│   ├── config.py               # Configuration classes
│   └── utils.py                # Helper functions
├── tests/
│   ├── __init__.py
│   ├── test_core.py
│   ├── test_models.py
│   └── conftest.py
└── data/                       # Optional: Data files included in package
    └── default_config.json
```

---

### Example: Creating ai4icore_utilities

**Step 1: Create directory structure**
```bash
mkdir -p libs/ai4icore_utilities/ai4icore_utilities/tests
```

**Step 2: Create pyproject.toml**
```toml
[build-system]
requires = ["setuptools>=65.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ai4icore-utilities"
version = "1.0.0"
description = "Common utility functions for AI4ICore services"
requires-python = ">=3.9"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=7.0", "pytest-asyncio>=0.20.0"]
```

**Step 3: Create __init__.py**
```python
# libs/ai4icore_utilities/ai4icore_utilities/__init__.py
"""
AI4ICore Utilities Library

Provides common utility functions for strings, tokens, collections, and datetime operations.
"""

from .strings import slugify, normalize_text, truncate
from .tokens import generate_secure_token, generate_email_token
from .collections import get_or_create_list, merge_dicts_recursive
from .datetime import now_utc, datetime_to_iso, iso_to_datetime

__version__ = "1.0.0"
__all__ = [
    "slugify",
    "normalize_text", 
    "truncate",
    "generate_secure_token",
    "generate_email_token",
    "get_or_create_list",
    "merge_dicts_recursive",
    "now_utc",
    "datetime_to_iso",
    "iso_to_datetime",
]
```

**Step 4: Create implementation files**
```python
# libs/ai4icore_utilities/ai4icore_utilities/strings.py
"""String manipulation utilities."""

import re
import html
from typing import Optional

def slugify(value: str, max_length: int = 50) -> str:
    """
    Convert string to URL-safe slug.
    
    Args:
        value: Input string
        max_length: Maximum length of output
    
    Returns:
        URL-safe slug
    
    Examples:
        >>> slugify("Hello World!")
        'hello-world'
        >>> slugify("Café Français", 10)
        'cafe-franç'
    """
    value = html.unescape(value)
    value = re.sub(r'[^\w\s-]', '', value, flags=re.UNICODE)
    value = re.sub(r'[-\s]+', '-', value)
    return value.strip('-').lower()[:max_length]
```

**Step 5: Create tests**
```python
# libs/ai4icore_utilities/tests/test_strings.py
import pytest
from ai4icore_utilities import slugify

def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"
    assert slugify("Hello World!") == "hello-world"

def test_slugify_max_length():
    result = slugify("hello world foo bar", max_length=10)
    assert len(result) <= 10

def test_slugify_unicode():
    assert slugify("Café") == "cafe"
```

**Step 6: Update service imports**
```python
# services/my-service/main.py
from ai4icore_utilities import slugify, generate_secure_token

# Use it directly
tenant_id = slugify(org_name)
verification_token = generate_secure_token()
```

---

## 3. Migration Checklist

### When Consolidating Existing Code

**Before moving code to shared library:**

- [ ] Identify all locations where code is duplicated (use grep/semantic search)
- [ ] Verify the code logic is identical (or only parameterized differences)
- [ ] Check for service-specific logic that needs to be abstracted
- [ ] Look for different implementations of the same concept
- [ ] Review error handling and edge cases across implementations

**Creating the shared library:**

- [ ] Create library directory structure
- [ ] Write comprehensive documentation with examples
- [ ] Implement comprehensive unit tests
- [ ] Set up CI/CD for the library
- [ ] Version the library (start with 1.0.0)

**Migrating services:**

- [ ] Update service dependency (pyproject.toml or requirements.txt)
- [ ] Update import statements
- [ ] Test the service with new imports
- [ ] Remove old/duplicate code
- [ ] Document any breaking changes

**Post-migration:**

- [ ] Run full test suite
- [ ] Update service documentation
- [ ] Create migration guide for other teams
- [ ] Remove old files from git history (if needed)
- [ ] Update CHANGELOG

---

## 4. DRY Principle Best Practices

### Rule 1: Extract Common Logic Early
Don't wait for 3 duplications; extract after 2.

### Rule 2: Use Inheritance for Shared Structure
```python
# ✅ Good: Share structure through inheritance
class BaseServiceResponse(BaseModel):
    request_id: str
    status: str
    result: Optional[Dict] = None
    error: Optional[str] = None

class TranslationResponse(BaseServiceResponse):
    result: Optional[Dict[str, str]] = None

# ❌ Bad: Copying structure
class TranslationResponse(BaseModel):
    request_id: str
    status: str
    result: Optional[Dict[str, str]] = None
    error: Optional[str] = None
```

### Rule 3: Use Composition Over Duplication
```python
# ✅ Good: Composition
class Logger:
    def get_logger(self, name: str): ...

class Service:
    def __init__(self):
        self.logger = Logger().get_logger(__name__)

# ❌ Bad: Each service implements logging
class Service:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # ... logging setup duplicated in every service
```

### Rule 4: Parameterize Variations
```python
# ✅ Good: Single function with parameters
def generate_token(
    length: int = 32,
    alphabet: str = string.ascii_letters + string.digits
) -> str:
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# ❌ Bad: Separate functions for each variation
def generate_token_32() -> str: ...
def generate_token_64() -> str: ...
def generate_uuid_token() -> str: ...
```

### Rule 5: Create Clear Abstractions
```python
# ✅ Good: Clear purpose and naming
def get_or_create_list_in_dict(d: Dict, key: str) -> List:
    """Get list from dict, creating empty list if key doesn't exist."""
    if key not in d:
        d[key] = []
    return d[key]

# ❌ Bad: Generic abstraction
def get_or_make(d, k):
    if k not in d:
        d[k] = []
    return d[k]
```

---

## 5. Testing Shared Libraries

### Unit Tests Required

```python
# libs/ai4icore_utilities/tests/test_tokens.py
import pytest
from ai4icore_utilities import generate_secure_token, generate_email_token

class TestTokenGeneration:
    def test_generate_secure_token_length(self):
        """Test token length is respected."""
        token = generate_secure_token(length=32)
        assert len(token) == 32
    
    def test_generate_secure_token_uniqueness(self):
        """Test tokens are unique."""
        tokens = {generate_secure_token() for _ in range(100)}
        assert len(tokens) == 100  # All unique
    
    def test_email_token_is_url_safe(self):
        """Test email tokens are URL-safe."""
        token = generate_email_token()
        # Should only contain URL-safe characters
        import re
        assert re.match(r'^[A-Za-z0-9_\-]+$', token)
```

### Integration Tests

```python
# libs/ai4icore_utilities/tests/test_integration.py
import pytest
from ai4icore_utilities import slugify, generate_secure_token

def test_tenant_id_generation(db):
    """Test complete tenant ID generation flow."""
    org_name = "Test Organization Inc."
    tenant_id = slugify(org_name)
    verification_token = generate_secure_token()
    
    # Should be able to use these in service
    assert tenant_id
    assert verification_token
    assert len(tenant_id) > 0
    assert len(verification_token) == 32
```

---

## 6. Documentation Template

### For New Shared Libraries

```markdown
# AI4ICore Utilities

Shared utility functions for all AI4ICore services.

## Installation

```bash
pip install ai4icore-utilities
```

## Usage

### String Utilities

```python
from ai4icore_utilities import slugify, normalize_text

# Convert to URL-safe slug
domain = slugify("My Cool Service")  # "my-cool-service"

# Normalize whitespace
text = normalize_text("Hello    World  ")  # "Hello World"
```

### Token Generation

```python
from ai4icore_utilities import generate_secure_token, generate_email_token

# Secure random token
token = generate_secure_token(length=32)

# Email verification token (URL-safe)
email_token = generate_email_token()
```

## API Reference

### Functions

#### slugify(value: str, max_length: int = 50) -> str
Convert string to URL-safe slug.

**Parameters:**
- value: Input string
- max_length: Maximum length of output

**Returns:** URL-safe slug

**Examples:**
```python
slugify("Hello World!")  # "hello-world"
slugify("Café Français")  # "cafe-francais"
```

## Contributing

When adding new utilities:
1. Add unit tests in tests/
2. Update documentation
3. Add to __all__ in __init__.py
4. Follow existing code style
```

---

## 7. Common Pitfalls to Avoid

### Pitfall 1: Over-abstraction
```python
# ❌ Don't: Too generic
def process_something(fn, data, options, callback):
    # 20 parameters, unclear purpose
    pass

# ✅ Do: Clear purpose
def extract_language_features(text: str) -> LanguageFeatures:
    pass
```

### Pitfall 2: Breaking Changes
```python
# ❌ Don't: Remove or change parameter names without warning
# Version 1.0.0:
def generate_token(length=32): ...

# Version 1.1.0 (BREAKS existing code):
def generate_token(token_length=32): ...  # Parameter renamed!

# ✅ Do: Support both for transition period
def generate_token(length=None, token_length=None):
    length = length or token_length or 32  # Backward compatible
```

### Pitfall 3: Circular Dependencies
```python
# ❌ Don't: Create circular imports
# ai4icore_utilities imports from ai4icore_exceptions
# ai4icore_exceptions imports from ai4icore_utilities

# ✅ Do: Design clear dependency hierarchy
# ai4icore_utilities (no deps)
# → ai4icore_exceptions (depends on utilities)
# → other libraries (depend on above)
```

### Pitfall 4: Missing Tests
```python
# ❌ Don't: Shared code without tests
def important_function(data):
    return process(data)  # No tests!

# ✅ Do: Comprehensive test coverage
def important_function(data: str) -> Result:
    """Process data and return result."""
    pass

# tests/test_important.py
def test_important_function_valid_input():
    result = important_function("valid")
    assert result.success
```

---

## 8. Checklist for Code Review

When reviewing code for DRY compliance:

- [ ] Is this logic already implemented elsewhere?
- [ ] Could this be parameterized instead of duplicated?
- [ ] Should this be in a shared library?
- [ ] Are there similar implementations with different names?
- [ ] Could inheritance reduce duplication?
- [ ] Is error handling duplicated across functions?
- [ ] Are configuration patterns consistent?
- [ ] Are test utilities reused?
- [ ] Could a base class eliminate duplication?
- [ ] Is this specific to one service or general-purpose?

---

## Questions?

Refer to the main DRY analysis document for detailed recommendations.
