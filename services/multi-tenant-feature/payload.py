
# Tenants Registration Payload Example

request = {
    "organization_name":"Acme Corp",
    "domain":"acme.com",
    "contact_email":"admin@acme.com",
    "requested_subscriptions":["tts","asr"]
  }



resposne = {
  "id": "6b1ad5f2-1c8f-4c4a-a3b6-c7f8c0a1d2e3",
  "tenant_id": "acme-corp-4a5f1b",
  "subdomain": "acme-corp-4a5f1b.ai4i.com",
  "schema_name": "tenant_acme_corp_4a5f1b",
  "validation_time": "2025-12-11T11:22:33.123456+00:00",
  "status": "pending"
}

true = True
# Service payload registration example 
request = {
    "service_name": "pipeline",
    "unit_type": "minute",
    "price_per_unit": 0.00010,
    "currency": "INR",
    "is_active": true
  }

response = {
    "id": 24154220,
    "service_name": "pipeline",
    "unit_type": "minute",
    "price_per_unit": "0.000100",
    "currency": "INR",
    "is_active": true,
    "created_at": "2025-12-19T10:15:44.873845Z",
    "updated_at": "2025-12-19T10:15:44.873845Z"
}


