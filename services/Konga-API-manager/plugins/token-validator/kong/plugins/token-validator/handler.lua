local http  = require "resty.http"
local redis = require "resty.redis"

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
  -- Check if rate limiting is explicitly enabled (handle both boolean and string "false")
  local rate_limit_enabled = conf.enable_rate_limit
  if type(rate_limit_enabled) == "string" then
    rate_limit_enabled = rate_limit_enabled ~= "false" and rate_limit_enabled ~= "0"
  end
  -- Also check for nil, false, or empty string
  if not rate_limit_enabled or rate_limit_enabled == false or rate_limit_enabled == "" then
    kong.log.debug("Rate limiting disabled, skipping")
    return
  end

  local client_ip = kong.client.get_ip() or "unknown"
  local now = ngx.time()
  local window = conf.rate_window or 60
  local bucket = math.floor(now / window)
  local key = string.format("rl:%s:%d", client_ip, bucket)

  local red = redis:new()
  -- Use reasonable timeout to allow connection establishment
  red:set_timeout(2000)  -- 2 second timeout for connection and operations

  -- Try to connect with timeout protection
  -- Use hostname first, but the timeout should prevent blocking
  local redis_host = conf.redis_host or "redis"
  local redis_port = conf.redis_port or 6379
  
  local ok, err = red:connect(redis_host, redis_port)
  if not ok then
    kong.log.warn("rate limit redis connect failed (fail-open): ", err, " host: ", redis_host, " port: ", redis_port)
    -- Fail-open: allow request to proceed if Redis is unavailable
    return
  end

  -- Set timeout for subsequent operations
  red:set_timeout(2000)

  if conf.redis_password and conf.redis_password ~= "" then
    local ok_auth, err_auth = red:auth(conf.redis_password)
    if not ok_auth then
      kong.log.warn("rate limit redis auth failed (fail-open): ", err_auth)
      red:close()
      return -- fail-open
    end
  end

  local current, err = red:incr(key)
  if not current then
    kong.log.warn("rate limit redis incr failed (fail-open): ", err)
    red:close()
    return -- fail-open
  end

  if current == 1 then
    -- Set expiration, but don't fail if it errors
    local expire_ok, expire_err = red:expire(key, window)
    if not expire_ok then
      kong.log.warn("rate limit redis expire failed: ", expire_err)
    end
  end

  -- Check rate limit before closing/keeping connection
  if current > (conf.rate_limit or 100) then
    red:close()
    return kong.response.exit(429, {
      message = "Rate limit exceeded",
    }, {
      ["Retry-After"] = tostring(window),
    })
  end

  -- Reuse connection with keepalive for better performance (only if not rate limited)
  local ok_keepalive, err_keepalive = red:set_keepalive(10000, 100)
  if not ok_keepalive then
    kong.log.warn("rate limit redis keepalive failed: ", err_keepalive)
    red:close()
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

function TokenValidator:access(conf)
  local method = kong.request.get_method()
  local path   = kong.request.get_path()
  
  kong.log.warn("=== TokenValidator:access START === path: ", path, " method: ", method)

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
      kong.log.info("Path matched public pattern: ", pattern, " for path: ", path)
      break
    end
  end
  
  if not is_public then
    kong.log.info("Path is NOT public: ", path)
  end

  -- 3) Auth for protected paths
  if not is_public then
    local token = get_bearer_token()
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
  end

  -- 4) Optional rate limit (per IP) - only for non-public paths or if explicitly enabled
  -- Skip rate limiting for public paths to avoid unnecessary Redis calls
  if not is_public then
    kong.log.info("Checking rate limit for non-public path: ", path)
    check_rate_limit(conf)
  else
    kong.log.info("Skipping rate limit for public path: ", path)
  end

  -- 5) Extra request headers
  local correlation_id = kong.request.get_header("X-Correlation-ID") or ngx.var.request_id or tostring(ngx.now())
  local request_id     = ngx.var.request_id or tostring(ngx.now())
  local now_iso        = os.date("!%Y-%m-%dT%H:%M:%SZ")

  kong.service.request.set_header("X-Correlation-ID", correlation_id)
  kong.service.request.set_header("X-Request-ID", request_id)
  kong.service.request.set_header("X-Gateway-Timestamp", now_iso)
  kong.service.request.set_header("X-Forwarded-For", kong.client.get_ip() or "")

  -- 6) X-API-Key injection (per service)
  if conf.api_key and conf.api_key ~= "" then
    kong.service.request.set_header("X-API-Key", conf.api_key)
  end
  
  -- Explicitly allow request to proceed to upstream
  -- In Kong plugins, returning nil allows the request to continue
  return
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

