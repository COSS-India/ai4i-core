"""update service and model column config

The service-column config row seeded in a3c5e7f9b1d4 used a placeholder
key/label/required shape that nothing ever read. This replaces configs.data
for type='service-column' with the actual column-definition shape consumed
by the services list UI (id/label/filter/sortable/mandatory/filterable/
defaultVisible), matching the payload the frontend already renders against.

It also updates configs.data for type='model-column': version, taskType
and providerName move from required=True to required=False, matching the
model list UI which no longer treats those columns as mandatory.

Only the data column is updated for either row; id, is_default,
created_by/at and updated_by/at are left untouched.

Both rows are editable via PUT /config/{id}. upgrade() and downgrade()
overwrite configs.data unconditionally, so any manual edit made between
this migration running and a later downgrade (or re-run) is replaced by
the hardcoded value below, not preserved or restored.

Revision ID: b4d6f8a0c2e4
Revises: 445916bf95f9
Create Date: 2026-11-18

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4d6f8a0c2e4"
down_revision: Union[str, None] = "445916bf95f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SERVICE_COLUMN_TYPE = "service-column"
_MODEL_COLUMN_TYPE = "model-column"

_OLD_MODEL_COLUMN_DATA = [
    {"key": "name", "label": "Name", "required": True},
    {"key": "version", "label": "Version", "required": True},
    {"key": "taskType", "label": "Task Type", "required": True},
    {"key": "providerName", "label": "Provider Name", "required": True},
    {"key": "status", "label": "Status", "required": False},
    {"key": "createdAt", "label": "Created At", "required": False},
    {"key": "noOfServices", "label": "No. of Services", "required": False},
    {"key": "actions", "label": "Actions", "required": True},
]

_NEW_MODEL_COLUMN_DATA = [
    {"key": "name", "label": "Name", "required": True},
    {"key": "version", "label": "Version", "required": True},
    {"key": "taskType", "label": "Task Type", "required": True},
    {"key": "providerName", "label": "Provider Name", "required": True},
    {"key": "status", "label": "Status", "required": False},
    {"key": "createdAt", "label": "Created At", "required": False},
    {"key": "noOfServices", "label": "No. of Services", "required": False},
    {"key": "actions", "label": "Actions", "required": True},
]

_OLD_SERVICE_COLUMN_DATA = [
    {"key": "name", "label": "Name", "required": True},
    {"key": "modelTaskType", "label": "Model Task Type", "required": False},
    {"key": "tier", "label": "Tier", "required": False},
    {"key": "status", "label": "Status", "required": False},
    {"key": "createdAt", "label": "Created At", "required": False},
    {"key": "modelName", "label": "Model Name", "required": False},
    {"key": "serviceId", "label": "Service ID", "required": False},
    {"key": "inputPrice", "label": "Input Price", "required": False},
    {"key": "outputPrice", "label": "Output Price", "required": False},
    {"key": "cachedInputPrice", "label": "Cached Input Price", "required": False},
    {"key": "publishedOn", "label": "Published On", "required": False},
    {"key": "actions", "label": "Actions", "required": True},
]

_NEW_SERVICE_COLUMN_DATA = [
    {
        "columns": [
            {
                "id": "name",
                "label": "Service Name",
                "filter": {"type": "text", "params": ["name"], "options": None},
                "sortable": True,
                "mandatory": True,
                "filterable": True,
                "defaultVisible": True,
            },
            {
                "id": "actions",
                "label": "Actions",
                "filter": None,
                "sortable": False,
                "mandatory": True,
                "filterable": False,
                "defaultVisible": True,
            },
            {
                "id": "task_type",
                "label": "Task Type",
                "filter": {
                    "type": "multi_select",
                    "params": ["task_types"],
                    "options": [
                        {"label": "asr", "value": "asr"},
                        {"label": "audio-lang-detection", "value": "audio-lang-detection"},
                        {"label": "language-detection", "value": "language-detection"},
                        {"label": "language-diarization", "value": "language-diarization"},
                        {"label": "llm", "value": "llm"},
                        {"label": "ner", "value": "ner"},
                        {"label": "nmt", "value": "nmt"},
                        {"label": "ocr", "value": "ocr"},
                        {"label": "pipeline", "value": "pipeline"},
                        {"label": "speaker-diarization", "value": "speaker-diarization"},
                        {"label": "transliteration", "value": "transliteration"},
                        {"label": "tts", "value": "tts"},
                    ],
                },
                "sortable": True,
                "mandatory": True,
                "filterable": True,
                "defaultVisible": True,
            },
            {
                "id": "model_name",
                "label": "Model Name",
                "filter": {"type": "text", "params": ["model_name"], "options": None},
                "sortable": True,
                "mandatory": True,
                "filterable": True,
                "defaultVisible": True,
            },
            {
                "id": "tier",
                "label": "Tier",
                "filter": {
                    "type": "multi_select",
                    "params": ["tier_ids"],
                    "options": None,
                },
                "sortable": True,
                "mandatory": True,
                "filterable": True,
                "defaultVisible": True,
            },
            {
                "id": "status",
                "label": "Status",
                "filter": {
                    "type": "single_select",
                    "params": ["is_published"],
                    "options": [
                        {"label": "Published", "value": "true"},
                        {"label": "Unpublished", "value": "false"},
                    ],
                },
                "sortable": True,
                "mandatory": False,
                "filterable": True,
                "defaultVisible": True,
            },
            {
                "id": "created_at",
                "label": "Created At",
                "filter": {
                    "type": "date_range",
                    "params": ["created_from", "created_to"],
                    "options": None,
                },
                "sortable": True,
                "mandatory": False,
                "filterable": True,
                "defaultVisible": True,
            },
            {
                "id": "service_id",
                "label": "Service ID",
                "filter": {"type": "text", "params": ["service_id"], "options": None},
                "sortable": True,
                "mandatory": False,
                "filterable": True,
                "defaultVisible": False,
            },
            {
                "id": "input_price",
                "label": "Input Price",
                "filter": None,
                "sortable": True,
                "mandatory": False,
                "filterable": False,
                "defaultVisible": False,
            },
            {
                "id": "output_price",
                "label": "Output Price",
                "filter": None,
                "sortable": True,
                "mandatory": False,
                "filterable": False,
                "defaultVisible": False,
            },
            {
                "id": "cached_input_price",
                "label": "Cached Input Price",
                "filter": None,
                "sortable": True,
                "mandatory": False,
                "filterable": False,
                "defaultVisible": False,
            },
            {
                "id": "published_at",
                "label": "Published On",
                "filter": {
                    "type": "date_range",
                    "params": ["published_from", "published_to"],
                    "options": None,
                },
                "sortable": True,
                "mandatory": False,
                "filterable": True,
                "defaultVisible": False,
            },
        ]
    }
]


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE configs SET data = CAST(:d AS jsonb) WHERE type = :t"),
        {"t": _SERVICE_COLUMN_TYPE, "d": json.dumps(_NEW_SERVICE_COLUMN_DATA)},
    )
    conn.execute(
        sa.text("UPDATE configs SET data = CAST(:d AS jsonb) WHERE type = :t"),
        {"t": _MODEL_COLUMN_TYPE, "d": json.dumps(_NEW_MODEL_COLUMN_DATA)},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE configs SET data = CAST(:d AS jsonb) WHERE type = :t"),
        {"t": _SERVICE_COLUMN_TYPE, "d": json.dumps(_OLD_SERVICE_COLUMN_DATA)},
    )
    conn.execute(
        sa.text("UPDATE configs SET data = CAST(:d AS jsonb) WHERE type = :t"),
        {"t": _MODEL_COLUMN_TYPE, "d": json.dumps(_OLD_MODEL_COLUMN_DATA)},
    )
