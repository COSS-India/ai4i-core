from enum import Enum

class TaskTypeEnum(str, Enum):
    
    nmt = "nmt"
    tts = "tts"
    asr = "asr"
    llm = "llm"
