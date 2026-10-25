#!/bin/sh
set -eu
echo "Starting Garmin MCP secure tunnel..."
export CONTROL_PLANE_TUNNEL_ID="$(jq -er '.tunnel_id | select(length > 0)' /data/options.json)"
export CONTROL_PLANE_API_KEY="$(jq -er '.openai_api_key | select(length > 0)' /data/options.json)"
export MCP_SERVER_URL="http://d1870399-garmin-mcp:8000/mcp"
echo "Tunnel configuration loaded."
echo "Connecting to Garmin MCP server..."
exec /usr/local/bin/tunnel-client run \
   --log.level=info
