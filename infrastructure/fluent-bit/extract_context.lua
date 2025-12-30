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
    
    return 1, timestamp, record
end
 
-- Function to add Jaeger trace URL to logs
function add_jaeger_url(tag, timestamp, record)
    -- Check if trace_id exists
    if record["trace_id"] ~= nil and type(record["trace_id"]) == "string" and record["trace_id"] ~= "" then
        local trace_id = record["trace_id"]
        -- Generate Jaeger URL (using localhost for external access)
        -- Change to http://jaeger:16686 if you need internal URL
        local jaeger_url = "http://localhost:16686/trace/" .. trace_id
        
        -- Add the URL as a string field
        record["jaeger_trace_url"] = jaeger_url
        
        -- Also add as a formatted URL field that OpenSearch Dashboards can recognize
        -- This helps with auto-detection of URLs
        record["jaeger_url"] = jaeger_url
        
        -- Add URL components separately for better searchability
        record["jaeger_host"] = "localhost:16686"
        record["jaeger_trace_id"] = trace_id
    end
    
    return 1, timestamp, record
end
 