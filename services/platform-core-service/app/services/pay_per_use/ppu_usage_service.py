"""PPU usage service — computes spend summary from DB rows."""
from __future__ import annotations

from app.repositories.pay_per_use.ppu_usage_repository import PPUUsageRepository
from app.schemas.pay_per_use.usage import SpendItem, UsageSummaryResponse

# Display label per inference type; unit_size from mm_services drives the divisor.
_UNIT_LABELS: dict[str, str] = {
    "LLM": "M Tokens",
    "ASR": "Minutes",
    "NMT": "M Characters",
}
_CURRENCY = "INR"
_DEFAULT_UNIT_SIZE = 1_000_000


class PPUUsageService:
    def __init__(self, repo: PPUUsageRepository) -> None:
        self._repo = repo

    async def get_summary(self, billing_month: str) -> UsageSummaryResponse:
        rows = await self._repo.get_usage_with_pricing(billing_month)

        items: list[dict] = []
        for row in rows:
            units = row.total_units or 0
            unit_size = row.unit_size or _DEFAULT_UNIT_SIZE
            consumption = round(units / unit_size, 1)

            if row.unit_rate:
                spend = round(float(units) * float(row.unit_rate), 2)
            elif row.cost_per_unit:
                spend = round(float(consumption) * float(row.cost_per_unit), 2)
            else:
                spend = 0.0

            items.append({
                "modelTaskType": row.inference_name,
                "unit": _UNIT_LABELS.get(row.inference_name, row.inference_name),
                "consumption": consumption,
                "spend": spend,
            })

        total_spend = sum(i["spend"] for i in items)
        spend_items = [
            SpendItem(
                **i,
                percentage=round(i["spend"] / total_spend * 100, 1) if total_spend > 0 else 0.0,
            )
            for i in items
        ]

        return UsageSummaryResponse(
            billingPeriod=billing_month,
            totalSpend=round(total_spend, 2),
            currency=_CURRENCY,
            spendByModelTaskType=spend_items,
        )
