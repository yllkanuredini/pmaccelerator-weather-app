from datetime import date as DateValue, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.database import Base


class WeatherRequest(Base):
    __tablename__ = "weather_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    location_input: Mapped[str] = mapped_column(String(200))
    resolved_location: Mapped[str] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    admin1: Mapped[str | None] = mapped_column(String(120), nullable=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    timezone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    start_date: Mapped[DateValue] = mapped_column(Date)
    end_date: Mapped[DateValue] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    days: Mapped[list["WeatherDay"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="WeatherDay.date",
    )


class WeatherDay(Base):
    __tablename__ = "weather_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("weather_requests.id"))
    date: Mapped[DateValue] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(40))
    weather_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temperature_2m_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_2m_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    apparent_temperature_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    apparent_temperature_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_sum: Mapped[float | None] = mapped_column(Float, nullable=True)
    sunrise: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sunset: Mapped[str | None] = mapped_column(String(40), nullable=True)
    wind_speed_10m_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction_10m_dominant: Mapped[float | None] = mapped_column(Float, nullable=True)
    request: Mapped[WeatherRequest] = relationship(back_populates="days")


def serialize_day(day: WeatherDay) -> dict:
    return {
        "id": day.id,
        "date": day.date.isoformat(),
        "source": day.source,
        "weather_code": day.weather_code,
        "temperature_2m_max": day.temperature_2m_max,
        "temperature_2m_min": day.temperature_2m_min,
        "apparent_temperature_max": day.apparent_temperature_max,
        "apparent_temperature_min": day.apparent_temperature_min,
        "precipitation_sum": day.precipitation_sum,
        "sunrise": day.sunrise,
        "sunset": day.sunset,
        "wind_speed_10m_max": day.wind_speed_10m_max,
        "wind_direction_10m_dominant": day.wind_direction_10m_dominant,
    }


def serialize_request(record: WeatherRequest, include_days: bool = True) -> dict:
    result = {
        "id": record.id,
        "location_input": record.location_input,
        "resolved_location": record.resolved_location,
        "country": record.country,
        "admin1": record.admin1,
        "latitude": record.latitude,
        "longitude": record.longitude,
        "timezone": record.timezone,
        "start_date": record.start_date.isoformat(),
        "end_date": record.end_date.isoformat(),
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }
    if include_days:
        result["days"] = [serialize_day(day) for day in record.days]
    return result


def apply_weather(record: WeatherRequest, location_input: str, weather: dict) -> None:
    location = weather["location"]
    record.location_input = location_input.strip()
    record.resolved_location = location["name"]
    record.country = location.get("country")
    record.admin1 = location.get("admin1")
    record.latitude = location["latitude"]
    record.longitude = location["longitude"]
    record.timezone = location.get("timezone")
    record.start_date = DateValue.fromisoformat(weather["start_date"])
    record.end_date = DateValue.fromisoformat(weather["end_date"])
    record.days.clear()

    for item in weather["days"]:
        record.days.append(
            WeatherDay(
                date=DateValue.fromisoformat(item["date"]),
                source=item["source"],
                weather_code=item.get("weather_code"),
                temperature_2m_max=item.get("temperature_2m_max"),
                temperature_2m_min=item.get("temperature_2m_min"),
                apparent_temperature_max=item.get("apparent_temperature_max"),
                apparent_temperature_min=item.get("apparent_temperature_min"),
                precipitation_sum=item.get("precipitation_sum"),
                sunrise=item.get("sunrise"),
                sunset=item.get("sunset"),
                wind_speed_10m_max=item.get("wind_speed_10m_max"),
                wind_direction_10m_dominant=item.get("wind_direction_10m_dominant"),
            )
        )


def create_weather_request(
    session: Session,
    location_input: str,
    weather: dict,
) -> dict:
    record = WeatherRequest()
    apply_weather(record, location_input, weather)
    session.add(record)
    session.commit()
    session.refresh(record)
    return serialize_request(record)


def list_weather_requests(session: Session) -> list[dict]:
    records = session.scalars(
        select(WeatherRequest).order_by(WeatherRequest.created_at.desc())
    ).all()
    return [serialize_request(record, include_days=False) for record in records]


def get_weather_request(session: Session, request_id: int) -> dict | None:
    record = session.get(WeatherRequest, request_id)
    if record is None:
        return None
    return serialize_request(record)


def get_weather_requests_for_export(session: Session) -> list[dict]:
    records = session.scalars(
        select(WeatherRequest).order_by(WeatherRequest.created_at.desc())
    ).all()
    return [serialize_request(record) for record in records]


def update_weather_request(
    session: Session,
    request_id: int,
    location_input: str,
    weather: dict,
) -> dict | None:
    record = session.get(WeatherRequest, request_id)
    if record is None:
        return None

    apply_weather(record, location_input, weather)
    record.updated_at = datetime.utcnow()
    session.commit()
    session.refresh(record)
    return serialize_request(record)


def delete_weather_request(session: Session, request_id: int) -> bool:
    record = session.get(WeatherRequest, request_id)
    if record is None:
        return False

    session.delete(record)
    session.commit()
    return True
