# weather_agent.py
# Install required packages before running (Colab note):
# pip install spacy[transformers] requests python-dateutil rapidfuzz dateparser python-dotenv

import os
import requests
import dateparser
from datetime import datetime, timezone, timedelta
from rapidfuzz import process
import spacy
from dotenv import load_dotenv

# Load .env if present (keeps Colab behavior if you haven't set an env var)
load_dotenv()

# -----------------------------
# Load transformer-based spaCy model
# -----------------------------
try:
    nlp = spacy.load("en_core_web_trf")  # Best for NER locations (keeps your Colab preference)
except Exception:
    print("Please install spacy-transformers and en_core_web_trf model!")
    nlp = None

# -----------------------------
# Set your OpenWeather API key
# -----------------------------
# Keep the same literal fallback so Colab runs unchanged if no env var is set.
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY") 

# -----------------------------
# Helper: Geocoding via OpenWeather
# -----------------------------
def get_candidate_locations(location: str):
    """
    Return a list of candidate location strings from OpenWeather geocoding.
    Each candidate is formatted like "City, CC" where CC is country code.
    """
    url = "http://api.openweathermap.org/geo/1.0/direct"
    params = {"q": location, "limit": 5, "appid": OPENWEATHER_API_KEY}
    try:
        resp = requests.get(url, params=params, timeout=5).json()
        return [f"{g.get('name','')}, {g.get('country','')}" for g in resp]
    except Exception:
        return []

# -----------------------------
# Extract location using spaCy + fuzzy matching
# -----------------------------
def extract_location(query: str):
    """
    Extract a location string from the query using spaCy NER when available,
    fallback regex, and validate/choose best candidate via OpenWeather geocoding + fuzzy match.
    Returns a city name (without country) or None.
    """
    location = None

    # Step 1: NER via spaCy
    if nlp:
        doc = nlp(query)
        for ent in doc.ents:
            if ent.label_ in ("GPE", "LOC"):
                location = ent.text.strip()
                break

    # Step 2: Fallback regex if spaCy fails
    if not location:
        import re
        match = re.search(r"\b(?:in|to|at)\s+([A-Za-z]+(?:\s[A-Za-z]+)*)", query, flags=re.IGNORECASE)
        if match:
            location = match.group(1).strip()


    if not location:
        return None

    # Step 3: Validate with OpenWeather geocoding
    candidates = get_candidate_locations(location)
    if candidates:
        # Use fuzzy matching to find best candidate
        best_match = process.extractOne(location, candidates, score_cutoff=70)
        if best_match:
            return best_match[0].split(",")[0]  # return city name only

    return location

# -----------------------------
# Parse travel/weather query
# -----------------------------
def nlu_parser_travel(query: str):
    """
    Parse a travel/weather-related query and extract location + date.
    Returns a dict with intent, entities, slots, and dialog_metadata.
    """
    location = extract_location(query)

    # Parse date using dateparser (keeps your Colab behavior)
    parsed_date_iso = None
    parsed = dateparser.parse(query)
    if parsed:
        parsed_date_iso = parsed.strftime("%Y-%m-%d")

    # textual fallback for today/tomorrow (UTC as in your Colab code)
    ql = (query or "").lower()
    if "today" in ql and not parsed_date_iso:
        parsed_date_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    elif "tomorrow" in ql and not parsed_date_iso:
        parsed_date_iso = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    return {
        "intent": "get_weather_travel_advice",
        "entities": {"location": location, "date": parsed_date_iso},
        "slots": {"theme": "travel"},
        "dialog_metadata": {
            "original_query": query,
            "language": "en",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    }

# -----------------------------
# Fetch weather from OpenWeather
# -----------------------------
def fetch_weather(location: str):
    """
    Calls OpenWeather API and returns structured JSON or an error dict.
    Mirrors your Colab implementation.
    """
    if not location:
        return {"error": "No location provided"}
    if not OPENWEATHER_API_KEY:
        return {"error": "OPENWEATHER_API_KEY not set"}

    # Step 1: Geocode location
    geo_url = "http://api.openweathermap.org/geo/1.0/direct"
    params = {"q": location, "limit": 1, "appid": OPENWEATHER_API_KEY}
    try:
        geo_resp = requests.get(geo_url, params=params, timeout=5).json()
        if not geo_resp:
            return {"error": f"Location '{location}' not found"}
        lat, lon = geo_resp[0]["lat"], geo_resp[0]["lon"]
    except Exception as e:
        return {"error": f"geocoding_failed: {e}"}

    # Step 2: Current weather
    weather_url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": "metric"}
    try:
        resp = requests.get(weather_url, params=params, timeout=5).json()
    except Exception as e:
        return {"error": f"weather_fetch_failed: {e}"}

    return {
        "location": resp.get("name"),
        "country": resp.get("sys", {}).get("country"),
        "weather_main": (resp.get("weather") or [{}])[0].get("main"),
        "weather_description": (resp.get("weather") or [{}])[0].get("description"),
        "temperature_c": resp.get("main", {}).get("temp"),
        "feels_like_c": resp.get("main", {}).get("feels_like"),
        "temp_min_c": resp.get("main", {}).get("temp_min"),
        "temp_max_c": resp.get("main", {}).get("temp_max"),
        "humidity": resp.get("main", {}).get("humidity"),
        "wind_speed": resp.get("wind", {}).get("speed"),
        "rain_1h": resp.get("rain", {}).get("1h", 0) if resp.get("rain") else 0,
        "cloudiness": resp.get("clouds", {}).get("all"),
        "timestamp": datetime.utcfromtimestamp(resp.get("dt")).replace(tzinfo=timezone.utc).isoformat() if resp.get("dt") else None,
        "raw": resp
    }

# -----------------------------
# Main agent
# -----------------------------
def travel_weather_agent(query: str):
    """
    Returns {'nlu': ..., 'weather': ...} — lowercase keys for consistency.
    """
    nlu = nlu_parser_travel(query)
    location = nlu.get("entities", {}).get("location")
    weather = fetch_weather(location) if location else {"error": "no_location_extracted"}
    return {"nlu": nlu, "weather": weather}
