"""migrate_speaker_diarization_to_v2

Revision ID: f4d5e6a7b8c9
Revises: e3c4d5f6a7b8
Create Date: 2026-06-12 00:00:00.000000

Migrates Speaker Diarization to the v2 (JSONata) schema (AI4IDS-1981). Its
aggregation (sort segments, dedup/count speakers, compute durations), which was
service code, moves into the output_transform; the SpeakerDiarizationTaskService
class is emptied in the same change. v1 typed inputs preserved; v1 config
snapshotted to mm_models_adapter_config_history; downgrade restores it.
Keyed by mm_models.name 'speaker-diarization'. Idempotent.
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4d5e6a7b8c9"
down_revision: Union[str, None] = "e3c4d5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


_MODEL_NAME = "speaker-diarization"
_JSON_TENSORS = ["DIARIZATION_RESULT"]
_SD_T = (
    '{ "taskType": "speaker-diarization", "output": [ $map(tensors.DIARIZATION_RESULT, '
    'function($dr){ ( $segs := $sort($dr.segments, function($a,$b){$a.start_time > $b.start_time})'
    '.{"start": start_time, "end": end_time, '
    '"duration": ($exists(duration) ? duration : end_time - start_time), "speaker": speaker}; '
    '{"total_segments": $count($segs), "num_speakers": $count($distinct($segs.speaker)), '
    '"speakers": $sort($distinct($segs.speaker)), "segments": $segs} ) }) ], '
    '"config": { "serviceId": request.config.serviceId, '
    '"language": ($exists(request.config.language) ? request.config.language : null) } }'
)


def _load(conn, name):
    row = conn.execute(
        sa.text(
            "SELECT model_id, version, inference_endpoint->'adapter_config' "
            "FROM mm_models WHERE name = :name"
        ),
        {"name": name},
    ).fetchone()
    if row is None or row[2] is None:
        return None
    cfg = row[2] if isinstance(row[2], dict) else json.loads(row[2])
    return row[0], row[1], cfg


def _write(conn, name, cfg):
    res = conn.execute(
        sa.text(
            "UPDATE mm_models SET inference_endpoint = jsonb_set("
            "inference_endpoint, '{adapter_config}', CAST(:cfg AS jsonb)) "
            "WHERE name = :name"
        ),
        {"cfg": json.dumps(cfg), "name": name},
    )
    if res.rowcount != 1:
        raise RuntimeError(f"{name}: expected to update 1 row, got {res.rowcount}")


def upgrade() -> None:
    conn = op.get_bind()
    loaded = _load(conn, _MODEL_NAME)
    if loaded is None:
        print(f"  SKIP {_MODEL_NAME}: no mm_models row / adapter_config")
        return
    model_id, version, v1 = loaded
    if str(v1.get("schema_version", "")).startswith("2"):
        print(f"  SKIP {_MODEL_NAME}: already v2")
        return

    conn.execute(
        sa.text(
            "INSERT INTO mm_models_adapter_config_history "
            "(model_id, version, schema_version, config) "
            "VALUES (:model_id, :version, :schema_version, CAST(:config AS jsonb))"
        ),
        {"model_id": model_id, "version": version,
         "schema_version": str(v1.get("version", "1")), "config": json.dumps(v1)},
    )

    v2 = {
        "schema_version": "2.0",
        "model_version": v1.get("model_version", "1"),
        "inputs": v1.get("inputs", []),
        "outputs": [
            ({"tensor": o["tensor"], "is_json": True}
             if o["tensor"] in _JSON_TENSORS else {"tensor": o["tensor"]})
            for o in v1.get("outputs", [])
        ],
        "output_transform": _SD_T,
    }
    _write(conn, _MODEL_NAME, v2)
    print(f"  OK {_MODEL_NAME}: adapter_config migrated to v2")


def downgrade() -> None:
    conn = op.get_bind()
    loaded = _load(conn, _MODEL_NAME)
    if loaded is None:
        return
    model_id, _version, _cfg = loaded
    row = conn.execute(
        sa.text(
            "SELECT config FROM mm_models_adapter_config_history "
            "WHERE model_id = :model_id ORDER BY archived_at DESC, id DESC LIMIT 1"
        ),
        {"model_id": model_id},
    ).fetchone()
    if row is None:
        raise RuntimeError(f"{_MODEL_NAME}: no v1 snapshot in history; cannot downgrade")
    v1 = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    _write(conn, _MODEL_NAME, v1)
    print(f"  OK {_MODEL_NAME}: adapter_config restored to v1 from history")
