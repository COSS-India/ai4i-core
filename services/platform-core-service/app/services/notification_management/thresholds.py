"""Threshold bands of a catalog row (notification_alert_threshold).

Bands are rows, not JSON: one typed row per band. The catalog PATCH sends
the whole list; the editable bands are replaced wholesale (W2) and each
band's severity is counted from the top of the ladder — highest CRITICAL,
second WARNING, every other INFO. The fixed 100 % band of the EXHAUSTED rows
(editable = false) is never touched.
"""

from collections import defaultdict
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_management.notification_alert_threshold import NotificationAlertThreshold
from app.schemas.enums.notification_management import Severity


def severities_from_top(count: int) -> List[Severity]:
    """Severity of each band of an ascending ladder of ``count`` bands."""
    severities = [Severity.INFO] * count
    if count >= 1:
        severities[-1] = Severity.CRITICAL
    if count >= 2:
        severities[-2] = Severity.WARNING
    return severities


async def load_bands(
    session: AsyncSession, notification_ids: Sequence[int]
) -> Dict[int, List[NotificationAlertThreshold]]:
    """Editable bands per notification id, ascending by value."""
    bands: Dict[int, List[NotificationAlertThreshold]] = defaultdict(list)
    if not notification_ids:
        return bands
    result = await session.execute(
        select(NotificationAlertThreshold)
        .where(
            NotificationAlertThreshold.notification_id.in_(list(notification_ids)),
            NotificationAlertThreshold.editable.is_(True),
        )
        .order_by(NotificationAlertThreshold.notification_id, NotificationAlertThreshold.band_value)
    )
    for band in result.scalars().all():
        bands[band.notification_id].append(band)
    return bands


async def replace_bands(
    session: AsyncSession,
    notification_id: int,
    bands: Sequence[Tuple[Decimal, bool]],
    unit: str,
    actor: Optional[str],
) -> None:
    """W2: delete the editable bands, insert the new (value, active) list
    with severity counted from the top. Not committed here."""
    await session.execute(
        delete(NotificationAlertThreshold).where(
            NotificationAlertThreshold.notification_id == notification_id,
            NotificationAlertThreshold.editable.is_(True),
        )
    )
    ordered = sorted(bands, key=lambda band: band[0])
    severities = severities_from_top(len(ordered))
    session.add_all(
        NotificationAlertThreshold(
            notification_id=notification_id,
            band_value=value,
            unit=unit,
            severity=severity.value,
            active=active,
            editable=True,
            created_by=actor,
            updated_by=actor,
        )
        for (value, active), severity in zip(ordered, severities)
    )
