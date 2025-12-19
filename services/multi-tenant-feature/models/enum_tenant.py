from enum import Enum

class TenantStatus(str, Enum):
    PENDING = "PENDING"          # waiting for email verification 
    IN_PROGRESS = "IN_PROGRESS"  # once email verified
    ACTIVE = "ACTIVE"            # once payment done
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"


class SubscriptionType(str, Enum):
    TTS = "tts"
    ASR = "asr"
    NMT = "nmt"
    LLM = "llm"
    PIPELINE = "pipeline"
    OCR = "ocr"
    NER = "ner"

    Transliteration = "transliteration"
    Langauage_detection = "language_detection"
    Speaker_diarization = "speaker_diarization"
    Language_diarization = "language_diarization"
    Audio_language_detection = "audio_language_detection"
    
    


class BillingStatus(str, Enum):
    PAID = "PAID"
    UNPAID = "UNPAID"
    OVERDUE = "OVERDUE"
    PENDING = "PENDING"

class AuditAction(str, Enum):
    tenant_created = "tenant_created"
    tenant_updated = "tenant_updated"
    tenant_suspended = "tenant_suspended"
    tenant_reactivated = "tenant_reactivated"
    manual_action = "manual_action"

    email_verified = "email_verified"
    password_reset = "password_reset"

    billing_updated = "billing_updated"
    payment_received = "payment_received"
    payment_failed = "payment_failed"

    

class AuditActorType(str, Enum):
    SYSTEM = "system"          # automated system action
    USER = "user"              # tenant user
    ADMIN = "admin"            # platform admin
    BILLING = "billing"        # billing service / webhook
    SUPPORT = "support"        # customer support staff
    CRON = "cron"              # scheduled job
    MIGRATION = "migration"  
    


class ServiceUnitType(str, Enum):
    CHARACTER = "character"
    SECOND = "second"
    MINUTE = "minute"
    HOUR = "hour"
    REQUEST = "request"


class ServiceCurrencyType(str,Enum):
    INR ="INR"
