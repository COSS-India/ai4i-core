"""
Pipeline Response Models

Pydantic models for pipeline inference responses.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class TranscriptOutput(BaseModel):
    """Transcript output from ASR."""
    source: str = Field(..., description="The transcribed text")
    nBestTokens: Optional[List[Dict[str, Any]]] = Field(None, description="N-best tokens")
    
    def dict(self, **kwargs):
        return super().dict(exclude_none=True, **kwargs)


class TranslationOutput(BaseModel):
    """Translation output from NMT."""
    source: str = Field(..., description="Source text")
    target: str = Field(..., description="Translated text")
    
    def dict(self, **kwargs):
        return super().dict(exclude_none=True, **kwargs)


class AudioOutput(BaseModel):
    """Audio output from TTS."""
    audioContent: str = Field(..., description="Base64 encoded audio content")
    
    def dict(self, **kwargs):
        return super().dict(exclude_none=True, **kwargs)


class PipelineTaskOutput(BaseModel):
    """Output from a pipeline task."""
    taskType: str = Field(..., description="Type of task that produced this output")
    serviceId: str = Field(..., description="Service ID used for this task")
    
    # Output data - structure depends on task type
    output: Optional[Any] = Field(None, description="Task output (structure varies by task type)")
    audio: Optional[List[AudioOutput]] = Field(None, description="Audio output (for TTS tasks)")
    config: Optional[Dict[str, Any]] = Field(None, description="Response configuration")
    
    def dict(self, **kwargs):
        return super().dict(exclude_none=True, **kwargs)


class PipelineInferenceResponse(BaseModel):
    """Main pipeline inference response model."""
    pipelineResponse: List[PipelineTaskOutput] = Field(..., description="Outputs from each pipeline task")
    
    class Config:
        json_schema_extra = {
            "example": {
                "pipelineResponse": [
                    {
                        "taskType": "asr",
                        "serviceId": "vakyansh-asr-en",
                        "output": [
                            {"source": "Hello world"}
                        ]
                    },
                    {
                        "taskType": "translation",
                        "serviceId": "indictrans-v2-all",
                        "output": [
                            {"source": "Hello world", "target": "नमस्ते दुनिया"}
                        ]
                    },
                    {
                        "taskType": "tts",
                        "serviceId": "indic-tts-coqui-dravidian",
                        "output": [
                            {"audioContent": "base64EncodedAudio..."}
                        ],
                        "config": {
                            "language": {"sourceLanguage": "hi"},
                            "audioFormat": "wav"
                        }
                    }
                ]
            }
        }
    
    def dict(self, **kwargs):
        return super().dict(exclude_none=True, **kwargs)
