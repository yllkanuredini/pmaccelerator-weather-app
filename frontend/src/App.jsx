import React, { useEffect, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const WEATHER_CODES = {
  0: ["Clear sky", "☀"],
  1: ["Mainly clear", "☀"],
  2: ["Partly cloudy", "◒"],
  3: ["Overcast", "☁"],
  45: ["Foggy", "≋"],
  48: ["Rime fog", "≋"],
  51: ["Light drizzle", "☂"],
  53: ["Drizzle", "☂"],
  55: ["Heavy drizzle", "☂"],
  61: ["Light rain", "☂"],
  63: ["Rain", "☂"],
  65: ["Heavy rain", "☂"],
  71: ["Light snow", "❄"],
  73: ["Snow", "❄"],
  75: ["Heavy snow", "❄"],
  80: ["Rain showers", "☂"],
  81: ["Rain showers", "☂"],
  82: ["Heavy showers", "☂"],
  95: ["Thunderstorm", "ϟ"],
  96: ["Thunderstorm", "ϟ"],
  99: ["Thunderstorm", "ϟ"],
};

function weatherInfo(code) {
  return WEATHER_CODES[code] || ["Current conditions", "◌"];
}

function locationLabel(location) {
  return [location.name, location.admin1, location.country].filter(Boolean).join(", ");
}

function formatForecastDate(dateValue) {
  return new Intl.DateTimeFormat("en", {
    weekday: "short",
    month: "short",
    day: "numeric",
  }).format(new Date(`${dateValue}T12:00:00`));
}

function isoDate(offset = 0) {
  const date = new Date();
  date.setDate(date.getDate() + offset);
  return date.toISOString().slice(0, 10);
}

function buildTravelInsights(weather, airQuality, forecast) {
  if (!weather) {
    return [];
  }

  const current = weather.current;
  const today = forecast?.days?.[0];
  const insights = [];

  if (current.temperature_2m >= 30) {
    insights.push({
      title: "Hot conditions",
      text: "Carry water and plan for shade during the warmest part of the day.",
    });
  } else if (current.temperature_2m <= 5) {
    insights.push({
      title: "Cold conditions",
      text: "Layer up if you plan to spend extended time outside.",
    });
  }

  if (current.precipitation > 0 || (today?.precipitation_sum ?? 0) >= 1) {
    insights.push({
      title: "Rain-ready",
      text: "Rain is active or expected today, so a light rain layer may be useful.",
    });
  }

  if (current.wind_speed_10m >= 25) {
    insights.push({
      title: "Windy",
      text: "Expect stronger wind in exposed areas and secure loose items.",
    });
  }

  if ((airQuality?.current?.uv_index ?? 0) >= 6) {
    insights.push({
      title: "High UV",
      text: "Sun protection is recommended during extended outdoor plans.",
    });
  }

  if ((airQuality?.current?.european_aqi ?? 0) >= 60) {
    insights.push({
      title: "Air quality caution",
      text: "Air quality is elevated; check local guidance before prolonged outdoor activity.",
    });
  }

  if (insights.length === 0) {
    insights.push({
      title: "Comfortable outlook",
      text: "No major weather-related concerns stand out for typical outdoor plans right now.",
    });
  }

  return insights.slice(0, 3);
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);

  if (response.status === 204) {
    return null;
  }

  const data = await response.json();

  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg).join(" ")
      : data.detail;
    throw new Error(detail || "The request could not be completed.");
  }

  return data;
}

function App() {
  const [query, setQuery] = useState("Prishtina");
  const [weather, setWeather] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [loading, setLoading] = useState(false);
  const [locating, setLocating] = useState(false);
  const [error, setError] = useState("");
  const [forecastError, setForecastError] = useState("");
  const [airQuality, setAirQuality] = useState(null);
  const [airQualityError, setAirQualityError] = useState("");

  const [savedRequests, setSavedRequests] = useState([]);
  const [savedLoading, setSavedLoading] = useState(false);
  const [savedError, setSavedError] = useState("");
  const [savedMessage, setSavedMessage] = useState("");
  const [selectedRequest, setSelectedRequest] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveForm, setSaveForm] = useState({
    location: "Prishtina",
    start_date: isoDate(1),
    end_date: isoDate(5),
  });
  const [editForm, setEditForm] = useState({
    location: "",
    start_date: "",
    end_date: "",
  });

  async function loadWeather(location) {
    const trimmed = location.trim();

    if (!trimmed) {
      setError("Enter a city, postal code, or coordinates.");
      return;
    }

    setLoading(true);
    setError("");
    setForecastError("");
    setAirQualityError("");
    setWeather(null);
    setForecast(null);
    setAirQuality(null);

    try {
      const currentData = await fetchJson(
        `${API_BASE_URL}/api/weather/current?location=${encodeURIComponent(trimmed)}`,
      );
      setWeather(currentData);
      setSaveForm((current) => ({ ...current, location: trimmed }));

      const [forecastResult, airQualityResult] = await Promise.allSettled([
        fetchJson(`${API_BASE_URL}/api/weather/forecast?location=${encodeURIComponent(trimmed)}`),
        fetchJson(`${API_BASE_URL}/api/air-quality?location=${encodeURIComponent(trimmed)}`),
      ]);

      if (forecastResult.status === "fulfilled") {
        setForecast(forecastResult.value);
      } else {
        setForecastError(
          forecastResult.reason instanceof TypeError
            ? "The forecast service is temporarily unavailable."
            : forecastResult.reason.message,
        );
      }

      if (airQualityResult.status === "fulfilled") {
        setAirQuality(airQualityResult.value);
      } else {
        setAirQualityError(
          airQualityResult.reason instanceof TypeError
            ? "Air-quality data is temporarily unavailable."
            : airQualityResult.reason.message,
        );
      }
    } catch (requestError) {
      setWeather(null);
      setForecast(null);
      setAirQuality(null);
      setError(
        requestError instanceof TypeError
          ? "Cannot reach the weather service. Make sure the backend is running."
          : requestError.message,
      );
    } finally {
      setLoading(false);
    }
  }

  async function loadSavedRequests() {
    setSavedLoading(true);
    setSavedError("");

    try {
      const data = await fetchJson(`${API_BASE_URL}/api/weather-requests`);
      setSavedRequests(data.requests || []);
    } catch (requestError) {
      setSavedError(
        requestError instanceof TypeError
          ? "Cannot reach the saved-weather service."
          : requestError.message,
      );
    } finally {
      setSavedLoading(false);
    }
  }

  async function createSavedRequest(event) {
    event.preventDefault();
    setSaving(true);
    setSavedError("");
    setSavedMessage("");

    try {
      const created = await fetchJson(`${API_BASE_URL}/api/weather-requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(saveForm),
      });
      setSavedMessage(`Saved request #${created.id}.`);
      setSelectedRequest(created);
      await loadSavedRequests();
    } catch (requestError) {
      setSavedError(
        requestError instanceof TypeError
          ? "Cannot reach the saved-weather service."
          : requestError.message,
      );
    } finally {
      setSaving(false);
    }
  }

  async function viewSavedRequest(id) {
    setSavedError("");
    setSavedMessage("");

    try {
      const request = await fetchJson(`${API_BASE_URL}/api/weather-requests/${id}`);
      setSelectedRequest(request);
    } catch (requestError) {
      setSavedError(requestError.message);
    }
  }

  function startEditing(request) {
    setEditingId(request.id);
    setEditForm({
      location: request.location_input,
      start_date: request.start_date,
      end_date: request.end_date,
    });
    setSavedError("");
    setSavedMessage("");
  }

  async function updateSavedRequest(event, id) {
    event.preventDefault();
    setSaving(true);
    setSavedError("");
    setSavedMessage("");

    try {
      const updated = await fetchJson(`${API_BASE_URL}/api/weather-requests/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editForm),
      });
      setEditingId(null);
      setSelectedRequest(updated);
      setSavedMessage(`Updated request #${id}.`);
      await loadSavedRequests();
    } catch (requestError) {
      setSavedError(
        requestError instanceof TypeError
          ? "Cannot reach the saved-weather service."
          : requestError.message,
      );
    } finally {
      setSaving(false);
    }
  }

  async function deleteSavedRequest(id) {
    if (!window.confirm(`Delete saved request #${id}?`)) {
      return;
    }

    setSavedError("");
    setSavedMessage("");

    try {
      await fetchJson(`${API_BASE_URL}/api/weather-requests/${id}`, {
        method: "DELETE",
      });
      if (selectedRequest?.id === id) {
        setSelectedRequest(null);
      }
      if (editingId === id) {
        setEditingId(null);
      }
      setSavedMessage(`Deleted request #${id}.`);
      await loadSavedRequests();
    } catch (requestError) {
      setSavedError(
        requestError instanceof TypeError
          ? "Cannot reach the saved-weather service."
          : requestError.message,
      );
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    loadWeather(query);
  }

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      setError("Your browser does not support location access. Search manually instead.");
      return;
    }

    setLocating(true);
    setError("");

    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const location = `${coords.latitude.toFixed(6)}, ${coords.longitude.toFixed(6)}`;
        setQuery(`${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}`);
        setLocating(false);
        loadWeather(location);
      },
      (geolocationError) => {
        setLocating(false);

        if (geolocationError.code === geolocationError.PERMISSION_DENIED) {
          setError("Location permission was denied. Search for a location manually instead.");
        } else if (geolocationError.code === geolocationError.POSITION_UNAVAILABLE) {
          setError("Your current location is unavailable. Search manually instead.");
        } else if (geolocationError.code === geolocationError.TIMEOUT) {
          setError("Getting your location took too long. Try again or search manually.");
        } else {
          setError("We couldn't access your current location. Search manually instead.");
        }
      },
      {
        enableHighAccuracy: false,
        timeout: 10000,
        maximumAge: 300000,
      },
    );
  }

  useEffect(() => {
    loadWeather("Prishtina");
    loadSavedRequests();
  }, []);

  const current = weather?.current;
  const units = weather?.units;
  const [condition, icon] = weatherInfo(current?.weather_code);
  const travelInsights = buildTravelInsights(weather, airQuality, forecast);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">W</span>
          <span>WeatherScope</span>
        </div>
        <span className="live-badge"><i /> Live weather</span>
      </header>

      <main className="page">
        <section className="intro">
          <p className="eyebrow">Weather intelligence</p>
          <h1>Know the conditions before you go.</h1>
          <p className="intro-copy">
            Search any city, postal code, or GPS coordinates for real-time weather.
          </p>

          <div className="search-tools">
            <form className="search" onSubmit={handleSubmit}>
              <span className="search-icon">⌕</span>
              <input
                aria-label="Location"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="City, postal code, or 42.66, 21.16"
              />
              <button type="submit" disabled={loading || locating}>
                {loading ? "Loading..." : "Check weather"}
              </button>
            </form>

            <button
              className="location-button"
              type="button"
              onClick={useCurrentLocation}
              disabled={loading || locating}
            >
              <span aria-hidden="true">⌖</span>
              {locating ? "Locating..." : "Use my location"}
            </button>
          </div>

          {error && <div className="error-message">{error}</div>}
        </section>

        <section className="dashboard" aria-live="polite">
          {loading && !weather ? (
            <div className="weather-card loading-card">
              <div className="skeleton skeleton-title" />
              <div className="skeleton skeleton-temp" />
              <div className="skeleton skeleton-line" />
            </div>
          ) : weather ? (
            <>
              <article className="weather-card">
                <div className="weather-card-top">
                  <div>
                    <p className="card-label">Current weather</p>
                    <h2>{locationLabel(weather.location)}</h2>
                    <p className="updated">Updated {current.time.replace("T", " · ")}</p>
                  </div>
                  <div className="condition-icon" aria-hidden="true">{icon}</div>
                </div>

                <div className="temperature-row">
                  <strong>{Math.round(current.temperature_2m)}°</strong>
                  <div>
                    <p>{condition}</p>
                    <span>Feels like {Math.round(current.apparent_temperature)}°</span>
                  </div>
                </div>

                <div className="location-coordinates">
                  {weather.location.latitude.toFixed(3)}°, {weather.location.longitude.toFixed(3)}°
                </div>
              </article>

              <div className="metrics-grid">
                <article className="metric-card">
                  <span className="metric-icon">◉</span>
                  <p>Humidity</p>
                  <strong>{current.relative_humidity_2m}{units.relative_humidity_2m}</strong>
                  <small>Current relative humidity</small>
                </article>

                <article className="metric-card">
                  <span className="metric-icon">↝</span>
                  <p>Wind</p>
                  <strong>{current.wind_speed_10m} <em>{units.wind_speed_10m}</em></strong>
                  <small>Direction {Math.round(current.wind_direction_10m)}°</small>
                </article>

                <article className="metric-card">
                  <span className="metric-icon">⌁</span>
                  <p>Precipitation</p>
                  <strong>{current.precipitation} <em>{units.precipitation}</em></strong>
                  <small>Current precipitation</small>
                </article>

                <article className="metric-card">
                  <span className="metric-icon">◎</span>
                  <p>Feels like</p>
                  <strong>{current.apparent_temperature}{units.apparent_temperature}</strong>
                  <small>Perceived temperature</small>
                </article>
              </div>
            </>
          ) : (
            <div className="empty-state">Search for a location to view live weather.</div>
          )}
        </section>

        {(forecast || forecastError) && (
          <section className="forecast-section" aria-live="polite">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Looking ahead</p>
                <h2>5-day forecast</h2>
              </div>
              {forecast && <span>{locationLabel(forecast.location)}</span>}
            </div>

            {forecastError ? (
              <div className="forecast-error">{forecastError}</div>
            ) : (
              <div className="forecast-grid">
                {forecast.days.map((day) => {
                  const [dayCondition, dayIcon] = weatherInfo(day.weather_code);

                  return (
                    <article className="forecast-card" key={day.date}>
                      <div className="forecast-card-top">
                        <div>
                          <strong>{formatForecastDate(day.date)}</strong>
                          <span>{dayCondition}</span>
                        </div>
                        <span className="forecast-icon" aria-hidden="true">{dayIcon}</span>
                      </div>

                      <div className="forecast-temperatures">
                        <strong>{Math.round(day.temperature_2m_max)}°</strong>
                        <span>{Math.round(day.temperature_2m_min)}°</span>
                      </div>

                      <div className="forecast-meta">
                        <span>Rain {day.precipitation_sum} mm</span>
                        <span>Wind {Math.round(day.wind_speed_10m_max)} km/h</span>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        )}

        {weather && (
          <section className="conditions-section">
            <article className="air-quality-panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Beyond temperature</p>
                  <h2>Air quality</h2>
                </div>
                {airQuality && (
                  <span className={`aqi-badge aqi-${airQuality.aqi_category.toLowerCase().replaceAll(" ", "-")}`}>
                    {airQuality.aqi_category}
                  </span>
                )}
              </div>

              {airQualityError ? (
                <div className="inline-notice">{airQualityError}</div>
              ) : airQuality ? (
                <>
                  <div className="aqi-summary">
                    <div>
                      <span>European AQI</span>
                      <strong>{Math.round(airQuality.current.european_aqi)}</strong>
                    </div>
                    <p>
                      Current air-quality context for {locationLabel(airQuality.location)}.
                    </p>
                  </div>

                  <div className="air-metrics">
                    <div>
                      <span>PM2.5</span>
                      <strong>{airQuality.current.pm2_5}</strong>
                      <small>{airQuality.units.pm2_5}</small>
                    </div>
                    <div>
                      <span>PM10</span>
                      <strong>{airQuality.current.pm10}</strong>
                      <small>{airQuality.units.pm10}</small>
                    </div>
                    <div>
                      <span>Ozone</span>
                      <strong>{airQuality.current.ozone}</strong>
                      <small>{airQuality.units.ozone}</small>
                    </div>
                    <div>
                      <span>UV index</span>
                      <strong>{airQuality.current.uv_index}</strong>
                      <small>current</small>
                    </div>
                  </div>
                </>
              ) : (
                <div className="inline-notice">Loading air-quality context...</div>
              )}
            </article>

            <article className="insights-panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Plan smarter</p>
                  <h2>Weather insights</h2>
                </div>
                <span className="insight-count">{travelInsights.length} {travelInsights.length === 1 ? "signal" : "signals"}</span>
              </div>

              <div className="insights-list">
                {travelInsights.map((insight) => (
                  <div className="insight-item" key={insight.title}>
                    <span aria-hidden="true">↗</span>
                    <div>
                      <strong>{insight.title}</strong>
                      <p>{insight.text}</p>
                    </div>
                  </div>
                ))}
              </div>
            </article>
          </section>
        )}


        <section className="about-section">
          <div className="about-copy">
            <p className="eyebrow">Assessment context</p>
            <h2>About PM Accelerator</h2>
            <p>
              Product Manager Accelerator supports product-management professionals across
              career stages through career-focused training, product-management skill
              development, leadership development, and hands-on AI product programs.
            </p>
            <a
              href="https://www.pmaccelerator.io/"
              target="_blank"
              rel="noreferrer"
            >
              Visit PM Accelerator
            </a>
          </div>

          <div className="candidate-card">
            <span>AI Engineer Intern Technical Assessment</span>
            <strong>Yllka Nuredini</strong>
            <p>Full-stack weather application</p>
          </div>
        </section>

        <section className="saved-section">
          <div className="section-heading saved-heading">
            <div>
              <p className="eyebrow">Persistence & CRUD</p>
              <h2>Saved weather requests</h2>
            </div>
            <span>Store, review, update, or remove requested weather ranges.</span>
          </div>

          <form className="save-form" onSubmit={createSavedRequest}>
            <label>
              <span>Location</span>
              <input
                value={saveForm.location}
                onChange={(event) => setSaveForm({ ...saveForm, location: event.target.value })}
                placeholder="Prishtina"
                required
              />
            </label>
            <label>
              <span>Start date</span>
              <input
                type="date"
                value={saveForm.start_date}
                onChange={(event) => setSaveForm({ ...saveForm, start_date: event.target.value })}
                required
              />
            </label>
            <label>
              <span>End date</span>
              <input
                type="date"
                value={saveForm.end_date}
                onChange={(event) => setSaveForm({ ...saveForm, end_date: event.target.value })}
                required
              />
            </label>
            <button type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save weather range"}
            </button>
          </form>

          {savedError && <div className="error-message saved-feedback">{savedError}</div>}
          {savedMessage && <div className="success-message">{savedMessage}</div>}

          <div className="saved-layout">
            <div className="saved-list">
              <div className="saved-list-title">
                <strong>Stored requests</strong>
                <button type="button" onClick={loadSavedRequests} disabled={savedLoading}>
                  {savedLoading ? "Refreshing..." : "Refresh"}
                </button>
              </div>

              {savedLoading && savedRequests.length === 0 ? (
                <div className="saved-empty">Loading saved requests...</div>
              ) : savedRequests.length === 0 ? (
                <div className="saved-empty">No saved weather requests yet.</div>
              ) : (
                savedRequests.map((request) => (
                  <article className="saved-request" key={request.id}>
                    <div className="saved-request-summary">
                      <div>
                        <span className="request-id">#{request.id}</span>
                        <strong>{request.resolved_location || request.location_input}</strong>
                        <small>{request.country || request.location_input}</small>
                      </div>
                      <span className="date-range">
                        {request.start_date} → {request.end_date}
                      </span>
                    </div>

                    {editingId === request.id ? (
                      <form
                        className="edit-form"
                        onSubmit={(event) => updateSavedRequest(event, request.id)}
                      >
                        <input
                          aria-label="Edit location"
                          value={editForm.location}
                          onChange={(event) => setEditForm({ ...editForm, location: event.target.value })}
                          required
                        />
                        <input
                          aria-label="Edit start date"
                          type="date"
                          value={editForm.start_date}
                          onChange={(event) => setEditForm({ ...editForm, start_date: event.target.value })}
                          required
                        />
                        <input
                          aria-label="Edit end date"
                          type="date"
                          value={editForm.end_date}
                          onChange={(event) => setEditForm({ ...editForm, end_date: event.target.value })}
                          required
                        />
                        <div className="edit-actions">
                          <button type="submit" disabled={saving}>Save update</button>
                          <button type="button" onClick={() => setEditingId(null)}>Cancel</button>
                        </div>
                      </form>
                    ) : (
                      <div className="request-actions">
                        <button type="button" onClick={() => viewSavedRequest(request.id)}>View</button>
                        <button type="button" onClick={() => startEditing(request)}>Edit</button>
                        <button
                          className="danger-action"
                          type="button"
                          onClick={() => deleteSavedRequest(request.id)}
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </article>
                ))
              )}
            </div>

            <aside className="saved-detail">
              {selectedRequest ? (
                <>
                  <div className="detail-header">
                    <div>
                      <span>Request #{selectedRequest.id}</span>
                      <h3>{selectedRequest.resolved_location}</h3>
                      <p>
                        {selectedRequest.start_date} → {selectedRequest.end_date}
                      </p>
                    </div>
                    <button type="button" onClick={() => setSelectedRequest(null)}>Close</button>
                  </div>

                  <div className="detail-meta">
                    <span>{selectedRequest.latitude.toFixed(3)}°, {selectedRequest.longitude.toFixed(3)}°</span>
                    <span>{selectedRequest.timezone}</span>
                  </div>

                  <div className="detail-days">
                    {selectedRequest.days.map((day) => {
                      const [dayCondition] = weatherInfo(day.weather_code);

                      return (
                        <div className="detail-day" key={day.id}>
                          <div>
                            <strong>{formatForecastDate(day.date)}</strong>
                            <span>{dayCondition}</span>
                          </div>
                          <div>
                            <strong>{Math.round(day.temperature_2m_max)}°</strong>
                            <span>{Math.round(day.temperature_2m_min)}°</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              ) : (
                <div className="detail-empty">
                  Select <strong>View</strong> on a stored request to inspect its persisted weather data.
                </div>
              )}
            </aside>
          </div>
        </section>
      </main>

      <footer>
        <span>
          Real-time conditions powered by weather APIs · Location data may include{" "}
          <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
            © OpenStreetMap contributors
          </a>
        </span>
        <span>Built by Yllka Nuredini · PM Accelerator Technical Assessment</span>
      </footer>
    </div>
  );
}

export default App;
