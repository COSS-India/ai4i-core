from enum import Enum

class TenantStatus(str, Enum):
    PENDING = "PENDING"          # waiting for email verification 
    IN_PROGRESS = "IN_PROGRESS"  # 
    ACTIVE = "ACTIVE"            # once email verified
    SUSPENDED = "SUSPENDED"
    # ARCHIVED = "ARCHIVED"
    
class TenantUserStatus(str, Enum):
    ACTIVE = "ACTIVE"            # user created and approved by tenant admin
    SUSPENDED = "SUSPENDED"


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

    user_created = "user_created"
    user_updated = "user_updated"
    user_deleted = "user_deleted"

    email_verified = "email_verified"
    password_reset = "password_reset"

    subscription_added = "subscription_added"
    subscription_removed = "subscription_removed"

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
