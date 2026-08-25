from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.weather import (
    WeatherServiceError,
    european_aqi_category,
    parse_coordinates,
    validate_date_range,
)


def sample_weather(location="Prishtina", start="2026-08-26", end="2026-08-28"):
    dates = []
    current = date.fromisoformat(start)
    final = date.fromisoformat(end)
    while current <= final:
        dates.append(current.isoformat())
        current += timedelta(days=1)

    return {
        "location": {
            "name": location,
            "country": "Kosovo" if location == "Prishtina" else "Germany",
            "admin1": None,
            "latitude": 42.66 if location == "Prishtina" else 52.52,
            "longitude": 21.16 if location == "Prishtina" else 13.41,
            "timezone": "Europe/Belgrade" if location == "Prishtina" else "Europe/Berlin",
        },
        "start_date": start,
        "end_date": end,
        "days": [
            {
                "date": day,
                "source": "forecast",
                "weather_code": 2,
                "temperature_2m_max": 30.0,
                "temperature_2m_min": 18.0,
                "apparent_temperature_max": 30.5,
                "apparent_temperature_min": 17.5,
                "precipitation_sum": 0.0,
                "sunrise": f"{day}T06:00",
                "sunset": f"{day}T19:30",
                "wind_speed_10m_max": 12.0,
                "wind_direction_10m_dominant": 180.0,
            }
            for day in dates
        ],
        "units": {},
    }


@pytest.fixture()
def client(monkeypatch):
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    main.Base.metadata.create_all(bind=test_engine)
    monkeypatch.setattr(main, "SessionLocal", testing_session)
    monkeypatch.setattr(main, "check_database", lambda: None)

    with TestClient(main.app) as test_client:
        yield test_client

    main.Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_current_weather_endpoint(client, monkeypatch):
    async def fake_current_weather(location):
        return {
            "location": {"name": location, "latitude": 42.66, "longitude": 21.16},
            "current": {"temperature_2m": 28.0},
            "units": {"temperature_2m": "°C"},
        }

    monkeypatch.setattr(main, "get_current_weather", fake_current_weather)
    response = client.get("/api/weather/current", params={"location": "Prishtina"})
    assert response.status_code == 200
    assert response.json()["location"]["name"] == "Prishtina"
    assert response.json()["current"]["temperature_2m"] == 28.0



def test_forecast_and_air_quality_endpoints(client, monkeypatch):
    async def fake_forecast(location):
        return sample_weather(location, "2026-08-25", "2026-08-29")

    async def fake_air_quality(location):
        return {
            "location": {"name": location, "latitude": 42.66, "longitude": 21.16},
            "current": {
                "european_aqi": 38,
                "pm10": 12.0,
                "pm2_5": 7.0,
                "ozone": 90.0,
                "uv_index": 2.0,
            },
            "aqi_category": "Fair",
            "units": {},
        }

    monkeypatch.setattr(main, "get_five_day_forecast", fake_forecast)
    monkeypatch.setattr(main, "get_air_quality", fake_air_quality)

    forecast = client.get("/api/weather/forecast", params={"location": "Prishtina"})
    assert forecast.status_code == 200
    assert len(forecast.json()["days"]) == 5

    air_quality = client.get("/api/air-quality", params={"location": "Prishtina"})
    assert air_quality.status_code == 200
    assert air_quality.json()["aqi_category"] == "Fair"

def test_weather_service_error_maps_to_http_error(client, monkeypatch):
    async def fake_current_weather(_location):
        raise WeatherServiceError(502, "Weather service is unavailable.")

    monkeypatch.setattr(main, "get_current_weather", fake_current_weather)
    response = client.get("/api/weather/current", params={"location": "Prishtina"})
    assert response.status_code == 502
    assert response.json()["detail"] == "Weather service is unavailable."


def test_create_read_update_delete_flow(client, monkeypatch):
    async def fake_range(location, start_date, end_date):
        return sample_weather(location, start_date.isoformat(), end_date.isoformat())

    monkeypatch.setattr(main, "get_weather_range", fake_range)

    created = client.post(
        "/api/weather-requests",
        json={
            "location": "Prishtina",
            "start_date": "2026-08-26",
            "end_date": "2026-08-28",
        },
    )
    assert created.status_code == 201
    request_id = created.json()["id"]
    assert len(created.json()["days"]) == 3

    listed = client.get("/api/weather-requests")
    assert listed.status_code == 200
    assert len(listed.json()["requests"]) == 1

    read = client.get(f"/api/weather-requests/{request_id}")
    assert read.status_code == 200
    assert read.json()["location_input"] == "Prishtina"

    updated = client.patch(
        f"/api/weather-requests/{request_id}",
        json={
            "location": "Berlin",
            "start_date": "2026-08-27",
            "end_date": "2026-08-29",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["location_input"] == "Berlin"
    assert len(updated.json()["days"]) == 3

    deleted = client.delete(f"/api/weather-requests/{request_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/weather-requests/{request_id}").status_code == 404


def test_invalid_update_does_not_replace_saved_data(client, monkeypatch):
    async def create_range(location, start_date, end_date):
        return sample_weather(location, start_date.isoformat(), end_date.isoformat())

    monkeypatch.setattr(main, "get_weather_range", create_range)
    created = client.post(
        "/api/weather-requests",
        json={
            "location": "Prishtina",
            "start_date": "2026-08-26",
            "end_date": "2026-08-28",
        },
    )
    request_id = created.json()["id"]

    async def invalid_range(_location, _start_date, _end_date):
        raise WeatherServiceError(400, "Start date cannot be after end date.")

    monkeypatch.setattr(main, "get_weather_range", invalid_range)
    response = client.patch(
        f"/api/weather-requests/{request_id}",
        json={"start_date": "2026-08-30", "end_date": "2026-08-27"},
    )
    assert response.status_code == 400

    saved = client.get(f"/api/weather-requests/{request_id}").json()
    assert saved["location_input"] == "Prishtina"
    assert saved["start_date"] == "2026-08-26"
    assert saved["end_date"] == "2026-08-28"


def test_empty_update_and_missing_record(client):
    empty = client.patch("/api/weather-requests/1", json={})
    assert empty.status_code == 400
    assert empty.json()["detail"] == "Provide at least one field to update."

    missing = client.get("/api/weather-requests/999999")
    assert missing.status_code == 404


def test_json_and_csv_export(client, monkeypatch):
    async def fake_range(location, start_date, end_date):
        return sample_weather(location, start_date.isoformat(), end_date.isoformat())

    monkeypatch.setattr(main, "get_weather_range", fake_range)
    client.post(
        "/api/weather-requests",
        json={
            "location": "Prishtina",
            "start_date": "2026-08-26",
            "end_date": "2026-08-28",
        },
    )

    json_response = client.get("/api/weather-requests/export", params={"format": "json"})
    assert json_response.status_code == 200
    assert len(json_response.json()["requests"]) == 1

    csv_response = client.get("/api/weather-requests/export", params={"format": "csv"})
    assert csv_response.status_code == 200
    assert "request_id,location_input,resolved_location" in csv_response.text
    assert csv_response.text.count("Prishtina") >= 3


def test_invalid_export_format_returns_422(client):
    response = client.get("/api/weather-requests/export", params={"format": "xml"})
    assert response.status_code == 422


def test_coordinate_validation():
    result = parse_coordinates("42.6629, 21.1655")
    assert result["latitude"] == 42.6629
    assert result["longitude"] == 21.1655

    with pytest.raises(WeatherServiceError) as error:
        parse_coordinates("900, 500")
    assert error.value.status_code == 400


def test_date_range_validation():
    today = date.today()

    with pytest.raises(WeatherServiceError) as reversed_error:
        validate_date_range(today + timedelta(days=2), today + timedelta(days=1))
    assert reversed_error.value.status_code == 400

    with pytest.raises(WeatherServiceError) as long_error:
        validate_date_range(today - timedelta(days=16), today + timedelta(days=16))
    assert long_error.value.status_code == 400


def test_aqi_categories():
    assert european_aqi_category(10) == "Good"
    assert european_aqi_category(30) == "Fair"
    assert european_aqi_category(50) == "Moderate"
    assert european_aqi_category(70) == "Poor"
    assert european_aqi_category(90) == "Very poor"
    assert european_aqi_category(110) == "Extremely poor"
