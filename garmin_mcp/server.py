import json
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import httpx
from fastmcp import FastMCP
from garmin_personal_api import (
   GarminPersonalApiClient,
   PersonalApiAuthenticator,
)
mcp = FastMCP("Garmin Connect")
TOKEN_URL = (
   "https://personal.connectapi.garmin.com/"
   "personalapitoken-service/personal-api/"
   "personal-api-key/token"
)
RANGE_METRICS = {
   "stress": "get_daily_stress",
   "steps": "get_daily_steps",
   "hydration": "get_daily_hydration",
   "weight": "get_weight_measurements",
   "sleep_summaries": "get_daily_sleep_summaries",
   "body_battery": "get_daily_body_battery",
   "daily_summaries": "get_daily_summaries",
   "hrv_summaries": "get_daily_hrv_summaries",
   "wellness_activities": "get_wellness_activity_summaries",
}
DAY_METRICS = {
   "sleep": "get_daily_sleep",
   "heart_rate": "get_daily_heart_rate",
   "hrv": "get_daily_hrv",
   "spo2": "get_daily_spo2",
   "fitness_age": "get_fitness_age",
   "food_logs": "get_daily_food_logs",
}
OTHER_METRICS = {
   "profile": "get_user_profile_settings",
   "heart_rate_zones": "get_heart_rate_zones",
}

def yesterday():
   today = datetime.now(ZoneInfo("Asia/Riyadh")).date()
   return today - timedelta(days=1)

def parse_date(value):
   if value is None or value == "":
       return yesterday()
   return date.fromisoformat(value)

def date_range(start_date, end_date, default_days=7):
   end = parse_date(end_date)
   start = (
       date.fromisoformat(start_date)
       if start_date
       else end - timedelta(days=default_days - 1)
   )
   if start > end:
       raise ValueError("Start date must be before end date.")
   if (end - start).days > 30:
       raise ValueError("Maximum range is 31 days.")
   return start.isoformat(), end.isoformat()

def get_api_key():
   options = json.loads(
       Path("/data/options.json").read_text()
   )
   key = options.get("garmin_api_key", "").strip()
   if not key:
       raise ValueError("Garmin API key is missing.")
   return key

@contextmanager
def garmin_client():
   with PersonalApiAuthenticator(
       bearer_token_cache_file="/data/garmin_token.json"
   ) as auth:
       token = auth.obtain_token(get_api_key())
   with GarminPersonalApiClient(token.access_token) as client:
       yield client

def result_json(data):
   encoded = json.dumps(
       data, default=str, separators=(",", ":")
   )
   if len(encoded) > 30000:
       return json.dumps({
           "truncated": True,
           "preview": encoded[:30000],
       })
   return encoded

def safe_error(error):
   return json.dumps({
       "error": type(error).__name__,
       "message": "Garmin request failed. Check add-on logs.",
   })

@mcp.tool
def garmin_auth_test() -> str:
   """Test Garmin authentication without exposing credentials."""
   try:
       response = httpx.post(
           TOKEN_URL,
           headers={
               "Authorization": f"ApiKey {get_api_key()}"
           },
           timeout=30,
       )
       if response.status_code == 200:
           return "Garmin authentication successful."
       return (
           "Garmin authentication returned HTTP "
           f"{response.status_code}."
       )
   except Exception as error:
       return safe_error(error)

@mcp.tool
def get_garmin_metric(
   metric: str,
   start_date: str = "",
   end_date: str = "",
) -> str:
   """
   Retrieve Garmin health data.
   Available metrics:
   stress, steps, hydration, weight,
   sleep_summaries, body_battery,
   daily_summaries, hrv_summaries,
   wellness_activities, sleep, heart_rate,
   hrv, spo2, fitness_age, food_logs,
   profile, heart_rate_zones.
   Dates use YYYY-MM-DD.
   Defaults to yesterday or the preceding 7 days.
   Range queries are limited to 31 days.
   """
   try:
       with garmin_client() as client:
           if metric in RANGE_METRICS:
               start, end = date_range(
                   start_date, end_date
               )
               method = getattr(
                   client, RANGE_METRICS[metric]
               )
               data = method(start, end)
           elif metric in DAY_METRICS:
               selected = parse_date(
                   end_date or start_date
               ).isoformat()
               method = getattr(
                   client, DAY_METRICS[metric]
               )
               data = method(selected)
           elif metric in OTHER_METRICS:
               method = getattr(
                   client, OTHER_METRICS[metric]
               )
               data = method()
           else:
               return result_json({
                   "error": "Unknown metric",
                   "available": list(RANGE_METRICS)
                   + list(DAY_METRICS)
                   + list(OTHER_METRICS),
               })
       return result_json(data)
   except Exception as error:
       return safe_error(error)

@mcp.tool
def get_garmin_day(
   calendar_date: str = "",
) -> str:
   """
   Retrieve a complete Garmin daily health snapshot:
   sleep, HRV, heart rate, Body Battery,
   stress, daily summary, and SpO2.
   Defaults to yesterday.
   """
   try:
       selected = parse_date(calendar_date).isoformat()
       requests = {
           "sleep": ("get_daily_sleep", (selected,)),
           "hrv": ("get_daily_hrv", (selected,)),
           "heart_rate": (
               "get_daily_heart_rate", (selected,)
           ),
           "body_battery": (
               "get_daily_body_battery",
               (selected, selected),
           ),
           "stress": (
               "get_daily_stress",
               (selected, selected),
           ),
           "daily_summary": (
               "get_daily_summaries",
               (selected, selected),
           ),
           "spo2": ("get_daily_spo2", (selected,)),
       }
       results = {"date": selected}
       with garmin_client() as client:
           for name, (method_name, args) in requests.items():
               try:
                   method = getattr(client, method_name)
                   results[name] = method(*args)
               except Exception as error:
                   results[name] = {
                       "error": type(error).__name__
                   }
       return result_json(results)
   except Exception as error:
       return safe_error(error)

@mcp.tool
def get_garmin_activities(
   start_date: str = "",
   end_date: str = "",
   limit: int = 20,
) -> str:
   """
   Retrieve Garmin workouts including running activities.
   Defaults to the past 7 days ending yesterday.
   Returns up to 30 activities.
   """
   try:
       start, end = date_range(
           start_date, end_date
       )
       limit = max(1, min(limit, 30))
       with garmin_client() as client:
           data = client.search_activities(
               start=0,
               limit=limit,
               start_date=start,
               end_date=end,
           )
       return result_json(data)
   except Exception as error:
       return safe_error(error)

@mcp.tool
def get_garmin_activity_details(
   activity_id: int,
) -> str:
   """
   Retrieve detailed information for a Garmin
   activity using its numeric activity ID.
   """
   try:
       with garmin_client() as client:
           data = client.get_activity(activity_id)
       return result_json(data)
   except Exception as error:
       return safe_error(error)

if __name__ == "__main__":
   mcp.run(
       transport="http",
       host="0.0.0.0",
       port=8000,
   )
