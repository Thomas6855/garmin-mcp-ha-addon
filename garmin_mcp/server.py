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
@mcp.tool
def get_garmin_stress() -> str:
   """Retrieve yesterday's Garmin stress data."""
   from datetime import datetime, timedelta
   from zoneinfo import ZoneInfo
   from garmin_personal_api import (
       GarminPersonalApiClient,
       PersonalApiAuthenticator,
   )
   options = json.loads(
       Path("/data/options.json").read_text()
   )
   api_key = options["garmin_api_key"]
   yesterday = (
       datetime.now(ZoneInfo("Asia/Riyadh")).date()
       - timedelta(days=1)
   )
   date = yesterday.isoformat()
   try:
       with PersonalApiAuthenticator(
           bearer_token_cache_file="/data/garmin_token.json"
       ) as auth:
           token = auth.obtain_token(api_key)
       with GarminPersonalApiClient(token.access_token) as client:
           data = client.get_daily_stress(date, date)
       return json.dumps(data)[:2000]
   except Exception as error:
       return f"Stress query failed: {type(error).__name__}"
if __name__ == "__main__":
   print(garmin_auth_test())
   print(get_garmin_stress(), flush=True)
   mcp.run(
       transport="http",
       host="0.0.0.0",
       port=8000,
   )
