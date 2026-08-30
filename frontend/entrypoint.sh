#!/bin/sh
set -e

# Fail loudly: an empty value yields "proxy_pass ;" and nginx dies on a parse
# error instead of telling you the variable was missing.
: "${BACKEND_URL:?must be set to the backend origin, e.g. https://host}"

# Scoped on purpose. A bare envsubst would also blank nginx's own $uri, $host
# and friends, silently breaking try_files and the proxy headers.
envsubst '${BACKEND_URL}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

# Runtime config for the SPA. Empty base URL keeps API calls same-origin, which
# is what keeps the twl_session cookie first-party under SameSite=Lax.
cat <<JSON > /usr/share/nginx/html/config.json
{
  "VITE_API_BASE_URL": "${VITE_API_BASE_URL:-}"
}
JSON

echo "config.json: $(cat /usr/share/nginx/html/config.json | tr -d '\n ')"
echo "api proxy -> ${BACKEND_URL}"

exec "$@"
