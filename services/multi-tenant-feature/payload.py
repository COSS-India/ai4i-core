true = True
false = False
null = None


##################################################### Tenants Registration Payload Example ######################################

request = {
    "organization_name":"Acme Corp",
    "domain":"acme.com",
    "contact_email":"admin@acme.com",
    "requested_subscriptions":["tts","asr"]
  }



response = {
  "id": "6b1ad5f2-1c8f-4c4a-a3b6-c7f8c0a1d2e3",
  "tenant_id": "acme-corp-4a5f1b",
  "subdomain": "acme-corp-4a5f1b.ai4i.com",
  "schema_name": "tenant_acme_corp_4a5f1b",
  "validation_time": "2025-12-11T11:22:33.123456+00:00",
  "status": "pending"
}
#################################################################################################################################




################################################### User Registration Payload Example ######################################

request = {
    "tenant_id": "acme-corp-55ac3d",
    "email": "user4@acme.com",
    "username": "user4",
    "password": "StrongPass123",
    "services": ["asr"],
    "is_approved": true
  }

response = {
    "user_id": 8,
    "tenant_id": "acme-corp-55ac3d",
    "username": "user1",
    "email": "user1@acme.com",
    "services": [
        "asr"
    ],
    "created_at": "2025-12-23T13:05:04.590227Z"
}
#################################################################################################################################

##################################################### Service registration payload example ######################################

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

#################################################################################################################################

######################################  Service Update Payload Example ##############################################################

request = {
    "service_id": 28331892,
    "price_per_unit": 0.75,
    "unit_type" : "request",
    "currency" : "INR",
    "is_active": false
  }

response = {
    "message": "Service pricing updated successfully",
    "service": {
        "id": 28331892,
        "service_name": "asr",
        "unit_type": "request",
        "price_per_unit": "0.75",
        "currency": "INR",
        "is_active": false,
        "created_at": "2025-12-19T09:55:19.012471Z",
        "updated_at": "2025-12-24T12:12:35.418204Z"
    },
    "changes": {
        "unit_type": {
            "old": "character",
            "new": "request"
        },
        "is_active": {
            "old": true,
            "new": false
        }
    }
}
#################################################################################################################################

##################################################### List Services Payload Example ######################################

{
    "count": 5,
    "services": [
        {
            "id": 16935274,
            "service_name": "tts",
            "unit_type": "character",
            "price_per_unit": "0.0001",
            "currency": "INR",
            "is_active": true,
            "created_at": "2025-12-19T09:57:17.293240Z",
            "updated_at": "2025-12-19T09:57:17.293240Z"
        },
        {
            "id": 32749796,
            "service_name": "nmt",
            "unit_type": "minute",
            "price_per_unit": "0.0001",
            "currency": "INR",
            "is_active": true,
            "created_at": "2025-12-19T09:58:19.309547Z",
            "updated_at": "2025-12-19T09:58:19.309547Z"
        },
        {
            "id": 24154220,
            "service_name": "pipeline",
            "unit_type": "minute",
            "price_per_unit": "0.0001",
            "currency": "INR",
            "is_active": true,
            "created_at": "2025-12-19T10:15:44.873845Z",
            "updated_at": "2025-12-19T10:15:44.873845Z"
        },
        {
            "id": 28331892,
            "service_name": "asr",
            "unit_type": "character",
            "price_per_unit": "0.75",
            "currency": "INR",
            "is_active": true,
            "created_at": "2025-12-19T09:55:19.012471Z",
            "updated_at": "2025-12-19T10:15:13.243543Z"
        },
        {
            "id": 29576134,
            "service_name": "ocr",
            "unit_type": "minute",
            "price_per_unit": "0.0001",
            "currency": "INR",
            "is_active": true,
            "created_at": "2025-12-19T09:59:03.195807Z",
            "updated_at": "2025-12-19T09:59:03.195807Z"
        }
    ]
}

###############################################################################################################

###################################################### Tenant Status Update Payload Examples ######################################

# Tenant Status Update Payload Examples

################### For SUSPENDED status
request = {
    "tenant_id": "acme-corp-55ac3d",
    "status": "SUSPENDED",
    "reason": "Payment overdue",
    "suspended_until": "2025-02-15"
  }

response = {
    "tenant_id": "acme-corp-55ac3d",
    "old_status": "ACTIVE",
    "new_status": "SUSPENDED"
}

###################### For ACTIVE status

request = {
    "tenant_id": "acme-corp-55ac3d",
    "status": "ACTIVE",
    "reason": "",
    "suspended_until": null
  }

# OR

request = {
    "tenant_id": "acme-corp-55ac3d",  
    "status": "ACTIVE"
    }

response = {
    "tenant_id": "acme-corp-55ac3d",
    "old_status": "SUSPENDED",
    "new_status": "ACTIVE"
}

#################################################################################################################################


#################################################### Tenant User Status Update Payload Examples ######################################

# Tenant User Status Update Payload Examples
request = {
    "tenant_id": "acme-corp-55ac3d",
    "user_id": 23,
    "status": "SUSPENDED"
  }

response = {
    "tenant_id": "acme-corp-55ac3d",
    "user_id": 23,
    "old_status": "ACTIVE",
    "new_status": "SUSPENDED"
}

#################################################################################################################################