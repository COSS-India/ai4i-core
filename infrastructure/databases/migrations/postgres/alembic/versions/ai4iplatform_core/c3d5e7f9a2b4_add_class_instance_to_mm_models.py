"""add_class_instance_to_mm_models

Revision ID: c3d5e7f9a2b4
Revises: a1f2e3d4c5b6
Create Date: 2026-06-04 00:00:00.000000

Adds class_instance column to mm_models so each model row carries the name
of the TaskService class the inference-service should use when routing
requests to any service built on that model.  Backfills existing rows from
the task->>'type' JSONB field so existing deployments continue to work
without a code change.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d5e7f9a2b4"
down_revision: Union[str, None] = "a1f2e3d4c5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

# Mapping from task type stored in mm_models.task->>'type' to the
# TaskService class name used by the inference-service registry.
_TASK_TYPE_TO_CLASS = {
    "asr":                      "ASRTaskService",
    "audio-lang-detection":     "AudioDefaultModel",
    "language-detection":       "LanguageDetectionTaskService",
    "language-diarization":     "LanguageDiarizationTaskService",
    "nmt":                      "TextDefaultModel",
    "ner":                      "NERTaskService",
    "ocr":                      "ImageDefaultModel",
    "pii":                      "PIITaskService",
    "speaker-diarization":      "SpeakerDiarizationTaskService",
    "transliteration":          "TransliterationTaskService",
    "tts":                      "TTSTaskService",
}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col["name"] for col in inspector.get_columns("mm_models")]
    if "class_instance" not in existing_columns:
        op.add_column(
            "mm_models",
            sa.Column("class_instance", sa.String(100), nullable=True),
        )

    for task_type, class_name in _TASK_TYPE_TO_CLASS.items():
        conn.execute(
            sa.text(
                "UPDATE mm_models SET class_instance = :class_name "
                "WHERE (task->>'type') = :task_type AND class_instance IS NULL"
            ),
            {"class_name": class_name, "task_type": task_type},
        )


def downgrade() -> None:
    op.drop_column("mm_models", "class_instance")
