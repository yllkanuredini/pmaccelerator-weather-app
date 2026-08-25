import csv
import json
from datetime import date
from io import StringIO
from typing import Literal

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app.database import Base, SessionLocal, check_database, engine
from app.persistence import (
    create_weather_request,
    delete_weather_request,
    get_weather_request,
    get_weather_requests_for_export,
    list_weather_requests,
    update_weather_request,
)
from app.weather import (
    WeatherServiceError,
    get_air_quality,
    get_current_weather,
    get_five_day_forecast,
    get_weather_range,
)


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="PM Accelerator Weather API",
    version="0.8.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class WeatherRequestCreate(BaseModel):
    location: str = Field(min_length=2, max_length=200)
    start_date: date
    end_date: date


class WeatherRequestUpdate(BaseModel):
    location: str | None = Field(default=None, min_length=2, max_length=200)
    start_date: date | None = None
    end_date: date | None = None


@app.get("/api/health")
def health():
    try:
        check_database()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc

    return {
        "status": "ok",
        "database": "connected",
    }


@app.get("/api/weather/current")
async def current_weather(location: str):
    try:
        return await get_current_weather(location)
    except WeatherServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/api/weather/forecast")
async def five_day_forecast(location: str):
    try:
        return await get_five_day_forecast(location)
    except WeatherServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/api/weather/range")
async def weather_range(location: str, start_date: date, end_date: date):
    try:
        return await get_weather_range(location, start_date, end_date)
    except WeatherServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.get("/api/air-quality")
async def air_quality(location: str):
    try:
        return await get_air_quality(location)
    except WeatherServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@app.post("/api/weather-requests", status_code=201)
async def save_weather_request(payload: WeatherRequestCreate):
    try:
        weather = await get_weather_range(
            payload.location,
            payload.start_date,
            payload.end_date,
        )
    except WeatherServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    try:
        with SessionLocal() as session:
            return create_weather_request(session, payload.location, weather)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Could not save weather request.") from exc


@app.get("/api/weather-requests")
def read_weather_requests():
    try:
        with SessionLocal() as session:
            return {"requests": list_weather_requests(session)}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Could not read weather requests.") from exc


@app.get("/api/weather-requests/export")
def export_weather_requests(format: Literal["csv", "json"]):
    try:
        with SessionLocal() as session:
            records = get_weather_requests_for_export(session)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Could not export weather requests.") from exc

    if format == "json":
        return Response(
            content=json.dumps({"requests": records}, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="weather-requests.json"'
            },
        )

    fields = [
        "request_id",
        "location_input",
        "resolved_location",
        "country",
        "admin1",
        "latitude",
        "longitude",
        "timezone",
        "start_date",
        "end_date",
        "created_at",
        "updated_at",
        "weather_day_id",
        "date",
        "source",
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
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()

    for record in records:
        request_values = {
            "request_id": record["id"],
            "location_input": record["location_input"],
            "resolved_location": record["resolved_location"],
            "country": record["country"],
            "admin1": record["admin1"],
            "latitude": record["latitude"],
            "longitude": record["longitude"],
            "timezone": record["timezone"],
            "start_date": record["start_date"],
            "end_date": record["end_date"],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
        }
        for day in record["days"]:
            writer.writerow(
                request_values
                | {
                    "weather_day_id": day["id"],
                    "date": day["date"],
                    "source": day["source"],
                    "weather_code": day["weather_code"],
                    "temperature_2m_max": day["temperature_2m_max"],
                    "temperature_2m_min": day["temperature_2m_min"],
                    "apparent_temperature_max": day["apparent_temperature_max"],
                    "apparent_temperature_min": day["apparent_temperature_min"],
                    "precipitation_sum": day["precipitation_sum"],
                    "sunrise": day["sunrise"],
                    "sunset": day["sunset"],
                    "wind_speed_10m_max": day["wind_speed_10m_max"],
                    "wind_direction_10m_dominant": day[
                        "wind_direction_10m_dominant"
                    ],
                }
            )

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="weather-requests.csv"'},
    )


@app.get("/api/weather-requests/{request_id}")
def read_weather_request(request_id: int):
    try:
        with SessionLocal() as session:
            record = get_weather_request(session, request_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Could not read weather request.") from exc

    if record is None:
        raise HTTPException(status_code=404, detail="Weather request not found.")

    return record


@app.patch("/api/weather-requests/{request_id}")
async def edit_weather_request(request_id: int, payload: WeatherRequestUpdate):
    if payload.location is None and payload.start_date is None and payload.end_date is None:
        raise HTTPException(status_code=400, detail="Provide at least one field to update.")

    try:
        with SessionLocal() as session:
            existing = get_weather_request(session, request_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Could not read weather request.") from exc

    if existing is None:
        raise HTTPException(status_code=404, detail="Weather request not found.")

    location = payload.location if payload.location is not None else existing["location_input"]
    start_date = payload.start_date or date.fromisoformat(existing["start_date"])
    end_date = payload.end_date or date.fromisoformat(existing["end_date"])

    try:
        weather = await get_weather_range(location, start_date, end_date)
    except WeatherServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    try:
        with SessionLocal() as session:
            updated = update_weather_request(
                session,
                request_id,
                location,
                weather,
            )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Could not update weather request.") from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Weather request not found.")

    return updated


@app.delete("/api/weather-requests/{request_id}", status_code=204)
def remove_weather_request(request_id: int):
    try:
        with SessionLocal() as session:
            deleted = delete_weather_request(session, request_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Could not delete weather request.") from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="Weather request not found.")

    return Response(status_code=204)
