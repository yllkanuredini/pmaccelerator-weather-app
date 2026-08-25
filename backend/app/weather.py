import asyncio
import re
import time
from datetime import date, timedelta

import httpx


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HISTORICAL_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
EARLIEST_HISTORICAL_DATE = date(2022, 1, 1)
MAX_RANGE_DAYS = 31
MAX_FORECAST_DAYS = 16
DAILY_VARIABLES = [
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "precipitation_sum",
    "sunrise",
    "sunset",
    "wind_speed_10m_max",
    "wind_direction_10m_dominant",
]
COORDINATES_PATTERN = re.compile(
    r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$"
)
NOMINATIM_CACHE = {}
NOMINATIM_LOCK = asyncio.Lock()
NOMINATIM_LAST_REQUEST = 0.0


class WeatherServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def parse_coordinates(location: str):
    match = COORDINATES_PATTERN.match(location)
    if not match:
        return None

    latitude = float(match.group(1))
    longitude = float(match.group(2))

    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise WeatherServiceError(
            400,
            "Latitude must be between -90 and 90 and longitude between -180 and 180.",
        )

    return {
        "name": "Coordinates",
        "country": None,
        "admin1": None,
        "latitude": latitude,
        "longitude": longitude,
    }


async def geocode_open_meteo(client: httpx.AsyncClient, location: str):
    response = await client.get(
        GEOCODING_URL,
        params={"name": location, "count": 1, "language": "en", "format": "json"},
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    if not results:
        return None

    result = results[0]
    return {
        "name": result["name"],
        "country": result.get("country"),
        "admin1": result.get("admin1"),
        "latitude": result["latitude"],
        "longitude": result["longitude"],
    }


async def geocode_nominatim(client: httpx.AsyncClient, location: str):
    global NOMINATIM_LAST_REQUEST

    cache_key = location.strip().casefold()
    if cache_key in NOMINATIM_CACHE:
        return NOMINATIM_CACHE[cache_key]

    async with NOMINATIM_LOCK:
        if cache_key in NOMINATIM_CACHE:
            return NOMINATIM_CACHE[cache_key]

        wait_time = 1.0 - (time.monotonic() - NOMINATIM_LAST_REQUEST)
        if wait_time > 0:
            await asyncio.sleep(wait_time)

        response = await client.get(
            NOMINATIM_URL,
            params={
                "q": location,
                "format": "jsonv2",
                "limit": 1,
                "addressdetails": 1,
                "featureType": "settlement",
            },
            headers={"User-Agent": "PMAcceleratorWeatherApp/1.0"},
        )
        NOMINATIM_LAST_REQUEST = time.monotonic()
        response.raise_for_status()
        results = response.json()

        if not results:
            NOMINATIM_CACHE[cache_key] = None
            return None

        result = results[0]
        address = result.get("address", {})
        name = (
            result.get("name")
            or address.get("city")
            or address.get("town")
            or address.get("village")
            or result["display_name"].split(",", 1)[0]
        )
        resolved = {
            "name": name,
            "country": address.get("country"),
            "admin1": address.get("state") or address.get("region"),
            "latitude": float(result["lat"]),
            "longitude": float(result["lon"]),
        }
        NOMINATIM_CACHE[cache_key] = resolved
        return resolved


async def resolve_location(location: str):
    location = location.strip()
    coordinates = parse_coordinates(location)
    if coordinates:
        return coordinates

    if len(location) < 2:
        raise WeatherServiceError(400, "Enter a valid location.")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resolved = await geocode_open_meteo(client, location)
            except httpx.HTTPError:
                resolved = None

            if resolved:
                return resolved

            resolved = await geocode_nominatim(client, location)
            if resolved:
                return resolved
    except httpx.TimeoutException as exc:
        raise WeatherServiceError(504, "Location service timed out.") from exc
    except httpx.HTTPError as exc:
        raise WeatherServiceError(502, "Location service is unavailable.") from exc

    raise WeatherServiceError(404, "We couldn't find that location.")


async def get_current_weather(location: str):
    resolved = await resolve_location(location)

    params = {
        "latitude": resolved["latitude"],
        "longitude": resolved["longitude"],
        "current": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "weather_code",
                "wind_speed_10m",
                "wind_direction_10m",
            ]
        ),
        "timezone": "auto",
    }

    data = await request_json(FORECAST_URL, params, "Weather")
    current = data.get("current")
    if not current:
        raise WeatherServiceError(502, "Weather service returned incomplete data.")

    return {
        "location": {
            **resolved,
            "timezone": data.get("timezone"),
        },
        "current": current,
        "units": data.get("current_units", {}),
    }


def validate_date_range(start_date: date, end_date: date) -> None:
    today = date.today()
    latest_forecast_date = today + timedelta(days=MAX_FORECAST_DAYS - 1)

    if start_date > end_date:
        raise WeatherServiceError(400, "Start date cannot be after end date.")

    if start_date < EARLIEST_HISTORICAL_DATE:
        raise WeatherServiceError(
            400,
            f"Historical date ranges are supported from {EARLIEST_HISTORICAL_DATE.isoformat()} onward.",
        )

    if end_date > latest_forecast_date:
        raise WeatherServiceError(
            400,
            f"Forecast weather is currently supported through {latest_forecast_date.isoformat()}.",
        )

    if (end_date - start_date).days + 1 > MAX_RANGE_DAYS:
        raise WeatherServiceError(
            400,
            f"Date range cannot exceed {MAX_RANGE_DAYS} days.",
        )


async def request_json(url: str, params: dict, service_name: str):
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise WeatherServiceError(504, f"{service_name} service timed out.") from exc
    except httpx.HTTPError as exc:
        raise WeatherServiceError(502, f"{service_name} service is unavailable.") from exc

    return response.json()


def european_aqi_category(value):
    if value is None:
        return None
    if value <= 20:
        return "Good"
    if value <= 40:
        return "Fair"
    if value <= 60:
        return "Moderate"
    if value <= 80:
        return "Poor"
    if value <= 100:
        return "Very poor"
    return "Extremely poor"


async def get_air_quality(location: str):
    resolved = await resolve_location(location)
    params = {
        "latitude": resolved["latitude"],
        "longitude": resolved["longitude"],
        "current": ",".join(
            [
                "european_aqi",
                "pm10",
                "pm2_5",
                "ozone",
                "uv_index",
            ]
        ),
        "timezone": "auto",
    }

    data = await request_json(AIR_QUALITY_URL, params, "Air quality")
    current = data.get("current")
    if not current:
        raise WeatherServiceError(502, "Air quality service returned incomplete data.")

    return {
        "location": {
            **resolved,
            "timezone": data.get("timezone"),
        },
        "current": current,
        "aqi_category": european_aqi_category(current.get("european_aqi")),
        "units": data.get("current_units", {}),
    }


def normalize_daily(data: dict, source: str):
    daily = data.get("daily")
    if not daily or not daily.get("time"):
        raise WeatherServiceError(502, "Weather service returned incomplete daily data.")

    fields = [
        "weather_code",
        "temperature_2m_max",
        "temperature_2m_min",
        "apparent_temperature_max",
        "apparent_temperature_min",
        "precipitation_sum",
        "sunrise",
        "sunset",
        "wind_speed_10m_max",
        "wind_direction_10m_dominant",
    ]

    days = []
    for index, day in enumerate(daily["time"]):
        item = {"date": day, "source": source}
        for field in fields:
            values = daily.get(field, [])
            item[field] = values[index] if index < len(values) else None
        days.append(item)

    return days


async def fetch_daily_weather(
    resolved: dict,
    start_date: date,
    end_date: date,
    historical: bool,
):
    params = {
        "latitude": resolved["latitude"],
        "longitude": resolved["longitude"],
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": "auto",
    }
    url = HISTORICAL_URL if historical else FORECAST_URL
    source = "historical_forecast" if historical else "forecast"
    data = await request_json(url, params, "Weather")
    return normalize_daily(data, source), data.get("daily_units", {}), data.get("timezone")


async def get_weather_range(location: str, start_date: date, end_date: date):
    validate_date_range(start_date, end_date)
    resolved = await resolve_location(location)
    today = date.today()
    days = []
    units = {}
    timezone = None

    if start_date < today:
        historical_end = min(end_date, today - timedelta(days=1))
        historical_days, historical_units, historical_timezone = await fetch_daily_weather(
            resolved,
            start_date,
            historical_end,
            historical=True,
        )
        days.extend(historical_days)
        units.update(historical_units)
        timezone = historical_timezone

    if end_date >= today:
        forecast_start = max(start_date, today)
        forecast_days, forecast_units, forecast_timezone = await fetch_daily_weather(
            resolved,
            forecast_start,
            end_date,
            historical=False,
        )
        days.extend(forecast_days)
        units.update(forecast_units)
        timezone = forecast_timezone or timezone

    days.sort(key=lambda item: item["date"])

    return {
        "location": {
            **resolved,
            "timezone": timezone,
        },
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "days": days,
        "units": units,
    }


async def get_five_day_forecast(location: str):
    today = date.today()
    return await get_weather_range(location, today, today + timedelta(days=4))
