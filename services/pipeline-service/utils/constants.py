"""Pipeline service utility constants."""

# Gateway-injected headers (set by APISIX forward-auth) to forward to downstream services
GATEWAY_HEADER_NAMES = ("X-Validated", "X-User-ID", "X-User-Email", "X-User-Roles", "X-Auth-Source")
