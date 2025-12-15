local http  = require "resty.http"
local redis = require "resty.redis"
local cjson = require "cjson"

local kong  = kong
local ngx   = ngx

local TokenValidator = {
  PRIORITY = 1000,
  VERSION  = "1.0.0",
}

-- Utility: extract Bearer token
local function get_bearer_token()
  local auth_header = kong.request.get_header("authorization")
  if not auth_header then
    return nil
  end

  local m, err = ngx.re.match(auth_header, [[^\s*Bearer\s+(.+)$]], "jo")
  if not m then
    return nil
  end

  return m[1]
end

-- Utility: basic CORS headers
local function build_cors_headers(conf)
  local origins = table.concat(conf.cors_allowed_origins or { "*" }, ", ")
  local methods = table.concat(conf.cors_allowed_methods or { "GET", "POST", "OPTIONS" }, ", ")
  -- If browser sent Access-Control-Request-Headers, echo them back so custom headers pass preflight
  local requested_headers = kong.request.get_header("access-control-request-headers")
  local headers
  if requested_headers and requested_headers ~= "" then
    headers = requested_headers
  else
    headers = table.concat(conf.cors_allowed_headers or { "Authorization", "Content-Type", "X-Requested-With" }, ", ")
  end

  local h = {
    ["Access-Control-Allow-Origin"]  = origins,
    ["Access-Control-Allow-Methods"] = methods,
    ["Access-Control-Allow-Headers"] = headers,
  }

  if conf.cors_allow_credentials then
    h["Access-Control-Allow-Credentials"] = "true"
  end

  return h
end

-- Optional rate limiting (per IP)
local function check_rate_limit(conf)
  if not conf.enable_rate_limit then
    return
  end

  local client_ip = kong.client.get_ip() or "unknown"
  local now = ngx.time()
  local window = conf.rate_window or 60
  local bucket = math.floor(now / window)
  local key = string.format("rl:%s:%d", client_ip, bucket)

  local red = redis:new()
  red:set_timeout(1000)

  local ok, err = red:connect(conf.redis_host or "redis", conf.redis_port or 6379)
  if not ok then
    kong.log.err("rate limit redis connect failed: ", err)
    return -- fail-open
  end

  if conf.redis_password and conf.redis_password ~= "" then
    local ok_auth, err_auth = red:auth(conf.redis_password)
    if not ok_auth then
      kong.log.err("rate limit redis auth failed: ", err_auth)
      return
    end
  end

  local current, err = red:incr(key)
  if not current then
    kong.log.err("rate limit redis incr failed: ", err)
    return
  end

  if current == 1 then
    red:expire(key, window)
  end

  if current > (conf.rate_limit or 100) then
    return kong.response.exit(429, {
      message = "Rate limit exceeded",
    }, {
      ["Retry-After"] = tostring(window),
    })
  end
end

-- Token validation via Auth Service
local function validate_token(conf, token)
  local httpc = http.new()
  httpc:set_timeout(5000)

  local auth_service_url = conf.auth_service_url or "http://auth-service:8081/api/v1/auth/validate"

  local res, err = httpc:request_uri(auth_service_url, {
    method  = "POST",
    headers = {
      ["Authorization"] = "Bearer " .. token,
      ["Content-Type"]  = "application/json",
    },
    body    = "{}",
    ssl_verify = false,
  })

  if not res then
    kong.log.err("Auth service validation error: ", err)
    return nil, "auth_service_unavailable"
  end

  if res.status ~= 200 then
    kong.log.warn("Token validation failed with status: ", res.status, " body: ", res.body or "")
    return false, "invalid_token"
  end

  return true, nil
end

-- API key permission validation via Auth Service
local function validate_api_key_permissions(conf, api_key, service, action)
  local httpc = http.new()
  httpc:set_timeout(5000)

  local url = conf.auth_api_key_url or "http://auth-service:8081/api/v1/auth/validate-api-key"

  local res, err = httpc:request_uri(url, {
    method  = "POST",
    headers = {
      ["Content-Type"]  = "application/json",
    },
    body    = cjson.encode({
      api_key = api_key,
      service = service,
      action  = action,
    }),
    ssl_verify = false,
  })

  if not res then
    kong.log.err("Auth service api-key validation error: ", err)
    return nil, "auth_service_unavailable"
  end

  if res.status ~= 200 then
    -- propagate message if present
    local msg = "Invalid API key or insufficient permissions"
    if res.body and res.body ~= "" then
      local ok, body = pcall(cjson.decode, res.body)
      if ok and body and (body.message or (body.detail and body.detail)) then
        msg = body.message or body.detail
      end
    end
    return false, msg
  end

  -- Check response body for valid field (even if status is 200)
  if res.body and res.body ~= "" then
    local ok, body = pcall(cjson.decode, res.body)
    if ok and body then
      -- Check if valid field is false
      if body.valid == false then
        local msg = body.message or "Invalid API key or insufficient permissions"
        return false, msg
      end
      -- If valid is true or not present, consider it valid
      if body.valid == true then
        return true, nil
      end
    end
  end

  -- Default to valid if status is 200 and no body validation
  return true, nil
end

local function determine_service_and_action(path, method)
  local p = string.lower(path or "")
  local m = string.upper(method or "GET")

  local service = "unknown"
  local services = { "asr", "nmt", "tts", "pipeline", "model-management", "llm" }
  for _, svc in ipairs(services) do
    if string.find(p, "/api/v1/" .. svc) then
      service = svc
      break
    end
  end

  local action = "read"
  if string.find(p, "/inference") and m == "POST" then
    action = "inference"
  elseif m ~= "GET" then
    -- treat other write methods as inference/modify operations
    action = "inference"
  end

  return service, action
end

-- Check if service requires both Bearer token AND API key
local function requires_both_auth_and_api_key(path)
  local p = string.lower(path or "")
  local services_requiring_both = { "asr", "nmt", "tts", "pipeline", "llm" }
  for _, svc in ipairs(services_requiring_both) do
    if string.find(p, "/api/v1/" .. svc) then
      return true
    end
  end
  return false
end

function TokenValidator:access(conf)
  local method = kong.request.get_method()
  local path   = kong.request.get_path()

  -- 1) CORS preflight: respond and skip auth
  if method == "OPTIONS" then
    local headers = build_cors_headers(conf)
    return kong.response.exit(204, nil, headers)
  end

  -- 2) Public paths (no auth, but still headers / CORS)
  local public_paths = {
    "^/api/v1/auth/login",
    "^/api/v1/auth/register",
    "^/api/v1/auth/refresh",
    "^/api/v1/auth/reset%-password",
    "^/api/v1/auth/request%-password%-reset",
    "^/api/v1/auth/oauth2",
    -- Feature flags / config service should be accessible without auth
    "^/api/v1/feature%-flags",
    "^/api/v1/config",
  }

  local is_public = false
  for _, pattern in ipairs(public_paths) do
    if string.match(path, pattern) then
      is_public = true
      break
    end
  end

  -- 3) Auth for protected paths
  if not is_public then
    local api_key = kong.request.get_header("X-API-Key")
    local token = get_bearer_token()
    local requires_both = requires_both_auth_and_api_key(path)
    local path_lower = string.lower(path or "")

    -- ******************************************************************
    -- Special case: MODEL-MANAGEMENT should be **JWT-only**
    -- Ignore X-API-Key completely and only validate the Bearer token.
    -- ******************************************************************
    if string.find(path_lower, "/api/v1/model%-management") then
      if not token or token == "" then
        return kong.response.exit(401, {
          message = "Missing or invalid Authorization header",
        }, {
          ["WWW-Authenticate"] = "Bearer",
          ["Content-Type"]     = "application/json",
        })
      end

      local ok, err = validate_token(conf, token)
      if err == "auth_service_unavailable" then
        return kong.response.exit(503, { message = "Authentication service unavailable" }, {
          ["Content-Type"] = "application/json",
        })
      end

      if not ok then
        return kong.response.exit(401, { message = "Invalid or expired token" }, {
          ["WWW-Authenticate"] = "Bearer",
          ["Content-Type"]     = "application/json",
        })
      end

      -- JWT is valid; propagate auth source as AUTH_TOKEN
      local auth_source = kong.request.get_header("X-Auth-Source")
      if auth_source and auth_source ~= "" then
        kong.service.request.set_header("X-Auth-Source", auth_source)
      else
        kong.service.request.set_header("X-Auth-Source", "AUTH_TOKEN")
      end

      -- Skip all API key logic for model-management
      goto done_auth
    end
    
    -- For ASR, NMT, TTS, Pipeline, LLM: require BOTH Bearer token AND API key
    if requires_both then
      -- Check if Bearer token is missing
      if not token or token == "" then
        return kong.response.exit(401, {
          error = "AUTHENTICATION_REQUIRED",
          message = "Authorization token is required."
        }, {
          ["WWW-Authenticate"] = "Bearer",
          ["Content-Type"]     = "application/json",
        })
      end
      
      -- Check if API key is missing
      if not api_key or api_key == "" then
        return kong.response.exit(401, {
          error = "API_KEY_MISSING",
          message = "API key is required to access this service."
        }, {
          ["Content-Type"] = "application/json",
        })
      end
      
      -- Validate Bearer token first
      local ok, err = validate_token(conf, token)
      if err == "auth_service_unavailable" then
        return kong.response.exit(503, { message = "Authentication service unavailable" }, {
          ["Content-Type"] = "application/json",
        })
      end

      if not ok then
        return kong.response.exit(401, {
          error = "AUTHENTICATION_REQUIRED",
          message = "Authorization token is required."
        }, {
          ["WWW-Authenticate"] = "Bearer",
          ["Content-Type"]     = "application/json",
        })
      end
      
      -- Validate API key permissions
      local service, action = determine_service_and_action(path, method)
      ok, err = validate_api_key_permissions(conf, api_key, service, action)

      if err == "auth_service_unavailable" then
        return kong.response.exit(503, { message = "Authentication service unavailable" }, {
          ["Content-Type"] = "application/json",
        })
      end

      if not ok then
        return kong.response.exit(401, {
          error = "API_KEY_MISSING",
          message = "API key is required to access this service."
        }, {
          ["Content-Type"] = "application/json",
        })
      end
      
      -- Both are valid; set headers
      local auth_source = kong.request.get_header("X-Auth-Source")
      if auth_source and auth_source ~= "" then
        kong.service.request.set_header("X-Auth-Source", auth_source)
      else
        kong.service.request.set_header("X-Auth-Source", "AUTH_TOKEN")
      end
    else
      -- For other services: default logic (either Bearer OR API key)
      -- First determine logical service/action from path
        local service, action = determine_service_and_action(path, method)
      local p_lower = string.lower(path or "")

      -- Special case: any model-management path should be JWT-only (no API key permission check),
      -- even if X-API-Key is present.
      if string.find(p_lower, "model%-management") then
        -- Ignore any X-API-Key header and just validate the Bearer token
        if not token or token == "" then
          return kong.response.exit(401, {
            message = "Missing or invalid Authorization header",
          }, {
            ["WWW-Authenticate"] = "Bearer",
            ["Content-Type"]     = "application/json",
          })
        end

        local ok, err = validate_token(conf, token)
        if err == "auth_service_unavailable" then
          return kong.response.exit(503, { message = "Authentication service unavailable" }, {
            ["Content-Type"] = "application/json",
          })
        end

        if not ok then
          return kong.response.exit(401, { message = "Invalid or expired token" }, {
            ["WWW-Authenticate"] = "Bearer",
            ["Content-Type"]     = "application/json",
          })
        end

        -- For model-management, mark auth source as JWT
        local auth_source = kong.request.get_header("X-Auth-Source")
        if auth_source and auth_source ~= "" then
          kong.service.request.set_header("X-Auth-Source", auth_source)
        else
          kong.service.request.set_header("X-Auth-Source", "AUTH_TOKEN")
        end

        -- Skip API key validation entirely for model-management
      elseif api_key and api_key ~= "" then
        -- For other services, if an API key is present, validate it via auth service
        local ok, err = validate_api_key_permissions(conf, api_key, service, action)

        if err == "auth_service_unavailable" then
          return kong.response.exit(503, { message = "Authentication service unavailable" }, {
            ["Content-Type"] = "application/json",
          })
        end

        if not ok then
          return kong.response.exit(403, { message = err or "Invalid API key or insufficient permissions" }, {
            ["Content-Type"] = "application/json",
          })
        end

        -- X-API-Key is valid; ensure X-Auth-Source is set
        local auth_source = kong.request.get_header("X-Auth-Source")
        if auth_source and auth_source ~= "" then
          kong.service.request.set_header("X-Auth-Source", auth_source)
        else
          kong.service.request.set_header("X-Auth-Source", "API_KEY")
        end
      else
        -- No (or ignored) X-API-Key, validate Bearer token (existing flow)
        if not token or token == "" then
          return kong.response.exit(401, {
            message = "Missing or invalid Authorization header",
          }, {
            ["WWW-Authenticate"] = "Bearer",
            ["Content-Type"]     = "application/json",
          })
        end

        local ok, err = validate_token(conf, token)
        if err == "auth_service_unavailable" then
          return kong.response.exit(503, { message = "Authentication service unavailable" }, {
            ["Content-Type"] = "application/json",
          })
        end

        if not ok then
          return kong.response.exit(401, { message = "Invalid or expired token" }, {
            ["WWW-Authenticate"] = "Bearer",
            ["Content-Type"]     = "application/json",
          })
        end
        
        -- Set X-Auth-Source for Bearer token
        local auth_source = kong.request.get_header("X-Auth-Source")
        if auth_source and auth_source ~= "" then
          kong.service.request.set_header("X-Auth-Source", auth_source)
        else
          kong.service.request.set_header("X-Auth-Source", "AUTH_TOKEN")
        end
      end
    end
  end

  ::done_auth::

  -- 4) Optional rate limit (per IP)
  check_rate_limit(conf)

  -- 5) Extra request headers
  local correlation_id = kong.request.get_header("X-Correlation-ID") or ngx.var.request_id or tostring(ngx.now())
  local request_id     = ngx.var.request_id or tostring(ngx.now())
  local now_iso        = os.date("!%Y-%m-%dT%H:%M:%SZ")

  kong.service.request.set_header("X-Correlation-ID", correlation_id)
  kong.service.request.set_header("X-Request-ID", request_id)
  kong.service.request.set_header("X-Gateway-Timestamp", now_iso)
  kong.service.request.set_header("X-Forwarded-For", kong.client.get_ip() or "")

  -- 6) X-API-Key injection (per service) - only if not already set from request
  -- Check original request header, not service request (which doesn't support get_header)
  local existing_api_key = kong.request.get_header("X-API-Key")
  if (not existing_api_key or existing_api_key == "") and conf.api_key and conf.api_key ~= "" then
    kong.service.request.set_header("X-API-Key", conf.api_key)
  end
end

function TokenValidator:header_filter(conf)
  -- CORS headers on all responses
  local headers = build_cors_headers(conf)
  for k, v in pairs(headers) do
    kong.response.set_header(k, v)
  end

  -- Extra response headers
  local correlation_id = kong.request.get_header("X-Correlation-ID") or ngx.var.request_id or tostring(ngx.now())
  kong.response.set_header("X-Correlation-ID", correlation_id)
  kong.response.set_header("X-Served-By", "kong-token-validator")
end

return TokenValidator

