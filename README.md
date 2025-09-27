# ☀️ Weather Assistant (AI Chatbot)

This project implements an **AI-powered weather assistant** that leverages a Python **FastAPI** backend for natural language processing (NLP), external weather APIs, and Google's Gemini for smart, tailored advice. The user interface is a modern single-page application built with **TypeScript/HTML/CSS**.

## 🚀 Features

- **Voice Input:** Transcribes user speech using external speech services (e.g., Azure).
- **Intelligent Routing:** Uses NLP (spaCy transformer) to identify weather-related intents, locations, and dates.
- **LLM Integration:** Provides contextual, human-like advice using Google Gemini based on real-time weather data.
- **Backend:** Built with **FastAPI** for high performance and asynchronous operation.
- **In-Session History:** Maintains chat history using client-side in-memory storage, resetting on refresh.

## 📁 Project Structure

| Directory/File                 | Description                                                                                             |
| :----------------------------- | :------------------------------------------------------------------------------------------------------ |
| `app/`                         | **FastAPI Backend:** Contains all Python logic (API endpoints, LLM integration, NLP, weather fetching). |
| `frontend/`                    | **Client-side UI:** Contains the HTML, CSS, and TypeScript logic for the web interface.                 |
| `uploads/`                     | Directory for temporarily storing audio files uploaded via the API.                                     |
| `venv/`                        | Isolated Python virtual environment (ignored by Git).                                                   |
| `.env`                         | **Sensitive:** Stores all API keys and environment variables (ignored by `.gitignore`).                 |
| `requirements.txt`             | Lists all required Python packages.                                                                     |
| `ffmpeg-8.0-essentials_build/` | Contains the **FFmpeg** binaries, which are required by the backend for audio processing.               |

## ⚙️ Setup and Installation

### 1. Prerequisites

You must have **Python 3.8+** and **Node.js/npm** installed.

### 2. Clone the Repository

```bash
git clone https://github.com/your-username/weatherbot.git
cd weatherbot
```

### 3. Set up Python Backend

Create and activate a virtual environment (venv):

```bash
# Create the environment
python -m venv venv

# Activate (Windows PowerShell)
.env\Scriptsctivate
# Activate (Linux/macOS or Git Bash)
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 4. Install NLP Model

The spaCy library requires a language model to function:

```bash
python -m spacy download en_core_web_trf
```

### 5. Configure Environment Variables

Create a file named `.env` in the root directory and populate it with your necessary API keys (e.g., from Google Gemini, OpenWeather, Azure).

```bash
# .env file content (Example)
GEMINI_API_KEY="YOUR_GOOGLE_GEMINI_API_KEY_HERE"
OPENWEATHER_API_KEY="YOUR_OPENWEATHER_MAP_API_KEY_HERE"

# Azure Speech/Translation (if used in app/ logic)
AZURE_SPEECH_KEY="YOUR_AZURE_KEY"
AZURE_SPEECH_REGION="YOUR_AZURE_REGION"
AZURE_TRANSLATOR_KEY="YOUR_AZURE_KEY"
AZURE_TRANSLATOR_REGION="YOUR_AZURE_REGION"
```

### 6. Set up Frontend

Navigate to the frontend directory and install Node.js dependencies:

```bash
cd frontend
npm install
```

### 7. FFmpeg Setup(required)

This project requires **FFmpeg** to work properly. Follow these steps to install and set it up:

1. Download the latest [`ffmpeg-8.0-essentials_build.zip`](https://www.gyan.dev/ffmpeg/builds/) from the official FFmpeg website.
2. Extract the downloaded ZIP file.
3. Inside the extracted folder, locate the `bin` directory (it contains `ffmpeg.exe`, `ffplay.exe`, etc.).
4. Add the **full path** of this `bin` folder to your system **PATH** environment variable.

## ▶️ Running the Application

### 1. Start the FastAPI Backend

From the root directory (`weatherbot/`), run the server using Uvicorn with the `--reload` flag for development:

```bash
# Ensure your venv is active!
uvicorn app.main:app --reload
```

The backend API will be available at `http://127.0.0.1:8000`.

### 2. Start the Frontend Development Server

Open a new terminal, navigate to the `frontend/` directory, and start the development server (e.g., if using Vite):

```bash
cd frontend
npm run dev
```

The frontend application will typically open in your browser at a local address like `http://localhost:5173`. Open this URL to interact with the Weather Assistant.
