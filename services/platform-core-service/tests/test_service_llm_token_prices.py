"""LLM token pricing on POST/PATCH /services: LLM services carry three prices
per unitSize tokens (costPerUnit = input, cachedInputCostPerUnit,
outputCostPerUnit), all mandatory; other task types carry costPerUnit only."""

from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.schemas.model_management.service import ServiceCreateRequest, ServiceUpdateRequest

_LONG_DESCRIPTION = "A service description long enough for the 25 character minimum."
_LLM_SCHEMA = [{"taskType": "llm", "request": {"messages": []}, "response": {"choices": []}}]

_CREATE_BASE = dict(
    serviceId="org/llm-service-1",
    name="org/llm-service-one",
    description=_LONG_DESCRIPTION,
    modelId="model-1",
    modelVersion="v1",
    inferenceEndPoint={
        "callbackUrl": "http://localhost:8080/v1/chat/completions",
        "infraDescription": "test-hw-cluster",
        "schema": _LLM_SCHEMA,
    },
    unitSize=1000,
    tierIds=["tier-1"],
)
_LLM_PRICES = dict(costPerUnit=100, cachedInputCostPerUnit=40, outputCostPerUnit=250)
_REQUIRED_MSG = "costPerUnit, cachedInputCostPerUnit and outputCostPerUnit are required for LLM services"
_LLM_ONLY_MSG = "cachedInputCostPerUnit and outputCostPerUnit apply only to LLM services"


def _create(**overrides):
    return ServiceCreateRequest(**{**_CREATE_BASE, "task": {"type": "llm"}, **_LLM_PRICES, **overrides})


def _asr_create(**overrides):
    asr_endpoint = {**_CREATE_BASE["inferenceEndPoint"], "schema": [{"taskType": "asr", "request": {}, "response": {}}]}
    return ServiceCreateRequest(
        **{**_CREATE_BASE, "inferenceEndPoint": asr_endpoint, "task": {"type": "asr"}, "costPerUnit": 0.01, **overrides}
    )


class TestCreate:
    def test_llm_with_all_three_prices(self) -> None:
        req = _create()
        assert (req.costPerUnit, req.cachedInputCostPerUnit, req.outputCostPerUnit) == (
            Decimal("100"), Decimal("40"), Decimal("250"),
        )

    def test_llm_via_deprecated_task_type_alias(self) -> None:
        payload = {**_CREATE_BASE, **_LLM_PRICES, "taskType": "llm"}
        assert ServiceCreateRequest(**payload).outputCostPerUnit == Decimal("250")

    @pytest.mark.parametrize("missing", ["cachedInputCostPerUnit", "outputCostPerUnit"])
    def test_llm_missing_a_new_price_is_rejected(self, missing) -> None:
        with pytest.raises(PydanticValidationError, match=_REQUIRED_MSG):
            _create(**{missing: None})

    def test_zero_prices_are_allowed(self) -> None:
        req = _create(costPerUnit=0, cachedInputCostPerUnit=0, outputCostPerUnit=0)
        assert req.cachedInputCostPerUnit == 0 and req.outputCostPerUnit == 0

    @pytest.mark.parametrize("field", ["cachedInputCostPerUnit", "outputCostPerUnit"])
    @pytest.mark.parametrize("value", [-1, 10_000_001])
    def test_price_out_of_range_is_rejected(self, field, value) -> None:
        with pytest.raises(PydanticValidationError, match=field):
            _create(**{field: value})

    def test_non_llm_without_new_prices(self) -> None:
        req = _asr_create()
        assert req.cachedInputCostPerUnit is None and req.outputCostPerUnit is None

    @pytest.mark.parametrize("field", ["cachedInputCostPerUnit", "outputCostPerUnit"])
    def test_non_llm_with_a_new_price_is_rejected(self, field) -> None:
        with pytest.raises(PydanticValidationError, match=_LLM_ONLY_MSG):
            _asr_create(**{field: 1})


_UPDATE_BILLING = dict(serviceId="org/llm-service-1", unitSize=1000, tierIds=["tier-1"])


class TestUpdate:
    def test_llm_with_full_billing_group(self) -> None:
        req = ServiceUpdateRequest(**_UPDATE_BILLING, taskType="llm", **_LLM_PRICES)
        assert req.cachedInputCostPerUnit == Decimal("40")

    def test_llm_missing_new_prices_lists_them(self) -> None:
        with pytest.raises(
            PydanticValidationError,
            match="cachedInputCostPerUnit, outputCostPerUnit must be provided together",
        ):
            ServiceUpdateRequest(**_UPDATE_BILLING, taskType="llm", costPerUnit=100)

    @pytest.mark.parametrize("missing", ["cachedInputCostPerUnit", "outputCostPerUnit"])
    def test_llm_missing_one_new_price_is_rejected(self, missing) -> None:
        with pytest.raises(PydanticValidationError, match=missing):
            ServiceUpdateRequest(**_UPDATE_BILLING, taskType="llm", **{**_LLM_PRICES, missing: None})

    def test_non_llm_with_a_new_price_is_rejected(self) -> None:
        with pytest.raises(PydanticValidationError, match=_LLM_ONLY_MSG):
            ServiceUpdateRequest(**_UPDATE_BILLING, taskType="asr", costPerUnit=1, outputCostPerUnit=2)

    def test_non_llm_billing_group_unchanged(self) -> None:
        req = ServiceUpdateRequest(**_UPDATE_BILLING, taskType="asr", costPerUnit=1)
        assert req.cachedInputCostPerUnit is None

    def test_publish_toggle_is_still_exempt(self) -> None:
        req = ServiceUpdateRequest(serviceId="org/llm-service-1", isPublished=True)
        assert req.isPublished is True
