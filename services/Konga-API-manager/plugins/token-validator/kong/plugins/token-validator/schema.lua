local typedefs = require "kong.db.schema.typedefs"

return {
  name = "token-validator",
  fields = {
    { consumer = typedefs.no_consumer },
    { protocols = typedefs.protocols_http },
    {
      config = {
        type = "record",
        fields = {
          {
            auth_service_url = {
              type = "string",
              required = true,
              default = "http://auth-service:8081/api/v1/auth/validate",
            },
          },
          {
            -- Service-specific API key to inject as X-API-Key
            api_key = {
              type = "string",
              required = false,
            },
          },

          -- CORS / preflight
          {
            cors_allowed_origins = {
              type = "array",
              elements = { type = "string" },
              required = false,
              default = { "*" },
            },
          },
          {
            cors_allowed_methods = {
              type = "array",
              elements = { type = "string" },
              required = false,
              default = { "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS" },
            },
          },
          {
            cors_allowed_headers = {
              type = "array",
              elements = { type = "string" },
              required = false,
              default = { "Authorization", "Content-Type", "X-Requested-With" },
            },
          },
          {
            cors_allow_credentials = {
              type = "boolean",
              required = false,
              default = true,
            },
          },

          -- Optional rate limiting (simple, per IP)
          {
            enable_rate_limit = {
              type = "boolean",
              required = false,
              default = false,
            },
          },
          {
            rate_limit = {
              type = "integer",
              required = false,
              default = 100,
            },
          },
          {
            rate_window = {
              type = "integer",
              required = false,
              default = 60,
            },
          },
          {
            redis_host = {
              type = "string",
              required = false,
              default = "redis",
            },
          },
          {
            redis_port = {
              type = "integer",
              required = false,
              default = 6379,
            },
          },
          {
            redis_password = {
              type = "string",
              required = false,
            },
          },
        },
      },
    },
  },
}

