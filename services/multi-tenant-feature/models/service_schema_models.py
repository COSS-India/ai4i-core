"""
Service Schema Models for Tenant-Specific Schemas

This file contains all service database models that will be created in each tenant's schema.
These models are used for service-specific request/result tracking (NMT, TTS, ASR, OCR, etc.)

Note: Foreign keys to auth schema tables (users, api_keys, sessions) are removed
since those tables exist in a separate auth database. The user_id, api_key_id, and
session_id columns are kept as Integer references but without FK constraints.
"""

from sqlalchemy import Column, String, Integer, Float, Text, DateTime, Boolean, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID, JSON, JSONB
from sqlalchemy.orm import relationship
from db_connection import ServiceSchemaBase

# ServiceSchemaBase is imported from db_connection.py
# This ensures:
# 1. Consistency with TenantDBBase and AuthDBBase
# 2. Centralized base class management
# 3. Separate metadata registry (tables only created in tenant schemas, not public schema)

# ============================================================================
# NMT (Neural Machine Translation) Models
# ============================================================================

class NMTRequestDB(ServiceSchemaBase):
    """NMT Request database model for tenant schemas"""
    __tablename__ = "nmt_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    # Note: user_id, api_key_id, session_id reference auth_db tables, no FK constraint
    user_id = Column(Integer, nullable=True)
    api_key_id = Column(Integer, nullable=True)
    session_id = Column(Integer, nullable=True)
    model_id = Column(String(100), nullable=False)
    source_language = Column(String(10), nullable=False)
    target_language = Column(String(10), nullable=False)
    text_length = Column(Integer, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    results = relationship("NMTResultDB", back_populates="request", cascade="all, delete-orphan")


class NMTResultDB(ServiceSchemaBase):
    """NMT Result database model for tenant schemas"""
    __tablename__ = "nmt_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("nmt_requests.id", ondelete="CASCADE"), nullable=False)
    translated_text = Column(Text, nullable=False)
    confidence_score = Column(Float, nullable=True)
    source_text = Column(Text, nullable=True)
    language_detected = Column(String(10), nullable=True)
    word_alignments = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    request = relationship("NMTRequestDB", back_populates="results")


# ============================================================================
# TTS (Text-to-Speech) Models
# ============================================================================

class TTSRequestDB(ServiceSchemaBase):
    """TTS request database model for tenant schemas"""
    __tablename__ = "tts_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(Integer, nullable=True)
    api_key_id = Column(Integer, nullable=True)
    session_id = Column(Integer, nullable=True)
    model_id = Column(String(100), nullable=False)
    voice_id = Column(String(50), nullable=False)
    language = Column(String(10), nullable=False)
    text_length = Column(Integer, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    results = relationship("TTSResultDB", back_populates="request", cascade="all, delete-orphan")


class TTSResultDB(ServiceSchemaBase):
    """TTS result database model for tenant schemas"""
    __tablename__ = "tts_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("tts_requests.id", ondelete="CASCADE"), nullable=False)
    audio_file_path = Column(Text, nullable=False)
    audio_duration = Column(Float, nullable=True)
    audio_format = Column(String(20), nullable=True)
    sample_rate = Column(Integer, nullable=True)
    bit_rate = Column(Integer, nullable=True)
    file_size = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    request = relationship("TTSRequestDB", back_populates="results")


# ============================================================================
# ASR (Automatic Speech Recognition) Models
# ============================================================================

class ASRRequestDB(ServiceSchemaBase):
    """ASR Request database model for tenant schemas"""
    __tablename__ = "asr_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(Integer, nullable=True)
    api_key_id = Column(Integer, nullable=True)
    session_id = Column(Integer, nullable=True)
    model_id = Column(String(100), nullable=False)
    language = Column(String(10), nullable=False)
    audio_duration = Column(Float, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    results = relationship("ASRResultDB", back_populates="request", cascade="all, delete-orphan")


class ASRResultDB(ServiceSchemaBase):
    """ASR Result database model for tenant schemas"""
    __tablename__ = "asr_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("asr_requests.id", ondelete="CASCADE"), nullable=False)
    transcript = Column(Text, nullable=False)
    confidence_score = Column(Float, nullable=True)
    word_timestamps = Column(JSON, nullable=True)
    language_detected = Column(String(10), nullable=True)
    audio_format = Column(String(20), nullable=True)
    sample_rate = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    request = relationship("ASRRequestDB", back_populates="results")


# ============================================================================
# OCR (Optical Character Recognition) Models
# ============================================================================

class OCRRequestDB(ServiceSchemaBase):
    """OCR request tracking table for tenant schemas"""
    __tablename__ = "ocr_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(Integer, nullable=True)
    api_key_id = Column(Integer, nullable=True)
    session_id = Column(Integer, nullable=True)
    model_id = Column(String(100), nullable=False)
    language = Column(String(10), nullable=False)
    image_count = Column(Integer, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    results = relationship("OCRResultDB", back_populates="request", cascade="all, delete-orphan")


class OCRResultDB(ServiceSchemaBase):
    """OCR result table for tenant schemas"""
    __tablename__ = "ocr_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("ocr_requests.id", ondelete="CASCADE"), nullable=False)
    extracted_text = Column(Text, nullable=False)
    page_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    request = relationship("OCRRequestDB", back_populates="results")


# ============================================================================
# NER (Named Entity Recognition) Models
# ============================================================================

class NERRequestDB(ServiceSchemaBase):
    """NER request tracking table for tenant schemas"""
    __tablename__ = "ner_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(Integer, nullable=True)
    api_key_id = Column(Integer, nullable=True)
    session_id = Column(Integer, nullable=True)
    model_id = Column(String(100), nullable=False)
    language = Column(String(10), nullable=False)
    text_length = Column(Integer, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    results = relationship("NERResultDB", back_populates="request", cascade="all, delete-orphan")


class NERResultDB(ServiceSchemaBase):
    """NER result table for tenant schemas"""
    __tablename__ = "ner_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("ner_requests.id", ondelete="CASCADE"), nullable=False)
    entities = Column(JSON, nullable=False)
    source_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    request = relationship("NERRequestDB", back_populates="results")


# ============================================================================
# LLM (Large Language Model) Models
# ============================================================================

class LLMRequestDB(ServiceSchemaBase):
    """LLM Request database model for tenant schemas"""
    __tablename__ = "llm_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(Integer, nullable=True)
    api_key_id = Column(Integer, nullable=True)
    session_id = Column(Integer, nullable=True)
    model_id = Column(String(100), nullable=False)
    input_language = Column(String(10), nullable=True)
    output_language = Column(String(10), nullable=True)
    text_length = Column(Integer, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    results = relationship("LLMResultDB", back_populates="request", cascade="all, delete-orphan")


class LLMResultDB(ServiceSchemaBase):
    """LLM Result database model for tenant schemas"""
    __tablename__ = "llm_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("llm_requests.id", ondelete="CASCADE"), nullable=False)
    output_text = Column(Text, nullable=False)
    source_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    request = relationship("LLMRequestDB", back_populates="results")


# ============================================================================
# Transliteration Models
# ============================================================================

class TransliterationRequestDB(ServiceSchemaBase):
    """Transliteration Request database model for tenant schemas"""
    __tablename__ = "transliteration_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(Integer, nullable=True)
    api_key_id = Column(Integer, nullable=True)
    session_id = Column(Integer, nullable=True)
    model_id = Column(String(100), nullable=False)
    source_language = Column(String(10), nullable=False)
    target_language = Column(String(10), nullable=False)
    text_length = Column(Integer, nullable=True)
    is_sentence_level = Column(Boolean, nullable=False, default=True)
    num_suggestions = Column(Integer, nullable=True, default=0)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    results = relationship("TransliterationResultDB", back_populates="request", cascade="all, delete-orphan")


class TransliterationResultDB(ServiceSchemaBase):
    """Transliteration Result database model for tenant schemas"""
    __tablename__ = "transliteration_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("transliteration_requests.id", ondelete="CASCADE"), nullable=False)
    transliterated_text = Column(JSON, nullable=False)
    source_text = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    request = relationship("TransliterationRequestDB", back_populates="results")


# ============================================================================
# Language Detection Models
# ============================================================================

class LanguageDetectionRequestDB(ServiceSchemaBase):
    """Language Detection Request database model for tenant schemas"""
    __tablename__ = "language_detection_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(Integer, nullable=True)
    api_key_id = Column(Integer, nullable=True)
    session_id = Column(Integer, nullable=True)
    model_id = Column(String(100), nullable=False)
    text_length = Column(Integer, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    results = relationship("LanguageDetectionResultDB", back_populates="request", cascade="all, delete-orphan")


class LanguageDetectionResultDB(ServiceSchemaBase):
    """Language Detection Result database model for tenant schemas"""
    __tablename__ = "language_detection_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("language_detection_requests.id", ondelete="CASCADE"), nullable=False)
    source_text = Column(Text, nullable=False)
    detected_language = Column(String(10), nullable=False)
    detected_script = Column(String(10), nullable=False)
    confidence_score = Column(Float, nullable=False)
    language_name = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    request = relationship("LanguageDetectionRequestDB", back_populates="results")


# ============================================================================
# Speaker Diarization Models
# ============================================================================

class SpeakerDiarizationRequestDB(ServiceSchemaBase):
    """Speaker Diarization Request database model for tenant schemas"""
    __tablename__ = "speaker_diarization_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(Integer, nullable=True)
    api_key_id = Column(Integer, nullable=True)
    session_id = Column(Integer, nullable=True)
    model_id = Column(String(100), nullable=False)
    audio_duration = Column(Float, nullable=True)
    num_speakers = Column(Integer, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    results = relationship("SpeakerDiarizationResultDB", back_populates="request", cascade="all, delete-orphan")


class SpeakerDiarizationResultDB(ServiceSchemaBase):
    """Speaker Diarization Result database model for tenant schemas"""
    __tablename__ = "speaker_diarization_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("speaker_diarization_requests.id", ondelete="CASCADE"), nullable=False)
    total_segments = Column(Integer, nullable=False)
    num_speakers = Column(Integer, nullable=False)
    speakers = Column(JSONB, nullable=False)
    segments = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    request = relationship("SpeakerDiarizationRequestDB", back_populates="results")


# ============================================================================
# Audio Language Detection Models
# ============================================================================

class AudioLangDetectionRequestDB(ServiceSchemaBase):
    """Audio Language Detection Request database model for tenant schemas"""
    __tablename__ = "audio_lang_detection_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(Integer, nullable=True)
    api_key_id = Column(Integer, nullable=True)
    session_id = Column(Integer, nullable=True)
    model_id = Column(String(100), nullable=False)
    audio_duration = Column(Float, nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    results = relationship("AudioLangDetectionResultDB", back_populates="request", cascade="all, delete-orphan")


class AudioLangDetectionResultDB(ServiceSchemaBase):
    """Audio Language Detection Result database model for tenant schemas"""
    __tablename__ = "audio_lang_detection_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("audio_lang_detection_requests.id", ondelete="CASCADE"), nullable=False)
    language_code = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=True)
    all_scores = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    request = relationship("AudioLangDetectionRequestDB", back_populates="results")


# ============================================================================
# Language Diarization Models
# ============================================================================

class LanguageDiarizationRequestDB(ServiceSchemaBase):
    """Language Diarization Request database model for tenant schemas"""
    __tablename__ = "language_diarization_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(Integer, nullable=True)
    api_key_id = Column(Integer, nullable=True)
    session_id = Column(Integer, nullable=True)
    model_id = Column(String(100), nullable=False)
    audio_duration = Column(Float, nullable=True)
    target_language = Column(String(10), nullable=True)
    processing_time = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="processing")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    results = relationship("LanguageDiarizationResultDB", back_populates="request", cascade="all, delete-orphan")


class LanguageDiarizationResultDB(ServiceSchemaBase):
    """Language Diarization Result database model for tenant schemas"""
    __tablename__ = "language_diarization_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("language_diarization_requests.id", ondelete="CASCADE"), nullable=False)
    total_segments = Column(Integer, nullable=False)
    segments = Column(JSONB, nullable=False)
    target_language = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    request = relationship("LanguageDiarizationRequestDB", back_populates="results")

