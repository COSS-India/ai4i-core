"""
Middleware for Dhruva Observability Plugin

Handles request tracking, service detection, and metrics collection.
"""
import time
import jwt
import json
import base64
import io
import wave
import hashlib
from typing import Optional, Dict, Any
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from .config import PluginConfig
from .metrics import MetricsCollector
import httpx


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware for tracking requests and collecting metrics."""
    
    def __init__(self, app, metrics_collector: Optional[MetricsCollector] = None, 
                 config: Optional[PluginConfig] = None):
        """Initialize middleware."""
        super().__init__(app)
        self.metrics_collector = metrics_collector or MetricsCollector()
        self.config = config or PluginConfig()
    
    async def dispatch(self, request: Request, call_next):
        """Process request through middleware."""
        if not self.config.enabled:
            return await call_next(request)
        
        start_time = time.time()
        
        # Extract metadata from request
        path = request.url.path
        method = request.method
        headers = request.headers
        
        # Extract organization and app (including from JWT token)
        organization, app = self._extract_customer_app(request)
        
        # Initialize body_bytes variable for potential reuse
        body_bytes = None
        body_already_read = False
        
        # For generic /pipeline endpoint, we need to check the request body to determine the specific endpoint
        # This is because the frontend calls /services/inference/pipeline instead of /services/inference/pipeline/txt-lang-detection
        if method == "POST" and (path.endswith("/pipeline") or path == "/services/inference/pipeline") and "/pipeline/" not in path:
            # Read body to detect task type (will be restored later)
            body_bytes = await request.body()
            body_already_read = True
            try:
                request_data = json.loads(body_bytes.decode('utf-8'))
                # Check if this is a txt-lang-detection request
                if 'pipelineTasks' in request_data and len(request_data.get('pipelineTasks', [])) > 0:
                    task_type = request_data['pipelineTasks'][0].get('taskType', '')
                    if task_type == 'txt-lang-detection':
                        # Update path to specific endpoint for accurate metrics tracking
                        path = path + '/txt-lang-detection'
                        if self.config.debug:
                            print(f"🔍 Detected txt-lang-detection in generic pipeline endpoint, updating path to: {path}")
            except Exception as e:
                if self.config.debug:
                    print(f"⚠️ Failed to parse request body for pipeline detection: {e}")
        
        # Detect service type
        service_type = self._detect_service_type(path)
        
        # Extract real character count for TTS, translation, ASR, OCR, Transliteration, NER, Audio Language Detection, Text Language Detection, and Speaker Verification
        # IMPORTANT: We need to read and restore the body to avoid consuming the stream
        tts_characters = 0
        translation_characters = 0
        asr_audio_length = 0
        ocr_characters = 0
        transliteration_characters = 0
        language_detection_characters = 0
        audio_lang_detection_length = 0
        ner_characters = 0
        speaker_verification_length = 0
        speaker_diarization_length = 0
        language_diarization_length = 0
        
        if method == "POST" and service_type in ["tts", "translation", "asr", "ocr", "transliteration", "ner", "language_detection", "audio_lang_detection", "speaker_verification", "speaker_diarization", "language_diarization"]:
            if not body_already_read:
                body_bytes = await request.body()
            
            # Restore the body for downstream handlers by providing a receive
            # callable that yields the body once and then an empty message.
            # This follows ASGI expected behaviour and avoids EndOfStream errors
            # when downstream consumers call receive().
            body_sent = False

            async def receive() -> dict:
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {"type": "http.request", "body": body_bytes, "more_body": False}
                # After the body has been sent, indicate end of stream
                return {"type": "http.request", "body": b"", "more_body": False}

            # Attach the receive coroutine to the request so downstream can
            # await request._receive() as expected by Starlette/FastAPI internals.
            request._receive = receive
            
            print("The service type",service_type )

            # Extract metrics from the body
            if service_type == "tts":
                tts_characters = self._extract_tts_characters_from_body(body_bytes)
            elif service_type == "translation":
                translation_characters = self._extract_translation_characters_from_body(body_bytes)
            elif service_type == "asr":
                asr_audio_length = self._extract_asr_audio_length_from_body(body_bytes)
            elif service_type == "ocr":
                ocr_characters = self._extract_ocr_characters_from_body(body_bytes)
            elif service_type == "transliteration":
                transliteration_characters = self._extract_transliteration_characters_from_body(body_bytes)
            elif service_type == "language_detection":
                language_detection_characters = self._extract_language_detection_characters_from_body(body_bytes)
            elif service_type == "audio_lang_detection":
                audio_lang_detection_length = self._extract_asr_audio_length_from_body(body_bytes)
            elif service_type == "speaker_verification":
                speaker_verification_length = self._extract_asr_audio_length_from_body(body_bytes)
            elif service_type == "speaker_diarization":
                speaker_diarization_length = self._extract_asr_audio_length_from_body(body_bytes)
            elif service_type == "language_diarization":
                language_diarization_length = self._extract_asr_audio_length_from_body(body_bytes)
            elif service_type == "ner":
                ner_characters = self._extract_ner_characters_from_body(body_bytes)

            # Always log extracted language detection characters to ensure tracking is visible in logs
            if language_detection_characters > 0:
                # Unconditional print so it appears in container logs even if debug flag is misconfigured
                print(f"LANG_DET_CHARS_EXTRACTED={language_detection_characters}")
        
        # Debug logging
        if self.config.debug:
            print(f"🔍 Request: {method} {path} -> Service: {service_type}, Organization: {organization}, App: {app}")
            if tts_characters > 0:
                print(f"📝 TTS Characters detected: {tts_characters}")
            if translation_characters > 0:
                print(f"📝 Translation Characters detected: {translation_characters}")
            if asr_audio_length > 0:
                print(f"🎵 ASR Audio length detected: {asr_audio_length:.2f} seconds")
            if ocr_characters > 0:
                print(f"📝 OCR Characters detected: {ocr_characters}")
            if transliteration_characters > 0:
                print(f"📝 Transliteration Characters detected: {transliteration_characters}")
            if language_detection_characters > 0:
                print(f"📝 Language Detection Characters detected: {language_detection_characters}")
            if audio_lang_detection_length > 0:
                print(f"🎵 Audio Language Detection Audio length detected: {audio_lang_detection_length:.2f} seconds")
            if ner_characters > 0:
                print(f"📝 NER Characters detected: {ner_characters}")
            if speaker_verification_length > 0:
                print(f"🎵 Speaker Verification Audio length detected: {speaker_verification_length:.2f} seconds")
            if speaker_diarization_length > 0:
                print(f"🎵 Speaker Diarization Audio length detected: {speaker_diarization_length:.2f} seconds")
            if language_diarization_length > 0:
                print(f"🎵 Language Diarization Audio length detected: {language_diarization_length:.2f} seconds")
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Track request
        try:
            # Debug: Log the full path being used for metrics
            if self.config.debug:
                print(f"📊 Tracking metrics for endpoint: {path}, service_type: {service_type}")
            
            self.metrics_collector.track_request(
                organization=organization,
                app=app,
                method=method,
                endpoint=path,
                status_code=response.status_code,
                duration=duration,
                service_type=service_type
            )
            
            # Track additional metrics based on service type
            self._track_additional_metrics(organization, app, service_type, path, duration, tts_characters, translation_characters, asr_audio_length, ocr_characters, transliteration_characters, language_detection_characters, audio_lang_detection_length, ner_characters, speaker_verification_length, speaker_diarization_length, language_diarization_length)
            
        except Exception as e:
            # Don't let metrics collection break the request
            if self.config.debug:
                print(f"⚠️ Metrics collection failed: {e}")

        return response
    
    def _decode_jwt_token(self, authorization_header: str) -> Optional[Dict[str, Any]]:
        """Decode JWT token from authorization header."""
        try:
            # Extract token from "Bearer <token>" format
            if not authorization_header.startswith("Bearer "):
                return None
            
            token = authorization_header[7:]  # Remove "Bearer " prefix
            
            # Decode without verification to get claims (for customer name extraction)
            # In production, you might want to verify the token with proper secret
            decoded_token = jwt.decode(token, options={"verify_signature": False})
            
            return decoded_token
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ JWT decoding failed: {e}")
            return None
    
    @staticmethod
    def _get_organization_from_api_key(api_key: str) -> str:
        """Map API key to organization name using consistent hashing."""
        # Organization names
        organizations = ["irctc", "kisanmitra", "bashadaan", "beml"]
        
        # Use hash of API key to consistently map to same organization
        hash_value = int(hashlib.md5(api_key.encode()).hexdigest(), 16)
        org_index = hash_value % len(organizations)
        
        return organizations[org_index]
    
    def _extract_customer_from_token(self, request: Request) -> Optional[str]:
        """Extract customer name from JWT token in authorization header."""
        auth_header = request.headers.get("authorization", "")
        
        if auth_header:
            decoded_token = self._decode_jwt_token(auth_header)
            if decoded_token:
                # Extract customer name from 'name' field in token
                customer_name = decoded_token.get("name")
                if customer_name:
                    if self.config.debug:
                        print(f"🔑 Extracted customer from JWT: {customer_name}")
                    return customer_name
                
                # Fallback: try to extract from 'sub' field if 'name' is not available
                sub = decoded_token.get("sub")
                if sub:
                    if self.config.debug:
                        print(f"🔑 Using 'sub' field as customer: {sub}")
                    return sub
        
        return None
    
    def _extract_customer_app(self, request: Request) -> tuple:
        """Extract organization and app from request headers and JWT token."""
        # First try to get customer from JWT token
        organization = self._extract_customer_from_token(request)
        
        # If not found in token, fallback to header
        if organization is None:
            organization = request.headers.get("X-Customer-ID")
        
        # Extract organization from API key
        auth_header = request.headers.get("authorization", "")
        
        if auth_header and organization is None:
            # Extract the API key (remove "Bearer " prefix if present)
            api_key = auth_header
            if auth_header.startswith("Bearer "):
                api_key = auth_header[7:]
            
            # Map API key to organization (overrides any previous value)
            organization = self._get_organization_from_api_key(api_key)
            
            if self.config.debug:
                print(f"🏢 Mapped API key to organization: {organization}")
        
        # If still no organization, use "unknown"
        if organization is None:
            organization = "unknown"
            if self.config.debug:
                print(f"⚠️ No organization found,  using: {organization}")
        
        # Get app from header or use "unknown"
        app = request.headers.get("X-App-ID")
        if app is None:
            app = "unknown"
            
        return organization, app
    
    def _detect_service_type(self, path: str) -> str:
        """Detect service type from URL path."""
        path_lower = path.lower()
        
        # IMPORTANT: Check specific pipeline patterns FIRST before generic patterns
        # This ensures specific endpoints like /services/inference/pipeline/txt-lang-detection
        # are matched correctly and the full path is preserved in metrics
        
        # Pipeline text language detection endpoint (txt-lang-detection) - check FIRST
        if any(pattern in path_lower for pattern in ["/services/inference/pipeline/txt-lang-detection", "/services/inference/pipeline/txt-language-detection", "/pipeline/txt-lang-detection"]):
            return "language_detection"
        # Pipeline OCR endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/ocr", "/pipeline/ocr"]):
            return "ocr"
        # Pipeline Transliteration endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/transliteration", "/services/inference/pipeline/translation/transliteration", "/pipeline/transliteration", "/pipeline/translation/transliteration"]):
            return "transliteration"
        # Pipeline audio language detection endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/audio-lang-detection", "/services/inference/pipeline/audio-language-detection", "/pipeline/audio-lang-detection"]):
            return "audio_lang_detection"
        # Pipeline speaker verification endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/speaker-verification", "/pipeline/speaker-verification"]):
            return "speaker_verification"
        # Pipeline speaker diarization endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/speaker-diarization", "/pipeline/speaker-diarization"]):
            return "speaker_diarization"
        # Pipeline language diarization endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/language-diarization", "/pipeline/language-diarization"]):
            return "language_diarization"
        
        # Then check for generic service patterns (non-pipeline endpoints)
        elif any(pattern in path_lower for pattern in ["/translation", "/nmt", "/translate"]):
            return "translation"
        elif any(pattern in path_lower for pattern in ["/asr", "/transcribe", "/speech"]):
            return "asr"
        elif any(pattern in path_lower for pattern in ["/tts", "/synthesize", "/speak"]):
            return "tts"
        elif any(pattern in path_lower for pattern in ["/ocr", "/text-recognition"]):
            return "ocr"
        elif any(pattern in path_lower for pattern in ["/transliteration", "/xlit", "/transliterate"]):
            return "transliteration"
        elif any(pattern in path_lower for pattern in ["/audio-lang-detection", "/audio-language-detection", "/audio-detect"]):
            return "audio_lang_detection"
        elif any(pattern in path_lower for pattern in ["/language-detection", "/lang-detect", "/detect-language"]):
            return "language_detection"
        elif any(pattern in path_lower for pattern in ["/ner", "/entity", "/entities"]):
            return "ner"
        elif any(pattern in path_lower for pattern in ["/speaker", "/speaker-enrollment", "/speaker-verification"]):
            return "speaker_verification"
        elif any(pattern in path_lower for pattern in ["/speaker-diarization", "/speaker-diarization-compute-call"]):
            return "speaker_diarization"
        elif any(pattern in path_lower for pattern in ["/language-diarization", "/language-diarization-compute-call"]):
            return "language_diarization"
        elif any(pattern in path_lower for pattern in ["/llm", "/generate", "/chat", "/completion"]):
            return "llm"
        elif any(pattern in path_lower for pattern in ["/enterprise", "/health", "/metrics", "/config"]):
            return "enterprise"
        elif any(pattern in path_lower for pattern in ["/docs", "/openapi", "/redoc"]):
            return "documentation"
        else:
            return "unknown"
    
    def _track_additional_metrics(self, organization: str, app: str, service_type: str, path: str, duration: float, tts_characters: int = 0, translation_characters: int = 0, asr_audio_length: float = 0, ocr_characters: int = 0, transliteration_characters: int = 0, language_detection_characters: int = 0, audio_lang_detection_length: float = 0, ner_characters: int = 0, speaker_verification_length: float = 0, speaker_diarization_length: float = 0, language_diarization_length: float = 0):
        """Track additional metrics based on service type."""
        try:
            # Track component latency
            self.metrics_collector.track_component_latency(
                organization=organization,
                app=app,
                component=service_type,
                duration=duration
            )
            
            # Track data processing based on service type
            if service_type == "llm":
                # Mock LLM token processing
                tokens = self._estimate_llm_tokens(path)
                self.metrics_collector.track_llm_tokens(
                    organization=organization,
                    app=app,
                    model="gpt-3.5-turbo",  # Mock model
                    tokens=tokens
                )
            elif service_type == "tts":
                # Track real TTS character count
                if tts_characters > 0:
                    self.metrics_collector.track_tts_characters(
                        organization=organization,
                        app=app,
                        language="en",  # Default language
                        characters=tts_characters
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real TTS characters: {tts_characters}")
            elif service_type == "translation":
                # Track real translation character count
                if translation_characters > 0:
                    self.metrics_collector.track_nmt_characters(
                        organization=organization,
                        app=app,
                        source_lang="en",  # Default source language
                        target_lang="hi",  # Default target language
                        characters=translation_characters
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real translation characters: {translation_characters}")
            elif service_type == "asr":
                # Track real ASR audio length
                if asr_audio_length > 0:
                    self.metrics_collector.track_asr_audio_length(
                        organization=organization,
                        app=app,
                        language="en",  # Default language
                        audio_seconds=asr_audio_length
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real ASR audio length: {asr_audio_length:.2f} seconds")
            elif service_type == "ocr":
                # Track real OCR character count
                if ocr_characters > 0:
                    self.metrics_collector.track_ocr_characters(
                        organization=organization,
                        app=app,
                        characters=ocr_characters
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real OCR characters: {ocr_characters}")
            elif service_type == "transliteration":
                # Track real transliteration character count
                if transliteration_characters > 0:
                    self.metrics_collector.track_transliteration_characters(
                        organization=organization,
                        app=app,
                        source_lang="en",  # Default source language
                        target_lang="hi",  # Default target language
                        characters=transliteration_characters
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real transliteration characters: {transliteration_characters}")
            elif service_type == "language_detection":
                # Track real language detection character count
                if language_detection_characters > 0:
                    self.metrics_collector.track_language_detection_characters(
                        organization=organization,
                        app=app,
                        characters=language_detection_characters
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real language detection characters: {language_detection_characters}")
            elif service_type == "audio_lang_detection":
                # Track real audio language detection audio length
                if audio_lang_detection_length > 0:
                    self.metrics_collector.track_audio_lang_detection_length(
                        organization=organization,
                        app=app,
                        audio_seconds=audio_lang_detection_length
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real audio language detection audio length: {audio_lang_detection_length:.2f} seconds")
            elif service_type == "ner":
                # Track real NER character count
                if ner_characters > 0:
                    self.metrics_collector.track_ner_characters(
                        organization=organization,
                        app=app,
                        characters=ner_characters
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real NER characters: {ner_characters}")
            elif service_type == "speaker_verification":
                # Track real speaker verification audio length
                if speaker_verification_length > 0:
                    self.metrics_collector.track_speaker_verification_length(
                        organization=organization,
                        app=app,
                        audio_seconds=speaker_verification_length
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real speaker verification audio length: {speaker_verification_length:.2f} seconds")
            elif service_type == "speaker_diarization":
                # Track real speaker diarization audio length
                if speaker_diarization_length > 0:
                    self.metrics_collector.track_speaker_diarization_length(
                        organization=organization,
                        app=app,
                        audio_seconds=speaker_diarization_length
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real speaker diarization audio length: {speaker_diarization_length:.2f} seconds")
            elif service_type == "language_diarization":
                # Track real language diarization audio length
                if language_diarization_length > 0:
                    self.metrics_collector.track_language_diarization_length(
                        organization=organization,
                        app=app,
                        audio_seconds=language_diarization_length
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real language diarization audio length: {language_diarization_length:.2f} seconds")
            
            # Update SLA compliance (mock calculation)
            compliance = self._calculate_sla_compliance(service_type, duration)
            self.metrics_collector.update_sla_compliance(
                organization=organization,
                app=app,
                sla_type=f"{service_type}_availability",
                compliance_percent=compliance
            )
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Additional metrics tracking failed: {e}")
    
    def _estimate_llm_tokens(self, path: str) -> int:
        """Estimate LLM tokens based on path."""
        # Mock estimation - in real implementation, this would analyze request content
        return 100  # Mock value
    
    
    
    def _extract_tts_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract real character count from TTS request body."""
        try:
            if not body_bytes:
                return 0
            
            # Parse JSON request
            request_data = json.loads(body_bytes.decode('utf-8'))
            
            # Extract character count from TTS input
            total_characters = 0
            if 'input' in request_data:
                for input_item in request_data['input']:
                    if 'source' in input_item:
                        total_characters += len(input_item['source'])
            
            return total_characters
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to extract TTS characters: {e}")
            return 0
    
    def _extract_translation_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract real character count from translation request body."""
        try:
            if not body_bytes:
                return 0
            
            # Parse JSON request
            request_data = json.loads(body_bytes.decode('utf-8'))
            
            # Extract character count from translation input
            total_characters = 0
            if 'input' in request_data:
                for input_item in request_data['input']:
                    if 'source' in input_item:
                        total_characters += len(input_item['source'])
            
            return total_characters
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to extract translation characters: {e}")
            return 0
    
    def _extract_ocr_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract real character count from OCR request body (from image text)."""
        try:
            if not body_bytes:
                return 0
            
            # Parse JSON request
            request_data = json.loads(body_bytes.decode('utf-8'))
            
            # Extract character count from OCR input (assuming image base64 data)
            total_characters = 0
            
            # OCR uses pipeline format: {"inputData": {"image": [...]}, ...}
            if 'inputData' in request_data and 'image' in request_data['inputData']:
                for image_item in request_data['inputData']['image']:
                    # Handle imageContent (base64 encoded image)
                    if 'imageContent' in image_item:
                        content = image_item['imageContent']
                        # Estimate characters: each base64 char represents ~0.75 bytes of actual data
                        # OCR typically extracts 5-10% of image data as text
                        estimated_chars = len(content) // 200  # Conservative estimate
                        total_characters += estimated_chars
                        if self.config.debug:
                            print(f"🔍 OCR imageContent length: {len(content)}, estimated chars: {estimated_chars}")
                    # Handle imageUri (URL to image)
                    elif 'imageUri' in image_item:
                        image_uri = image_item['imageUri']
                        try:
                            # Download image from URL to estimate size
                            response = httpx.get(image_uri, timeout=5.0, follow_redirects=True)
                            if response.status_code == 200:
                                image_data = response.content
                                # Estimate characters based on image size
                                # Rough estimate: ~1000 bytes per character for typical images
                                estimated_chars = len(image_data) // 1000
                                total_characters += estimated_chars
                                if self.config.debug:
                                    print(f"🔍 OCR imageUri downloaded: {len(image_data)} bytes, estimated chars: {estimated_chars}")
                            else:
                                if self.config.debug:
                                    print(f"⚠️ Failed to download image from URI: {response.status_code}")
                        except Exception as e:
                            if self.config.debug:
                                print(f"⚠️ Error downloading image from URI: {e}")
                        
            return total_characters
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to extract OCR characters: {e}")
            return 0
    
    def _extract_transliteration_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract real character count from transliteration request body."""
        try:
            if not body_bytes:
                return 0
            
            # Parse JSON request
            request_data = json.loads(body_bytes.decode('utf-8'))
            
            # Extract character count from transliteration input
            total_characters = 0
            # Support both direct `input` and pipeline `inputData.input` formats
            if 'input' in request_data:
                for input_item in request_data['input']:
                    if 'source' in input_item and isinstance(input_item['source'], str):
                        total_characters += len(input_item['source'])
            elif 'inputData' in request_data and 'input' in request_data['inputData']:
                for input_item in request_data['inputData']['input']:
                    if 'source' in input_item and isinstance(input_item['source'], str):
                        total_characters += len(input_item['source'])

            if self.config.debug and total_characters > 0:
                print(f"🔤 Transliteration characters extracted: {total_characters}")
            
            return total_characters
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to extract transliteration characters: {e}")
            return 0
    
    def _extract_language_detection_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract real character count from language detection request body."""
        try:
            if not body_bytes:
                return 0
            
            # Parse JSON request
            request_data = json.loads(body_bytes.decode('utf-8'))
            
            # Extract character count from language detection input
            total_characters = 0
            # Support both direct `input` and pipeline `inputData.input` formats
            if 'input' in request_data:
                for input_item in request_data['input']:
                    if 'source' in input_item and isinstance(input_item['source'], str):
                        total_characters += len(input_item['source'])
            elif 'inputData' in request_data and 'input' in request_data['inputData']:
                for input_item in request_data['inputData']['input']:
                    if 'source' in input_item and isinstance(input_item['source'], str):
                        total_characters += len(input_item['source'])

            if self.config.debug:
                print(f"🔤 Language detection characters extracted: {total_characters}")
            
            return total_characters
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to extract language detection characters: {e}")
            return 0
    
    def _extract_ner_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract real character count from NER request body."""
        try:
            if not body_bytes:
                return 0
            
            # Parse JSON request
            request_data = json.loads(body_bytes.decode('utf-8'))
            
            # Extract character count from NER input
            total_characters = 0
            if 'input' in request_data:
                for input_item in request_data['input']:
                    if 'source' in input_item:
                        total_characters += len(input_item['source'])
            
            return total_characters
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to extract NER characters: {e}")
            return 0
    
    def _extract_asr_audio_length_from_body(self, body_bytes: bytes) -> float:
        """Extract real audio length in seconds from ASR request body."""
        try:
            if not body_bytes:
                return 0.0
            
            # Parse JSON request
            request_data = json.loads(body_bytes.decode('utf-8'))
            
            # Extract audio length from ASR input
            total_audio_length = 0.0
            audio_items_found = 0
            
            # Check for standard ASR format: {"audio": [...], "config": {...}}
            if 'audio' in request_data:
                for audio_item in request_data['audio']:
                    if 'audioContent' in audio_item:
                        # Decode base64 audio and calculate length
                        audio_length = self._calculate_audio_length_from_base64(audio_item['audioContent'])
                        total_audio_length += audio_length
                        audio_items_found += 1
                        if self.config.debug:
                            print(f"🎵 ASR audio item {audio_items_found}: {audio_length:.2f} seconds")
                    elif 'audioUri' in audio_item:
                        # audioUri requires downloading the file to calculate length,
                        # which is not practical in middleware. Skip for now.
                        if self.config.debug:
                            print(f"⚠️ audioUri detected but audio length cannot be calculated from URI without downloading file")
            # Also check for pipeline format: {"inputData": {"audio": [...]}, ...}
            elif 'inputData' in request_data and 'audio' in request_data['inputData']:
                for audio_item in request_data['inputData']['audio']:
                    if 'audioContent' in audio_item:
                        # Decode base64 audio and calculate length
                        audio_length = self._calculate_audio_length_from_base64(audio_item['audioContent'])
                        total_audio_length += audio_length
                        audio_items_found += 1
                        if self.config.debug:
                            print(f"🎵 ASR audio item {audio_items_found}: {audio_length:.2f} seconds")
                    elif 'audioUri' in audio_item:
                        # audioUri requires downloading the file to calculate length,
                        # which is not practical in middleware. Skip for now.
                        if self.config.debug:
                            print(f"⚠️ audioUri detected but audio length cannot be calculated from URI without downloading file")
            else:
                if self.config.debug:
                    print(f"⚠️ ASR request structure not recognized. Keys: {list(request_data.keys())}")
            
            return total_audio_length
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to extract ASR audio length: {e}")
            return 0.0
    
    def _calculate_audio_length_from_base64(self, base64_audio: str) -> float:
        """Calculate audio length in seconds from base64 encoded audio."""
        try:
            # Decode base64 audio
            audio_data = base64.b64decode(base64_audio)
            
            # Create a BytesIO object to read the audio data
            audio_buffer = io.BytesIO(audio_data)
            
            # Try to read as WAV file
            with wave.open(audio_buffer, 'rb') as wav_file:
                frames = wav_file.getnframes()
                sample_rate = wav_file.getframerate()
                duration = frames / float(sample_rate)
                if self.config.debug:
                    print(f"✅ Calculated WAV audio length: {duration:.2f} seconds ({frames} frames @ {sample_rate} Hz)")
                return duration
                
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to parse as WAV file: {e}, trying fallback estimation")
            # Fallback: estimate based on data size (rough approximation)
            try:
                audio_data = base64.b64decode(base64_audio)
                # Rough estimate: 16-bit audio at 16kHz = 32KB per second
                estimated_duration = len(audio_data) / 32000
                if self.config.debug:
                    print(f"📊 Estimated audio length: {estimated_duration:.2f} seconds (based on {len(audio_data)} bytes)")
                return estimated_duration
            except Exception as fallback_error:
                if self.config.debug:
                    print(f"❌ Fallback estimation also failed: {fallback_error}")
                return 0.0
    
    def _calculate_sla_compliance(self, service_type: str, duration: float) -> float:
        """Calculate SLA compliance based on service type and duration."""
        # Mock SLA compliance calculation
        if service_type == "llm":
            return 99.5 if duration < 2.0 else 95.0
        elif service_type == "tts":
            return 99.8 if duration < 1.0 else 97.0
        elif service_type == "translation":
            return 99.9 if duration < 0.5 else 98.0
        elif service_type == "asr":
            return 99.7 if duration < 1.5 else 96.0
        elif service_type == "ocr":
            return 99.8 if duration < 1.0 else 97.0
        elif service_type == "transliteration":
            return 99.9 if duration < 0.5 else 98.0
        elif service_type == "language_detection":
            return 99.9 if duration < 0.3 else 98.5
        elif service_type == "audio_lang_detection":
            return 99.7 if duration < 1.5 else 96.0
        elif service_type == "ner":
            return 99.8 if duration < 0.8 else 97.5
        elif service_type == "speaker_verification":
            return 99.6 if duration < 2.0 else 95.5
        elif service_type == "speaker_diarization":
            return 99.5 if duration < 3.0 else 95.0
        elif service_type == "language_diarization":
            return 99.6 if duration < 2.5 else 95.5
        else:
            return 99.0