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
    {"key": "version", "label": "Version", "required": False},
    {"key": "taskType", "label": "Task Type", "required": False},
    {"key": "providerName", "label": "Provider Name", "required": False},
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
                "id": "tier",
                "label": "Tier",
                "filter": {
                    "type": "multi_select",
                    "params": ["tier_ids"],
                    "options": [
                        {"label": "3411 Test", "value": "fd2a5b16-e695-4a74-9a6e-6f5f1ae77fee"},
                        {"label": "AB", "value": "21dfbac1-9b48-4869-aac7-d04876b77e59"},
                        {"label": "Alerts v2 LLM Budget Check", "value": "3546a6d1-598b-40d2-9028-07c000f86b3e"},
                        {"label": "Alerts v2 LLM Quota Check", "value": "d52f6189-8d71-4dab-8701-a4cccdae1b18"},
                        {"label": "Ambarish test tier (Api key rotation)", "value": "6c8c8bf4-9adc-454c-9111-6b4542c05165"},
                        {"label": "Basic Plan", "value": "71afd1cb-e154-47f2-9297-a6abc3f5ad49"},
                        {"label": "Bharathi tier 1", "value": "54380fb3-c96a-4153-9cb9-2623d2bcad80"},
                        {"label": "Budget Quota Notification check", "value": "8df2959c-c16c-417e-8900-82ccc50c645a"},
                        {"label": "Dev Test tier", "value": "8e5de806-ae06-4c50-a845-7bfd64534e2c"},
                        {"label": "Diamond-22", "value": "0cf9c496-bbac-4aff-8662-196c99939686"},
                        {"label": "Economy-1", "value": "5728d4d7-dc0d-455f-88c2-830529a704bc"},
                        {"label": "Economy-tier", "value": "a9c61d38-2400-46f4-8273-6574c43ec312"},
                        {"label": "Emerald-22", "value": "4aa16033-c158-4769-acd2-9ce58a6a4b9e"},
                        {"label": "Gold-22", "value": "87740b8e-5330-4ecc-8ebf-dc1e3446c3b2"},
                        {"label": "QA Dev Test Tier", "value": "b820accb-ad0b-4583-839a-474814652262"},
                        {"label": "RateLimit", "value": "63b7a3cc-1644-45d8-9177-8e3d92c64ae9"},
                        {"label": "SHORT TIER", "value": "998124ee-a3cf-4fb9-90b1-c7da6ccf43ec"},
                        {"label": "Standard", "value": "3cb1bb8b-30b9-4ed2-97ae-26fe2f9cf204"},
                        {"label": "Test", "value": "98e9a5aa-57d7-4407-ae0b-96e8afb685f3"},
                        {"label": "Test 16", "value": "51972718-1ca1-4575-a3b4-351a9380c4d8"},
                        {"label": "Testing Alignment", "value": "90b09209-0aad-4dad-bf3b-957e090399bb"},
                        {"label": "Testing Tier Statuses", "value": "afe930e7-0656-41d6-98fc-0e92bba93f3e"},
                        {"label": "Testing Tier Statuss", "value": "68f54936-d27b-454c-a154-8bfcefa62576"},
                        {"label": "Tier Limit Testing", "value": "1eb17ae0-1baa-4471-b5bc-56445e352a09"},
                        {"label": "Token Pricing Check Tier", "value": "a9e9ef55-3ed5-4b54-94a8-404d6bdaf3ad"},
                        {"label": "Ultra LLM", "value": "c755daa5-49e2-49d4-9a25-c8e620f9524d"},
                        {"label": "asr-tier-1", "value": "a571685a-5112-4732-8240-88eea0ff0e2b"},
                        {"label": "check", "value": "2758879d-9ec0-4fab-9d09-af22abbcaae7"},
                        {"label": "nmt-tier-1", "value": "ca47ccb0-d200-49d0-90f3-be7d45e8aa5a"},
                        {"label": "test", "value": "10cbe9d1-aef8-4332-a1fe-4abcd259dd89"},
                        {"label": "test tier quota", "value": "01130e5b-7720-40ad-ab58-c9026e7934da"},
                        {"label": "test tier quota 2", "value": "d2805150-45a2-45f7-8e99-d6bb4b3fc3b8"},
                        {"label": "test tier quota 3", "value": "66eac231-ad1c-4159-aec8-80ae381c18f1"},
                        {"label": "tts-tier-1", "value": "64d2c1c8-30fe-4aa8-a7dd-5b79c2359312"},
                    ],
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
                "id": "model_name",
                "label": "Model Name",
                "filter": {"type": "text", "params": ["model_name"], "options": None},
                "sortable": True,
                "mandatory": True,
                "filterable": True,
                "defaultVisible": False,
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
