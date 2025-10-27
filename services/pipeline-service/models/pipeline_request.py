"""
Pipeline Request Models

Pydantic models for pipeline inference requests, supporting chaining of AI tasks.
Adapted from Dhruva-Platform-2 ULCA schemas for pipeline service.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator, model_validator


class TaskType(str, Enum):
    """Supported pipeline task types."""
    ASR = "asr"
    TRANSLATION = "translation"
    TTS = "tts"
    TRANSLITERATION = "transliteration"


class LanguageConfig(BaseModel):
    """Language configuration for pipeline tasks."""
    sourceLanguage: str = Field(..., description="Source language code (e.g., 'en', 'hi', 'ta')")
    targetLanguage: Optional[str] = Field(None, description="Target language code (for translation)")
    sourceScriptCode: Optional[str] = Field(None, description="Script code if applicable")
    targetScriptCode: Optional[str] = Field(None, description="Target script code")


class AudioInput(BaseModel):
    """Audio input specification."""
    audioContent: str = Field(..., description="Base64 encoded audio content")
    
    @validator('audioContent')
    def validate_audio_content(cls, v):
        if not v or not v.strip():
            raise ValueError('Audio content cannot be empty')
        return v.strip()


class TextInput(BaseModel):
    """Text input specification."""
    source: str = Field(..., description="Input text")
    
    @validator('source')
    def validate_source_text(cls, v):
        if not v or not v.strip():
            raise ValueError('Source text cannot be empty')
        return v.strip()


class PipelineTaskConfig(BaseModel):
    """Configuration for a pipeline task."""
    serviceId: str = Field(..., description="Identifier for the AI service/model")
    language: LanguageConfig = Field(..., description="Language configuration")
    
    # ASR-specific config
    audioFormat: Optional[str] = Field(None, description="Audio format")
    preProcessors: Optional[List[str]] = Field(None, description="Preprocessors")
    postProcessors: Optional[List[str]] = Field(None, description="Postprocessors")
    transcriptionFormat: Optional[str] = Field("transcript", description="Transcription format")
    
    # TTS-specific config
    gender: Optional[str] = Field(None, description="Voice gender (male/female)")
    
    # Additional config
    additionalParams: Optional[Dict[str, Any]] = Field(None, description="Additional parameters")


class PipelineTask(BaseModel):
    """Configuration for a pipeline task."""
    taskType: TaskType = Field(..., description="Type of task to execute")
    config: PipelineTaskConfig = Field(..., description="Configuration for the task")


class PipelineInferenceRequest(BaseModel):
    """Main pipeline inference request model."""
    pipelineTasks: List[PipelineTask] = Field(..., description="List of tasks to execute in sequence", min_items=1)
    
    # Initial input data - can be audio for ASR or text for translation
    inputData: Dict[str, Any] = Field(..., description="Initial input data (audio for ASR-first pipelines)")
    controlConfig: Optional[Dict[str, Any]] = Field(None, description="Additional control parameters")
    
    @validator('pipelineTasks')
    def validate_task_sequence(cls, v):
        """Validate that the pipeline task sequence is valid."""
        if not v:
            raise ValueError('At least one pipeline task is required')
        if len(v) > 10:
            raise ValueError('Maximum 10 tasks allowed per pipeline')
        
        # Validate task sequence
        for i in range(len(v) - 1):
            current_task = v[i].taskType
            next_task = v[i + 1].taskType
            
            # ASR can only be followed by Translation
            if current_task == TaskType.ASR:
                if next_task != TaskType.TRANSLATION:
                    raise ValueError('ASR can only be followed by Translation')
            
            # Translation can only be followed by TTS
            elif current_task == TaskType.TRANSLATION:
                if next_task != TaskType.TTS:
                    raise ValueError('Translation can only be followed by TTS')
            
            # Transliteration can be followed by Translation or TTS
            elif current_task == TaskType.TRANSLITERATION:
                if next_task not in {TaskType.TRANSLATION, TaskType.TTS}:
                    raise ValueError('Transliteration can only be followed by Translation or TTS')
        
        return v
    
    @model_validator(mode='after')
    def validate_input_data(self):
        """Validate input data matches the first task type."""
        if not self.pipelineTasks:
            return self
        
        first_task = self.pipelineTasks[0].taskType
        
        # First task must be ASR or TRANSLATION
        if first_task not in {TaskType.ASR, TaskType.TRANSLATION}:
            raise ValueError('First task in pipeline must be ASR or Translation')
        
        # Check input data structure
        if first_task == TaskType.ASR:
            if 'audio' not in self.inputData:
                raise ValueError('Input data must contain "audio" for ASR-first pipeline')
            if not isinstance(self.inputData['audio'], list):
                raise ValueError('Input audio must be a list')
        elif first_task == TaskType.TRANSLATION:
            if 'input' not in self.inputData:
                raise ValueError('Input data must contain "input" for Translation-first pipeline')
        
        return self
    
    def dict(self, **kwargs):
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)
