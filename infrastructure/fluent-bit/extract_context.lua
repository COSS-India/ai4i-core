-- Helper function to recursively flatten nested tables
function flatten_table(tbl, prefix, result)
    result = result or {}
    prefix = prefix or ""
    
    for key, value in pairs(tbl) do
        local new_key = prefix .. key
        
        if type(value) == "table" then
            -- Recursively flatten nested tables
            flatten_table(value, new_key .. ".", result)
        else
            -- Add the flattened field
            result[new_key] = value
        end
    end
    
    return result
end

function extract_context_fields(tag, timestamp, record)
    -- Check if context exists and is a table
    if record["context"] ~= nil and type(record["context"]) == "table" then
        local context = record["context"]
        
        -- Extract nested fields to top level with camelCase names
        if context["status_code"] ~= nil then
            record["statusCode"] = context["status_code"]
        end
        if context["path"] ~= nil then
            record["path"] = context["path"]
        end
        if context["method"] ~= nil then
            record["method"] = context["method"]
        end
        if context["client_ip"] ~= nil then
            record["clientIp"] = context["client_ip"]
        end
        if context["user_agent"] ~= nil then
            record["userAgent"] = context["user_agent"]
        end
        if context["duration_ms"] ~= nil then
            record["durationMs"] = context["duration_ms"]
        end
        if context["api_key_id"] ~= nil then
            record["apiKeyId"] = context["api_key_id"]
        end
        if context["user_id"] ~= nil then
            record["userId"] = context["user_id"]
        end
        if context["correlation_id"] ~= nil then
            record["correlationId"] = context["correlation_id"]
        end
        -- Extract jaeger_trace_url from context if it exists
        -- This ensures it's available at top level for OpenSearch Dashboards
        if context["jaeger_trace_url"] ~= nil and context["jaeger_trace_url"] ~= "" then
            record["jaeger_trace_url"] = context["jaeger_trace_url"]
            -- Also ensure it's in context.jaeger_trace_url for nested access
            record["context"]["jaeger_trace_url"] = context["jaeger_trace_url"]
        end
    end
    
    -- Flatten nested req.* fields if they exist
    if record["req"] ~= nil and type(record["req"]) == "table" then
        local req_flat = flatten_table(record["req"], "req.")
        for key, value in pairs(req_flat) do
            -- Keep nested structure but also add flattened version for easier searching
            record[key] = value
        end
    end
    
    -- Flatten nested res.* fields if they exist
    if record["res"] ~= nil and type(record["res"]) == "table" then
        local res_flat = flatten_table(record["res"], "res.")
        for key, value in pairs(res_flat) do
            -- Keep nested structure but also add flattened version for easier searching
            record[key] = value
        end
        
        -- Also extract common response fields to top level with camelCase
        if record["res"]["statusCode"] ~= nil then
            record["resStatusCode"] = record["res"]["statusCode"]
        end
        if record["res"]["contentLength"] ~= nil then
            record["resContentLength"] = record["res"]["contentLength"]
        end
        if record["res"]["responseTime"] ~= nil then
            record["resResponseTime"] = record["res"]["responseTime"]
        end
    end
    
    -- Flatten input_details.* fields if they exist (common field structure)
    if record["input_details"] ~= nil and type(record["input_details"]) == "table" then
        local input_details = record["input_details"]
        
        -- Flatten all nested fields with prefix for searching
        local input_flat = flatten_table(input_details, "input_details.")
        for key, value in pairs(input_flat) do
            -- Add flattened version for easier searching and table display
            record[key] = value
        end
        
        -- Extract key input fields to top level with cleaner names for document details visibility
        if input_details["character_length"] ~= nil then
            record["inputCharacterLength"] = input_details["character_length"]
        end
        if input_details["word_count"] ~= nil then
            record["inputWordCount"] = input_details["word_count"]
        end
        if input_details["audio_length_seconds"] ~= nil then
            record["inputAudioLengthSeconds"] = input_details["audio_length_seconds"]
        end
        if input_details["audio_length_ms"] ~= nil then
            record["inputAudioLengthMs"] = input_details["audio_length_ms"]
        end
        if input_details["input_count"] ~= nil then
            record["inputCount"] = input_details["input_count"]
        end
        if input_details["token_count"] ~= nil then
            record["inputTokenCount"] = input_details["token_count"]
        end
    end
    
    -- Flatten output_details.* fields if they exist (common field structure)
    if record["output_details"] ~= nil and type(record["output_details"]) == "table" then
        local output_details = record["output_details"]
        
        -- Flatten all nested fields with prefix for searching
        local output_flat = flatten_table(output_details, "output_details.")
        for key, value in pairs(output_flat) do
            -- Add flattened version for easier searching and table display
            record[key] = value
        end
        
        -- Extract key output fields to top level with cleaner names for document details visibility
        if output_details["character_length"] ~= nil then
            record["outputCharacterLength"] = output_details["character_length"]
        end
        if output_details["word_count"] ~= nil then
            record["outputWordCount"] = output_details["word_count"]
        end
        if output_details["audio_length_seconds"] ~= nil then
            record["outputAudioLengthSeconds"] = output_details["audio_length_seconds"]
        end
        if output_details["audio_length_ms"] ~= nil then
            record["outputAudioLengthMs"] = output_details["audio_length_ms"]
        end
        if output_details["output_count"] ~= nil then
            record["outputCount"] = output_details["output_count"]
        end
        if output_details["token_count"] ~= nil then
            record["outputTokenCount"] = output_details["token_count"]
        end
    end
    
    return 1, timestamp, record
end

-- Function to add Jaeger trace URL to logs
function add_jaeger_url(tag, timestamp, record)
    -- First, check if jaeger_trace_url already exists at top level (from nest filter or extract_context_fields)
    -- If it exists and is not empty, preserve it and return
    if record["jaeger_trace_url"] ~= nil and record["jaeger_trace_url"] ~= "" then
        -- Ensure it's also in context for consistency
        if record["context"] == nil then
            record["context"] = {}
        end
        if type(record["context"]) == "table" then
            record["context"]["jaeger_trace_url"] = record["jaeger_trace_url"]
        end
        return 1, timestamp, record
    end
    
    -- If not at top level, check if it exists in context
    if record["context"] ~= nil and type(record["context"]) == "table" then
        local context = record["context"]
        if context["jaeger_trace_url"] ~= nil and context["jaeger_trace_url"] ~= "" then
            record["jaeger_trace_url"] = context["jaeger_trace_url"]
            return 1, timestamp, record
        end
    end
    
    -- Only add jaeger_trace_url if it doesn't already exist (fallback: construct from trace_id)
    if record["jaeger_trace_url"] == nil or record["jaeger_trace_url"] == "" then
        -- Check if trace_id exists
        if record["trace_id"] ~= nil and type(record["trace_id"]) == "string" and record["trace_id"] ~= "" then
            local trace_id = record["trace_id"]
            -- Store only the trace_id in jaeger_trace_url field
            -- OpenSearch Dashboards will use URL template to construct: http://localhost:16686/trace/{trace_id}
            -- This ensures the URL is treated as external absolute URL, not relative path
            record["jaeger_trace_url"] = trace_id
        end
    end
    
    return 1, timestamp, record
end

-- Function to filter logs based on service allowlist (INCLUDE_SERVICE_LOGS)
function filter_dashboard_logs(tag, timestamp, record)
    -- Read environment variables (no hardcoding)
    local include_services = os.getenv("INCLUDE_SERVICE_LOGS") or ""
    local exclude_init_logs = os.getenv("EXCLUDE_INIT_LOGS") or "false"
    
    -- Parse exclude_init_logs boolean
    local exclude_init = exclude_init_logs:lower():match("^%s*(true|1|yes|on)%s*$") ~= nil
    
    -- Filter initialization/noise logs if enabled
    if exclude_init then
        local message = record["message"] or ""
        local logger = record["logger"] or ""
        local level = record["level"] or ""
        local trace_id = record["trace_id"] or ""
        local method = record["method"] or ""
        
        -- Filter logs from "main" logger with INFO level (most initialization logs)
        -- But keep them if they have a method (HTTP request logs)
        if type(logger) == "string" and logger:lower() == "main" then
            if type(level) == "string" and level:upper() == "INFO" then
                -- Only filter if it's not an HTTP request log (no method field)
                if method == nil or method == "" then
                    return -1, timestamp, record
                end
            end
        end
        
        -- Filter initialization messages by pattern (case-insensitive)
        if type(message) == "string" and message ~= "" then
            local msg_lower = message:lower()
            
            -- Check if message matches initialization patterns
            local is_init_log = msg_lower:match("distributed tracing initialized") or
               msg_lower:match("fastapi instrumentation") or
               msg_lower:match("redis client created") or
               msg_lower:match("rate limiting middleware") or
               msg_lower:match("observability plugin") or
               msg_lower:match("model management plugin") or
               msg_lower:match("plugin initialized") or
               msg_lower:match("connected to redis") or
               msg_lower:match("connected to postgres") or
               msg_lower:match("starting.*service") or
               msg_lower:match("initialized for.*service") or
               (msg_lower:match("initialized") and msg_lower:match("service")) or
               (msg_lower:match("created") and (msg_lower:match("middleware") or msg_lower:match("for"))) or
               msg_lower:match("middleware added") or
               -- Additional patterns for service startup logs
               msg_lower:match("registered.*service.*registry") or
               msg_lower:match(".*service started successfully") or
               msg_lower:match(".*service started") or
               msg_lower:match("database tables verified") or
               msg_lower:match("database tables created") or
               msg_lower:match("tables verified/created") or
               msg_lower:match("socket%.io.*endpoint mounted") or
               msg_lower:match("streaming service initialized") or
               msg_lower:match("streaming endpoint mounted") or
               msg_lower:match("shutting down.*service") or
               msg_lower:match("service shutdown") or
               msg_lower:match("service registry registration")
            
            -- Filter initialization logs (especially those with trace_id that won't exist in Jaeger)
            if is_init_log then
                return -1, timestamp, record
            end
        end
    end
    
    -- If INCLUDE_SERVICE_LOGS is not set or empty, keep all logs (no filtering)
    if include_services == nil or include_services == "" then
        return 1, timestamp, record
    end
    
    -- Parse comma-separated service list and normalize service names
    local allowed_services = {}
    for service in include_services:gmatch("([^,]+)") do
        service = service:gsub("^%s+", ""):gsub("%s+$", ""):lower()  -- Trim whitespace and lowercase
        if service ~= "" then
            -- Map user-friendly names to actual service names in logs
            local service_mapping = {
                ["asr"] = "asr-service",
                ["audio lang detection"] = "audio-lang-detection-service",
                ["audio-lang-detection"] = "audio-lang-detection-service",
                ["language detection"] = "language-detection-service",
                ["language-detection"] = "language-detection-service",
                ["language diarization"] = "language-diarization-service",
                ["language-diarization"] = "language-diarization-service",
                ["llm"] = "llm-service",
                ["ner"] = "ner-service",
                ["nmt"] = "nmt-service",
                ["ocr"] = "ocr-service",
                ["pipeline"] = "pipeline-service",
                ["speaker diarization"] = "speaker-diarization-service",
                ["speaker-diarization"] = "speaker-diarization-service",
                ["transliteration"] = "transliteration-service",
                ["tts"] = "tts-service",
                ["auth"] = "auth-service"
            }
            
            -- Use mapping if available, otherwise assume it's already a service name
            local mapped_service = service_mapping[service] or service
            -- If user provided name without "-service", add it
            if not mapped_service:match("%-service$") then
                mapped_service = mapped_service .. "-service"
            end
            allowed_services[mapped_service] = true
        end
    end
    
    -- If no valid services in allowlist, keep all logs (backward compatible)
    if next(allowed_services) == nil then
        return 1, timestamp, record
    end
    
    -- Get service from log record
    local service = record["service"] or ""
    
    -- If log has no service field, drop it (dashboard logs, Kafka logs, etc. don't have service field)
    if service == nil or service == "" then
        return -1, timestamp, record
    end
    
    -- Normalize service name for comparison
    local service_lower = service:lower()
    
    -- Check if service is in allowed list
    local is_allowed = false
    for allowed_service, _ in pairs(allowed_services) do
        if service_lower == allowed_service:lower() or 
           service_lower:match("^" .. allowed_service:lower()) then
            is_allowed = true
            break
        end
    end
    
    -- Keep log if service is in allowlist, otherwise drop it
    if is_allowed then
        return 1, timestamp, record
    else
        return -1, timestamp, record
    end
end



