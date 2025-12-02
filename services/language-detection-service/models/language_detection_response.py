"""
Language Detection Response Models
Pydantic models for language detection inference responses
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class LanguagePrediction(BaseModel):
    """Language prediction result"""
    langCode: str = Field(..., description="ISO 639-3 language code (e.g., 'hin', 'eng', 'tam')")
    scriptCode: str = Field(..., description="ISO 15924 script code (e.g., 'Deva', 'Latn', 'Taml')")
    langScore: float = Field(..., description="Confidence score for the prediction (0.0 to 1.0)")
    language: str = Field(..., description="Full language name (e.g., 'Hindi', 'English')")


class LanguageDetectionOutput(BaseModel):
    """Output for a single text input"""
    source: str = Field(..., description="Source text")
    langPrediction: List[LanguagePrediction] = Field(
        ..., 
        description="List of language predictions (typically top-1 or top-N)"
    )


class LanguageDetectionInferenceResponse(BaseModel):
    """Response model for language detection inference"""
    output: List[LanguageDetectionOutput] = Field(
        ..., 
        description="Language detection results"
    )
    config: Optional[dict] = Field(None, description="Response configuration metadata")
    
    class Config:
        schema_extra = {
            "example": {
                "output": [
                    {
                        "source": "नमस्ते दुनिया",
                        "langPrediction": [
                            {
                                "langCode": "hin",
                                "scriptCode": "Deva",
                                "langScore": 0.98,
                                "language": "Hindi"
                            }
                        ]
                    },
                    {
                        "source": "Hello world",
                        "langPrediction": [
                            {
                                "langCode": "eng",
                                "scriptCode": "Latn",
                                "langScore": 0.99,
                                "language": "English"
                            }
                        ]
                    }
                ]
            }
        }

