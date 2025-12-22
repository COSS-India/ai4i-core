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
    end
    
    return 1, timestamp, record
end

