from datetime import datetime
import httpx

BASE_URL = "https://api.open-meteo.com/v1/forecast"

WMO_DESCRIPTIONS = {
    0: "Clear sky", 1: "Mainly clear",
    2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Foggy",
    51: "Light drizzle", 53: "Drizzle",
    55: "Heavy drizzle", 61: "Slight rain",
    63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow",
    75: "Heavy snow", 80: "Rain showers",
    81: "Rain showers", 82: "Heavy showers",
    95: "Thunderstorm", 96: "Thunderstorm",
    99: "Thunderstorm with hail",
}

BAD_WEATHER_CODES = {
    51, 53, 55, 61, 63, 65, 71, 73, 75, 80, 81, 82, 95, 96, 99,
}


async def get_location_forecast(
    lat: float = 40.7812,
    lng: float = -73.9665,
    location_name: str = "NYC",
    forecast_days: int = 7,
) -> dict:
    forecast_days = max(1, min(16, int(forecast_days)))
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lng, 4),
        "daily": [
            "temperature_2m_max",
            "precipitation_sum",
            "windspeed_10m_max",
            "weathercode",
        ],
        "timezone": "America/New_York",
        "forecast_days": forecast_days,
        "temperature_unit": "fahrenheit",
        "windspeed_unit": "mph",
        "precipitation_unit": "inch",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(BASE_URL, params=params)
            r.raise_for_status()
            data = r.json()
        daily = data["daily"]
        forecast = {}
        for i, date_str in enumerate(daily["time"]):
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            code = int(daily["weathercode"][i])
            is_bad = code in BAD_WEATHER_CODES
            precip = float(daily["precipitation_sum"][i] or 0)
            temp = float(daily["temperature_2m_max"][i] or 0)
            wind = float(daily["windspeed_10m_max"][i] or 0)

            if is_bad or precip > 0.1:
                quality = "Poor"
                is_good = False
                note = "Rain expected — fewer birds active"
            elif wind > 20:
                quality = "Fair"
                is_good = True
                note = "Windy — birds may shelter in trees"
            elif code in {0, 1, 2}:
                quality = "Excellent"
                is_good = True
                note = "Clear skies — great for birding!"
            else:
                quality = "Good"
                is_good = True
                note = "Good conditions for birding"

            forecast[date_str] = {
                "date": date_str,
                "day_name": dt.strftime("%A"),
                "display_date": dt.strftime("%a %b %d"),
                "name": dt.strftime("%A %b %d"),
                "temperature": round(temp),
                "precipitation": round(precip, 2),
                "windspeed": round(wind),
                "shortForecast": WMO_DESCRIPTIONS.get(code, "Variable conditions"),
                "birding_note": note,
                "birding_quality": quality,
                "is_good": is_good,
            }
        print(f"Open-Meteo: {forecast_days}-day forecast for {location_name}")
        return forecast
    except Exception as e:
        print(f"Open-Meteo error: {e}")
        return {}


async def get_nyc_week_forecast(
    lat: float = 40.7812,
    lng: float = -73.9665,
    location_name: str = "NYC",
    forecast_days: int = 7,
) -> dict:
    return await get_location_forecast(lat, lng, location_name, forecast_days)
