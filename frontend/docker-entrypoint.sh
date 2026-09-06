#!/bin/sh
# Frontend container entrypoint (M5.6 §53, §74-75, §83).
#
# Generates /usr/share/nginx/html/runtime-config.js from runtime LIVEPHOTO_* environment variables
# and templates the CSP connect-src from the API base URL, so the SAME image can run with different
# API URLs / VLM flags without a rebuild. Never writes secrets into the config.
set -eu

WEB_ROOT=/usr/share/nginx/html
CONFIG_FILE="$WEB_ROOT/runtime-config.js"

# Runtime public settings (non-secret). Empty/absent values fall back to app defaults.
APP_ENV="${LIVEPHOTO_APP_ENV:-}"
API_BASE_URL="${LIVEPHOTO_API_BASE_URL:-}"
VLM_UI="${LIVEPHOTO_VLM_EXPERIMENT_UI_ENABLED:-false}"

# Normalize boolean ("true"/"false" -> boolean literal).
case "$VLM_UI" in
  true|1|TRUE) VLM_UI_BOOL=true ;;
  *) VLM_UI_BOOL=false ;;
esac

cat > "$CONFIG_FILE" <<EOF
window.__LIVEPHOTO_CONFIG__ = {
  appEnv: "${APP_ENV}",
  apiBaseUrl: "${API_BASE_URL}",
  vlmExperimentUiEnabled: ${VLM_UI_BOOL}
};
EOF
echo "[livephoto-frontend] wrote $CONFIG_FILE (appEnv=${APP_ENV:-dev}, vlmUi=${VLM_UI_BOOL})"

# Template CSP connect-src from the API origin (tight, not broad). Same-origin if unset.
if [ -n "$API_BASE_URL" ]; then
  CONNECT_SRC=$(printf '%s' "$API_BASE_URL" | sed -E 's#(https?://[^/]+).*#\1#')
else
  CONNECT_SRC="'self'"
fi
CSP="default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src ${CONNECT_SRC}; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
# Template the config into a writable location (non-root runtime cannot write /etc/nginx).
cp /etc/nginx/nginx.conf /tmp/nginx.conf
sed -i "s#__CSP__#${CSP}#g" /tmp/nginx.conf
echo "[livephoto-frontend] CSP connect-src=${CONNECT_SRC}"

exec nginx -c /tmp/nginx.conf -g 'daemon off;'
