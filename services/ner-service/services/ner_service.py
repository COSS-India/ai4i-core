"""
Core business logic for NER inference.

This mirrors the behavior of Dhruva's /inference/ner while fitting
into the microservice structure used by ASR/TTS/NMT/OCR in this repo.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

import numpy as np
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from models.ner_request import NerInferenceRequest
from models.ner_response import (
    NerInferenceResponse,
    NerPrediction,
    NerTokenPrediction,
)
from utils.triton_client import TritonClient, TritonInferenceError

logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("ner-service")


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

    def __init__(self, triton_client: TritonClient, model_name: str):
        """
        Initialize NER service.
        
        Args:
            triton_client: Triton client instance
            model_name: Model name (should be resolved by Model Management middleware)
        """
        self.triton_client = triton_client
        self.model_name = model_name

    def run_inference(
        self, 
        request: NerInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> NerInferenceResponse:
        """
        Synchronous NER inference entrypoint.

        NOTE: This is intentionally synchronous like OCR core service; the
        FastAPI router can call it from an async endpoint.
        """
        if not tracer:
            # Fallback if tracing not available
            return self._run_inference_impl(request, user_id, api_key_id, session_id)
        
        start_time = time.time()
        
        with tracer.start_as_current_span("ner.process_batch") as span:
            try:
                # Extract configuration
                service_id = request.config.serviceId
                language = request.config.language.sourceLanguage
                
                span.set_attribute("ner.total_inputs", len(request.input))
                span.set_attribute("ner.service_id", service_id)
                span.set_attribute("ner.language", language)
                span.set_attribute("ner.model_name", self.model_name)
                
                if user_id:
                    span.set_attribute("user.id", str(user_id))
                if api_key_id:
                    span.set_attribute("api_key.id", str(api_key_id))
                if session_id:
                    span.set_attribute("session.id", str(session_id))
                
                # Prepare input texts (normalize newlines/whitespace)
                with tracer.start_as_current_span("ner.preprocess_texts") as preprocess_span:
                    input_texts: List[str] = []
                    for text_input in request.input:
                        normalized = (text_input.source or " ").replace("\n", " ").strip()
                        input_texts.append(normalized)
                    total_text_length = sum(len(text) for text in input_texts)
                    preprocess_span.set_attribute("ner.total_text_length", total_text_length)
                    preprocess_span.set_attribute("ner.preprocessed_count", len(input_texts))
                
                # Prepare Triton inputs/outputs
                with tracer.start_as_current_span("ner.prepare_triton_inputs") as prep_span:
                    try:
                        inputs, outputs = self.triton_client.get_ner_io_for_triton(
                            input_texts, language
                        )
                        prep_span.set_attribute("ner.input_count", len(inputs))
                        prep_span.set_attribute("ner.output_count", len(outputs))
                    except Exception as e:
                        prep_span.set_attribute("error", True)
                        prep_span.set_attribute("error.type", type(e).__name__)
                        prep_span.set_attribute("error.message", str(e))
                        prep_span.set_status(Status(StatusCode.ERROR, str(e)))
                        prep_span.record_exception(e)
                        raise

                # Send Triton request (triton_client will create its own span)
                with tracer.start_as_current_span("ner.triton_inference") as triton_span:
                    try:
                        response = self.triton_client.send_triton_request(
                            model_name=self.model_name,
                            inputs=inputs,
                            outputs=outputs,
                        )
                        triton_span.set_attribute("ner.triton_success", True)
                    except TritonInferenceError as exc:
                        # Propagate Triton-specific errors but make sure we record them
                        triton_span.set_attribute("error", True)
                        triton_span.set_attribute("error.type", "TritonInferenceError")
                        triton_span.set_attribute("error.message", str(exc))
                        triton_span.set_status(Status(StatusCode.ERROR, str(exc)))
                        triton_span.record_exception(exc)
                        raise
                    except Exception as exc:
                        triton_span.set_attribute("error", True)
                        triton_span.set_attribute("error.type", type(exc).__name__)
                        triton_span.set_attribute("error.message", str(exc))
                        triton_span.set_status(Status(StatusCode.ERROR, str(exc)))
                        triton_span.record_exception(exc)
                        logger.error("Triton NER inference failed: %s", exc, exc_info=True)
                        raise TritonInferenceError(f"Triton NER inference failed: {exc}") from exc

                # Decode Triton OUTPUT_TEXT
                with tracer.start_as_current_span("ner.decode_output") as decode_span:
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
                    decode_span.set_attribute("ner.decoded_length", len(decoded_str))

                # Parse the JSON from Triton
                with tracer.start_as_current_span("ner.parse_json") as parse_span:
                    try:
                        parsed_data = json.loads(decoded_str)
                        parse_span.set_attribute("ner.parse_success", True)
                    except json.JSONDecodeError as e:
                        parse_span.set_attribute("error", True)
                        parse_span.set_attribute("error.type", "JSONDecodeError")
                        parse_span.set_attribute("error.message", str(e))
                        parse_span.set_status(Status(StatusCode.ERROR, str(e)))
                        parse_span.record_exception(e)
                        raise

                # Normalize different response structures
                with tracer.start_as_current_span("ner.normalize_response") as normalize_span:
                    if isinstance(parsed_data, dict) and "output" in parsed_data:
                        raw_output = parsed_data["output"]
                    elif isinstance(parsed_data, dict):
                        raw_output = [parsed_data]
                    else:
                        raw_output = parsed_data if isinstance(parsed_data, list) else [parsed_data]
                    normalize_span.set_attribute("ner.raw_output_count", len(raw_output))

                # Process predictions
                with tracer.start_as_current_span("ner.process_predictions") as process_span:
                    predictions: List[NerPrediction] = []
                    total_tokens = 0
                    total_entities = 0

                    for item_idx, item in enumerate(raw_output):
                        with tracer.start_as_current_span("ner.process_item") as item_span:
                            item_span.set_attribute("ner.item_index", item_idx)
                            
                            source_text = item.get("source", "")
                            ner_predictions_raw = item.get("nerPrediction", [])
                            
                            item_span.set_attribute("ner.source_text_length", len(source_text))
                            item_span.set_attribute("ner.raw_predictions_count", len(ner_predictions_raw))
                            
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
                            entity_count = 0
                            for word_idx, word_info in enumerate(word_positions):
                                word = word_info["word"]
                                if word_idx in word_to_pred:
                                    assigned_tag = word_to_pred[word_idx]["tag"]
                                    if assigned_tag != "O":
                                        entity_count += 1
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
                            
                            total_tokens += len(token_predictions)
                            total_entities += entity_count
                            item_span.set_attribute("ner.tokens_count", len(token_predictions))
                            item_span.set_attribute("ner.entities_count", entity_count)
                    
                    process_span.set_attribute("ner.total_tokens", total_tokens)
                    process_span.set_attribute("ner.total_entities", total_entities)
                    process_span.set_attribute("ner.predictions_count", len(predictions))
                
                # Create response
                response = NerInferenceResponse(output=predictions)
                
                processing_time = time.time() - start_time
                span.set_attribute("ner.processing_time_seconds", processing_time)
                span.set_attribute("ner.output_count", len(response.output))
                span.set_attribute("ner.total_tokens", total_tokens)
                span.set_attribute("ner.total_entities", total_entities)
                
                logger.info(f"NER inference completed in {processing_time:.2f}s, {len(predictions)} predictions, {total_entities} entities")
                return response
                
            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.error(f"NER inference failed: {e}")
                raise
    
    def _run_inference_impl(
        self,
        request: NerInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> NerInferenceResponse:
        """Fallback implementation when tracing is not available."""
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
                model_name=self.model_name,
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



