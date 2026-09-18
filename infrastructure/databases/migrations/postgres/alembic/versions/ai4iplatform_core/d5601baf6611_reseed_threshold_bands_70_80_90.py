"""reseed_threshold_bands_70_80_90

6dc231d5809a already shipped to dev with threshold bands 50/75/90 for
QUOTA_THRESHOLD and BUDGET_THRESHOLD — editing that migration in place is
not safe once it has run somewhere, since a fresh environment and an
upgraded one would then disagree on what state ran at that revision. This
is a proper follow-up revision instead: it UPDATEs the two rows' existing
config.thresholds keys from 50/75/90 to 70/80/90, keeping the same
shipped-disabled (false) semantics 6dc231d5809a used — the bands exist so
an Adopter Admin can toggle them on, not because any fire by default.

Targets the two rows by name, not by config content, so this is
idempotent and safe to run whether or not an Adopter Admin has already
toggled any of the old keys on — a row already enabled at, say, 50% would
otherwise have no new key to move that "on" state to; renaming the keys
here also resets both rows to fully-disabled, matching a fresh reseed.

Revision ID: d5601baf6611
Revises: 8f754a278bee
Create Date: 2026-09-11 00:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd5601baf6611'
down_revision: Union[str, None] = '8f754a278bee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_THRESHOLDS = {"thresholds": {"50": False, "75": False, "90": False}}
_NEW_THRESHOLDS = {"thresholds": {"70": False, "80": False, "90": False}}

_NAMES = ["QUOTA_THRESHOLD", "BUDGET_THRESHOLD"]


def _set_thresholds(config: dict) -> None:
    names = ",".join(f"'{name}'" for name in _NAMES)
    config_json = json.dumps(config).replace("'", "''")
    op.execute(
        "UPDATE configs_notification_alert "
        f"SET config = '{config_json}'::jsonb "
        f"WHERE name IN ({names});"
    )


def upgrade() -> None:
    _set_thresholds(_NEW_THRESHOLDS)


def downgrade() -> None:
    _set_thresholds(_OLD_THRESHOLDS)
