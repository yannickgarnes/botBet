"""
Weather API Client — Project Omniscience
Fetches real-time match-day weather using Open-Meteo (100% FREE, no API key).

Wind and rain significantly affect football outcomes:
- Wind > 30 km/h → reduces accuracy of long passes and crosses
- Rain → increases slips, reduces ball control, favors defensive teams
"""
import requests
import logging
from typing import Dict, Optional

logger = logging.getLogger("WeatherAPI")

OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"

# ============================================================
# STADIUM COORDINATES (Major leagues)
# In production, this would be a DB lookup. Here's a starter set.
# ============================================================
STADIUM_COORDS = {
    # Spain — La Liga
    "real madrid": (40.4531, -3.6883),       # Santiago Bernabéu
    "barcelona": (41.3809, 2.1228),           # Camp Nou / Spotify Camp Nou
    "atletico madrid": (40.4362, -3.5995),    # Cívitas Metropolitano
    "sevilla": (37.3840, -5.9705),            # Ramón Sánchez-Pizjuán
    "real betis": (37.3564, -5.9817),         # Benito Villamarín
    "real sociedad": (43.3013, -1.9738),      # Reale Arena
    "athletic bilbao": (43.2643, -2.9493),    # San Mamés
    "villarreal": (39.9440, -0.1036),         # Estadio de la Cerámica
    "valencia": (39.4745, -0.3583),           # Mestalla
    "celta vigo": (42.2116, -8.7396),         # Balaídos
    
    # England — EPL
    "manchester city": (53.4831, -2.2004),    # Etihad
    "manchester united": (53.4631, -2.2913),  # Old Trafford
    "liverpool": (53.4308, -2.9609),          # Anfield
    "arsenal": (51.5549, -0.1084),            # Emirates
    "chelsea": (51.4817, -0.1910),            # Stamford Bridge
    "tottenham": (51.6042, -0.0662),          # Tottenham Hotspur Stadium
    
    # Germany — Bundesliga
    "bayern munich": (48.2188, 11.6247),      # Allianz Arena
    "borussia dortmund": (51.4926, 7.4516),   # Signal Iduna Park
    
    # Italy — Serie A
    "ac milan": (45.4781, 9.1240),            # San Siro
    "inter milan": (45.4781, 9.1240),         # San Siro (shared)
    "juventus": (45.1096, 7.6413),            # Allianz Stadium
    "roma": (41.9341, 12.4547),               # Stadio Olimpico
    "napoli": (40.8279, 14.1931),             # Diego Armando Maradona
    
    # France — Ligue 1
    "paris saint-germain": (48.8414, 2.2530), # Parc des Princes
    "marseille": (43.2698, 5.3959),           # Vélodrome
    "lyon": (45.7654, 4.9821),                # Groupama Stadium

    # Default (Central Europe)
    "_default": (48.8566, 2.3522),            # Paris as neutral fallback
}


class WeatherClient:
    """
    Fetches match-day weather conditions.
    Returns normalized factors for the LSTM model.
    """

    def get_match_weather(self, home_team: str) -> Dict:
        """
        Gets current weather for the home team's stadium.
        
        Returns:
            {
                "temperature": 12.5,       # °C
                "wind_speed": 25.3,        # km/h
                "rain_probability": 0.65,  # 0-1
                "wind_factor": 0.63,       # Normalized 0-1 (0=calm, 1=storm)
                "rain_factor": 0.65,       # Normalized 0-1
                "weather_impact": "MODERATE"  # LOW / MODERATE / HIGH / EXTREME
            }
        """
        lat, lon = self._get_coordinates(home_team)

        try:
            params = {
                "latitude": lat,
                "longitude": lon,
                "current_weather": "true",
                "hourly": "temperature_2m,windspeed_10m,precipitation_probability",
                "forecast_days": 1,
                "timezone": "auto"
            }

            resp = requests.get(OPEN_METEO_BASE, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return self._parse_weather(data)
            else:
                logger.warning(f"Weather API returned {resp.status_code}")
        except Exception as e:
            logger.error(f"Weather fetch failed: {e}")

        # Fallback: neutral weather
        return self._neutral_weather()

    def _parse_weather(self, data: Dict) -> Dict:
        """Parses Open-Meteo response into model-ready features."""
        current = data.get("current_weather", {})
        hourly = data.get("hourly", {})

        temp = current.get("temperature", 15.0)
        wind = current.get("windspeed", 10.0)

        # Get average rain probability for the next few hours
        rain_probs = hourly.get("precipitation_probability", [0])
        avg_rain = sum(rain_probs[:6]) / max(len(rain_probs[:6]), 1) / 100.0

        # Normalize factors (0-1)
        wind_factor = min(wind / 40.0, 1.0)   # 40 km/h = max impact
        rain_factor = min(avg_rain, 1.0)

        # Combined impact assessment
        combined = (wind_factor * 0.6) + (rain_factor * 0.4)
        if combined > 0.7:
            impact = "EXTREME"
        elif combined > 0.4:
            impact = "HIGH"
        elif combined > 0.2:
            impact = "MODERATE"
        else:
            impact = "LOW"

        return {
            "temperature": round(temp, 1),
            "wind_speed": round(wind, 1),
            "rain_probability": round(avg_rain, 2),
            "wind_factor": round(wind_factor, 3),
            "rain_factor": round(rain_factor, 3),
            "weather_impact": impact
        }

    def _get_coordinates(self, team_name: str) -> tuple:
        """Looks up stadium coordinates by team name (fuzzy match)."""
        team_lower = team_name.lower().strip()

        # Direct match
        if team_lower in STADIUM_COORDS:
            return STADIUM_COORDS[team_lower]

        # Fuzzy match
        for key, coords in STADIUM_COORDS.items():
            if key == "_default":
                continue
            if key in team_lower or team_lower in key:
                return coords

        logger.info(f"No stadium found for '{team_name}', using default coords")
        return STADIUM_COORDS["_default"]

    def _neutral_weather(self) -> Dict:
        """Returns neutral weather when API fails."""
        return {
            "temperature": 15.0,
            "wind_speed": 10.0,
            "rain_probability": 0.1,
            "wind_factor": 0.25,
            "rain_factor": 0.1,
            "weather_impact": "LOW"
        }


if __name__ == "__main__":
    w = WeatherClient()

    # Test: Get weather for Real Madrid's stadium
    weather = w.get_match_weather("Real Madrid")
    print(f"Weather at Bernabéu: {weather}")

    # Test: Get weather for Liverpool
    weather2 = w.get_match_weather("Liverpool")
    print(f"Weather at Anfield: {weather2}")
