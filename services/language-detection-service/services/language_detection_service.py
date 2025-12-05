"""
Language Detection Service
Core business logic for language detection inference
"""

import time
import logging
import json
from typing import Optional, List
from uuid import UUID
import math

import numpy as np

from models.language_detection_request import LanguageDetectionInferenceRequest
from models.language_detection_response import (
    LanguageDetectionInferenceResponse,
    LanguageDetectionOutput,
    LanguagePrediction
)
from repositories.language_detection_repository import LanguageDetectionRepository
from services.text_service import TextService
from utils.triton_client import TritonClient

logger = logging.getLogger(__name__)


class TritonInferenceError(Exception):
    pass


class TextProcessingError(Exception):
    pass


class LanguageDetectionService:
    """Main language detection service for text language identification"""
    
    # Mapping from IndicLID format (lang_Script) to full language names
    INDICLID_TO_LANGUAGE = {
        "asm_Beng": "Assamese",
        "asm_Latn": "Assamese (Latin script)",
        "ben_Beng": "Bengali",
        "ben_Latn": "Bengali (Latin script)",
        "brx_Deva": "Bodo",
        "brx_Latn": "Bodo (Latin script)",
        "doi_Deva": "Dogri",
        "doi_Latn": "Dogri (Latin script)",
        "eng_Latn": "English",
        "guj_Gujr": "Gujarati",
        "guj_Latn": "Gujarati (Latin script)",
        "hin_Deva": "Hindi",
        "hin_Latn": "Hindi (Latin script)",
        "kan_Knda": "Kannada",
        "kan_Latn": "Kannada (Latin script)",
        "kas_Arab": "Kashmiri (Perso-Arabic script)",
        "kas_Deva": "Kashmiri (Devanagari script)",
        "kas_Latn": "Kashmiri (Latin script)",
        "kok_Deva": "Konkani",
        "kok_Latn": "Konkani (Latin script)",
        "mai_Deva": "Maithili",
        "mai_Latn": "Maithili (Latin script)",
        "mal_Mlym": "Malayalam",
        "mal_Latn": "Malayalam (Latin script)",
        "mni_Beng": "Manipuri (Bengali script)",
        "mni_Mtei": "Manipuri (Meitei Mayek script)",
        "mni_Latn": "Manipuri (Latin script)",
        "mar_Deva": "Marathi",
        "mar_Latn": "Marathi (Latin script)",
        "nep_Deva": "Nepali",
        "nep_Latn": "Nepali (Latin script)",
        "ori_Orya": "Odia",
        "ori_Latn": "Odia (Latin script)",
        "pan_Guru": "Punjabi",
        "pan_Latn": "Punjabi (Latin script)",
        "san_Deva": "Sanskrit",
        "san_Latn": "Sanskrit (Latin script)",
        "sat_Olck": "Santali",
        "snd_Arab": "Sindhi (Perso-Arabic script)",
        "snd_Latn": "Sindhi (Latin script)",
        "tam_Taml": "Tamil",
        "tam_Latn": "Tamil (Latin script)",
        "tel_Telu": "Telugu",
        "tel_Latn": "Telugu (Latin script)",
        "urd_Arab": "Urdu",
        "urd_Latn": "Urdu (Latin script)",
        "other": "Other"
    }
    
    # Service registry mapping serviceId to (triton_endpoint, triton_model_name)
    # Each entry: service_id -> (endpoint, model_name)
    # Note: Triton HTTP client expects host:port format (without http://), and model names should not contain special characters
    SERVICE_REGISTRY = {
        "ai4bharat/indiclid": ("65.1.35.3:8000", "indiclid"),
        "ai4bharat-indiclid": ("65.1.35.3:8000", "indiclid"),
        "indiclid": ("65.1.35.3:8000", "indiclid"),
        "default": ("65.1.35.3:8000", "indiclid")
    }
    
    def __init__(
        self,
        repository: LanguageDetectionRepository,
        text_service: TextService,
        default_triton_client: TritonClient,
        get_triton_client_func=None
    ):
        self.repository = repository
        self.text_service = text_service
        self.default_triton_client = default_triton_client
        self.get_triton_client_func = get_triton_client_func
        self._triton_clients = {}
    
    def get_triton_client(self, service_id: str) -> TritonClient:
        """Get Triton client for the given service ID"""
        # Check cache first
        if service_id in self._triton_clients:
            return self._triton_clients[service_id]
        
        # Get endpoint and model info from registry
        service_info = self.SERVICE_REGISTRY.get(service_id)
        if service_info:
            endpoint, _ = service_info
        else:
            # Use default client if service not in registry
            return self.default_triton_client
        
        # Create client using factory function if available
        if self.get_triton_client_func:
            client = self.get_triton_client_func(endpoint)
            self._triton_clients[service_id] = client
            return client
        else:
            # Fallback to default client
            return self.default_triton_client
    
    def get_model_name(self, service_id: str) -> str:
        """Get Triton model name based on service ID"""
        service_info = self.SERVICE_REGISTRY.get(service_id)
        if service_info:
            return service_info[1]  # Return model name
        return "indiclid"  # Default to "indiclid" if not found
    
    def normalize_confidence_score(self, confidence: float) -> float:
        """Normalize confidence score to be between 0.0 and 1.0.
        
        The database constraint requires confidence_score to be in [0.0, 1.0].
        This function handles cases where the model returns scores outside this range.
        
        Args:
            confidence: Raw confidence score from the model
            
        Returns:
            Normalized confidence score in [0.0, 1.0]
        """
        # If already in valid range, return as is
        if 0.0 <= confidence <= 1.0:
            return confidence
        
        # Log warning when normalization is needed
        logger.warning(
            f"Confidence score {confidence} is outside [0.0, 1.0] range. "
            f"Normalizing using sigmoid function."
        )
        
        # Use sigmoid to normalize to [0, 1]
        # This handles log probabilities, log-odds, or other scales
        normalized = 1.0 / (1.0 + math.exp(-confidence))
        logger.debug(f"Normalized confidence {confidence} -> {normalized}")
        return normalized
    
    async def run_inference(
        self,
        request: LanguageDetectionInferenceRequest,
        api_key_name: str,
        user_id: str
    ) -> LanguageDetectionInferenceResponse:
        """Run language detection inference"""
        start_time = time.time()
        request_id = None
        
        try:
            service_id = request.config.serviceId
            model_name = self.get_model_name(service_id)
            
            # Prepare input texts
            input_texts = []
            for text_input in request.input:
                normalized_text = self.text_service.normalize_text(text_input.source)
                input_texts.append(normalized_text)
            
            total_text_length = sum(len(text) for text in input_texts)
            
            # Create request record
            request_record = await self.repository.create_request(
                model_id=service_id,
                text_length=total_text_length,
                user_id=int(user_id) if user_id else None,
                api_key_id=None,
                session_id=None
            )
            request_id = request_record.id
            
            # Get Triton client
            triton_client = self.get_triton_client(service_id)
            service_info = self.SERVICE_REGISTRY.get(service_id)
            endpoint = service_info[0] if service_info else "default"
            logger.info(f"Using Triton endpoint: {endpoint}, model: {model_name} for service: {service_id}")
            
            # Prepare Triton inputs/outputs
            inputs, outputs = triton_client.get_language_detection_io_for_triton(input_texts)
            
            # Send request to Triton
            response = triton_client.send_triton_request(
                model_name=model_name,
                inputs=inputs,
                outputs=outputs
            )
            
            # Parse response
            encoded_result = response.as_numpy("OUTPUT_TEXT")
            if encoded_result is None:
                encoded_result = np.array([])
            
            # Process results
            results = []
            if encoded_result.size > 0:
                result_list = encoded_result.tolist()
                
                for idx, (source_text, result_row) in enumerate(zip(input_texts, result_list)):
                    if result_row and len(result_row) > 0:
                        # Parse JSON string from Triton response
                        json_str = result_row[0].decode("utf-8") if isinstance(result_row[0], bytes) else str(result_row[0])
                        
                        try:
                            detection_data = json.loads(json_str)
                            lang_code_full = detection_data.get("langCode", "other")
                            raw_confidence = float(detection_data.get("confidence", 0.0))
                            
                            # Log the raw confidence from Triton model for debugging
                            logger.debug(
                                f"Triton model returned confidence: {raw_confidence} "
                                f"for text: '{source_text[:50]}...' (lang: {lang_code_full})"
                            )
                            
                            # Normalize confidence score to [0.0, 1.0] for database constraint
                            # The IndicLID model may return log probabilities or raw scores
                            # that need to be normalized to match database CHECK constraint
                            normalized_confidence = self.normalize_confidence_score(raw_confidence)
                            
                            # Split langCode format "lang_Script" into language and script
                            if "_" in lang_code_full:
                                lang_code, script_code = lang_code_full.split("_", 1)
                            else:
                                lang_code = lang_code_full
                                script_code = "Latn"
                            
                            # Get full language name
                            language_name = self.INDICLID_TO_LANGUAGE.get(lang_code_full, "Other")
                            
                            # Create prediction (use normalized confidence for API response too)
                            prediction = LanguagePrediction(
                                langCode=lang_code,
                                scriptCode=script_code,
                                langScore=normalized_confidence,
                                language=language_name
                            )
                            
                            results.append(LanguageDetectionOutput(
                                source=source_text,
                                langPrediction=[prediction]
                            ))
                            
                            # Store result in database with normalized confidence
                            await self.repository.create_result(
                                request_id=request_id,
                                source_text=source_text,
                                detected_language=lang_code,
                                detected_script=script_code,
                                confidence_score=normalized_confidence,
                                language_name=language_name
                            )
                            
                        except (json.JSONDecodeError, KeyError, ValueError) as e:
                            logger.error(f"Failed to parse language detection result: {e}")
                            # Return empty prediction for failed parse
                            results.append(LanguageDetectionOutput(
                                source=source_text,
                                langPrediction=[]
                            ))
                    else:
                        # Empty result
                        results.append(LanguageDetectionOutput(
                            source=source_text,
                            langPrediction=[]
                        ))
            else:
                # No results from Triton
                for source_text in input_texts:
                    results.append(LanguageDetectionOutput(
                        source=source_text,
                        langPrediction=[]
                    ))
            
            response_model = LanguageDetectionInferenceResponse(output=results)
            
            # Update request status
            processing_time = time.time() - start_time
            await self.repository.update_request_status(
                request_id=request_id,
                status="completed",
                processing_time=processing_time
            )
            
            logger.info(f"Language detection completed for request {request_id} in {processing_time:.2f}s")
            return response_model
            
        except Exception as e:
            logger.error(f"Language detection failed: {e}")
            if request_id:
                try:
                    await self.repository.update_request_status(
                        request_id=request_id,
                        status="failed",
                        error_message=str(e)
                    )
                except Exception as update_error:
                    logger.error(f"Failed to update request status: {update_error}")
            raise TextProcessingError(f"Language detection failed: {e}")

