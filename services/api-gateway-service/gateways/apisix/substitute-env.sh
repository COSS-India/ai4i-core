# Substitute APISIX environment variables into the routes config.
# Reads the template from APISIX_CONFIG_TEMPLATE and writes to APISIX_CONF_DIR/apisix.yaml.
# Set APISIX_PUBLIC_ORIGIN, APISIX_UPSTREAM_SUFFIX in the environment.

set -e

CONF_DIR="${APISIX_CONF_DIR:-/usr/local/apisix/conf}"
TEMPLATE="${APISIX_CONFIG_TEMPLATE:-$CONF_DIR/apisix.yaml.template}"
OUTPUT="$CONF_DIR/apisix.yaml"

APISIX_PUBLIC_ORIGIN="${APISIX_PUBLIC_ORIGIN:-http://localhost:3000}"
APISIX_UPSTREAM_SUFFIX="${APISIX_UPSTREAM_SUFFIX:-}"

if [ ! -f "$TEMPLATE" ]; then
    echo "Error: APISIX template not found at $TEMPLATE" >&2
    exit 1
fi

# Escape & and \ for sed replacement (no envsubst in APISIX image).
escape_sed() { printf '%s' "$1" | sed 's/[&\\]/\\&/g'; }

sed -e "s#\${APISIX_PUBLIC_ORIGIN}#$(escape_sed "$APISIX_PUBLIC_ORIGIN")#g" \
    -e "s#\${APISIX_UPSTREAM_SUFFIX}#$(escape_sed "$APISIX_UPSTREAM_SUFFIX")#g" \
    < "$TEMPLATE" > "$OUTPUT"

echo "APISIX config generated at $OUTPUT (origin=$APISIX_PUBLIC_ORIGIN upstream_suffix=${APISIX_UPSTREAM_SUFFIX:-<empty>})"
