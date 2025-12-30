"""
Core business logic for NER inference.

This mirrors the behavior of Dhruva's /inference/ner while fitting
into the microservice structure used by ASR/TTS/NMT/OCR in this repo.
"""

import json
import logging
from typing import Any, Dict, List

import numpy as np

from models.ner_request import NerInferenceRequest
from models.ner_response import (
    NerInferenceResponse,
    NerPrediction,
    NerTokenPrediction,
)
from utils.triton_client import TritonClient, TritonInferenceError

logger = logging.getLogger(__name__)


class NerService:
    """
    NER inference service.

    Responsibilities:
    - Take NerInferenceRequest
    - Prepare Triton inputs (INPUT_TEXT, LANG_ID)
    - Call Triton NER model
    - Decode JSON output and align entities to tokens
    - Return NerInferenceResponse
    """

    def __init__(self, triton_client: TritonClient):
        self.triton_client = triton_client

    def run_inference(self, request: NerInferenceRequest) -> NerInferenceResponse:
        """
        Synchronous NER inference entrypoint.

        NOTE: This is intentionally synchronous like OCR core service; the
        FastAPI router can call it from an async endpoint.
        """
        # Prepare input texts (normalize newlines/whitespace)
        input_texts: List[str] = []
        for text_input in request.input:
            normalized = (text_input.source or " ").replace("\n", " ").strip()
            input_texts.append(normalized)

        language = request.config.language.sourceLanguage

        # Prepare Triton inputs/outputs
        try:
            inputs, outputs = self.triton_client.get_ner_io_for_triton(
                input_texts, language
            )

            response = self.triton_client.send_triton_request(
                model_name="ner",
                inputs=inputs,
                outputs=outputs,
            )
        except TritonInferenceError:
            # Let TritonInferenceError bubble up to router for 503 mapping
            raise
        except Exception as exc:
            logger.error("Triton NER inference failed: %s", exc, exc_info=True)
            raise TritonInferenceError(f"Triton NER inference failed: {exc}") from exc

        # Decode Triton OUTPUT_TEXT
        encoded_result = response.as_numpy("OUTPUT_TEXT")
        if encoded_result is None:
            encoded_result = np.array([np.array([])])

        encoded_result = encoded_result.tolist()
        raw_data = encoded_result[0] if isinstance(encoded_result, list) else encoded_result

        # Decode bytes to string
        if isinstance(raw_data, bytes):
            decoded_str = raw_data.decode("utf-8")
        else:
            decoded_str = str(raw_data)

        # Handle the case where Triton returns string like "[b'{...}']"
        if decoded_str.startswith("[b'") and decoded_str.endswith("']"):
            decoded_str = decoded_str[3:-2]
        elif decoded_str.startswith("[b\"") and decoded_str.endswith("\"]"):
            decoded_str = decoded_str[3:-2]

        # Decode escaped backslashes and unicode
        decoded_str = decoded_str.replace("\\\\", "\\")

        # Parse the JSON from Triton
        parsed_data = json.loads(decoded_str)

        # Normalize different response structures
        if isinstance(parsed_data, dict) and "output" in parsed_data:
            raw_output = parsed_data["output"]
        elif isinstance(parsed_data, dict):
            raw_output = [parsed_data]
        else:
            raw_output = parsed_data if isinstance(parsed_data, list) else [parsed_data]

        predictions: List[NerPrediction] = []

        for item in raw_output:
            source_text = item.get("source", "")
            ner_predictions_raw = item.get("nerPrediction", [])

            # Split source text into words and track character positions
            words = source_text.split()
            word_positions: List[Dict[str, Any]] = []
            pos = 0
            for word in words:
                word_start = source_text.find(word, pos)
                word_positions.append(
                    {
                        "word": word,
                        "start": word_start,
                        "end": word_start + len(word),
                    }
                )
                pos = word_start + len(word)

            # Create merged prediction groups (merge subword tokens starting with ##)
            prediction_groups: List[Dict[str, Any]] = []
            i = 0
            while i < len(ner_predictions_raw):
                pred = ner_predictions_raw[i]
                entity = pred.get("entity", "")
                tag = pred.get("class", "O")

                if not entity:
                    i += 1
                    continue

                # Merge subsequent "##" subword pieces (we only track first char + tag)
                j = i + 1
                while j < len(ner_predictions_raw):
                    next_entity = ner_predictions_raw[j].get("entity", "")
                    if next_entity.startswith("##"):
                        j += 1
                    else:
                        break

                prediction_groups.append(
                    {
                        "tag": tag,
                        "first_char": entity[0] if entity else "",
                    }
                )
                i = j

            # Map predictions to words using a simple first-character heuristic
            word_to_pred: Dict[int, Dict[str, Any]] = {}
            used_predictions = set()

            for pred_idx, pred_group in enumerate(prediction_groups):
                pred_first_char = pred_group["first_char"]

                for word_idx, word_info in enumerate(word_positions):
                    word = word_info["word"]
                    if (
                        word_idx not in word_to_pred
                        and word
                        and pred_first_char
                        and word[0] == pred_first_char
                        and pred_idx not in used_predictions
                    ):
                        word_to_pred[word_idx] = pred_group
                        used_predictions.add(pred_idx)
                        break

            # Build final NerTokenPrediction list
            token_predictions: List[NerTokenPrediction] = []
            for word_idx, word_info in enumerate(word_positions):
                word = word_info["word"]
                if word_idx in word_to_pred:
                    assigned_tag = word_to_pred[word_idx]["tag"]
                else:
                    assigned_tag = "O"

                token_predictions.append(
                    NerTokenPrediction(
                        token=word,
                        tag=assigned_tag,
                        tokenIndex=word_idx,
                        tokenStartIndex=word_info["start"],
                        tokenEndIndex=word_info["end"],
                    )
                )

            predictions.append(
                NerPrediction(source=source_text, nerPrediction=token_predictions)
            )

        return NerInferenceResponse(output=predictions)



