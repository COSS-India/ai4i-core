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

-- Function to filter logs based on service and endpoint whitelist
-- Only logs matching BOTH service AND endpoint are kept
function filter_dashboard_logs(tag, timestamp, record)
    -- Read environment variables
    local exclude_init_logs = os.getenv("EXCLUDE_INIT_LOGS") or "false"
    
    -- Parse exclude_init_logs boolean
    local exclude_init = exclude_init_logs:lower():match("^%s*(true|1|yes|on)%s*$") ~= nil
    
    -- Filter initialization/noise logs if enabled
    if exclude_init then
        local message = record["message"] or ""
        local logger = record["logger"] or ""
        local level = record["level"] or ""
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
               msg_lower:match("service registry registration") or
               msg_lower:match("requestloggingmiddleware initialized")
            
            -- Filter initialization logs
            if is_init_log then
                return -1, timestamp, record
            end
        end
    end
    
    -- Define whitelist of allowed service + endpoint combinations
    local allowed_combinations = {
        ["asr-service"] = {
            "/asr/inference",
            "/api/v1/asr/inference"
        },
        ["audio-lang-detection-service"] = {
            "/audio-lang-detection/inference",
            "/api/v1/audio-lang-detection/inference"
        },
        ["language-detection-service"] = {
            "/language-detection/inference",
            "/api/v1/language-detection/inference"
        },
        ["language-diarization-service"] = {
            "/language-diarization/inference",
            "/api/v1/language-diarization/inference"
        },
        ["llm-service"] = {
            "/llm/inference",
            "/api/v1/llm/inference"
        },
        ["ner-service"] = {
            "/ner/inference",
            "/api/v1/ner/inference"
        },
        ["nmt-service"] = {
            "/nmt/inference",
            "/api/v1/nmt/inference"
        },
        ["ocr-service"] = {
            "/ocr/inference",
            "/api/v1/ocr/inference"
        },
        ["pipeline-service"] = {
            "/pipeline/inference",
            "/api/v1/pipeline/inference"
        },
        ["speaker-diarization-service"] = {
            "/speaker-diarization/inference",
            "/api/v1/speaker-diarization/inference"
        },
        ["transliteration-service"] = {
            "/transliteration/inference",
            "/api/v1/transliteration/inference"
        },
        ["tts-service"] = {
            "/tts/inference",
            "/api/v1/tts/inference"
        },
        ["auth-service"] = {
            "/auth/login",
            "/api/v1/auth/login",
            "/auth/logout",
            "/api/v1/auth/logout"
        }
    }
    
    -- Get service and path from log record
    local service = record["service"] or ""
    
    -- CRITICAL: Check path in multiple locations
    -- Priority 1: Check if path was already lifted by nest filter (should be at top level)
    local path = record["path"] or ""
    
    -- Priority 2: Check context.path (source of truth for RequestLoggingMiddleware logs)
    -- The nest filter should lift it, but we check context.path directly as fallback
    if (path == nil or path == "") then
        if record["context"] ~= nil and type(record["context"]) == "table" then
            path = record["context"]["path"] or ""
            -- If found in context, set it at top level for matching and indexing
            if path ~= "" then
                record["path"] = path
            end
        end
    end
    
    -- Priority 3: Try req.path (some logs have path in req object)
    if (path == nil or path == "") then
        if record["req"] ~= nil and type(record["req"]) == "table" then
            path = record["req"]["path"] or record["req"]["url"] or ""
            if path ~= "" then
                record["path"] = path
            end
        end
    end
    
    -- If path is empty, try to extract from message field
    if path == nil or path == "" then
        local message = record["message"] or ""
        if type(message) == "string" and message ~= "" then
            -- Look for patterns like "POST /api/v1/asr/inference - 200" or "GET /auth/login"
            -- Also handle "[TENANT_DEBUG] _extract_tenant_id called for path: /api/v1/asr/inference"
            -- First try: Extract path from HTTP method pattern "METHOD /path - status"
            -- Pattern: METHOD SPACE PATH (where PATH is everything until space-dash-space or end)
            -- This handles: "POST /api/v1/auth/logout - 200"
            -- Use more flexible pattern to match paths with slashes, dashes, dots, and word characters
            local method_match, path_part = message:match("(GET|POST|PUT|DELETE|PATCH)%s+([/%w%-%./]+)")
            if path_part and path_part:match("^/") then
                path = path_part
            else
                -- Try pattern: "path: /api/v1/asr/inference"
                local extracted = message:match("path:%s+([/%w%-%./]+)")
                if extracted then
                    path = extracted
                else
                    -- Last resort: extract path from message like "POST /api/v1/auth/logout - 200"
                    -- Match everything after method until space-dash or space-number
                    local _, extracted_path2 = message:match("(GET|POST|PUT|DELETE|PATCH)%s+([^%s%-]+)")
                    if extracted_path2 and extracted_path2:match("^/") then
                        path = extracted_path2
                    end
                end
            end
        end
    end
    
    -- CRITICAL: Set path in record IMMEDIATELY after extraction
    -- This ensures it's available for both matching and indexing
    if path ~= nil and path ~= "" then
        record["path"] = path
    end
    
    -- If log has no service field, drop it
    if service == nil or service == "" then
        return -1, timestamp, record
    end
    
    -- Normalize service name for comparison
    local service_lower = service:lower()
    
    -- EARLY EXIT: For auth-service with login/logout, always allow through
    -- This ensures logs are never dropped due to path extraction issues
    if service_lower == "auth-service" then
        local message = record["message"] or ""
        if type(message) == "string" and (message:find("login") or message:find("logout")) then
            -- Extract path from message if not already found
            if (path == nil or path == "") then
                local _, msg_path = message:match("(GET|POST|PUT|DELETE|PATCH)%s+([/%w%-%./]+)")
                if msg_path and msg_path:match("^/") then
                    path = msg_path
                end
            end
            -- Also try to get from context
            if (path == nil or path == "") and record["context"] ~= nil and type(record["context"]) == "table" then
                path = record["context"]["path"] or ""
            end
            -- Set path in record for indexing
            if path ~= nil and path ~= "" then
                record["path"] = path
            end
            -- Always allow auth-service login/logout logs through
            return 1, timestamp, record
        end
    end
    
    -- For other services, extract path from message if not found in context
    if (path == nil or path == "") then
        local message = record["message"] or ""
        if type(message) == "string" and message ~= "" then
            -- Extract from "POST /api/v1/auth/login - 200"
            -- Use more flexible pattern to match paths with slashes, dashes, dots, and word characters
            local _, msg_path = message:match("(GET|POST|PUT|DELETE|PATCH)%s+([/%w%-%./]+)")
            if msg_path and msg_path:match("^/") then
                path = msg_path
            end
        end
    end
    
    -- CRITICAL: Always set path in record so it's indexed in OpenSearch
    -- This must be done BEFORE the matching logic
    if path ~= nil and path ~= "" then
        record["path"] = path
    end
    
    -- Check if service is in whitelist
    local allowed_endpoints = nil
    for allowed_service, endpoints in pairs(allowed_combinations) do
        if service_lower == allowed_service:lower() or 
           service_lower:match("^" .. allowed_service:lower()) then
            allowed_endpoints = endpoints
            break
        end
    end
    
    -- If service is not in whitelist, drop the log
    if allowed_endpoints == nil then
        return -1, timestamp, record
    end
    
    -- SAFETY: For RequestLoggingMiddleware logs, ensure path is extracted before dropping
    -- These are the actual API request logs we want to keep - check BEFORE dropping empty paths
    local logger = record["logger"] or ""
    if (path == nil or path == "") and type(logger) == "string" and logger:find("request_logging") and allowed_endpoints ~= nil then
        -- Extract path from message if not already found
        local message = record["message"] or ""
        if type(message) == "string" and message ~= "" then
            local _, msg_path = message:match("(GET|POST|PUT|DELETE|PATCH)%s+([/%w%-%./]+)")
            if msg_path and msg_path:match("^/") then
                path = msg_path
                record["path"] = path
            end
        end
        -- Also try to get from context (most reliable source)
        if (path == nil or path == "") and record["context"] ~= nil and type(record["context"]) == "table" then
            path = record["context"]["path"] or ""
            if path ~= "" then
                record["path"] = path
            end
        end
        -- If we found the path, allow through (don't drop)
        if path ~= nil and path ~= "" then
            -- Path found, continue to matching logic below
        else
            -- Even if path extraction failed, allow RequestLoggingMiddleware logs through
            -- Extract from message as last resort and set a placeholder
            if type(message) == "string" and message ~= "" then
                local _, msg_path = message:match("(GET|POST|PUT|DELETE|PATCH)%s+([/%w%-%./]+)")
                if msg_path and msg_path:match("^/") then
                    record["path"] = msg_path
                    path = msg_path
                end
            end
            -- Always allow RequestLoggingMiddleware logs through if service is whitelisted
            if allowed_endpoints ~= nil then
                return 1, timestamp, record
            end
        end
    end
    
    -- If path is still empty, drop the log (we only want endpoint-specific logs)
    -- BUT: RequestLoggingMiddleware logs are already handled above
    if path == nil or path == "" then
        return -1, timestamp, record
    end
    
    -- Normalize path for comparison (remove query strings, trailing slashes)
    local path_normalized = path:gsub("%?.*$", ""):gsub("/+$", "")
    if path_normalized == "" then
        path_normalized = "/"
    end
    
    -- Filter out health checks and metrics endpoints
    if path_normalized:match("/health") or 
       path_normalized:match("/metrics") or 
       path_normalized:match("/status") or
       path_normalized:match("/healthz") or
       path_normalized:match("/ready") then
        return -1, timestamp, record
    end
    
    -- Check if path matches any allowed endpoint for this service
    local path_matches = false
    for _, allowed_path in ipairs(allowed_endpoints) do
        local allowed_normalized = allowed_path:gsub("%?.*$", ""):gsub("/+$", "")
        if allowed_normalized == "" then
            allowed_normalized = "/"
        end
        
        -- Exact match
        if path_normalized == allowed_normalized then
            path_matches = true
            break
        end
        
        -- Match if path ends with allowed path (handles /api/v1/asr/inference matching /asr/inference)
        -- Escape special characters in allowed_path for pattern matching
        local escaped_allowed = allowed_normalized:gsub("([%-%.%+%[%]%(%)%^%$%%])", "%%%1")
        if path_normalized:match(escaped_allowed .. "$") then
            path_matches = true
            break
        end
        
        -- Match if path contains the allowed path (handles /api/v1/asr/inference containing /asr/inference)
        -- Use plain string find (not pattern matching) for substring search
        if path_normalized:find(allowed_normalized, 1, true) then
            path_matches = true
            break
        end
    end
    
    -- Keep log only if both service AND path match whitelist
    if path_matches then
        -- Ensure path is set in record for OpenSearch indexing (in case it wasn't set earlier)
        if record["path"] == nil or record["path"] == "" then
            record["path"] = path
        end
        return 1, timestamp, record
    else
        -- SAFETY: For RequestLoggingMiddleware logs (logger contains "request_logging")
        -- These are the actual API request logs we want to keep - they have the path in context.path
        -- Allow them through if service is in whitelist, regardless of path matching
        local request_logger = record["logger"] or ""
        if type(request_logger) == "string" and request_logger:find("request_logging") and allowed_endpoints ~= nil then
            -- Extract path from message if not already found
            if (path == nil or path == "") then
                local message = record["message"] or ""
                if type(message) == "string" and message ~= "" then
                    local _, msg_path = message:match("(GET|POST|PUT|DELETE|PATCH)%s+([/%w%-%./]+)")
                    if msg_path and msg_path:match("^/") then
                        path = msg_path
                    end
                end
            end
            -- Also try to get from context (most reliable source)
            if (path == nil or path == "") and record["context"] ~= nil and type(record["context"]) == "table" then
                path = record["context"]["path"] or ""
            end
            -- Set path in record for indexing (use message extraction as fallback)
            if path ~= nil and path ~= "" then
                record["path"] = path
            elseif (path == nil or path == "") then
                -- Last resort: extract from message
                local message = record["message"] or ""
                if type(message) == "string" and message ~= "" then
                    local _, msg_path = message:match("(GET|POST|PUT|DELETE|PATCH)%s+([/%w%-%./]+)")
                    if msg_path and msg_path:match("^/") then
                        record["path"] = msg_path
                    end
                end
            end
            -- Always allow RequestLoggingMiddleware logs through if service is whitelisted
            return 1, timestamp, record
        end
        
        -- SAFETY: For auth-service, always allow logs with login/logout in message
        -- This ensures logs aren't dropped due to path extraction or matching issues
        if service_lower == "auth-service" then
            local message = record["message"] or ""
            if type(message) == "string" and (message:find("login") or message:find("logout")) then
                -- Extract path from message and set it
                local _, msg_path = message:match("(GET|POST|PUT|DELETE|PATCH)%s+([/%w%-%./]+)")
                if msg_path and msg_path:match("^/") then
                    record["path"] = msg_path
                elseif path ~= nil and path ~= "" then
                    -- Use the path we extracted earlier
                    record["path"] = path
                else
                    -- Fallback: extract from context if available
                    if record["context"] ~= nil and type(record["context"]) == "table" then
                        local ctx_path = record["context"]["path"]
                        if ctx_path then
                            record["path"] = ctx_path
                        end
                    end
                end
                -- Always allow auth-service login/logout logs through
                return 1, timestamp, record
            end
        end
        return -1, timestamp, record
    end
end




