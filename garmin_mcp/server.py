import json
from pathlib import Path
import httpx
from fastmcp import FastMCP
mcp = FastMCP("Garmin Connect")
TOKEN_URL = (
   "https://personal.connectapi.garmin.com/"
   "personalapitoken-service/personal-api/"
   "personal-api-key/token"
)

@mcp.tool
def garmin_auth_test() -> str:
   """Test Garmin authentication without exposing credentials."""
   options = json.loads(
       Path("/data/options.json").read_text()
   )
   api_key = options.get("garmin_api_key", "").strip()
   if not api_key:
       return "Garmin API key is missing."
   try:
       response = httpx.post(
           TOKEN_URL,
           headers={"Authorization": f"ApiKey {api_key}"},
           timeout=30,
       )
       if response.status_code != 200:
           return f"Garmin authentication returned HTTP {response.status_code}."
       return "Garmin authentication successful."
   except httpx.RequestError:
       return "Unable to contact Garmin API."

if __name__ == "__main__":
   mcp.run(
       transport="http",
       host="0.0.0.0",
       port=8000,
   )
