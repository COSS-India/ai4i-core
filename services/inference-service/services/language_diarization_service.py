"""
LanguageDiarizationTaskService — implements language diarization inference.

Extends AudioBase (base64 passthrough, adapter_config driven).
Overrides postprocess to produce the same
output structure as the old language-diarization-service.

Triton tensor contract (adapter_config from MMS):
  Inputs:  AUDIO_DATA (BYTES [1,1]) — base64 audio
           LANGUAGE   (BYTES [1,1]) — target language code, "" = all languages
  Output:  DIARIZATION_RESULT (BYTES) — JSON blob
"""

from typing import Any, Dict, List, Tuple

from services.base.audio_base import AudioBase


class LanguageDiarizationTaskService(AudioBase):
    """
    TaskService for Language Diarization inference.

    Inherits base64-passthrough preprocessing from AudioBase.
    Overrides convert_payload_to_triton_format (normalise target_language),
    and postprocess (parse DIARIZATION_RESULT JSON + envelope).
    """

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Normalise target_language (camelCase or snake_case, defaults to "")."""
        config = dict(config)
        config["target_language"] = str(
            config.get("target_language") or config.get("targetLanguage") or ""
        )
        return await super().convert_payload_to_triton_format(input_data, config)

    # postprocess_output: adapter_config-driven — DIARIZATION_RESULT is
    # json_parse'd and splatted into the item (response_key "output[]");
    # the envelope declares task_type + config_keys ["serviceId"]. The model
    # emits the contract fields directly (total_segments, sorted segments
    # with numeric times, target_language), so no reshaping code is needed.


__all__ = ["LanguageDiarizationTaskService"]
