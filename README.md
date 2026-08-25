# WeatherScope

Full-stack weather application built by **Yllka Nuredini** for the **PM Accelerator AI Engineer Intern Technical Assessment**.

WeatherScope combines live weather, a 5-day forecast, current-location weather, air-quality context, useful weather insights, persisted weather-range requests, CRUD operations, and CSV/JSON export in one responsive web application.

## Features

- Search by city, town, postal code, or GPS coordinates
- Browser **Use my location** support
- Real current weather with temperature, feels-like, humidity, precipitation, and wind
- 5-day forecast with daily min/max temperature, precipitation, and wind
- Air quality with European AQI, PM2.5, PM10, ozone, and UV index
- Deterministic weather/travel insights based on live conditions
- Validated past/future date-range weather requests
- SQLite persistence
- Full CREATE / READ / UPDATE / DELETE workflow
- CSV and JSON export of persisted weather data
- Clear invalid-location, invalid-date, API-failure, and geolocation errors
- Responsive desktop, tablet, and mobile layout
- FastAPI Swagger/OpenAPI documentation

## Architecture

```text
User
  |
  v
React + Vite frontend
  |
  | REST / JSON
  v
FastAPI backend
  |-------------------|
  |                   |
  v                   v
Weather/geocoding     SQLite
APIs                   persistence
  |
  +-- Open-Meteo Forecast
  +-- Open-Meteo Historical Forecast
  +-- Open-Meteo Air Quality
  +-- Open-Meteo Geocoding
  +-- Nominatim settlement fallback
```

The frontend and backend are intentionally separated. FastAPI owns validation, external API access, persistence, CRUD, exports, and error translation. React owns presentation, browser geolocation, user interaction, responsive layout, and client-side states.

## Technology

### Frontend

- React 19
- Vite 6
- JavaScript
- CSS

### Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- SQLite
- HTTPX

### Testing

- Pytest
- FastAPI TestClient
- Production frontend build verification
- Manual desktop/tablet/mobile regression checks

## External services

Weather and air-quality data are retrieved from Open-Meteo services.

Location resolution uses Open-Meteo Geocoding first. A settlement-only Nominatim fallback is used when necessary. The fallback identifies the application with a User-Agent, caches results in process, and rate-limits public Nominatim requests.

Location data from OpenStreetMap is attributed to **© OpenStreetMap contributors** and is available under the Open Database License. See the OpenStreetMap copyright page for details.

No API key is required for the default local setup.

## Project structure

```text
pmaccelerator-weather-app/
├── backend/
│   ├── app/
│   │   ├── database.py
│   │   ├── main.py
│   │   ├── persistence.py
│   │   └── weather.py
│   ├── tests/
│   │   └── test_backend.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── styles.css
│   ├── .env.example
│   ├── index.html
│   ├── package.json
│   └── package-lock.json
├── .gitignore
└── README.md
```

`backend/weather.db`, `frontend/node_modules`, `frontend/dist`, virtual environments, caches, and local environment files are intentionally excluded from Git.

## Run locally

### Requirements

- Python 3.11+
- Node.js 18+

### Backend

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Backend:

```text
http://127.0.0.1:8000
```

Swagger/OpenAPI:

```text
http://127.0.0.1:8000/docs
```

The SQLite database is created automatically when the backend starts.

### Frontend

Open another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Frontend:

```text
http://localhost:5173
```

The frontend defaults to `http://127.0.0.1:8000` for the API.

To use another backend URL, copy `frontend/.env.example` to `frontend/.env` and change `VITE_API_BASE_URL`.

## REST API

### Live weather

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | API/database health |
| GET | `/api/weather/current?location=...` | Current weather |
| GET | `/api/weather/forecast?location=...` | 5-day forecast |
| GET | `/api/weather/range?location=...&start_date=...&end_date=...` | Weather date range |
| GET | `/api/air-quality?location=...` | Current air-quality data |

### Persisted weather requests

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/weather-requests` | Create and persist a weather request |
| GET | `/api/weather-requests` | List saved requests |
| GET | `/api/weather-requests/{id}` | Read one saved request |
| PATCH | `/api/weather-requests/{id}` | Update and re-fetch a saved request |
| DELETE | `/api/weather-requests/{id}` | Delete a saved request |
| GET | `/api/weather-requests/export?format=csv` | CSV export |
| GET | `/api/weather-requests/export?format=json` | JSON export |

## Validation and error handling

The application handles:

- missing/unknown locations
- invalid coordinate ranges
- invalid date formats
- start date after end date
- unsupported weather dates
- external API failures/timeouts
- missing database records
- empty update requests
- browser geolocation denied/unavailable/timeout states
- backend connection failures

Changing a saved location or date range does not edit stored weather numbers directly. The backend validates the new request, retrieves fresh weather data, and replaces the associated persisted weather days.

## Testing

### Backend

```powershell
cd backend
python -m pytest -q
```

Verified during development:

```text
12 passed
```

### Frontend production build

```powershell
cd frontend
npm run build
```

### Manual verification

The application was manually checked for:

- valid and invalid location searches
- GPS-coordinate search
- browser current location
- geolocation permission denial
- current weather
- 5-day forecast
- air quality
- weather insights
- CRUD create/read/update/delete
- failed-update integrity
- persistence after server restart
- CSV/JSON export
- backend-unavailable handling
- desktop layout
- tablet layout at 768 × 1024
- mobile layout at 390 × 844
- horizontal overflow
- browser runtime errors

## Assessment requirement coverage

| Requirement | Implementation |
|---|---|
| Real weather API | Open-Meteo |
| Location input | City/town/postal code/GPS coordinates |
| Current location | Browser Geolocation API |
| Weather icons/visual indicators | Weather-code visual mapping |
| Responsive web-first frontend | React + responsive CSS |
| 5-day forecast | Forecast section |
| Invalid location/API errors | User-facing error states |
| Database persistence | SQLite + SQLAlchemy |
| CREATE | Saved weather-range form |
| READ | Stored-request list and detail view |
| UPDATE | Validated PATCH + fresh weather retrieval |
| DELETE | Saved-request deletion |
| REST API | FastAPI endpoints + Swagger |
| Additional API | Open-Meteo Air Quality |
| Export | CSV + JSON |
| Candidate name | Yllka Nuredini shown in application |
| PM Accelerator information | About PM Accelerator section |
| Tests | 12 automated backend tests + manual regression |

## Known limitations

- Nominatim is used only as a low-volume fallback for settlement lookup and is not intended for autocomplete or high-volume geocoding.
- Weather availability is limited to the ranges supported by the external provider.
- The application is intentionally single-user; authentication and row-level access control were not required by the assessment.
- Current-location searches use GPS coordinates directly rather than reverse-geocoding them into a city name.

## Candidate

**Yllka Nuredini**  
AI Engineer Intern Technical Assessment  
PM Accelerator
