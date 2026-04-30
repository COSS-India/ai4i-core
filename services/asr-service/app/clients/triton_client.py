"""ASR-specific Triton client extending shared base."""

import logging
from typing import List, Tuple, Dict

import numpy as np
from tritonclient.http import InferInput, InferRequestedOutput
from tritonclient.utils import np_to_triton_dtype

from ai4icore_model_management import TritonClient
from ai4icore_exceptions import TritonInferenceError

logger = logging.getLogger(__name__)


class ASRTritonClient(TritonClient):
    """Triton client with ASR-specific I/O preparation."""

    def get_asr_io_for_triton(
        self,
        audio_chunks: List[np.ndarray],
        service_id: str,
        language: str,
        n_best_tok: int = 0,
    ) -> Tuple[List[InferInput], List[InferRequestedOutput]]:
        """Prepare inputs and outputs for ASR Triton inference."""
        try:
            # Pad batch to the actual max length in this batch
            padded_audio, num_samples = self._pad_batch(audio_chunks)

            batch_size, max_length = padded_audio.shape
            inputs = []

            # AUDIO_SIGNAL input (FP32)
            audio_input = InferInput(
                "AUDIO_SIGNAL",
                [batch_size, max_length],
                np_to_triton_dtype(np.float32),
            )
            audio_input.set_data_from_numpy(padded_audio.astype(np.float32))
            inputs.append(audio_input)

            # NUM_SAMPLES input (INT32) - shape [batch_size, 1]
            num_samples_input = InferInput(
                "NUM_SAMPLES",
                [batch_size, 1],
                np_to_triton_dtype(np.int32),
            )
            num_samples_input.set_data_from_numpy(num_samples.reshape(-1, 1).astype(np.int32))
            inputs.append(num_samples_input)

            # LANG_ID input (BYTES) - shape [batch_size, 1]
            lang_ids = [language.encode('utf-8') for _ in range(len(audio_chunks))]
            lang_input = self._get_string_tensor(
                [language] * len(audio_chunks), "LANG_ID"
            )
            inputs.append(lang_input)

            # TOPK input (INT32) - shape [batch_size, 1] - only if n_best_tok > 0
            if n_best_tok > 0:
                topk_values = np.array([[n_best_tok]] * len(audio_chunks), dtype=np.int32)
                topk_input = InferInput(
                    "TOPK",
                    [batch_size, 1],
                    np_to_triton_dtype(np.int32),
                )
                topk_input.set_data_from_numpy(topk_values)
                inputs.append(topk_input)

            # Create outputs
            outputs = [InferRequestedOutput("TRANSCRIPTS")]

            return inputs, outputs

        except Exception as e:
            logger.error(f"Failed to prepare ASR IO for Triton: {e}")
            raise TritonInferenceError(f"Failed to prepare ASR IO: {e}")

    def get_vad_io_for_triton(
        self,
        audio: np.ndarray,
        sample_rate: int,
        threshold: float,
        min_silence_duration_ms: int,
        speech_pad_ms: int,
        min_speech_duration_ms: int,
    ) -> Tuple[List[InferInput], List[InferRequestedOutput]]:
        """Prepare inputs and outputs for VAD Triton inference."""
        try:
            padded_audio, num_samples = self._pad_batch([audio])
            inputs = []

            # WAVPATH input (FP32)
            wavpath_input = InferInput(
                "WAVPATH",
                list(padded_audio.shape),
                np_to_triton_dtype(padded_audio.dtype),
            )
            wavpath_input.set_data_from_numpy(padded_audio)
            inputs.append(wavpath_input)

            # SAMPLING_RATE input (INT32)
            sampling_rate_values = np.array([sample_rate], dtype=np.int32)
            sampling_rate_input = InferInput("SAMPLING_RATE", list(sampling_rate_values.shape), np_to_triton_dtype(sampling_rate_values.dtype))
            sampling_rate_input.set_data_from_numpy(sampling_rate_values)
            inputs.append(sampling_rate_input)

            # THRESHOLD input (FP32)
            threshold_values = np.array([threshold], dtype=np.float32)
            threshold_input = InferInput("THRESHOLD", list(threshold_values.shape), np_to_triton_dtype(threshold_values.dtype))
            threshold_input.set_data_from_numpy(threshold_values)
            inputs.append(threshold_input)

            # MIN_SILENCE_DURATION_MS input (INT32)
            min_silence_values = np.array([min_silence_duration_ms], dtype=np.int32)
            min_silence_input = InferInput("MIN_SILENCE_DURATION_MS", list(min_silence_values.shape), np_to_triton_dtype(min_silence_values.dtype))
            min_silence_input.set_data_from_numpy(min_silence_values)
            inputs.append(min_silence_input)

            # SPEECH_PAD_MS input (INT32)
            speech_pad_values = np.array([speech_pad_ms], dtype=np.int32)
            speech_pad_input = InferInput("SPEECH_PAD_MS", list(speech_pad_values.shape), np_to_triton_dtype(speech_pad_values.dtype))
            speech_pad_input.set_data_from_numpy(speech_pad_values)
            inputs.append(speech_pad_input)

            # MIN_SPEECH_DURATION_MS input (INT32)
            min_speech_values = np.array([min_speech_duration_ms], dtype=np.int32)
            min_speech_input = InferInput("MIN_SPEECH_DURATION_MS", list(min_speech_values.shape), np_to_triton_dtype(min_speech_values.dtype))
            min_speech_input.set_data_from_numpy(min_speech_values)
            inputs.append(min_speech_input)

            outputs = [InferRequestedOutput("TIMESTAMPS")]

            return inputs, outputs

        except Exception as e:
            logger.error(f"Failed to prepare VAD IO for Triton: {e}")
            raise TritonInferenceError(f"Failed to prepare VAD IO: {e}")

    # ------------------------------------------------------------------
    # Batch padding helper
    # ------------------------------------------------------------------
    @staticmethod
    def _pad_batch(batch_data: List[np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
        """Pad batch data to same length."""
        if not batch_data:
            return np.array([]), np.array([])

        max_length = max(len(item) for item in batch_data)
        batch_size = len(batch_data)

        padded_array = np.zeros((batch_size, max_length), dtype=batch_data[0].dtype)
        lengths_array = np.zeros(batch_size, dtype=np.int32)

        for i, item in enumerate(batch_data):
            length = len(item)
            padded_array[i, :length] = item
            lengths_array[i] = length

        return padded_array, lengths_array
