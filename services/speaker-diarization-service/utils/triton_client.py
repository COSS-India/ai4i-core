"""
Triton Inference Server client wrapper for Speaker Diarization.

This client sends base64-encoded audio to a Triton deployment of the
speaker diarization model and parses its JSON output.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import tritonclient.http as http_client
from tritonclient.utils import np_to_triton_dtype
import httpx
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("speaker-diarization-service")


class TritonInferenceError(Exception):
    """Custom exception for Triton inference errors."""

    pass


class TritonClient:
    """Triton Inference Server client for Speaker Diarization operations."""

    def __init__(self, triton_url: str, api_key: Optional[str] = None, timeout: float = 300.0, model_name: Optional[str] = None):
        """
        :param triton_url: Triton server URL (host:port or http://host:port).
        :param api_key: Optional Bearer token for Authorization header.
        :param timeout: Request timeout in seconds (default: 300.0).
        :param model_name: Triton model name (REQUIRED - resolved via Model Management).
        """
        if not model_name:
            raise ValueError("model_name is required and must be resolved via Model Management")
        self.triton_url = self._normalize_url(triton_url)
        self.api_key = api_key
        self.timeout = timeout
        self.model_name = model_name
        self._client: Optional[http_client.InferenceServerClient] = None

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize Triton URL to host:port format."""
        url = url.strip()
        if url.startswith("http://"):
            url = url[7:]
        elif url.startswith("https://"):
            url = url[8:]
        return url

    @property
    def client(self) -> http_client.InferenceServerClient:
        """Lazy initialization of Triton HTTP client."""
        if self._client is None:
            logger.info(
                "Initializing Triton client for Speaker Diarization with URL: %s",
                self.triton_url,
            )
            try:
                self._client = http_client.InferenceServerClient(
                    url=self.triton_url,
                    verbose=False,
                )
            except Exception as exc:  # pragma: no cover - connectivity error path
                logger.error(
                    "Failed to initialize Triton client with URL '%s': %s",
                    self.triton_url,
                    exc,
                    exc_info=True,
                )
                raise TritonInferenceError(
                    f"Failed to initialize Triton client: {exc}"
                ) from exc
        return self._client

    def _get_string_tensor(
        self, values: List[List[str]], tensor_name: str
    ) -> http_client.InferInput:
        """
        Create a BYTES/string tensor input.

        values should be a nested list shaped like [[value1], [value2], ...]
        so that the final shape is [batch_size, 1].
        """
        arr = np.array(values, dtype=object)
        inp = http_client.InferInput(
            tensor_name,
            arr.shape,
            np_to_triton_dtype(arr.dtype),
        )
        inp.set_data_from_numpy(arr)
        return inp

    def get_speaker_diarization_io_for_triton(
        self, audio_base64: str, num_speakers: Optional[int] = None
    ) -> Tuple[List[http_client.InferInput], List[http_client.InferRequestedOutput]]:
        """
        Prepare inputs and outputs for speaker diarization inference.

        Args:
            audio_base64: Base64-encoded audio string
            num_speakers: Optional number of speakers (if None, will be auto-detected)

        Returns:
            tuple: (inputs, outputs) for Triton inference
        """
        # Shape needs to be [1, 1] for Triton (batch_size=1, num_elements=1)
        # NUM_SPEAKERS is expected as a string in BYTES format
        num_speakers_str = str(num_speakers) if num_speakers is not None else ""

        inputs = [
            self._get_string_tensor([[audio_base64]], "AUDIO_DATA"),
            self._get_string_tensor([[num_speakers_str]], "NUM_SPEAKERS"),
        ]
        outputs = [http_client.InferRequestedOutput("DIARIZATION_RESULT")]
        return inputs, outputs

    def run_speaker_diarization_inference(
        self, audio_base64: str, num_speakers: Optional[int] = None
    ) -> Dict:
        """
        Run speaker diarization on a single base64-encoded audio with detailed tracing.

        Returns a parsed JSON object from the diarization model.
        If the result cannot be parsed, an empty dict is returned.
        """
        # Try to use tracing if available, fallback to implementation without tracing
        try:
            return self._run_inference_with_tracing(audio_base64, num_speakers)
        except AttributeError:
            # Tracer not properly initialized, use fallback
            return self._run_inference_impl(audio_base64, num_speakers)

    def _run_inference_with_tracing(
        self, audio_base64: str, num_speakers: Optional[int] = None
    ) -> Dict:
        """Implementation with OpenTelemetry tracing."""
        with tracer.start_as_current_span("triton.speaker_diarization") as span:
            # Add request metadata
            audio_size_bytes = len(audio_base64) if audio_base64 else 0
            span.set_attribute("triton.model_name", self.model_name)
            span.set_attribute("triton.endpoint", self.triton_url)
            span.set_attribute("triton.has_auth", bool(self.api_key))
            span.set_attribute("triton.audio_size_bytes", audio_size_bytes)
            span.set_attribute("triton.num_speakers_requested", num_speakers if num_speakers else "auto")
            span.add_event("triton.speaker_diarization.start")

            if not audio_base64:
                span.set_attribute("triton.status", "skipped")
                span.set_attribute("triton.skip_reason", "empty_audio")
                return {}

            # SPAN 1: Prepare Triton I/O
            with tracer.start_as_current_span("triton.prepare_io") as prep_span:
                prep_span.set_attribute("audio_size_bytes", audio_size_bytes)
                prep_span.set_attribute("num_speakers", str(num_speakers) if num_speakers else "auto")
                
                inputs, outputs = self.get_speaker_diarization_io_for_triton(
                    audio_base64, num_speakers
                )
                prep_span.set_attribute("triton.input_tensors", len(inputs))
                prep_span.set_attribute("triton.output_tensors", len(outputs))
                prep_span.add_event("triton.io_prepared", {
                    "input_names": ",".join([inp.name() for inp in inputs]),
                    "output_names": ",".join([out.name() for out in outputs])
                })

            headers: Dict[str, str] = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            # SPAN 2: Execute Triton Inference
            with tracer.start_as_current_span("triton.infer") as infer_span:
                infer_span.set_attribute("triton.model_name", self.model_name)
                infer_span.set_attribute("triton.timeout", self.timeout)
                infer_span.add_event("triton.inference.start")
                
                try:
                    response = self.client.infer(
                        model_name=self.model_name,
                        inputs=inputs,
                        outputs=outputs,
                        headers=headers or None,
                    )
                    infer_span.set_attribute("triton.status", "success")
                    infer_span.add_event("triton.inference.complete", {"status": "success"})
                except Exception as exc:  # pragma: no cover - external failure path
                    infer_span.set_attribute("error", True)
                    infer_span.set_attribute("error.type", type(exc).__name__)
                    infer_span.set_attribute("error.message", str(exc))
                    infer_span.set_attribute("triton.status", "failed")
                    infer_span.set_status(Status(StatusCode.ERROR))
                    infer_span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR))
                    logger.error(
                        "Triton Speaker Diarization inference failed: %s", exc, exc_info=True
                    )
                    raise TritonInferenceError(
                        f"Triton Speaker Diarization inference failed: {exc}"
                    ) from exc

            # SPAN 3: Parse Response
            with tracer.start_as_current_span("triton.parse_response") as parse_span:
                result = response.as_numpy("DIARIZATION_RESULT")
                if result is None or len(result) == 0:
                    parse_span.set_attribute("triton.output_status", "empty")
                    parse_span.set_attribute("parse.status", "failed")
                    parse_span.add_event("triton.empty_response")
                    logger.warning("Empty response from Triton for speaker diarization")
                    return {}

                # Decode the response - Result shape is [1, 1], so access [0][0]
                try:
                    result_bytes = result[0][0]
                    parse_span.set_attribute("result.extraction", "success")
                except Exception as extract_exc:
                    parse_span.set_attribute("result.extraction", "failed")
                    parse_span.set_attribute("error", True)
                    parse_span.record_exception(extract_exc)
                    logger.warning("Failed to extract result from Triton response")
                    return {}

                if isinstance(result_bytes, bytes):
                    result_str = result_bytes.decode("utf-8")
                else:
                    result_str = str(result_bytes)

                parse_span.set_attribute("result.size_bytes", len(result_str))
                logger.debug(
                    "Speaker Diarization Triton response preview=%s",
                    result_str[:200],
                )

                try:
                    parsed_result = json.loads(result_str)
                    parse_span.set_attribute("parse.status", "success")
                    
                    # Add detailed attributes about the parsed result
                    if isinstance(parsed_result, dict):
                        if "segments" in parsed_result:
                            num_segments = len(parsed_result["segments"])
                            parse_span.set_attribute("result.num_segments", num_segments)
                            span.set_attribute("diarization.num_segments", num_segments)
                        
                        if "speakers" in parsed_result:
                            num_speakers_detected = len(parsed_result["speakers"])
                            parse_span.set_attribute("result.num_speakers", num_speakers_detected)
                            span.set_attribute("diarization.num_speakers", num_speakers_detected)
                        
                        if "num_speakers" in parsed_result:
                            parse_span.set_attribute("result.speakers_field", parsed_result["num_speakers"])
                        
                        if "total_segments" in parsed_result:
                            parse_span.set_attribute("result.total_segments", parsed_result["total_segments"])
                    
                    parse_span.add_event("triton.response_parsed", {"status": "success"})
                    span.set_attribute("triton.status", "completed")
                    return parsed_result
                    
                except json.JSONDecodeError as json_exc:
                    parse_span.set_attribute("parse.status", "failed")
                    parse_span.set_attribute("error", True)
                    parse_span.set_attribute("error.type", "JSONDecodeError")
                    parse_span.record_exception(json_exc)
                    logger.exception("Failed to parse Speaker Diarization JSON from Triton")
                    return {}

    def _run_inference_impl(
        self, audio_base64: str, num_speakers: Optional[int] = None
    ) -> Dict:
        """Fallback implementation when tracing is not available."""
        if not audio_base64:
            return {}

        inputs, outputs = self.get_speaker_diarization_io_for_triton(
            audio_base64, num_speakers
        )

        headers: Dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = self.client.infer(
                model_name=self.model_name,
                inputs=inputs,
                outputs=outputs,
                headers=headers or None,
            )
        except Exception as exc:  # pragma: no cover - external failure path
            logger.error(
                "Triton Speaker Diarization inference failed: %s", exc, exc_info=True
            )
            raise TritonInferenceError(
                f"Triton Speaker Diarization inference failed: {exc}"
            ) from exc

        result = response.as_numpy("DIARIZATION_RESULT")
        if result is None or len(result) == 0:
            logger.warning("Empty response from Triton for speaker diarization")
            return {}

        # Decode the response - Result shape is [1, 1], so access [0][0]
        try:
            result_bytes = result[0][0]
        except Exception:
            logger.warning("Failed to extract result from Triton response")
            return {}

        if isinstance(result_bytes, bytes):
            result_str = result_bytes.decode("utf-8")
        else:
            result_str = str(result_bytes)

        logger.debug(
            "Speaker Diarization Triton response preview=%s",
            result_str[:200],
        )

        try:
            return json.loads(result_str)
        except json.JSONDecodeError:
            logger.exception("Failed to parse Speaker Diarization JSON from Triton")
            return {}
