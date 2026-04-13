"""
Core business logic for NER inference.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

import numpy as np

from app.schemas.inference import (
    NerInferenceRequest,
    NerInferenceResponse,
    NerPrediction,
    NerTokenPrediction,
)
from app.repositories.ner_repository import NERRepository
from app.clients.triton_client import NERTritonClient
from ai4icore_exceptions import TritonInferenceError
from ai4icore_telemetry import StandardSpanManager

logger = logging.getLogger(__name__)
_standard_spans = StandardSpanManager("ner")


class NerService:
    """
    NER inference service.

    Responsibilities:
    - Take NerInferenceRequest
    - Prepare Triton inputs (INPUT_TEXT, LANG_ID)
    - Call Triton NER model
    - Decode JSON output and align entities to tokens
    - Return NerInferenceResponse
    - Log requests and results to database
    """

    def __init__(
        self,
        repository: NERRepository,
        triton_client: NERTritonClient,
        model_name: str,
    ):
        self.repository = repository
        self.triton_client = triton_client
        self.model_name = model_name

    async def run_inference(
        self,
        request: NerInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
    ) -> NerInferenceResponse:
        """
        Async NER inference entrypoint.

        Standard phases: preprocess → resolve_model → triton_inference → postprocess → persist.
        """
        start_time = time.time()
        request_id = None
        service_id = request.config.serviceId
        language = request.config.language.sourceLanguage
        input_count = len(request.input)
        model_name = self.model_name

        with _standard_spans.inference(
            service_id=service_id,
            model_name=None,
            input_count=input_count,
            input_type="text",
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id,
            extra_attrs={"ner.source_language": language},
        ) as parent_span:
            try:
                input_texts: List[str] = []
                with _standard_spans.preprocess() as preprocess_span:
                    for text_input in request.input:
                        normalized = (text_input.source or " ").replace("\n", " ").strip()
                        input_texts.append(normalized)
                    total_text_length = sum(len(text) for text in input_texts)
                    preprocess_span.set_attribute("ner.input.character_length", total_text_length)
                    preprocess_span.set_attribute(
                        "ner.preprocessed_count", len(input_texts)
                    )
                    if parent_span is not None:
                        try:
                            parent_span.set_attribute(
                                "ner.input.character_length", total_text_length
                            )
                        except Exception:
                            pass

                with _standard_spans.resolve_model() as resolve_span:
                    resolve_span.set_attribute("ner.model_name", model_name)
                    if parent_span is not None:
                        try:
                            parent_span.set_attribute("ner.model_name", model_name)
                        except Exception:
                            pass

                decoded_str = ""
                with _standard_spans.triton_inference() as triton_span:
                    try:
                        inputs, outputs = self.triton_client.get_ner_io_for_triton(
                            input_texts, language
                        )
                    except Exception as e:
                        triton_span.set_attribute("error.type", type(e).__name__)
                        triton_span.set_attribute("error.message", str(e))
                        raise

                    triton_span.set_attribute("ner.input_tensor_count", len(inputs))
                    triton_span.set_attribute("ner.output_tensor_count", len(outputs))
                    triton_span.add_event(
                        "ner.prepare_triton_inputs.completed",
                        {"batch_size": len(input_texts)},
                    )

                    try:
                        response = self.triton_client.send_triton_request(
                            model_name=model_name,
                            inputs=inputs,
                            outputs=outputs,
                        )
                    except TritonInferenceError as exc:
                        triton_span.set_attribute("error.type", "TritonInferenceError")
                        triton_span.set_attribute("error.message", str(exc))
                        raise
                    except Exception as exc:
                        triton_span.set_attribute("error.type", type(exc).__name__)
                        triton_span.set_attribute("error.message", str(exc))
                        logger.error(
                            "Triton NER inference failed: %s", exc, exc_info=True
                        )
                        raise TritonInferenceError(
                            f"Triton NER inference failed: {exc}"
                        ) from exc

                    encoded_result = response.as_numpy("OUTPUT_TEXT")
                    if encoded_result is None:
                        encoded_result = np.array([np.array([])])

                    encoded_result = encoded_result.tolist()
                    raw_data = (
                        encoded_result[0]
                        if isinstance(encoded_result, list)
                        else encoded_result
                    )

                    if isinstance(raw_data, bytes):
                        decoded_str = raw_data.decode("utf-8")
                    else:
                        decoded_str = str(raw_data)

                    if decoded_str.startswith("[b'") and decoded_str.endswith("']"):
                        decoded_str = decoded_str[3:-2]
                    elif decoded_str.startswith("[b\"") and decoded_str.endswith("\"]"):
                        decoded_str = decoded_str[3:-2]

                    decoded_str = decoded_str.replace("\\\\", "\\")
                    triton_span.set_attribute("ner.decoded_length", len(decoded_str))
                    triton_span.add_event(
                        "ner.extract_raw_output.completed",
                        {"decoded_length": len(decoded_str)},
                    )

                predictions: List[NerPrediction] = []
                total_tokens = 0
                total_entities = 0

                with _standard_spans.postprocess() as post_span:
                    try:
                        parsed_data = json.loads(decoded_str)
                        post_span.add_event("ner.parse_json.completed", {})
                    except json.JSONDecodeError as e:
                        post_span.add_event(
                            "ner.parse_json.failed",
                            {"error.type": "JSONDecodeError", "error.message": str(e)},
                        )
                        raise

                    if isinstance(parsed_data, dict) and "output" in parsed_data:
                        raw_output = parsed_data["output"]
                    elif isinstance(parsed_data, dict):
                        raw_output = [parsed_data]
                    else:
                        raw_output = (
                            parsed_data if isinstance(parsed_data, list) else [parsed_data]
                        )
                    post_span.set_attribute("ner.raw_output_count", len(raw_output))

                    for item_idx, item in enumerate(raw_output):
                        source_text = item.get("source", "")
                        ner_predictions_raw = item.get("nerPrediction", [])

                        word_positions: List[Dict[str, Any]] = []
                        words = source_text.split()
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

                        prediction_groups: List[Dict[str, Any]] = []
                        i = 0
                        while i < len(ner_predictions_raw):
                            pred = ner_predictions_raw[i]
                            entity = pred.get("entity", "")
                            tag = pred.get("class", "O")

                            if not entity:
                                i += 1
                                continue

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
                            NerPrediction(
                                source=source_text, nerPrediction=token_predictions
                            )
                        )

                        total_tokens += len(token_predictions)
                        total_entities += entity_count
                        post_span.add_event(
                            "ner.item.completed",
                            {
                                "item_index": item_idx,
                                "tokens_count": len(token_predictions),
                                "entities_count": entity_count,
                            },
                        )

                    post_span.set_attribute("ner.total_tokens", total_tokens)
                    post_span.set_attribute("ner.total_entities", total_entities)
                    post_span.set_attribute("ner.predictions_count", len(predictions))

                    if parent_span is not None:
                        try:
                            parent_span.set_attribute(
                                "ner.output.character_length",
                                sum(len(p.source) for p in predictions),
                            )
                        except Exception:
                            pass

                ner_response = NerInferenceResponse(output=predictions)
                processing_time = time.time() - start_time

                with _standard_spans.persist() as persist_span:
                    db_request = await self.repository.create_request(
                        model_id=service_id,
                        language=language,
                        text_length=total_text_length,
                        user_id=user_id,
                        api_key_id=api_key_id,
                        session_id=session_id,
                    )
                    request_id = db_request.id
                    persist_span.set_attribute("ner.request_id", str(request_id))
                    persist_span.add_event(
                        "ner.db.request_created",
                        {"request_id": str(request_id)},
                    )

                    for prediction in predictions:
                        entities_data = {
                            "nerPrediction": [
                                {
                                    "token": token.token,
                                    "tag": token.tag,
                                    "tokenIndex": token.tokenIndex,
                                    "tokenStartIndex": token.tokenStartIndex,
                                    "tokenEndIndex": token.tokenEndIndex,
                                }
                                for token in prediction.nerPrediction
                            ]
                        }
                        await self.repository.create_result(
                            request_id=request_id,
                            entities=entities_data,
                            source_text=prediction.source,
                        )
                        persist_span.add_event(
                            "ner.db.result.created",
                            {"source_length": len(prediction.source)},
                        )

                    await self.repository.update_request_status(
                        request_id, "completed", processing_time
                    )
                    persist_span.add_event(
                        "ner.db.request_completed",
                        {
                            "request_id": str(request_id),
                            "processing_time_seconds": processing_time,
                        },
                    )

                if parent_span is not None:
                    try:
                        parent_span.set_attribute(
                            "ner.output_count", len(ner_response.output)
                        )
                        parent_span.set_attribute("ner.total_tokens", total_tokens)
                        parent_span.set_attribute("ner.total_entities", total_entities)
                    except Exception:
                        pass

                logger.info(
                    "NER inference completed in %.2fs, %s predictions, %s entities",
                    processing_time,
                    len(predictions),
                    total_entities,
                )
                return ner_response

            except Exception as e:
                logger.error("NER inference failed: %s", e)

                if request_id:
                    try:
                        await self.repository.update_request_status(
                            request_id, "failed", error_message=str(e)
                        )
                    except Exception as update_error:
                        logger.error(
                            "Failed to update request status: %s", update_error
                        )
                else:
                    try:
                        ttl = sum(
                            len((ti.source or " ").replace("\n", " ").strip())
                            for ti in request.input
                        )
                        dr = await self.repository.create_request(
                            model_id=service_id,
                            language=language,
                            text_length=ttl,
                            user_id=user_id,
                            api_key_id=api_key_id,
                            session_id=session_id,
                        )
                        await self.repository.update_request_status(
                            dr.id, "failed", error_message=str(e)
                        )
                    except Exception as db_err:
                        logger.error(
                            "ner: failed to record failed request: %s", db_err
                        )

                raise
