from enum import Enum

class TaskTypeEnum(str, Enum):
    
    nmt = "nmt"
    tts = "tts"
    asr = "asr"
    llm = "llm"
    transliteration = "transliteration"
    ocr = "ocr"
    ner = "ner"
    language_detection = "language_detection"
    speaker_diarization = "speaker_diarization"
    language_diarization = "language_diarization"
    audio_lang_detection = "audio_lang_detection"
