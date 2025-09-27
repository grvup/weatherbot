# app/chatbot.py
import os
import json
import re
from datetime import datetime
import argparse

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_nlu_weather(root):
    """Extract nlu + weather, fallback to agent_raw if needed."""
    nlu = root.get("nlu") or root.get("agent_raw", {}).get("nlu")
    weather = root.get("weather") or root.get("agent_raw", {}).get("weather")
    if not nlu:
        raise ValueError("No NLU found in JSON")
    if not weather:
        raise ValueError("No weather found in JSON")
    return nlu, weather


def build_merged_context(nlu, weather):
    """
    Builds the structured context dictionary required for the LLM prompt.
    This function is now exposed for use by both file-based and direct text processing.
    """
    dialog_md = nlu.get("dialog_metadata", {}) or {}
    entities = nlu.get("entities", {}) or {}
    slots = nlu.get("slots", {}) or {}

    # For text queries, 'original_query' will be the raw text input
    original_query = dialog_md.get("original_query") or "" 
    date_val = entities.get("date")
    theme_val = slots.get("theme")

    loc = (weather.get("location") or entities.get("location") or "").strip()
    country = (weather.get("country") or "").strip()
    location_str = f"{loc}, {country}".strip(", ").strip()

    return {
        "user_query": original_query,
        "intent": nlu.get("intent"),
        "location": location_str,
        "date": date_val,
        "theme": theme_val,
        "weather_data": weather,
    }


def extract_trace_id_from_path(path):
    name = os.path.basename(path)
    m = UUID_RE.search(name)
    return m.group(0) if m else None


def sanitize_filename(s: str):
    return re.sub(r"[^\w\-\.]", "_", s).strip("_")[:120] if s else None


def call_model_generate(api_key: str, system_prompt: str, user_prompt: str, model_name: str = "gemini-2.5-pro"):
    """
    Core function to generate content from the LLM. 
    Renamed from _call_model_generate to expose it cleanly.
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    contents = [
        {"role": "model", "parts": [{"text": system_prompt}]},
        {"role": "user", "parts": [{"text": user_prompt}]},
    ]
    resp = model.generate_content(contents=contents)
    return getattr(resp, "text", None) or str(resp)


def generate_travel_response(trace_id: str, sidecar_path: str, api_key: str = None):
    """Generate chatbot response from a sidecar file. Used by background_process_trace()."""
    api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("No API key provided for chatbot")

    root = load_json(sidecar_path)
    nlu, weather = extract_nlu_weather(root)
    merged_context = build_merged_context(nlu, weather)

    city = (weather.get("location") or (nlu.get("entities") or {}).get("location") or "unknown").split(",")[0].strip()

    system_prompt = (
        "You are a friendly travel assistant and weather guide. "
        "Always start with a concise weather summary for the location and date, "
        "then add 1–2 short travel tips if relevant."
    )
    user_prompt = (
        f"Original query: '{merged_context.get('user_query')}'\n"
        f"Context: {json.dumps(merged_context, ensure_ascii=False, indent=2)}\n\n"
        "Produce 1–3 sentences for the weather + 1 short travel tip."
    )

    try:
        response_text = call_model_generate(api_key, system_prompt, user_prompt)
        error_note = None
    except Exception as e:
        response_text, error_note = "", f"chatbot_failed: {e}"

    return {
        "trace_id": trace_id,
        "city": city,
        "response_text": response_text,
        "merged_context": merged_context,
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "response_language": "en",
        "tts": None,
        "error": error_note,
    }


# Optional CLI for debugging
def _cli_main():
    parser = argparse.ArgumentParser(description="Generate chatbot travel advice from a sidecar JSON.")
    parser.add_argument("--input", "-i", default="uploads/sample.json", help="Path to sidecar JSON")
    parser.add_argument("--api-key", "-k", default=None, help="API key (optional)")
    args = parser.parse_args()

    trace_id = extract_trace_id_from_path(args.input)
    out = generate_travel_response(trace_id, args.input, api_key=args.api_key)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _cli_main()