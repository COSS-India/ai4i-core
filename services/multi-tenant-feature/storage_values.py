
# Example storage values for usage field in Tenant model
from models.db_models import Tenant

Tenant.usage = {
  "api_calls_today": 394,
  "api_calls_month": 24011,
  "tts_seconds_used": 500,
  "asr_minutes_processed": 20,
  "nmt_characters_translated": 124000,
  "storage_gb_used": 1.8
}