
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

TIMEZONE = ZoneInfo("Asia/Riyadh")


# -----------------------------------------
# Configuration and authentication
# -----------------------------------------

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


def yesterday():
    return (
        datetime.now(TIMEZONE).date()
        - timedelta(days=1)
    )


def parse_date(value):
    if not value:
        return yesterday()

    return date.fromisoformat(value)


def date_range(start_date="", end_date="", days=7):
    end = parse_date(end_date)

    if start_date:
        start = date.fromisoformat(start_date)
    else:
        start = end - timedelta(days=days - 1)

    if start > end:
        raise ValueError("Start date is after end date.")

    if (end - start).days > 30:
        raise ValueError("Maximum date range is 31 days.")

    return start.isoformat(), end.isoformat()


def result_json(data):
    encoded = json.dumps(
        data,
        default=str,
        separators=(",", ":"),
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
        "message": "Garmin request failed.",
    })


# -----------------------------------------
# Supported Garmin metrics
# -----------------------------------------

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


# -----------------------------------------
# Tool 1: Authentication test
# -----------------------------------------

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


# -----------------------------------------
# Tool 2: Individual Garmin metrics
# -----------------------------------------

@mcp.tool
def get_garmin_metric(
    metric: str,
    start_date: str = "",
    end_date: str = "",
) -> str:
    """
    Retrieve detailed Garmin health data.

    Metrics:
    stress, steps, hydration, weight,
    sleep_summaries, body_battery,
    daily_summaries, hrv_summaries,
    wellness_activities, sleep, heart_rate,
    hrv, spo2, fitness_age, food_logs,
    profile, heart_rate_zones.

    Dates must use YYYY-MM-DD.
    Defaults to yesterday or the last 7 days.
    Maximum range is 31 days.
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
                    "available_metrics": (
                        list(RANGE_METRICS)
                        + list(DAY_METRICS)
                        + list(OTHER_METRICS)
                    ),
                })

        return result_json(data)

    except Exception as error:
        return safe_error(error)


# -----------------------------------------
# Tool 3: Compact daily snapshot
# -----------------------------------------

@mcp.tool
def get_garmin_day(
    calendar_date: str = "",
) -> str:
    """
    Retrieve a compact daily health and recovery snapshot.

    Includes sleep, HRV, Body Battery, stress,
    resting heart rate, steps, calories, and workouts.

    Defaults to yesterday.
    """
    return get_garmin_recovery_week(
        days=1,
        end_date=calendar_date,
    )


# -----------------------------------------
# Tool 4: Multi-day recovery trends
# -----------------------------------------

@mcp.tool
def get_garmin_recovery_week(
    days: int = 7,
    end_date: str = "",
) -> str:
    """
    Retrieve 1-14 days of Garmin recovery and activity data.

    Includes:
    Sleep duration and score
    Deep and REM sleep
    Overnight HRV and HRV status
    Body Battery charge and drain
    Average stress
    Resting heart rate
    Daily steps
    Active and total calories
    Workout distance, duration, HR, and Training Effect

    Defaults to the last 7 completed days.
    """
    try:
        days = max(1, min(days, 14))

        end = parse_date(end_date)
        start = end - timedelta(days=days - 1)

        first = start.isoformat()
        last = end.isoformat()

        results = {}

        for i in range(days):
            day = (
                start + timedelta(days=i)
            ).isoformat()

            results[day] = {
                "date": day,
            }

        errors = {}

        with garmin_client() as client:

            def fetch(name, method_name, *args, **kwargs):
                try:
                    method = getattr(
                        client, method_name
                    )
                    return method(*args, **kwargs)
                except Exception as error:
                    errors[name] = type(error).__name__
                    return None

            sleeps = fetch(
                "sleep",
                "get_daily_sleep_summaries",
                first,
                last,
            ) or []

            hrv_response = fetch(
                "hrv",
                "get_daily_hrv_summaries",
                first,
                last,
            ) or {}

            batteries = fetch(
                "body_battery",
                "get_daily_body_battery",
                first,
                last,
            ) or []

            stresses = fetch(
                "stress",
                "get_daily_stress",
                first,
                last,
            ) or []

            summary_response = fetch(
                "daily_summaries",
                "get_daily_summaries",
                first,
                last,
            ) or {}

            activities = fetch(
                "activities",
                "search_activities",
                start=0,
                limit=100,
                start_date=first,
                end_date=last,
            ) or []

        # Sleep
        for item in sleeps:
            day = item.get("calendarDate")

            if day not in results:
                continue

            scores = item.get("sleepScores") or {}
            overall = scores.get("overall") or {}

            results[day]["sleep"] = {
                "hours": round(
                    (item.get("sleepTimeSeconds") or 0)
                    / 3600, 2
                ),
                "score": overall.get("value"),
                "deep_minutes": round(
                    (item.get("deepSleepSeconds") or 0)
                    / 60
                ),
                "light_minutes": round(
                    (item.get("lightSleepSeconds") or 0)
                    / 60
                ),
                "rem_minutes": round(
                    (item.get("remSleepSeconds") or 0)
                    / 60
                ),
                "average_sleep_hr": item.get(
                    "avgHeartRate"
                ),
            }

        # Heart rate variability
        for item in hrv_response.get(
            "hrvSummaries", []
        ):
            day = item.get("calendarDate")

            if day not in results:
                continue

            results[day]["hrv"] = {
                "last_night_ms": item.get(
                    "lastNightAvg"
                ),
                "weekly_average_ms": item.get(
                    "weeklyAvg"
                ),
                "status": item.get("status"),
            }

        # Body Battery
        for item in batteries:
            day = item.get("date")

            if day not in results:
                continue

            values = item.get(
                "bodyBatteryValuesArray"
            ) or []

            results[day]["body_battery"] = {
                "charged": item.get("charged"),
                "drained": item.get("drained"),
                "last_recorded": (
                    values[-1][1] if values else None
                ),
            }

        # Stress
        for item in stresses:
            day = item.get("calendarDate")

            if day not in results:
                continue

            values = item.get("values") or {}

            results[day]["stress"] = {
                "average": values.get(
                    "overallStressLevel"
                ),
            }

        # Daily health and activity summary
        for item in summary_response.get(
            "data", []
        ):
            day = item.get("calendarDate")

            if day not in results:
                continue

            hr = item.get("heartRate") or {}
            movement = item.get("movement") or {}
            steps = movement.get("steps") or {}
            calories = item.get("calories") or {}
            intensity = item.get(
                "intensityMinutes"
            ) or {}

            results[day]["daily_summary"] = {
                "resting_hr": hr.get("restingValue"),
                "steps": steps.get("value"),
                "distance_km": round(
                    (steps.get("distanceInMeters") or 0)
                    / 1000, 2
                ),
                "active_calories": calories.get(
                    "burnedActive"
                ),
                "total_calories": calories.get(
                    "burnedTotal"
                ),
                "moderate_intensity_minutes": (
                    intensity.get("moderate")
                ),
                "vigorous_intensity_minutes": (
                    intensity.get("vigorous")
                ),
            }

        # Workouts
        for item in activities:
            day = (
                item.get("startTimeLocal") or ""
            )[:10]

            if day not in results:
                continue

            activity_type = (
                item.get("activityType") or {}
            ).get("typeKey")

            workout = {
                "id": item.get("activityId"),
                "name": item.get("activityName"),
                "type": activity_type,
                "distance_km": round(
                    (item.get("distance") or 0)
                    / 1000, 2
                ),
                "duration_minutes": round(
                    (item.get("duration") or 0)
                    / 60, 1
                ),
                "average_hr": item.get(
                    "averageHR"
                ),
                "calories": item.get("calories"),
                "aerobic_training_effect": item.get(
                    "aerobicTrainingEffect"
                ),
                "anaerobic_training_effect": item.get(
                    "anaerobicTrainingEffect"
                ),
            }

            results[day].setdefault(
                "workouts", []
            ).append(workout)

        return result_json({
            "start_date": first,
            "end_date": last,
            "days": list(results.values()),
            "endpoint_errors": errors,
        })

    except Exception as error:
        return safe_error(error)


# -----------------------------------------
# Tool 5: Recent activities
# -----------------------------------------

@mcp.tool
def get_garmin_activities(
    start_date: str = "",
    end_date: str = "",
    limit: int = 20,
) -> str:
    """
    Retrieve Garmin activities including running workouts.

    Defaults to the past 7 completed days.
    Maximum 30 activities per request.
    """
    try:
        start, end = date_range(
            start_date,
            end_date,
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


# -----------------------------------------
# Tool 6: Individual activity details
# -----------------------------------------

@mcp.tool
def get_garmin_activity_details(
    activity_id: int,
) -> str:
    """
    Retrieve detailed workout information
    using a Garmin activity ID.
    """
    try:
        with garmin_client() as client:
            data = client.get_activity(activity_id)

        return result_json(data)

    except Exception as error:
        return safe_error(error)


# -----------------------------------------
# Start the MCP HTTP server
# -----------------------------------------

if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=8000,
    )
