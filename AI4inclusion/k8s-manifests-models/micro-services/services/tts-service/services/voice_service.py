from typing import List, Optional, Tuple
from models.voice_models import VoiceMetadata, VoiceGender, VoiceAge


class VoiceNotFoundError(Exception):
    """Exception raised when voice is not found."""
    pass


class NoVoiceAvailableError(Exception):
    """Exception raised when no voice is available for the given criteria."""
    pass


class VoiceService:
    """Service for managing voice catalog and voice selection."""
    
    def __init__(self):
        """Initialize voice service with static voice catalog."""
        self.voices = self._initialize_voice_catalog()
    
    def _initialize_voice_catalog(self) -> List[VoiceMetadata]:
        """Initialize the static voice catalog."""
        return [
            VoiceMetadata(
                voice_id="indic-tts-coqui-dravidian-female",
                name="Dravidian Female Voice",
                gender=VoiceGender.FEMALE,
                age=VoiceAge.ADULT,
                languages=["kn", "ml", "ta", "te"],
                model_id="indic-tts-coqui-dravidian",
                sample_rate=22050,
                description="Female voice for Dravidian languages (Kannada, Malayalam, Tamil, Telugu)"
            ),
            VoiceMetadata(
                voice_id="indic-tts-coqui-dravidian-male",
                name="Dravidian Male Voice",
                gender=VoiceGender.MALE,
                age=VoiceAge.ADULT,
                languages=["kn", "ml", "ta", "te"],
                model_id="indic-tts-coqui-dravidian",
                sample_rate=22050,
                description="Male voice for Dravidian languages"
            ),
            VoiceMetadata(
                voice_id="indic-tts-coqui-indo_aryan-female",
                name="Indo-Aryan Female Voice",
                gender=VoiceGender.FEMALE,
                age=VoiceAge.ADULT,
                languages=["hi", "bn", "gu", "mr", "pa"],
                model_id="indic-tts-coqui-indo_aryan",
                sample_rate=22050,
                description="Female voice for Indo-Aryan languages (Hindi, Bengali, Gujarati, Marathi, Punjabi)"
            ),
            VoiceMetadata(
                voice_id="indic-tts-coqui-indo_aryan-male",
                name="Indo-Aryan Male Voice",
                gender=VoiceGender.MALE,
                age=VoiceAge.ADULT,
                languages=["hi", "bn", "gu", "mr", "pa"],
                model_id="indic-tts-coqui-indo_aryan",
                sample_rate=22050,
                description="Male voice for Indo-Aryan languages"
            ),
            VoiceMetadata(
                voice_id="indic-tts-coqui-misc-female",
                name="Miscellaneous Female Voice",
                gender=VoiceGender.FEMALE,
                age=VoiceAge.ADULT,
                languages=["en", "brx", "mni"],
                model_id="indic-tts-coqui-misc",
                sample_rate=22050,
                description="Female voice for English and other languages"
            ),
            VoiceMetadata(
                voice_id="indic-tts-coqui-misc-male",
                name="Miscellaneous Male Voice",
                gender=VoiceGender.MALE,
                age=VoiceAge.ADULT,
                languages=["en", "brx", "mni"],
                model_id="indic-tts-coqui-misc",
                sample_rate=22050,
                description="Male voice for English and other languages"
            )
        ]
    
    def list_voices(
        self,
        language: Optional[str] = None,
        gender: Optional[VoiceGender] = None,
        age: Optional[VoiceAge] = None,
        is_active: bool = True
    ) -> List[VoiceMetadata]:
        """List voices with optional filtering."""
        filtered_voices = self.voices.copy()
        
        # Filter by language
        if language:
            filtered_voices = [v for v in filtered_voices if language in v.languages]
        
        # Filter by gender
        if gender:
            filtered_voices = [v for v in filtered_voices if v.gender == gender]
        
        # Filter by age
        if age:
            filtered_voices = [v for v in filtered_voices if v.age == age]
        
        # Filter by active status
        if is_active is not None:
            filtered_voices = [v for v in filtered_voices if v.is_active == is_active]
        
        return filtered_voices
    
    def get_voice_by_id(self, voice_id: str) -> Optional[VoiceMetadata]:
        """Get voice by ID."""
        for voice in self.voices:
            if voice.voice_id == voice_id:
                return voice
        return None
    
    def get_voices_by_language(self, language: str) -> List[VoiceMetadata]:
        """Get all voices that support a specific language."""
        return [v for v in self.voices if language in v.languages and v.is_active]
    
    def resolve_voice(self, voice_id: str) -> Tuple[str, str]:
        """Resolve voice_id to (model_id, gender) for Triton inference."""
        voice = self.get_voice_by_id(voice_id)
        if not voice:
            raise VoiceNotFoundError(f"Voice '{voice_id}' not found")
        
        return voice.model_id, voice.gender.value
    
    def get_default_voice(
        self,
        language: str,
        gender: Optional[VoiceGender] = None
    ) -> VoiceMetadata:
        """Get default voice for language and gender."""
        voices = self.get_voices_by_language(language)
        
        if not voices:
            raise NoVoiceAvailableError(f"No voice available for language '{language}'")
        
        # If gender specified, prefer that gender
        if gender:
            gender_voices = [v for v in voices if v.gender == gender]
            if gender_voices:
                return gender_voices[0]
        
        # Default to female voice if available, otherwise first available
        female_voices = [v for v in voices if v.gender == VoiceGender.FEMALE]
        if female_voices:
            return female_voices[0]
        
        return voices[0]
