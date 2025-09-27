# app/main.py
import os
import uuid
import json
import asyncio
import logging
from datetime import datetime # Import datetime for generating timestamps

from fastapi import FastAPI, BackgroundTasks, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from .weather_agent import travel_weather_agent, nlu_parser_travel, fetch_weather

# --- CORE IMPORTS ---
from .chatbot import (
    generate_travel_response,
    build_merged_context,
    call_model_generate, # Renamed from _call_model_generate in fixed chatbot.py
)
from .stt_helpers import (
    process_trace,
    background_process_trace,
    stt_sidecar_path,
    UPLOAD_DIR,
    save_upload_and_convert_async,
)
from .weather_agent import travel_weather_agent # Needed for the new /api/text endpoint

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("weatherbot")

app = FastAPI()

# CORS (frontend runs on :8080 during dev)
origins = [
    "http://127.0.0.1:8080",
    "http://localhost:8080",
    "http://localhost:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ensure upload dir exists
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


@app.get("/health")
def health():
    return {"status": "ok"}


# --- 1. VOICE/AUDIO ENDPOINTS ---

@app.post("/api/voice")
async def upload_voice(background_tasks: BackgroundTasks, audio: UploadFile = File(...)):
    """
    Accept uploaded audio, convert, and enqueue background processing (STT -> Agent -> Chatbot).
    """
    trace_id = str(uuid.uuid4())
    logger.info(f"Received upload, trace_id={trace_id}, filename={getattr(audio, 'filename', None)}")

    try:
        # Save + convert (writes final WAV as UPLOAD_DIR/{trace_id}.wav)
        await save_upload_and_convert_async(
            upload_file=audio,
            trace_id=trace_id,
            upload_dir=Path(UPLOAD_DIR),
            delete_original=True,
            sample_rate=16000,
        )
    except Exception as e:
        logger.exception("Failed to save/convert upload")
        raise HTTPException(status_code=500, detail=f"save_or_convert_failed: {e}")

    # schedule background work (STT + agent)
    background_tasks.add_task(background_process_trace, trace_id, ["en-US", "ja-JP"])
    logger.info(f"Scheduled background task for trace_id={trace_id}")

    return JSONResponse({"trace_id": trace_id, "status": "processing"})


# --- 2. NEW: TEXT INPUT ENDPOINT ---

@app.post("/api/text")
async def process_text_query(query: str = Query(..., max_length=500)):
    """
    Accepts a raw text query, runs NLU/Weather agent synchronously, and generates a chatbot response.
    """
    logger.info(f"Received text query: {query}")
    
    # 1. Run the NLU/Weather Agent
    try:
        agent_output = travel_weather_agent(query)
    except Exception as e:
        logger.exception("Text agent failed")
        raise HTTPException(status_code=500, detail=f"agent_failed: {e}")

    nlu = agent_output.get("nlu")
    weather = agent_output.get("weather")
    
    # Check for immediate NLU or Location failure
    if not nlu or weather.get("error") == "no_location_extracted":
        return JSONResponse({
            "status": "failed", 
            "response_text": "I couldn't identify the location in your query. Please be specific.",
            "error": "NLU failed to extract location"
        })

    # 2. Build the LLM Context and Prompts
    try:
        # The agent output is passed to build_merged_context
        merged_context = build_merged_context(nlu, weather)
        
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("No API key provided for chatbot")

        system_prompt = "You are a friendly travel assistant and weather guide..."
        user_prompt = (
            f"Original query: '{query}'\n"
            f"Context: {json.dumps(merged_context, indent=2)}\n\n"
            "Produce 1–3 sentences for the weather + 1 short travel tip."
        )

    except Exception as e:
        logger.exception("Failed to build context or prompt")
        raise HTTPException(status_code=500, detail=f"context_error: {e}")

    # 3. Generate Chatbot Response
    try:
        response_text = call_model_generate(api_key, system_prompt, user_prompt)
        
        return JSONResponse({
            "status": "done", 
            "response_text": response_text,
            "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "nlu": nlu,
            "weather": weather
        })
        
    except Exception as e:
        logger.exception("Text chatbot failed")
        raise HTTPException(status_code=500, detail=f"chatbot_failed: {e}")


# --- 3. STATUS/DEBUG ENDPOINTS ---

@app.post("/api/stt/{trace_id}/process")
def stt_process_endpoint(trace_id: str):
    # ... existing implementation ...
    try:
        result = process_trace(trace_id, languages=["en-US", "ja-JP"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="trace_id audio not found")
    except Exception as e:
        logger.exception(f"Manual process_trace failed for {trace_id}")
        raise HTTPException(status_code=500, detail=f"processing_failed: {e}")
    return result


@app.get("/api/stt/{trace_id}")
def get_stt_result(trace_id: str):
    # ... existing implementation ...
    sidecar = stt_sidecar_path(trace_id)
    if not os.path.exists(sidecar):
        return JSONResponse({"trace_id": trace_id, "status": "pending"})
    with open(sidecar, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data


@app.get("/api/stt/{trace_id}/agent")
def get_agent_result(trace_id: str):
    # ... existing implementation ...
    sidecar = stt_sidecar_path(trace_id)
    if not os.path.exists(sidecar):
        return JSONResponse({"trace_id": trace_id, "status": "pending"})

    with open(sidecar, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    return {
        "trace_id": trace_id,
        "nlu": data.get("nlu"),
        "weather": data.get("weather"),
        "status": data.get("status", "done"),
    }

@app.get("/api/stt/{trace_id}/response")
def get_chatbot_response(trace_id: str):
    # ... existing implementation ...
    sidecar = stt_sidecar_path(trace_id)
    if not os.path.exists(sidecar):
        return JSONResponse({"trace_id": trace_id, "status": "pending"})

    try:
        out = generate_travel_response(trace_id, sidecar)
        return out
    except Exception as e:
        logger.exception(f"Chatbot generation failed for trace_id={trace_id}")
        raise HTTPException(status_code=500, detail=f"chatbot_failed: {e}")