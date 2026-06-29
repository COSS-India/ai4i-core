"""ASR TaskService — Automatic Speech Recognition inference."""

from typing import Any, Dict

from services.base.audio_base import (
    AudioBase,
    decode_audio_bytes,
    equalize_amplitude,
    resample,
    stereo_to_mono,
)


class ASRTaskService(AudioBase):
    """
    TaskService for Automatic Speech Recognition.

    The only audio task that sends decoded float PCM to Triton, so it overrides
    the AudioBase base64 passthrough with a single override:
      preprocess_input → bytes → decode → mono → resample (16 kHz) → equalize,
                         writing samples / num_samples onto the item for the
                         config's value_paths (input.samples, input.num_samples).

    sourceLanguage is enforced by the renderer (the LANG_ID input declares
    value_path request.config.language.sourceLanguage with no default, so a
    missing value is a 400). Output is adapter_config-driven (output_transform):
    the transcript maps to the ULCA output[].source. service_info (incl.
    adapter_config) is injected by the Orchestrator.
    """

    TARGET_SAMPLE_RATE = 16000  # All audio is resampled to this rate before Triton

    async def preprocess_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Float-PCM preprocessing, applied to each item in sequence:
          1. raw audio bytes (base64 decode or URI download)
          2. decode → float32 array + original sample rate
          3. stereo → mono
          4. resample to TARGET_SAMPLE_RATE
          5. equalize amplitude
        Enriches each item with samples / num_samples / sample_rate.
        """
        input_data = payload.get(self.payload_key) or []
        if not input_data:
            raise ValueError(f"{self.task_name}: audio list cannot be empty")

        items = []
        for item in input_data:
            audio_bytes = await self._get_audio_bytes(item)
            try:
                audio_data, sample_rate = decode_audio_bytes(audio_bytes)
            except ValueError as decode_err:
                raise ValueError(f"{self.task_name}: {decode_err}") from decode_err
            audio_data = stereo_to_mono(audio_data)
            audio_data = resample(audio_data, sample_rate, self.TARGET_SAMPLE_RATE)
            audio_data = equalize_amplitude(audio_data)

            # samples must be a plain Python list — the renderer's _cast_dtype
            # operates on Python lists, not numpy arrays.
            item["samples"] = audio_data.tolist()
            item["num_samples"] = len(audio_data)
            item["sample_rate"] = self.TARGET_SAMPLE_RATE
            items.append(item)

        payload[self.payload_key] = items
        return payload
