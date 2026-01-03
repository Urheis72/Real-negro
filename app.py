import os
import asyncio
import threading
import base64
import requests
from flask import Flask, render_template_string, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient
from google import genai
from google.genai import types

# ======================================================
# CONFIGURAÇÕES
# ======================================================
GEMINI_KEY = "AIzaSyCu7cyG4zuxx8hzG_4nbdsgIaKsfCPxx7k"
ELEVEN_KEY = "80f20c0648bd28e0f7c7c77c6d41551f5e5e03109f94f40a9bf0176a981e5b8f"
VOICE_ID = "pNInz6obpgDQGcFmaJgB"

TG_API_ID = 34303434
TG_API_HASH = "5d521f53f9721a6376586a014b51173d"
TG_BOT_TOKEN = "SEU_TOKEN_DO_BOTFATHER_AQUI"

MODEL_NAME = "models/gemini-2.0-flash-exp"

# ======================================================
# BACKEND
# ======================================================
app = Flask(__name__)
CORS(app)

# Gemini Client (SDK NOVO)
client_ai = genai.Client(api_key=GEMINI_KEY)

# Telegram
client_tg = TelegramClient("jarvis_bot_session", TG_API_ID, TG_API_HASH)

def start_telegram():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        if TG_BOT_TOKEN != "SEU_TOKEN_DO_BOTFATHER_AQUI":
            client_tg.start(bot_token=TG_BOT_TOKEN)
            print(">>> TELEGRAM ONLINE")
            client_tg.loop.run_forever()
    except Exception as e:
        print(f"Erro Telegram: {e}")

threading.Thread(target=start_telegram, daemon=True).start()

# ======================================================
# FUNÇÕES
# ======================================================
def get_ai_response(text):
    try:
        response = client_ai.models.generate_content(
            model=MODEL_NAME,
            contents=text,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=1024
            )
        )
        return response.text
    except Exception as e:
        return f"Erro no processamento neural (Gemini): {e}"

def get_voice(text):
    if not ELEVEN_KEY:
        return None

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {
        "xi-api-key": ELEVEN_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.8
        }
    }

    try:
        r = requests.post(url, json=data, headers=headers)
        if r.status_code == 200:
            return base64.b64encode(r.content).decode("utf-8")
    except:
        return None

# ======================================================
# API
# ======================================================
@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    msg = data.get("message", "")

    reply = get_ai_response(msg)
    audio = get_voice(reply)

    return jsonify({
        "reply": reply,
        "audio": audio
    })

# ======================================================
# FRONTEND (HTML ORIGINAL – SEM ALTERAÇÕES)
# ======================================================
HTML_PAGE = """SEU HTML PERMANECE EXATAMENTE IGUAL"""
# ⚠️ Cole aqui o mesmo HTML que você já tem

@app.route("/")
def home():
    return render_template_string(HTML_PAGE)

# ======================================================
# START
# ======================================================
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 King AI — Gemini 2.0 Flash (SDK NOVO)")
    print("=" * 50)
    print(f"Modelo: {MODEL_NAME}")
    print("Servidor: http://localhost:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True)
