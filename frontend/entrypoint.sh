#!/bin/sh

# Create the config.json file dynamically in the serving directory
cat <<EOF > /usr/share/nginx/html/config.json
{
  "VITE_API_BASE_URL": "${VITE_API_BASE_URL:-}"
}
EOF

echo "Generated runtime config.json successfully:"
cat /usr/share/nginx/html/config.json

# Run original command
exec "$@"
