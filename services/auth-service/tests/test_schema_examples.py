"""Every Swagger example wired via ``ConfigDict(json_schema_extra={"examples": [...]})``
must validate against its own model — otherwise the docs show a payload that
FastAPI would actually reject.

This walks every module under ``app.schemas`` plus ``app.routes.internal``
(the only route file with inline request models) and auto-discovers any
Pydantic model carrying declared examples, so a new example added anywhere
is covered automatically — no per-model registration needed here. Required
for any future PR that adds or edits a schema example.

One deliberate exception: id/uuid fields intentionally hold a bracketed
placeholder (``"<place your id here>"``) instead of a real-looking value —
a fabricated ID would misleadingly imply a record that exists in the
tester's own system, so those fields never type-round-trip and that is
expected. Only a validation error on a *non*-placeholder field indicates
real drift (a renamed/added/tightened field the example wasn't updated for).
"""

import importlib
import pkgutil
import re

import pytest
from pydantic import BaseModel, ValidationError

import app.routes.internal as internal_routes
import app.schemas as schemas_pkg

_PLACEHOLDER_RE = re.compile(r"^<.*>$")


def _is_placeholder(value) -> bool:
    if isinstance(value, str):
        return bool(_PLACEHOLDER_RE.match(value))
    if isinstance(value, list):
        return bool(value) and all(_is_placeholder(item) for item in value)
    return False


def _value_at_loc(data, loc):
    """Walk a pydantic error's ``loc`` tuple through the original example dict."""
    current = data
    for key in loc:
        try:
            current = current[key]
        except (KeyError, IndexError, TypeError):
            return None
    return current


def _discover_example_models():
    modules = [internal_routes]
    for _, module_name, _ in pkgutil.walk_packages(
        schemas_pkg.__path__, prefix=f"{schemas_pkg.__name__}."
    ):
        modules.append(importlib.import_module(module_name))

    seen = set()
    found = []
    for module in modules:
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if not (isinstance(obj, type) and issubclass(obj, BaseModel)):
                continue
            if obj in seen:
                continue
            examples = (obj.model_config or {}).get("json_schema_extra", {}).get("examples")
            if examples:
                seen.add(obj)
                found.append((obj, examples))
    return found


_MODELS_WITH_EXAMPLES = _discover_example_models()


@pytest.mark.parametrize(
    "model_cls,examples",
    _MODELS_WITH_EXAMPLES,
    ids=[cls.__name__ for cls, _ in _MODELS_WITH_EXAMPLES],
)
def test_schema_example_round_trips(model_cls, examples):
    """Every declared example must construct its model — a ValidationError is
    only acceptable when every offending field's example value is a
    deliberate ``<place your ... here>`` placeholder."""
    for example in examples:
        try:
            model_cls(**example)
        except ValidationError as exc:
            for error in exc.errors():
                value = _value_at_loc(example, error["loc"])
                assert _is_placeholder(value), (
                    f"{model_cls.__name__}: example fails validation at "
                    f"{'.'.join(str(p) for p in error['loc'])} with a non-placeholder "
                    f"value ({value!r}): {error['msg']}"
                )


def test_schema_examples_were_discovered():
    """Guards against the discovery walk silently finding nothing (e.g. a
    renamed package breaking pkgutil.walk_packages) and the parametrized
    test above becoming a vacuous pass."""
    assert len(_MODELS_WITH_EXAMPLES) > 0
