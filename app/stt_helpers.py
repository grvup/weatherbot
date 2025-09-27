# app/stt_helpers.py
import os
import shlex
import subprocess
import json
import time
import shutil
from pathlib import Path
import asyncio

import requests
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv
load_dotenv()

# ---- Config ----
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

AZURE_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_REGION = os.getenv("AZURE_SPEECH_REGION")

TRANSLATOR_KEY = os.getenv("AZURE_TRANSLATOR_KEY")
TRANSLATOR_REGION = os.getenv("AZURE_TRANSLATOR_REGION")
TRANSLATOR_ENDPOINT = "https://api.cognitive.microsofttranslator.com/translate"


def stt_sidecar_path(trace_id: str) -> str:
    return os.path.join(UPLOAD_DIR, f"{trace_id}.json")


# ---- ffmpeg helpers ----
def ffmpeg_convert_to_wav(input_path: str, output_path: str, sample_rate: int = 16000) -> str:
    """
    Convert any input audio to WAV (pcm_s16le), mono, specified sample_rate,
    and write to `output_path` exactly.
    Raises RuntimeError on ffmpeg failure (stderr included).
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ac", "1",
        "-ar", str(sample_rate),
        "-vn",
        "-acodec", "pcm_s16le",
        output_path,
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(f"ffmpeg error: {stderr}")
    return output_path


async def async_save_uploadfile(upload_file, dest_path: Path):
    """
    Save FastAPI UploadFile to disk, without loading entire content in memory.
    Runs blocking I/O in a thread to avoid blocking the event loop.
    """
    def _write():
        # ensure parent dir exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with dest_path.open("wb") as f:
            shutil.copyfileobj(upload_file.file, f)
    await asyncio.to_thread(_write)
    await upload_file.close()


async def save_upload_and_convert_async(
    upload_file,
    trace_id: str,
    upload_dir: Path,
    delete_original: bool = True,
    sample_rate: int = 16000,
) -> Path:
    """
    High-level helper used by main.upload_voice.
    - saves raw upload to uploads/rec-<trace_id>.<orig_suffix>
    - converts it to uploads/<trace_id>.wav (16k, mono, s16)
    - deletes the original if requested
    - returns Path to the converted wav
    """
    upload_dir.mkdir(parents=True, exist_ok=True)

    orig_suffix = Path(upload_file.filename).suffix or ".webm"
    raw_name = f"rec-{trace_id}{orig_suffix}"
    raw_path = upload_dir / raw_name

    target_wav_name = f"{trace_id}.wav"          # note: process_trace expects <trace_id>.wav
    target_wav_path = upload_dir / target_wav_name

    # 1) save upload to disk (async)
    await async_save_uploadfile(upload_file, raw_path)

    # 2) convert to canonical wav (run ffmpeg in threadpool)
    def _convert():
        return ffmpeg_convert_to_wav(str(raw_path), str(target_wav_path), sample_rate=sample_rate)

    try:
        await asyncio.to_thread(_convert)
    except Exception as e:
        # keep raw file for debugging if conversion failed
        raise RuntimeError(f"conversion_failed: {e}")

    # 3) delete original if requested
    if delete_original:
        try:
            if raw_path.exists():
                raw_path.unlink()
        except Exception as e:
            # non-fatal, just warn
            print(f"Warning: could not delete original {raw_path}: {e}")

    return target_wav_path


# ---- Azure STT ----
def transcribe_with_azure(wav_path: str, languages: list = ["en-US", "ja-JP"]) -> dict:
    if not AZURE_KEY or not AZURE_REGION:
        raise RuntimeError("Azure credentials not set in AZURE_SPEECH_KEY / AZURE_SPEECH_REGION")

    speech_config = speechsdk.SpeechConfig(subscription=AZURE_KEY, region=AZURE_REGION)
    auto_detect = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(languages=languages)
    audio_input = speechsdk.AudioConfig(filename=wav_path)
    recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config,
        audio_config=audio_input,
        auto_detect_source_language_config=auto_detect,
    )

    result = recognizer.recognize_once()
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        try:
            payload = json.loads(result.json)
            detected = payload.get("PrimaryLanguage", {}).get("Language")
        except Exception:
            detected = None
        return {"text": result.text, "confidence": None, "provider": "azure-speech", "detected_language": detected}
    elif result.reason == speechsdk.ResultReason.NoMatch:
        return {"text": "", "confidence": 0.0, "provider": "azure-speech", "detected_language": None}
    else:
        err = getattr(result, "error_details", None)
        raise RuntimeError(f"Azure STT failed: {err}")


# ---- Azure Translator ----
def translate_to_english(text: str, from_lang: str = None) -> str:
    if not TRANSLATOR_KEY or not TRANSLATOR_REGION:
        raise RuntimeError("Azure Translator credentials not set (AZURE_TRANSLATOR_KEY / AZURE_TRANSLATOR_REGION)")

    params = {"api-version": "3.0", "to": "en"}
    if from_lang:
        params["from"] = from_lang

    headers = {
        "Ocp-Apim-Subscription-Key": TRANSLATOR_KEY,
        "Ocp-Apim-Subscription-Region": TRANSLATOR_REGION,
        "Content-Type": "application/json",
    }
    body = [{"text": text}]
    resp = requests.post(TRANSLATOR_ENDPOINT, params=params, headers=headers, json=body)
    resp.raise_for_status()
    data = resp.json()
    return data[0]["translations"][0]["text"]


# ---- Full pipeline (updated to call weather agent) ----
def process_trace(trace_id: str, languages: list = ["en-US", "ja-JP"]) -> dict:
    orig_wav = os.path.join(UPLOAD_DIR, f"{trace_id}.wav")
    if not os.path.exists(orig_wav):
        raise FileNotFoundError("trace_id audio not found")

    converted = orig_wav  # file already converted and named <trace_id>.wav by save_upload_and_convert_async
    stt_result = transcribe_with_azure(converted, languages=languages)

    result = {
        "trace_id": trace_id,
        "text": stt_result.get("text"),
        "confidence": stt_result.get("confidence"),
        "provider": stt_result.get("provider"),
        "detected_language": stt_result.get("detected_language"),
        "processed_at": int(time.time()),
    }

    english_text = result["text"]
    det = result.get("detected_language") or ""
    if english_text and det.lower().startswith("ja"):
        try:
            translated = translate_to_english(english_text, from_lang="ja")
            result["text_en"] = translated
            english_text = translated
        except Exception as e:
            result["text_en"] = None
            result.setdefault("warnings", []).append(f"translation_failed:{str(e)}")
    else:
        result["text_en"] = english_text

    # write partial sidecar early (so STT results are saved even if agent fails)
    with open(stt_sidecar_path(trace_id), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    # write plain text file for downstream use
    text_path = os.path.join(UPLOAD_DIR, f"{trace_id}.txt")
    with open(text_path, "w", encoding="utf-8") as tf:
        tf.write(english_text if english_text else "")

    result["text_file"] = text_path

    # ---------- Agent: NLU + Weather (non-fatal) ----------
    text_for_agent = result.get("text_en") or result.get("text") or ""
    try:
        # import here to avoid circular imports at module load time
        from .weather_agent import travel_weather_agent  # expects {"NLU":..., "Weather":...} per your working snippet
        agent_output = travel_weather_agent(text_for_agent)

        # Attach agent output into sidecar. Use the exact keys returned by the agent.
        # Normalize to lowercase keys for convenience, but keep original under 'agent_raw' too.
        result["agent_raw"] = agent_output
        # if agent returns uppercase keys like "NLU" / "Weather", keep that shape too
        if isinstance(agent_output, dict):
            # add both lowercase convenience names and original
            if "NLU" in agent_output:
                result["nlu"] = agent_output.get("NLU")
            elif "nlu" in agent_output:
                result["nlu"] = agent_output.get("nlu")
            else:
                result["nlu"] = agent_output.get("nlu") if isinstance(agent_output, dict) else None

            if "Weather" in agent_output:
                result["weather"] = agent_output.get("Weather")
            elif "weather" in agent_output:
                result["weather"] = agent_output.get("weather")
            else:
                result["weather"] = None
        else:
            result["nlu"] = {"error": "agent_returned_non_dict"}
            result["weather"] = {"error": "agent_returned_non_dict"}

    except Exception as e:
        # agent failed — include warning and continue
        err_text = str(e)
        result.setdefault("warnings", []).append(f"agent_failed:{err_text}")
        result["agent_raw"] = {"error": err_text}
        result["nlu"] = {"error": f"agent_failed:{err_text}"}
        result["weather"] = {"error": f"agent_failed:{err_text}"}

    # finalize sidecar (update with agent output)
    with open(stt_sidecar_path(trace_id), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    return result


# ---- Background task ----
def background_process_trace(trace_id: str, languages: list = ["en-US", "ja-JP"]):
    """
    Background wrapper that:
      - runs process_trace()
      - then attempts to generate the chatbot response (LLM) and merges it into the sidecar
      - on failures writes a failed sidecar
    """
    try:
        # 1) run the normal pipeline (stt -> translate -> agent)
        result = process_trace(trace_id, languages=languages)

        # 2) try to generate chatbot response and merge into sidecar (non-fatal)
        try:
            # Import here to avoid circular imports at module load time
            from .chatbot import generate_travel_response

            # Prefer explicit env var for API key (accept OPENAI_API_KEY or GOOGLE_API_KEY)
            api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GOOGLE_API_KEY")

            # If api_key is None, generate_travel_response will raise — catch and treat as non-fatal
            bot_out = generate_travel_response(trace_id, stt_sidecar_path(trace_id), api_key=api_key)

            # merge useful fields into the main sidecar 'result'
            result.setdefault("response", {})
            result["response"].update({
                "text": bot_out.get("response_text"),
                "generated_at": bot_out.get("generated_at"),
                "response_language": bot_out.get("response_language"),
                "tts": bot_out.get("tts"),
                "error": bot_out.get("error"),
            })

            # mark overall completion
            result["status"] = "done"

            # write updated sidecar
            with open(stt_sidecar_path(trace_id), "w", encoding="utf-8") as fh:
                json.dump(result, fh, ensure_ascii=False, indent=2)

        except Exception as bot_exc:
            # Non-fatal: keep the agent output but attach a warning
            warn_text = str(bot_exc)
            result.setdefault("warnings", []).append(f"chatbot_failed:{warn_text}")
            # don't overwrite existing fields; ensure final status indicates partial failure
            result["status"] = "agent_done_chatbot_failed"
            with open(stt_sidecar_path(trace_id), "w", encoding="utf-8") as fh:
                json.dump(result, fh, ensure_ascii=False, indent=2)
            print(f"[CHATBOT_ERR] trace {trace_id} chatbot generation failed: {bot_exc}")

    except Exception as e:
        err = {
            "trace_id": trace_id,
            "status": "failed",
            "error": str(e),
            "processed_at": int(time.time()),
        }
        with open(stt_sidecar_path(trace_id), "w", encoding="utf-8") as fh:
            json.dump(err, fh, ensure_ascii=False, indent=2)
        print(f"[BACKGROUND_ERR] trace {trace_id} failed: {e}")