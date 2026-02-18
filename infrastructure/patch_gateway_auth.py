#!/usr/bin/env python3
"""
Patch the API Gateway's main.py to bypass authentication when AUTH_ENABLED=false.
This script runs at container startup before uvicorn starts.
It patches:
  1. ensure_authenticated_for_request() - general auth bypass
  2. check_permission() - permission/role check bypass (model-management, alerts, etc.)
"""
import re
import sys

MAIN_PY = "/app/main.py"

MARKER = "# [PATCHED] Skip auth"

with open(MAIN_PY, "r") as f:
    content = f.read()

# Already patched?
if MARKER in content:
    print("[patch_gateway_auth] Already patched, skipping.")
    sys.exit(0)

patched = 0

# --- Patch 1: ensure_authenticated_for_request ---
AUTH_BYPASS = (
    '    # [PATCHED] Skip auth when AUTH_ENABLED=false\n'
    '    import os as _os\n'
    '    if _os.getenv("AUTH_ENABLED", "true").lower() == "false":\n'
    '        req.state.user_id = None\n'
    '        req.state.api_key_id = None\n'
    '        req.state.is_authenticated = True\n'
    '        return\n'
)

pattern1 = (
    r'(async def ensure_authenticated_for_request\([^)]*\)[^:]*:\s*\n'
    r'(?:\s*"""[^"]*"""\s*\n)?)'
)

match1 = re.search(pattern1, content)
if match1:
    insert_pos = match1.end()
    content = content[:insert_pos] + AUTH_BYPASS + content[insert_pos:]
    patched += 1
    print("[patch_gateway_auth] Patched ensure_authenticated_for_request().")
else:
    print("[patch_gateway_auth] WARNING: Could not find ensure_authenticated_for_request().")

# --- Patch 2: check_permission ---
PERM_BYPASS = (
    '    # [PATCHED] Skip permission check when AUTH_ENABLED=false\n'
    '    import os as _os2\n'
    '    if _os2.getenv("AUTH_ENABLED", "true").lower() == "false":\n'
    '        return\n'
)

pattern2 = (
    r'(async def check_permission\([^)]*\)[^:]*:\s*\n'
    r'(?:\s*"""[\s\S]*?"""\s*\n)?)'
)

match2 = re.search(pattern2, content)
if match2:
    insert_pos = match2.end()
    content = content[:insert_pos] + PERM_BYPASS + content[insert_pos:]
    patched += 1
    print("[patch_gateway_auth] Patched check_permission().")
else:
    print("[patch_gateway_auth] WARNING: Could not find check_permission().")

if patched > 0:
    with open(MAIN_PY, "w") as f:
        f.write(content)
    print(f"[patch_gateway_auth] Successfully patched {patched} function(s).")
else:
    print("[patch_gateway_auth] WARNING: No functions patched. Gateway may require authentication.")
